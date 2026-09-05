"""Development-only execution for causal references and aggregate baseline ladder."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from prism_ads.causal.estimators import (
    cross_fitted_doubly_robust,
    empirical_bayes,
    private_aggregate_difference,
    randomized_difference,
    regression_adjusted,
)
from prism_ads.experiments.t3_generator import publish_json, relation, sha256_file, utc_now
from prism_ads.warehouse.preprocess import configure


def fit_t3_baselines(
    connection: duckdb.DuckDBPyConnection, observations: Path, output: Path
) -> dict[str, Any]:
    query = (
        "SELECT campaign, segment, count(*)::BIGINT AS units, "
        "sum(treatment)::DOUBLE AS n1, sum(1-treatment)::DOUBLE AS n0, "
        "sum(treatment*outcome_R2)::DOUBLE AS y1, "
        "sum((1-treatment)*outcome_R2)::DOUBLE AS y0 "
        f"FROM {relation(observations)} WHERE role='method_validation' "
        "GROUP BY campaign, segment HAVING n1 > 0 AND n0 > 0 ORDER BY campaign, segment"
    )
    arrays = connection.execute(query).fetchnumpy()
    effects, variances = private_aggregate_difference(
        arrays["y1"], arrays["n1"], arrays["y0"], arrays["n0"]
    )
    pooled, hyperparameters = empirical_bayes(effects, variances)
    table = pa.table(
        {
            "campaign": arrays["campaign"],
            "segment": arrays["segment"],
            "units": arrays["units"],
            "B1_estimate": effects,
            "B2_estimate": effects,
            "B2_variance": variances,
            "B3_estimate": pooled,
        }
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".parquet.tmp")
    pq.write_table(table, temporary, compression="zstd")
    os.replace(temporary, output)
    output.chmod(0o444)
    return {"groups": table.num_rows, "B3_hyperparameters": hyperparameters}


def score_frozen_t3_predictions(
    connection: duckdb.DuckDBPyConnection, predictions: Path, individual_truth: Path
) -> dict[str, Any]:
    truth = (
        "SELECT campaign, segment, count(*) AS truth_units, avg(ite_R2) AS true_ate FROM "
        f"{relation(individual_truth)} WHERE role='method_validation' GROUP BY campaign, segment"
    )
    joined = (
        f"SELECT p.*, t.true_ate FROM {relation(predictions)} p JOIN ({truth}) t "
        "USING(campaign, segment)"
    )
    metrics: dict[str, Any] = {}
    for model in ("B1", "B2", "B3"):
        row = connection.execute(
            f"SELECT sqrt(sum(units*pow({model}_estimate-true_ate,2))/sum(units)), "
            f"sqrt(avg(pow({model}_estimate-true_ate,2))), "
            f"avg(abs({model}_estimate-true_ate)), count(*) FROM ({joined})"
        ).fetchone()
        assert row is not None
        metrics[model] = {
            "weighted_rmse": row[0],
            "macro_rmse": row[1],
            "mae": row[2],
            "groups": row[3],
        }
    return metrics


def run_t1_references(connection: duckdb.DuckDBPyConnection, t1: Path) -> dict[str, Any]:
    features = ", ".join(f"f{i}" for i in range(12))
    arrays = connection.execute(
        f"SELECT treatment, conversion, {features} FROM {relation(t1)} "
        "WHERE role='validation' AND row_id % 100 = 0 ORDER BY row_id"
    ).fetchnumpy()
    treatment = arrays.pop("treatment").astype(np.float64)
    outcome = arrays.pop("conversion").astype(np.float64)
    x = np.column_stack([arrays[f"f{i}"] for i in range(12)]).astype(np.float64)
    nr0 = randomized_difference(outcome, treatment)
    nr1 = regression_adjusted(outcome, treatment, x)
    nr2 = cross_fitted_doubly_robust(outcome, treatment, x, float(treatment.mean()))
    return {
        "rows": outcome.size,
        "role": "validation",
        "outcome": "conversion",
        "NR0": asdict(nr0),
        "NR1": asdict(nr1),
        "NR2": asdict(nr2),
    }


def run(root: Path) -> dict[str, Any]:
    root = root.resolve()
    t1 = root / "data" / "validated" / "t1_uplift_roles.parquet"
    observations = root / "data" / "validated" / "t3_observations.parquet"
    truth = (
        root
        / "artifacts"
        / "qualification"
        / "P05"
        / "sealed_truth"
        / "t3_individual_truth.parquet"
    )
    predictions = root / "artifacts" / "development" / "P06" / "t3_r2_predictions.parquet"
    connection = duckdb.connect()
    try:
        configure(connection, root)
        t1_results = run_t1_references(connection, t1)
        fit = fit_t3_baselines(connection, observations, predictions)
        prediction_identity = {
            "path": str(predictions.relative_to(root)).replace("\\", "/"),
            "sha256": sha256_file(predictions),
            "bytes": predictions.stat().st_size,
            "status": "frozen_before_truth_scoring",
        }
        scores = score_frozen_t3_predictions(connection, predictions, truth)
    finally:
        connection.close()
    result = {
        "phase": "P06",
        "created_at": utc_now(),
        "status": "PASS",
        "T1_randomized_references": t1_results,
        "T3_development": {
            "role": "method_validation",
            "effect_regime": "R2",
            "fit": fit,
            "predictions": prediction_identity,
            "scores": scores,
            "privacy_status": (
                "aggregate-only interface validated; no formal DP claim until P07"
            ),
        },
    }
    publish_json(root / "artifacts" / "development" / "P06" / "metrics.json", result)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    result = run(args.root)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
