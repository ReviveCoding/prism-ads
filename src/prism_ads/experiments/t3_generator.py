"""Deterministic real-structure, known-truth causal benchmark generator."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

from prism_ads.warehouse.preprocess import configure, quote_path

REGIMES = ("R0", "R1", "R2", "R3", "R4", "R5", "R6", "R7")
ASSIGNMENT_SEED = 2026090401
OUTCOME_SEED = 2026090402


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def relation(path: Path) -> str:
    return f"read_parquet('{quote_path(path)}')"


def publish_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def copy_atomic(connection: duckdb.DuckDBPyConnection, query: str, target: Path) -> None:
    if target.is_file():
        connection.execute(f"SELECT count(*) FROM {relation(target)}").fetchone()
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    connection.execute(
        f"COPY ({query}) TO '{quote_path(temporary)}' "
        "(FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 131072)"
    )
    connection.execute(f"SELECT count(*) FROM {relation(temporary)}").fetchone()
    os.replace(temporary, target)


def build_structure(
    connection: duckdb.DuckDBPyConnection, t2_roles: Path, target: Path
) -> None:
    source = relation(t2_roles)
    role = (
        "CASE WHEN role = 'train' AND "
        "md5_number_lower('t3-role:' || uid::VARCHAR) % 5 < 2 "
        "THEN 'generator_development' "
        "WHEN role = 'train' THEN 'method_development' "
        "WHEN role = 'validation' THEN 'method_validation' ELSE role END"
    )
    query = (
        "WITH units AS (SELECT uid, campaign, any_value(role) AS source_role, "
        "count(*) AS impressions, sum(click)::BIGINT AS clicks, "
        "count(DISTINCT path_key)::BIGINT AS path_count, avg(cost) AS mean_cost, "
        "mode(cat1) AS dominant_cat1 FROM "
        f"{source} GROUP BY uid, campaign), enriched AS (SELECT *, "
        "count(*) OVER (PARTITION BY campaign)::BIGINT AS campaign_units FROM units) "
        "SELECT row_number() OVER (ORDER BY uid, campaign) - 1 AS unit_id, "
        f"uid, campaign, {role.replace('role', 'source_role')} AS role, "
        "(md5_number_lower(dominant_cat1::VARCHAR || ':' || campaign::VARCHAR) "
        "% 8)::TINYINT AS segment, "
        "impressions, clicks, path_count, mean_cost, campaign_units, dominant_cat1 "
        "FROM enriched ORDER BY uid, campaign"
    )
    copy_atomic(connection, query, target)


def probability_expressions() -> dict[str, tuple[str, str]]:
    campaign_effect = (
        "(((md5_number_lower('campaign:' || campaign::VARCHAR) % 2001)::DOUBLE "
        "/ 1000.0) - 1.0) * 0.35"
    )
    segment_effect = "((segment::DOUBLE - 3.5) / 3.5) * 0.20"
    base = (
        f"(-4.2 + 0.35 * ln(1 + impressions) + 1.5 * clicks / impressions "
        f"+ {campaign_effect} + {segment_effect})"
    )
    campaign_hash = "md5_number_lower('tau:' || campaign::VARCHAR)"
    expressions = {
        "R0": (base, "0.0"),
        "R1": (base, "0.30"),
        "R2": (
            base,
            "0.15 + 0.10 * tanh(ln(1 + impressions) - 0.7) "
            "+ 0.05 * (segment::DOUBLE - 3.5) / 3.5",
        ),
        "R3": (base, f"CASE WHEN {campaign_hash} % 10 = 0 THEN 0.90 ELSE 0.02 END"),
        "R4": (base, f"CASE WHEN {campaign_hash} % 2 = 0 THEN 0.45 ELSE -0.30 END"),
        "R5": (base, "0.05 + 0.55 / sqrt(greatest(campaign_units, 1))"),
        "R6": (f"({base} - 2.0)", "0.35"),
        "R7": (
            base,
            "0.10 + CASE WHEN segment IN (1, 3, 6) THEN 0.35 ELSE -0.10 END "
            "+ CASE WHEN clicks / impressions > 0.20 THEN 0.30 ELSE 0.0 END "
            "- CASE WHEN segment IN (0, 7) AND impressions > 2 THEN 0.35 ELSE 0.0 END",
        ),
    }
    return expressions


def build_generated(
    connection: duckdb.DuckDBPyConnection, structure: Path, target: Path
) -> None:
    expressions = probability_expressions()
    logits = ", ".join(
        f"{base} AS logit0_{regime}, {tau} AS tau_{regime}"
        for regime, (base, tau) in expressions.items()
    )
    probabilities = ", ".join(
        f"1.0 / (1.0 + exp(-logit0_{regime})) AS p0_{regime}, "
        f"1.0 / (1.0 + exp(-(logit0_{regime} + tau_{regime}))) AS p1_{regime}"
        for regime in REGIMES
    )
    outcomes = ", ".join(
        f"CASE WHEN (md5_number_lower('{OUTCOME_SEED}:{regime}:' || unit_id::VARCHAR) "
        f"% 1000000)::DOUBLE / 1000000.0 < "
        f"p0_{regime} + treatment * (p1_{regime} - p0_{regime}) THEN 1 ELSE 0 END::TINYINT "
        f"AS outcome_{regime}"
        for regime in REGIMES
    )
    query = (
        "WITH logits AS (SELECT *, " + logits + " FROM " + relation(structure) + "), "
        "probs AS (SELECT *, " + probabilities + ", "
        f"CASE WHEN md5_number_lower('{ASSIGNMENT_SEED}:' || unit_id::VARCHAR) "
        "% 1000000 < 500000 THEN 1 ELSE 0 END::TINYINT AS treatment FROM logits) "
        "SELECT *, " + outcomes + " FROM probs"
    )
    copy_atomic(connection, query, target)


def build_observations(
    connection: duckdb.DuckDBPyConnection, generated: Path, target: Path
) -> None:
    outcome_columns = ", ".join(f"outcome_{regime}" for regime in REGIMES)
    query = (
        "SELECT unit_id, uid, campaign, role, segment, impressions, clicks, path_count, "
        f"mean_cost, campaign_units, treatment, {outcome_columns} FROM {relation(generated)}"
    )
    copy_atomic(connection, query, target)


def build_individual_truth(
    connection: duckdb.DuckDBPyConnection, generated: Path, target: Path
) -> None:
    columns = ", ".join(
        f"p0_{regime}, p1_{regime}, p1_{regime} - p0_{regime} AS ite_{regime}"
        for regime in REGIMES
    )
    query = f"SELECT unit_id, campaign, segment, role, {columns} FROM {relation(generated)}"
    copy_atomic(connection, query, target)


def build_group_truth(
    connection: duckdb.DuckDBPyConnection,
    truth: Path,
    group_columns: tuple[str, ...],
    target: Path,
) -> None:
    groups = ", ".join(group_columns)
    pieces = [
        f"SELECT '{regime}' AS effect_regime, {groups}, count(*) AS units, "
        f"avg(ite_{regime}) AS true_ate FROM {relation(truth)} GROUP BY {groups}"
        for regime in REGIMES
    ]
    copy_atomic(connection, " UNION ALL ".join(pieces), target)


def scalar(connection: duckdb.DuckDBPyConnection, query: str) -> Any:
    row = connection.execute(query).fetchone()
    if row is None:
        raise RuntimeError("query returned no row")
    return row[0]


def run(root: Path) -> dict[str, Any]:
    root = root.resolve()
    t2 = root / "data" / "validated" / "t2_attribution_roles.parquet"
    structure = root / "data" / "validated" / "t3_structure.parquet"
    observations = root / "data" / "validated" / "t3_observations.parquet"
    sealed = root / "artifacts" / "qualification" / "P05" / "sealed_truth"
    individual = sealed / "t3_individual_truth.parquet"
    campaign = sealed / "t3_campaign_truth.parquet"
    segment = sealed / "t3_segment_truth.parquet"
    campaign_segment = sealed / "t3_campaign_segment_truth.parquet"
    generated = root / ".codex-tmp" / "t3_generated.parquet"
    connection = duckdb.connect()
    try:
        configure(connection, root)
        build_structure(connection, t2, structure)
        build_generated(connection, structure, generated)
        build_observations(connection, generated, observations)
        build_individual_truth(connection, generated, individual)
        build_group_truth(connection, individual, ("campaign",), campaign)
        build_group_truth(connection, individual, ("segment",), segment)
        build_group_truth(connection, individual, ("campaign", "segment"), campaign_segment)
        units = scalar(connection, f"SELECT count(*) FROM {relation(structure)}")
        users = scalar(connection, f"SELECT count(DISTINCT uid) FROM {relation(structure)}")
        campaigns = scalar(
            connection, f"SELECT count(DISTINCT campaign) FROM {relation(structure)}"
        )
        segments = scalar(
            connection, f"SELECT count(DISTINCT segment) FROM {relation(structure)}"
        )
        role_counts = dict(
            connection.execute(
                f"SELECT role, count(*) FROM {relation(structure)} GROUP BY role"
            ).fetchall()
        )
        treatment_rate = scalar(
            connection, f"SELECT avg(treatment) FROM {relation(observations)}"
        )
        null_max = scalar(
            connection, f"SELECT max(abs(ite_R0)) FROM {relation(individual)}"
        )
        bounds = connection.execute(
            "SELECT min(value), max(value) FROM ("
            + " UNION ALL ".join(
                f"SELECT p0_{regime} AS value FROM {relation(individual)} UNION ALL "
                f"SELECT p1_{regime} AS value FROM {relation(individual)}"
                for regime in REGIMES
            )
            + ")"
        ).fetchone()
        assert bounds is not None
    finally:
        connection.close()
    if generated.exists():
        generated.unlink()
    for path in (individual, campaign, segment, campaign_segment):
        path.chmod(0o444)
    artifacts = {}
    for name, path in {
        "structure": structure,
        "observations": observations,
        "individual_truth": individual,
        "campaign_truth": campaign,
        "segment_truth": segment,
        "campaign_segment_truth": campaign_segment,
    }.items():
        artifacts[name] = {
            "path": str(path.relative_to(root)).replace("\\", "/"),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
    result = {
        "phase": "P05",
        "generator_id": "t3-logit-v1.1",
        "created_at": utc_now(),
        "status": (
            "PASS"
            if null_max == 0 and bounds[0] > 0 and bounds[1] < 1 and segments == 8
            else "FAIL"
        ),
        "units": units,
        "users": users,
        "campaigns": campaigns,
        "segments": segments,
        "role_counts": role_counts,
        "treatment_rate": treatment_rate,
        "null_max_absolute_ite": null_max,
        "probability_min": bounds[0],
        "probability_max": bounds[1],
        "regimes": list(REGIMES),
        "artifacts": artifacts,
        "truth_access": (
            "sealed; candidate code may read observations only; scoring after output freeze"
        ),
    }
    publish_json(root / "artifacts" / "qualification" / "P05" / "generator_validation.json", result)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    result = run(args.root)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
