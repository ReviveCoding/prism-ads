"""Stream the official archives into typed Parquet and a DuckDB catalog."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import shutil
import zipfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

CHUNK_BYTES = 8 * 1024 * 1024

T1_COLUMNS = {**{f"f{i}": "DOUBLE" for i in range(12)}, **{
    "treatment": "TINYINT",
    "conversion": "TINYINT",
    "visit": "TINYINT",
    "exposure": "TINYINT",
}}
T2_COLUMNS = {
    "timestamp": "BIGINT",
    "uid": "BIGINT",
    "campaign": "BIGINT",
    "conversion": "TINYINT",
    "conversion_timestamp": "BIGINT",
    "conversion_id": "BIGINT",
    "attribution": "TINYINT",
    "click": "TINYINT",
    "click_pos": "INTEGER",
    "click_nb": "INTEGER",
    "cost": "DOUBLE",
    "cpo": "DOUBLE",
    "time_since_last_click": "BIGINT",
    **{f"cat{i}": "BIGINT" for i in range(1, 10)},
}


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def quote_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").replace("'", "''")


def columns_literal(columns: dict[str, str]) -> str:
    pairs = ", ".join(f"'{name}': '{kind}'" for name, kind in columns.items())
    return "{" + pairs + "}"


def extract_nested_t2(root: Path) -> Path:
    raw_zip = root / "data" / "raw" / "criteo_attribution_dataset.zip"
    staged = root / "data" / "staged" / "criteo_attribution_dataset.tsv.gz"
    if staged.is_file():
        return staged
    staged.parent.mkdir(parents=True, exist_ok=True)
    temporary = staged.with_suffix(".gz.tmp")
    with zipfile.ZipFile(raw_zip) as archive:
        with archive.open("criteo_attribution_dataset.tsv.gz") as source:
            with temporary.open("wb") as target:
                shutil.copyfileobj(source, target, CHUNK_BYTES)
                target.flush()
                os.fsync(target.fileno())
    with gzip.open(temporary, "rb") as handle:
        while handle.read(CHUNK_BYTES):
            pass
    os.replace(temporary, staged)
    return staged


def configure(connection: duckdb.DuckDBPyConnection, root: Path) -> None:
    temp_dir = root / ".codex-tmp" / "duckdb"
    temp_dir.mkdir(parents=True, exist_ok=True)
    connection.execute("SET threads = 8")
    connection.execute("SET memory_limit = '12GB'")
    connection.execute(f"SET temp_directory = '{quote_path(temp_dir)}'")
    connection.execute("SET preserve_insertion_order = false")


def convert_csv(
    connection: duckdb.DuckDBPyConnection,
    source: Path,
    target: Path,
    columns: dict[str, str],
    delimiter: str,
) -> None:
    if target.is_file():
        connection.execute(f"SELECT count(*) FROM read_parquet('{quote_path(target)}')").fetchone()
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".parquet.tmp")
    source_sql = (
        f"read_csv('{quote_path(source)}', delim='{delimiter}', header=true, "
        f"columns={columns_literal(columns)}, compression='gzip', "
        "null_padding=false, strict_mode=true)"
    )
    typed = ", ".join(f"CAST({name} AS {kind}) AS {name}" for name, kind in columns.items())
    query = f"SELECT row_number() OVER () - 1 AS row_id, {typed} FROM {source_sql}"
    connection.execute(
        f"COPY ({query}) TO '{quote_path(temporary)}' "
        "(FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 131072)"
    )
    connection.execute(f"SELECT count(*) FROM read_parquet('{quote_path(temporary)}')").fetchone()
    os.replace(temporary, target)


def parquet_manifest(
    connection: duckdb.DuckDBPyConnection,
    dataset_id: str,
    path: Path,
    source_sha256: str,
) -> dict[str, Any]:
    parquet = quote_path(path)
    count_row = connection.execute(f"SELECT count(*) FROM read_parquet('{parquet}')").fetchone()
    if count_row is None:
        raise RuntimeError(f"could not count {path}")
    row_count = count_row[0]
    schema_rows = connection.execute(f"DESCRIBE SELECT * FROM read_parquet('{parquet}')").fetchall()
    schema = [{"name": row[0], "type": row[1], "nullable": row[2]} for row in schema_rows]
    return {
        "manifest_version": 1,
        "dataset_id": dataset_id,
        "created_at": utc_now(),
        "source_sha256": source_sha256,
        "path": str(path.relative_to(path.parents[2])).replace("\\", "/"),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "rows": row_count,
        "schema": schema,
        "format": "parquet",
        "compression": "zstd",
    }


def publish_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def build_catalog(root: Path, t1: Path, t2: Path) -> Path:
    target = root / "data" / "marts" / "prism_ads.duckdb"
    temporary = target.with_suffix(".duckdb.tmp")
    target.parent.mkdir(parents=True, exist_ok=True)
    if temporary.exists():
        temporary.unlink()
    connection = duckdb.connect(str(temporary))
    try:
        configure(connection, root)
        connection.execute(
            f"CREATE VIEW t1_uplift AS SELECT * FROM read_parquet('{quote_path(t1)}')"
        )
        connection.execute(
            f"CREATE VIEW t2_attribution AS SELECT * FROM read_parquet('{quote_path(t2)}')"
        )
        connection.execute("CREATE TABLE warehouse_metadata AS SELECT now() AS created_at")
        connection.execute("CHECKPOINT")
    finally:
        connection.close()
    if target.exists():
        target.unlink()
    os.replace(temporary, target)
    return target


def preprocess(root: Path) -> dict[str, Any]:
    root = root.resolve()
    t1_source = root / "data" / "raw" / "criteo-uplift-v2.1.csv.gz"
    t2_source = extract_nested_t2(root)
    t1_target = root / "data" / "staged" / "t1_uplift.parquet"
    t2_target = root / "data" / "staged" / "t2_attribution.parquet"
    connection = duckdb.connect()
    try:
        configure(connection, root)
        convert_csv(connection, t1_source, t1_target, T1_COLUMNS, ",")
        convert_csv(connection, t2_source, t2_target, T2_COLUMNS, "\\t")
        t1_manifest = parquet_manifest(
            connection,
            "T1",
            t1_target,
            "2716e1bf0fd157a93b5bf86924d9088419dfbac2022c6cd90030220634f616dc",
        )
        t2_manifest = parquet_manifest(
            connection,
            "T2",
            t2_target,
            "242acae50d9eadda739da1dab7c5fec6f4aee3e4e17b315e2c42c2d42f339d09",
        )
    finally:
        connection.close()
    publish_json(root / "data" / "manifests" / "t1_warehouse_manifest.json", t1_manifest)
    publish_json(root / "data" / "manifests" / "t2_warehouse_manifest.json", t2_manifest)
    catalog = build_catalog(root, t1_target, t2_target)
    return {
        "status": "PASS",
        "T1": t1_manifest,
        "T2": t2_manifest,
        "catalog": {
            "path": str(catalog.relative_to(root)).replace("\\", "/"),
            "bytes": catalog.stat().st_size,
            "sha256": sha256_file(catalog),
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    print(json.dumps(preprocess(args.root), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
