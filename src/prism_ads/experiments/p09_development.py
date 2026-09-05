"""Build T2 paths, run A0-A5, and validate T3 decision metrics."""

from __future__ import annotations

import argparse
import json
import math
import os
from collections import Counter, defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from prism_ads.attribution.methods import Touch, attribute_path, markov_removal_effect
from prism_ads.decisions.metrics import decision_regret, reference_decision_deviation
from prism_ads.experiments.t3_generator import publish_json, relation, sha256_file, utc_now
from prism_ads.warehouse.preprocess import configure, quote_path


def scalar(connection: duckdb.DuckDBPyConnection, query: str) -> Any:
    row = connection.execute(query).fetchone()
    if row is None:
        raise RuntimeError("query returned no row")
    return row[0]


def build_paths(
    connection: duckdb.DuckDBPyConnection, events: Path, target: Path
) -> None:
    if target.is_file():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".parquet.tmp")
    query = (
        "SELECT uid, path_key, any_value(role) AS role, max(conversion)::TINYINT AS converted, "
        "list(campaign ORDER BY timestamp, row_id) AS campaigns, "
        "list(timestamp ORDER BY timestamp, row_id) AS touch_timestamps, "
        "max(CASE WHEN conversion_timestamp >= 0 THEN conversion_timestamp ELSE timestamp END) "
        f"AS terminal_timestamp, count(*) AS impressions FROM {relation(events)} "
        "GROUP BY uid, path_key"
    )
    connection.execute(
        f"COPY ({query}) TO '{quote_path(temporary)}' "
        "(FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 131072)"
    )
    os.replace(temporary, target)


def run_attribution(
    connection: duckdb.DuckDBPyConnection, paths: Path, output: Path
) -> dict[str, Any]:
    rows = connection.execute(
        f"SELECT campaigns, touch_timestamps, terminal_timestamp, converted FROM {relation(paths)} "
        "WHERE role='validation' AND md5_number_lower(path_key) % 1000 = 0"
    ).fetchall()
    converted_rows = [row for row in rows if row[3] == 1]
    credits: defaultdict[tuple[str, int], float] = defaultdict(float)
    methods = [
        "A0_last_click",
        "A1_first_click",
        "A2_linear",
        "A3_time_decay",
        "A4_position_based",
    ]
    for campaigns, timestamps, terminal, _ in converted_rows:
        touches = [
            Touch(int(campaign), int(timestamp))
            for campaign, timestamp in zip(campaigns, timestamps, strict=True)
        ]
        for method in methods:
            for campaign, credit in attribute_path(touches, method, int(terminal)).items():
                credits[(method, campaign)] += credit
    frequency = Counter(int(campaign) for row in rows for campaign in row[0])
    top_campaigns = {campaign for campaign, _ in frequency.most_common(20)}
    markov_paths = [
        ([int(value) if int(value) in top_campaigns else -1 for value in row[0]], bool(row[3]))
        for row in rows
    ]
    markov = markov_removal_effect(markov_paths)
    for campaign, credit in markov.items():
        credits[("A5_markov_removal", campaign)] = credit * len(converted_rows)
    ordered = sorted(credits.items())
    table = pa.table(
        {
            "method": [key[0] for key, _ in ordered],
            "campaign": [key[1] for key, _ in ordered],
            "credit": [value for _, value in ordered],
        }
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".parquet.tmp")
    pq.write_table(table, temporary, compression="zstd")
    os.replace(temporary, output)
    return {
        "sample_paths": len(rows),
        "sample_conversion_paths": len(converted_rows),
        "markov_top_campaigns_plus_other": len(top_campaigns) + 1,
        "credit_rows": table.num_rows,
    }


