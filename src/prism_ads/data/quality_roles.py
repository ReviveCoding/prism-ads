"""Full-data quality diagnostics and protected-role construction for T1/T2."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

from prism_ads.warehouse.preprocess import configure, quote_path

T1_SALT = "prism-ads-v2.2-t1-role-salt-20260904"
ROLE_THRESHOLDS = (
    (5000, "train"),
    (6500, "validation"),
    (7500, "calibration"),
    (8500, "policy"),
    (9000, "qualification"),
    (10000, "locked_final"),
)


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def publish_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def scalar(connection: duckdb.DuckDBPyConnection, query: str) -> Any:
    row = connection.execute(query).fetchone()
    if row is None:
        raise RuntimeError("query returned no row")
    return row[0]


def relation(path: Path) -> str:
    return f"read_parquet('{quote_path(path)}')"


def t1_quality(connection: duckdb.DuckDBPyConnection, path: Path) -> dict[str, Any]:
    rel = relation(path)
    features = [f"f{i}" for i in range(12)]
    binaries = ["treatment", "conversion", "visit", "exposure"]
    row = connection.execute(
        "SELECT count(*) AS rows, "
        "sum(treatment) AS treated, sum(conversion) AS conversions, "
        "sum(visit) AS visits, sum(exposure) AS exposures "
        f"FROM {rel}"
    ).fetchone()
    if row is None:
        raise RuntimeError("T1 summary returned no row")
    rows, treated, conversions, visits, exposures = row
    controls = rows - treated
    expected_treated = rows * 0.85
    expected_control = rows * 0.15
    srm_chi2 = (treated - expected_treated) ** 2 / expected_treated + (
        controls - expected_control
    ) ** 2 / expected_control
    srm_p = math.erfc(math.sqrt(srm_chi2 / 2.0))

    null_terms = ", ".join(
        f"sum(CASE WHEN {name} IS NULL THEN 1 ELSE 0 END) AS {name}" 
        for name in [*features, *binaries]
    )
    null_row = connection.execute(f"SELECT {null_terms} FROM {rel}").fetchone()
    assert null_row is not None
    missing = dict(zip([*features, *binaries], null_row, strict=True))
    missing_by_treatment_rows = connection.execute(
        f"SELECT treatment, {null_terms} FROM {rel} GROUP BY treatment ORDER BY treatment"
    ).fetchall()
    missing_by_treatment = {
        str(row[0]): dict(zip([*features, *binaries], row[1:], strict=True))
        for row in missing_by_treatment_rows
    }
    invalid_binary = {
        name: scalar(connection, f"SELECT count(*) FROM {rel} WHERE {name} NOT IN (0, 1)")
        for name in binaries
    }
    nonfinite = {
        name: scalar(connection, f"SELECT count(*) FROM {rel} WHERE NOT isfinite({name})")
        for name in features
    }

    stats = connection.execute(
        "SELECT treatment, "
        + ", ".join(
            f"avg({name}) AS {name}_mean, stddev_samp({name}) AS {name}_sd" for name in features
        )
        + f" FROM {rel} GROUP BY treatment ORDER BY treatment"
    ).fetchall()
    control_stats, treated_stats = stats
    smd: dict[str, float] = {}
    for index, name in enumerate(features):
        c_mean, c_sd = control_stats[1 + 2 * index : 3 + 2 * index]
        t_mean, t_sd = treated_stats[1 + 2 * index : 3 + 2 * index]
        pooled = math.sqrt((c_sd**2 + t_sd**2) / 2.0)
        smd[name] = 0.0 if pooled == 0 else (t_mean - c_mean) / pooled

    outcomes = connection.execute(
        "SELECT treatment, count(*) AS rows, avg(conversion), avg(visit), avg(exposure) "
        f"FROM {rel} GROUP BY treatment ORDER BY treatment"
    ).fetchall()
    columns_without_id = [*features, *binaries]
    duplicate_rows = scalar(
        connection,
        "SELECT coalesce(sum(n - 1), 0) FROM (SELECT count(*) AS n FROM "
        f"{rel} GROUP BY {', '.join(columns_without_id)} HAVING count(*) > 1)"
    )
    max_abs_smd = max(abs(value) for value in smd.values())
    practical_balance_threshold = 0.10
    material_srm = abs(treated / rows - 0.85) > 0.001
    return {
        "rows": rows,
        "treated": treated,
        "controls": controls,
        "treatment_ratio": treated / rows,
        "documented_treatment_ratio": 0.85,
        "srm_chi_square": srm_chi2,
        "srm_p_value": srm_p,
        "srm_practical_deviation": treated / rows - 0.85,
        "srm_material_inconsistency": material_srm,
        "conversions": conversions,
        "conversion_rate": conversions / rows,
        "visits": visits,
        "visit_rate": visits / rows,
        "exposures": exposures,
        "exposure_rate": exposures / rows,
        "outcomes_by_treatment": outcomes,
        "missing": missing,
        "missing_by_treatment": missing_by_treatment,
        "invalid_binary": invalid_binary,
        "nonfinite": nonfinite,
        "duplicate_rows_excluding_row_id": duplicate_rows,
        "feature_smd": smd,
        "max_abs_feature_smd": max_abs_smd,
        "practical_balance_threshold": practical_balance_threshold,
        "gate": "PASS"
        if not material_srm
        and max_abs_smd < practical_balance_threshold
        and not any(missing.values())
        and not any(invalid_binary.values())
        and not any(nonfinite.values())
        else "FAIL",
    }


def t2_quality(connection: duckdb.DuckDBPyConnection, path: Path) -> dict[str, Any]:
    rel = relation(path)
    columns = [
        "timestamp", "uid", "campaign", "conversion", "conversion_timestamp",
        "conversion_id", "attribution", "click", "click_pos", "click_nb", "cost", "cpo",
        "time_since_last_click", *(f"cat{i}" for i in range(1, 10)),
    ]
    summary = connection.execute(
        "SELECT count(*), count(DISTINCT uid), count(DISTINCT campaign), "
        "sum(conversion), count(DISTINCT CASE WHEN conversion_id >= 0 THEN conversion_id END), "
        "sum(click), sum(attribution), min(timestamp), max(timestamp) "
        f"FROM {rel}"
    ).fetchone()
    assert summary is not None
    null_terms = ", ".join(
        f"sum(CASE WHEN {name} IS NULL THEN 1 ELSE 0 END)" for name in columns
    )
    null_row = connection.execute(f"SELECT {null_terms} FROM {rel}").fetchone()
    assert null_row is not None
    missing = dict(zip(columns, null_row, strict=True))
    invalid_binary = {
        name: scalar(connection, f"SELECT count(*) FROM {rel} WHERE {name} NOT IN (0, 1)")
        for name in ("conversion", "attribution", "click")
    }
    nonfinite = {
        name: scalar(connection, f"SELECT count(*) FROM {rel} WHERE NOT isfinite({name})")
        for name in ("cost", "cpo")
    }
    chronology_violations = scalar(
        connection,
        "SELECT count(*) FROM (SELECT timestamp, lag(timestamp) OVER (ORDER BY row_id) AS prior "
        f"FROM {rel}) WHERE prior IS NOT NULL AND timestamp < prior",
    )
    conversion_time_violations = scalar(
        connection,
        f"SELECT count(*) FROM {rel} WHERE conversion = 1 "
        "AND (conversion_timestamp < timestamp OR conversion_timestamp < 0 OR conversion_id < 0)",
    )
    conversion_ids_reused_across_users = scalar(
        connection,
        "SELECT count(*) FROM (SELECT conversion_id FROM "
        f"{rel} WHERE conversion_id >= 0 GROUP BY conversion_id HAVING count(DISTINCT uid) > 1)",
    )
    composite_conversion_time_conflicts = scalar(
        connection,
        "SELECT count(*) FROM (SELECT uid, conversion_id FROM "
        f"{rel} WHERE conversion_id >= 0 GROUP BY uid, conversion_id "
        "HAVING count(DISTINCT conversion_timestamp) > 1)",
    )
    duplicates = scalar(
        connection,
        "SELECT coalesce(sum(n - 1), 0) FROM (SELECT count(*) AS n FROM "
        f"{rel} GROUP BY {', '.join(columns)} HAVING count(*) > 1)",
    )
    gate = (
        "PASS"
        if not any(missing.values())
        and not any(invalid_binary.values())
        and not any(nonfinite.values())
        and chronology_violations == 0
        and conversion_time_violations == 0
        and composite_conversion_time_conflicts == 0
        else "FAIL"
    )
    return {
        "rows": summary[0],
        "users": summary[1],
        "campaigns": summary[2],
        "conversion_impressions": summary[3],
        "unique_conversions": summary[4],
        "clicks": summary[5],
        "attributed_conversion_impressions": summary[6],
        "timestamp_min": summary[7],
        "timestamp_max": summary[8],
        "missing": missing,
        "invalid_binary": invalid_binary,
        "nonfinite": nonfinite,
        "row_order_chronology_violations": chronology_violations,
        "conversion_time_violations": conversion_time_violations,
        "conversion_ids_reused_across_users": conversion_ids_reused_across_users,
        "composite_conversion_time_conflicts": composite_conversion_time_conflicts,
        "conversion_path_identity": "(uid, conversion_id)",
        "duplicate_rows_excluding_row_id": duplicates,
        "gate": gate,
    }


def role_case(bucket_expression: str) -> str:
    clauses = " ".join(
        f"WHEN {bucket_expression} < {threshold} THEN '{role}'"
        for threshold, role in ROLE_THRESHOLDS
    )
    return f"CASE {clauses} END"


def build_t1_roles(connection: duckdb.DuckDBPyConnection, source: Path, target: Path) -> None:
    if target.is_file():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".parquet.tmp")
    bucket = f"md5_number_lower('{T1_SALT}:' || row_id::VARCHAR) % 10000"
    query = f"SELECT *, {role_case(bucket)} AS role FROM {relation(source)}"
    connection.execute(
        f"COPY ({query}) TO '{quote_path(temporary)}' "
        "(FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 131072)"
    )
    os.replace(temporary, target)


def t2_cutpoints(connection: duckdb.DuckDBPyConnection, source: Path) -> list[int]:
    rel = relation(source)
    query = (
        "WITH users AS (SELECT uid, "
        "max(CASE WHEN conversion_timestamp >= 0 THEN conversion_timestamp "
        "ELSE timestamp END) user_end "
        f"FROM {rel} GROUP BY uid) "
        "SELECT quantile_cont(user_end, [0.50, 0.65, 0.75, 0.85, 0.90]) FROM users"
    )
    values = scalar(connection, query)
    return [int(value) for value in values]


def build_t2_roles(
    connection: duckdb.DuckDBPyConnection, source: Path, target: Path, cutpoints: list[int]
) -> None:
    if target.is_file():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".parquet.tmp")
    rel = relation(source)
    path_key = (
        "CASE WHEN conversion_id >= 0 THEN 'c:' || uid::VARCHAR || ':' || conversion_id::VARCHAR "
        "ELSE 'n:' || uid::VARCHAR || ':' || floor(timestamp / 86400)::BIGINT::VARCHAR END"
    )
    role = (
        f"CASE WHEN user_end <= {cutpoints[0]} THEN 'train' "
        f"WHEN user_end <= {cutpoints[1]} THEN 'validation' "
        f"WHEN user_end <= {cutpoints[2]} THEN 'calibration' "
        f"WHEN user_end <= {cutpoints[3]} THEN 'policy' "
        f"WHEN user_end <= {cutpoints[4]} THEN 'qualification' ELSE 'locked_final' END"
    )
    query = (
        "WITH events AS (SELECT *, " + path_key + " AS path_key FROM " + rel + "), "
        "users AS (SELECT uid, max(CASE WHEN conversion_timestamp >= 0 "
        "THEN conversion_timestamp ELSE timestamp END) AS user_end FROM events GROUP BY uid) "
        f"SELECT events.*, users.user_end, {role} AS role FROM events JOIN users USING(uid)"
    )
    connection.execute(
        f"COPY ({query}) TO '{quote_path(temporary)}' "
        "(FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 131072)"
    )
    os.replace(temporary, target)


def validate_roles(
    connection: duckdb.DuckDBPyConnection,
    path: Path,
    expected_rows: int,
    path_key: bool,
    user_key: bool = False,
) -> dict[str, Any]:
    rel = relation(path)
    rows = scalar(connection, f"SELECT count(*) FROM {rel}")
    counts = dict(connection.execute(f"SELECT role, count(*) FROM {rel} GROUP BY role").fetchall())
    distinct_ids = scalar(connection, f"SELECT count(DISTINCT row_id) FROM {rel}")
    leakage = 0
    if path_key:
        leakage = scalar(
            connection,
            "SELECT count(*) FROM (SELECT path_key FROM "
            f"{rel} GROUP BY path_key HAVING count(DISTINCT role) > 1)",
        )
    user_leakage = 0
    user_counts: dict[str, int] = {}
    time_ranges: dict[str, dict[str, int]] = {}
    if user_key:
        user_leakage = scalar(
            connection,
            "SELECT count(*) FROM (SELECT uid FROM "
            f"{rel} GROUP BY uid HAVING count(DISTINCT role) > 1)",
        )
        user_counts = dict(
            connection.execute(
                f"SELECT role, count(DISTINCT uid) FROM {rel} GROUP BY role"
            ).fetchall()
        )
        time_ranges = {
            row[0]: {"event_min": row[1], "event_max": row[2], "user_end_max": row[3]}
            for row in connection.execute(
                "SELECT role, min(timestamp), max(timestamp), max(user_end) FROM "
                f"{rel} GROUP BY role"
            ).fetchall()
        }
    return {
        "rows": rows,
        "expected_rows": expected_rows,
        "role_counts": counts,
        "distinct_row_ids": distinct_ids,
        "path_role_leakage_groups": leakage,
        "user_role_leakage_groups": user_leakage,
        "user_counts": user_counts,
        "time_ranges": time_ranges,
        "gate": "PASS"
        if rows == expected_rows
        and distinct_ids == expected_rows
        and set(counts) == {role for _, role in ROLE_THRESHOLDS}
        and leakage == 0
        and user_leakage == 0
        else "FAIL",
    }


def run(root: Path) -> dict[str, Any]:
    root = root.resolve()
    staged = root / "data" / "staged"
    validated = root / "data" / "validated"
    t1_source = staged / "t1_uplift.parquet"
    t2_source = staged / "t2_attribution.parquet"
    t1_target = validated / "t1_uplift_roles.parquet"
    t2_target = validated / "t2_attribution_roles.parquet"
    connection = duckdb.connect()
    try:
        configure(connection, root)
        quality_t1 = t1_quality(connection, t1_source)
        quality_t2 = t2_quality(connection, t2_source)
        cutpoints = t2_cutpoints(connection, t2_source)
        build_t1_roles(connection, t1_source, t1_target)
        build_t2_roles(connection, t2_source, t2_target, cutpoints)
        roles_t1 = validate_roles(connection, t1_target, quality_t1["rows"], False)
        roles_t2 = validate_roles(connection, t2_target, quality_t2["rows"], True, True)
        t1_bucket = f"md5_number_lower('{T1_SALT}:' || row_id::VARCHAR) % 10000"
        roles_t1["assignment_mismatches"] = scalar(
            connection,
            f"SELECT count(*) FROM {relation(t1_target)} "
            f"WHERE role != {role_case(t1_bucket)}",
        )
        t2_role = (
            f"CASE WHEN user_end <= {cutpoints[0]} THEN 'train' "
            f"WHEN user_end <= {cutpoints[1]} THEN 'validation' "
            f"WHEN user_end <= {cutpoints[2]} THEN 'calibration' "
            f"WHEN user_end <= {cutpoints[3]} THEN 'policy' "
            f"WHEN user_end <= {cutpoints[4]} THEN 'qualification' ELSE 'locked_final' END"
        )
        roles_t2["assignment_mismatches"] = scalar(
            connection,
            f"SELECT count(*) FROM {relation(t2_target)} WHERE role != {t2_role}",
        )
        if roles_t1["assignment_mismatches"]:
            roles_t1["gate"] = "FAIL"
        if roles_t2["assignment_mismatches"]:
            roles_t2["gate"] = "FAIL"
    finally:
        connection.close()
    quality = {
        "phase": "P04",
        "created_at": utc_now(),
        "T1": quality_t1,
        "T2": quality_t2,
        "overall_gate": "PASS"
        if quality_t1["gate"] == quality_t2["gate"] == "PASS"
        else "FAIL",
    }
    roles = {
        "phase": "P04",
        "created_at": utc_now(),
        "T1": {
            **roles_t1,
            "strategy": "stable MD5 lower-64-bit bucket over salt and immutable row_id",
            "salt": T1_SALT,
            "thresholds_per_10000": dict((role, threshold) for threshold, role in ROLE_THRESHOLDS),
            "path": "data/validated/t1_uplift_roles.parquet",
            "sha256": sha256_file(t1_target),
            "bytes": t1_target.stat().st_size,
        },
        "T2": {
            **roles_t2,
            "strategy": (
                "time-aware user-end quantiles; every user's events stay in one role, "
                "which also keeps (uid, conversion_id) paths intact"
            ),
            "cutpoints": cutpoints,
            "embargo": (
                "not used because roles are user-disjoint; role time ranges overlap because "
                "each user's complete history follows that user's end-time assignment"
            ),
            "path": "data/validated/t2_attribution_roles.parquet",
            "sha256": sha256_file(t2_target),
            "bytes": t2_target.stat().st_size,
        },
        "overall_gate": "PASS"
        if roles_t1["gate"] == roles_t2["gate"] == "PASS"
        else "FAIL",
    }
    publish_json(root / "artifacts" / "qualification" / "P04" / "data_quality.json", quality)
    publish_json(root / "artifacts" / "qualification" / "P04" / "protected_roles.json", roles)
    return {"quality": quality, "roles": roles}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    result = run(args.root)
    print(json.dumps(result, sort_keys=True))
    gates_pass = result["quality"]["overall_gate"] == result["roles"]["overall_gate"] == "PASS"
    return 0 if gates_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
