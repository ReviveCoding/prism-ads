from __future__ import annotations

import gzip
import zipfile
from pathlib import Path

import duckdb

from prism_ads.data.quality_roles import (
    build_t1_roles,
    build_t2_roles,
    relation,
    role_case,
    scalar,
    t1_quality,
    t2_cutpoints,
    t2_quality,
    validate_roles,
)
from prism_ads.warehouse.preprocess import (
    T1_COLUMNS,
    build_catalog,
    convert_csv,
    extract_nested_t2,
    parquet_manifest,
    publish_json,
    quote_path,
    sha256_file,
)


def write_t1_csv(path: Path, rows: int = 100) -> None:
    columns = [*T1_COLUMNS]
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        handle.write(",".join(columns) + "\n")
        for index in range(rows):
            treatment = 1 if index % 20 < 17 else 0
            values = [str((index + feature) % 7 / 7) for feature in range(12)]
            values.extend(
                [
                    str(treatment),
                    str(index % 2),
                    str(index % 3 == 0).lower(),
                    str(index % 4 == 0).lower(),
                ]
            )
            handle.write(",".join(values).replace("true", "1").replace("false", "0") + "\n")


def write_t2_parquet(connection: duckdb.DuckDBPyConnection, target: Path) -> None:
    cats = ",".join(f"i % 5 AS cat{index}" for index in range(1, 10))
    connection.execute(
        f"COPY (SELECT i AS row_id, 1000+i AS timestamp, i AS uid, i%4 AS campaign, "
        "CASE WHEN i%3=0 THEN 1 ELSE 0 END AS conversion, "
        "CASE WHEN i%3=0 THEN 1100+i ELSE -1 END AS conversion_timestamp, "
        "CASE WHEN i%3=0 THEN i ELSE -1 END AS conversion_id, "
        "CASE WHEN i%3=0 THEN 1 ELSE 0 END AS attribution, i%2 AS click, "
        "0 AS click_pos, 1 AS click_nb, 0.1+i AS cost, 1.0+i AS cpo, "
        f"0 AS time_since_last_click, {cats} FROM range(24) t(i)) "
        f"TO '{quote_path(target)}' (FORMAT PARQUET)"
    )


def test_local_warehouse_conversion_manifest_and_catalog(tmp_path: Path) -> None:
    source = tmp_path / "t1.csv.gz"
    target = tmp_path / "data" / "staged" / "t1.parquet"
    write_t1_csv(source)
    connection = duckdb.connect()
    try:
        convert_csv(connection, source, target, T1_COLUMNS, ",")
        convert_csv(connection, source, target, T1_COLUMNS, ",")
        manifest = parquet_manifest(connection, "T1", target, sha256_file(source))
    finally:
        connection.close()
    assert manifest["rows"] == 100
    assert manifest["schema"][0]["name"] == "row_id"
    output = tmp_path / "manifest.json"
    publish_json(output, manifest)
    assert output.is_file() and not output.with_suffix(".json.tmp").exists()
    catalog = build_catalog(tmp_path, target, target)
    with duckdb.connect(str(catalog), read_only=True) as catalog_connection:
        assert catalog_connection.execute("SELECT count(*) FROM t1_uplift").fetchone() == (100,)


def test_nested_archive_extraction_is_resume_safe(tmp_path: Path) -> None:
    raw = tmp_path / "data" / "raw"
    raw.mkdir(parents=True)
    nested = tmp_path / "nested.gz"
    with gzip.open(nested, "wb") as handle:
        handle.write(b"fixture")
    with zipfile.ZipFile(raw / "criteo_attribution_dataset.zip", "w") as archive:
        archive.write(nested, "criteo_attribution_dataset.tsv.gz")
    first = extract_nested_t2(tmp_path)
    second = extract_nested_t2(tmp_path)
    assert first == second
    with gzip.open(first, "rb") as handle:
        assert handle.read() == b"fixture"


def test_quality_and_role_functions_on_tiny_parquet(tmp_path: Path) -> None:
    t1_source = tmp_path / "t1.csv.gz"
    t1_parquet = tmp_path / "t1.parquet"
    t2_parquet = tmp_path / "t2.parquet"
    write_t1_csv(t1_source, 200)
    connection = duckdb.connect()
    try:
        convert_csv(connection, t1_source, t1_parquet, T1_COLUMNS, ",")
        write_t2_parquet(connection, t2_parquet)
        t1 = t1_quality(connection, t1_parquet)
        t2 = t2_quality(connection, t2_parquet)
        cutpoints = t2_cutpoints(connection, t2_parquet)
        t1_roles = tmp_path / "t1_roles.parquet"
        t2_roles = tmp_path / "t2_roles.parquet"
        build_t1_roles(connection, t1_parquet, t1_roles)
        build_t1_roles(connection, t1_parquet, t1_roles)
        build_t2_roles(connection, t2_parquet, t2_roles, cutpoints)
        build_t2_roles(connection, t2_parquet, t2_roles, cutpoints)
        t1_validation = validate_roles(connection, t1_roles, 200, False)
        t2_validation = validate_roles(connection, t2_roles, 24, True, True)
        assert scalar(connection, f"SELECT count(*) FROM {relation(t1_roles)}") == 200
    finally:
        connection.close()
    assert t1["rows"] == 200 and t1["gate"] in {"PASS", "FAIL"}
    assert t2["rows"] == 24 and t2["gate"] == "PASS"
    assert len(cutpoints) == 5
    assert t1_validation["rows"] == 200
    assert t2_validation["user_role_leakage_groups"] == 0
    assert role_case("bucket").startswith("CASE WHEN bucket < 5000")