def t3_decisions(
    connection: duckdb.DuckDBPyConnection, predictions: Path, truth: Path
) -> dict[str, Any]:
    query = (
        "WITH predicted AS (SELECT campaign, sum(B3_estimate*units)/sum(units) estimate "
        f"FROM {relation(predictions)} GROUP BY campaign), truth AS (SELECT campaign, "
        "avg(ite_R2) true_effect, count(*)::DOUBLE value_weight FROM "
        f"{relation(truth)} WHERE role='method_validation' GROUP BY campaign) "
        "SELECT p.campaign, p.estimate, t.true_effect, t.value_weight FROM predicted p "
        "JOIN truth t USING(campaign) ORDER BY campaign"
    )
    rows = connection.execute(query).fetchall()
    estimate = np.array([row[1] for row in rows])
    true_effect = np.array([row[2] for row in rows])
    weight = np.array([row[3] for row in rows])
    count = len(rows)
    budgets = {
        "top_10_percent": max(1, math.ceil(0.10 * count)),
        "top_25_percent": max(1, math.ceil(0.25 * count)),
        "fixed_50": min(50, count),
    }
    return {
        name: {
            "selected_campaigns": selected,
            "true_decision_regret": decision_regret(
                true_effect, estimate, weight, selected
            ),
        }
        for name, selected in budgets.items()
    }


def run(root: Path) -> dict[str, Any]:
    root = root.resolve()
    events = root / "data" / "validated" / "t2_attribution_roles.parquet"
    paths = root / "data" / "marts" / "t2_paths.parquet"
    credit = root / "artifacts" / "development" / "P09" / "attribution_credit.parquet"
    predictions = root / "artifacts" / "development" / "P06" / "t3_r2_predictions.parquet"
    truth = (
        root
        / "artifacts"
        / "qualification"
        / "P05"
        / "sealed_truth"
        / "t3_individual_truth.parquet"
    )
    connection = duckdb.connect()
    try:
        configure(connection, root)
        build_paths(connection, events, paths)
        path_rows = scalar(connection, f"SELECT count(*) FROM {relation(paths)}")
        conversion_paths = scalar(
            connection, f"SELECT count(*) FROM {relation(paths)} WHERE converted=1"
        )
        chronology_failures = scalar(
            connection,
            f"SELECT count(*) FROM {relation(paths)} WHERE converted=1 "
            "AND list_max(touch_timestamps) > terminal_timestamp",
        )
        path_role_leakage = scalar(
            connection,
            "SELECT count(*) FROM (SELECT path_key FROM "
            f"{relation(paths)} GROUP BY path_key HAVING count(DISTINCT role)>1)",
        )
        attribution = run_attribution(connection, paths, credit)
        decision = t3_decisions(connection, predictions, truth)
        methods = connection.execute(
            f"SELECT method, list(credit ORDER BY campaign) FROM {relation(credit)} "
            "GROUP BY method ORDER BY method"
        ).fetchall()
        reference_deviation: dict[str, float] = {}
        reference = np.asarray(methods[0][1], dtype=float)
        for method, values in methods[1:5]:
            candidate = np.asarray(values, dtype=float)
            size = min(reference.size, candidate.size)
            reference_deviation[method] = reference_decision_deviation(
                reference[:size], candidate[:size], min(10, size)
            )
    finally:
        connection.close()
    result = {
        "phase": "P09",
        "created_at": utc_now(),
        "status": "PASS" if chronology_failures == path_role_leakage == 0 else "FAIL",
        "paths": {
            "rows": path_rows,
            "conversion_paths": conversion_paths,
            "chronology_failures": chronology_failures,
            "path_role_leakage": path_role_leakage,
            "path": str(paths.relative_to(root)).replace("\\", "/"),
            "bytes": paths.stat().st_size,
            "sha256": sha256_file(paths),
        },
        "attribution": {
            **attribution,
            "methods": ["A0", "A1", "A2", "A3", "A4", "A5"],
            "reference_decision_deviation": reference_deviation,
            "claim_boundary": "attribution credit is not causal incrementality",
            "output_sha256": sha256_file(credit),
        },
        "T3_decision_regret": decision,
    }
    publish_json(root / "artifacts" / "development" / "P09" / "validation.json", result)
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
