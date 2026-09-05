"""Independent T3 reproducibility, truth-seal, and leakage validation."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import duckdb

from prism_ads.experiments.t3_generator import (
    ASSIGNMENT_SEED,
    OUTCOME_SEED,
    REGIMES,
    publish_json,
    relation,
    utc_now,
)
from prism_ads.warehouse.preprocess import configure


def scalar(connection: duckdb.DuckDBPyConnection, query: str) -> Any:
    row = connection.execute(query).fetchone()
    if row is None:
        raise RuntimeError("query returned no row")
    return row[0]


def run(root: Path) -> dict[str, Any]:
    root = root.resolve()
    structure = root / "data" / "validated" / "t3_structure.parquet"
    observations = root / "data" / "validated" / "t3_observations.parquet"
    sealed = root / "artifacts" / "qualification" / "P05" / "sealed_truth"
    individual = sealed / "t3_individual_truth.parquet"
    group_paths = {
        "campaign": sealed / "t3_campaign_truth.parquet",
        "segment": sealed / "t3_segment_truth.parquet",
        "campaign_segment": sealed / "t3_campaign_segment_truth.parquet",
    }
    connection = duckdb.connect()
    try:
        configure(connection, root)
        units = scalar(connection, f"SELECT count(*) FROM {relation(structure)}")
        observation_rows = scalar(
            connection, f"SELECT count(*) FROM {relation(observations)}"
        )
        truth_rows = scalar(connection, f"SELECT count(*) FROM {relation(individual)}")
        distinct_units = scalar(
            connection, f"SELECT count(DISTINCT unit_id) FROM {relation(observations)}"
        )
        user_role_leakage = scalar(
            connection,
            "SELECT count(*) FROM (SELECT uid FROM "
            f"{relation(structure)} GROUP BY uid HAVING count(DISTINCT role) > 1)",
        )
        observation_schema = [
            row[0]
            for row in connection.execute(
                f"DESCRIBE SELECT * FROM {relation(observations)}"
            ).fetchall()
        ]
        leaked_truth_columns = [
            name
            for name in observation_schema
            if name.startswith(("p0_", "p1_", "ite_", "tau_", "logit0_"))
        ]
        treatment_mismatches = scalar(
            connection,
            f"SELECT count(*) FROM {relation(observations)} WHERE treatment != "
            f"CASE WHEN md5_number_lower('{ASSIGNMENT_SEED}:' || unit_id::VARCHAR) "
            "% 1000000 < 500000 THEN 1 ELSE 0 END",
        )
        outcome_mismatches: dict[str, int] = {}
        for regime in REGIMES:
            uniform = (
                f"(md5_number_lower('{OUTCOME_SEED}:{regime}:' || o.unit_id::VARCHAR) "
                "% 1000000)::DOUBLE / 1000000.0"
            )
            expected = (
                f"CASE WHEN {uniform} < t.p0_{regime} + o.treatment * "
                f"(t.p1_{regime} - t.p0_{regime}) THEN 1 ELSE 0 END"
            )
            outcome_mismatches[regime] = scalar(
                connection,
                f"SELECT count(*) FROM {relation(observations)} o JOIN {relation(individual)} t "
                f"USING(unit_id) WHERE o.outcome_{regime} != {expected}",
            )
        group_truth: dict[str, Any] = {}
        for name, path in group_paths.items():
            group_truth[name] = {
                "rows": scalar(connection, f"SELECT count(*) FROM {relation(path)}"),
                "null_true_ate": scalar(
                    connection,
                    f"SELECT count(*) FROM {relation(path)} WHERE true_ate IS NULL",
                ),
                "regimes": scalar(
                    connection,
                    f"SELECT count(DISTINCT effect_regime) FROM {relation(path)}",
                ),
            }
    finally:
        connection.close()
    gates = {
        "row_lineage": units == observation_rows == truth_rows == distinct_units,
        "user_role_leakage": user_role_leakage == 0,
        "candidate_truth_column_leakage": not leaked_truth_columns,
        "treatment_reproducibility": treatment_mismatches == 0,
        "outcome_reproducibility": not any(outcome_mismatches.values()),
        "group_truth_complete": all(
            value["null_true_ate"] == 0 and value["regimes"] == len(REGIMES)
            for value in group_truth.values()
        ),
        "all_segment_buckets_realized": group_truth["segment"]["rows"]
        == 8 * len(REGIMES),
    }
    result = {
        "phase": "P05",
        "validated_at": utc_now(),
        "status": "PASS" if all(gates.values()) else "FAIL",
        "units": units,
        "observation_rows": observation_rows,
        "individual_truth_rows": truth_rows,
        "distinct_observation_units": distinct_units,
        "user_role_leakage": user_role_leakage,
        "leaked_truth_columns": leaked_truth_columns,
        "treatment_mismatches": treatment_mismatches,
        "outcome_mismatches": outcome_mismatches,
        "group_truth": group_truth,
        "gates": gates,
    }
    publish_json(root / "artifacts" / "qualification" / "P05" / "seal_validation.json", result)
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
