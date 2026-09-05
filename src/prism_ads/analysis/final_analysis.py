"""Produce the mandated ordered final analysis from registered evidence."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import duckdb
import numpy as np

from prism_ads.experiments.t3_generator import publish_json, sha256_file, utc_now
from prism_ads.governance.freeze import verify_freeze_manifest
from prism_ads.pipeline.controller import ProjectController

FREEZE_ID = "prism-ads-v2.2-20260904-8d98593fabdf-r2"


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected object: {path}")
    return value


def run(root: Path) -> dict[str, Any]:
    root = root.resolve()
    locked = root / "artifacts" / "locked" / FREEZE_ID
    master = locked / "analysis_master.parquet"
    primary = _load(locked / "primary_results.json")
    promotion = _load(locked / "promotion_gate.json")
    secondary = _load(locked / "secondary" / "secondary_results.json")
    p04 = _load(root / "artifacts" / "receipts" / "P04.json")
    p10 = _load(root / "artifacts" / "development" / "P10" / "method_selection_v3.json")
    privacy = _load(root / "artifacts" / "qualification" / "P11" / "privacy_accounting.json")
    controller = ProjectController.discover(root).verify()
    freeze = verify_freeze_manifest(
        root, root / "artifacts" / "qualification" / "P12" / "freeze_manifest_v2.json"
    )
    connection = duckdb.connect()
    try:
        metrics_rows = connection.execute(
            "SELECT model, sqrt(sum(units*squared_error)/sum(units)) weighted_rmse, "
            "sqrt(avg(squared_error)) macro_rmse, avg(absolute_error) mae, "
            "avg(CASE WHEN lower_95<=true_ate AND true_ate<=upper_95 THEN 1.0 ELSE 0 END) coverage "
            "FROM read_parquet(?) WHERE evidence_scope='primary' GROUP BY model ORDER BY model",
            [str(master)],
        ).fetchall()
        long_tail_rows = connection.execute(
            "SELECT model, sqrt(sum(units*squared_error)/sum(units)) weighted_rmse, "
            "sqrt(avg(squared_error)) macro_rmse FROM read_parquet(?) "
            "WHERE evidence_scope='primary' AND campaign_size_decile=1 "
            "GROUP BY model ORDER BY model",
            [str(master)],
        ).fetchall()
        decision_rows = connection.execute(
            "SELECT replicate, model, campaign, sum(units*true_ate)/sum(units) truth, "
            "sum(units*estimate)/sum(units) estimate, sum(units) value_weight "
            "FROM read_parquet(?) WHERE evidence_scope='primary' "
            "GROUP BY replicate, model, campaign ORDER BY replicate, model, campaign",
            [str(master)],
        ).fetchall()
    finally:
        connection.close()
    metrics = {
        str(row[0]): {
            "weighted_rmse": float(row[1]),
            "macro_rmse": float(row[2]),
            "mae": float(row[3]),
            "coverage": float(row[4]),
        }
        for row in metrics_rows
    }
    long_tail = {
        str(row[0]): {"weighted_rmse": float(row[1]), "macro_rmse": float(row[2])}
        for row in long_tail_rows
    }
    decision_regret: dict[str, dict[str, float]] = {}
    for fraction in (0.10, 0.25):
        by_model: dict[str, list[float]] = {"B3": [], "PRISM": []}
        for replicate in range(10):
            for model in by_model:
                selected_rows = [
                    row
                    for row in decision_rows
                    if int(row[0]) == replicate and str(row[1]) == model
                ]
                truth = np.asarray([row[3] for row in selected_rows], dtype=float)
                estimate = np.asarray([row[4] for row in selected_rows], dtype=float)
                weight = np.asarray([row[5] for row in selected_rows], dtype=float)
                value = truth * weight
                count = max(1, round(value.size * fraction))
                oracle = float(np.partition(value, -count)[-count:].sum())
                chosen = np.argpartition(estimate * weight, -count)[-count:]
                by_model[model].append((oracle - float(value[chosen].sum())) / oracle)
        decision_regret[f"top{int(fraction * 100)}"] = {
            model: float(np.mean(values)) for model, values in by_model.items()
        }
    sections: list[dict[str, Any]] = [
        {
            "order": 1,
            "topic": "artifact_integrity",
            "result": {
                "controller": controller,
                "freeze": freeze,
                "analysis_master_sha256": sha256_file(master),
            },
        },
        {"order": 2, "topic": "data_validity", "result": p04["gates"]},
        {
            "order": 3,
            "topic": "randomization_diagnostics",
            "result": {"T1": secondary["T1_randomized"], "P04": p04["gates"]},
        },
        {"order": 4, "topic": "privacy_accounting_validity", "result": privacy},
        {
            "order": 5,
            "topic": "inference_health",
            "result": {
                "status": promotion["inference_health"],
                "replicates": primary["inference_health"],
            },
        },
        {"order": 6, "topic": "primary_weighted_rmse", "result": primary["primary"]},
        {
            "order": 7,
            "topic": "macro_rmse",
            "result": {model: value["macro_rmse"] for model, value in metrics.items()},
        },
        {"order": 8, "topic": "long_tail_result", "result": long_tail},
        {
            "order": 9,
            "topic": "interval_coverage",
            "result": {model: value["coverage"] for model, value in metrics.items()},
        },
        {
            "order": 10,
            "topic": "decision_regret",
            "result": decision_regret,
        },
        {
            "order": 11,
            "topic": "privacy_utility",
            "result": {"scores": secondary["scores"], "threshold": secondary["threshold_study"]},
        },
        {"order": 12, "topic": "attribution", "result": secondary["T2_private_attribution"]},
        {"order": 13, "topic": "falsification", "result": p10["falsification"]},
        {
            "order": 14,
            "topic": "ablation",
            "result": {
                "order": p10["ablation_order"],
                "scores": {
                    key: value for key, value in p10["scores"].items() if key.startswith("C")
                },
            },
        },
        {"order": 15, "topic": "sensitivity", "result": secondary["sensitivity"]},
        {
            "order": 16,
            "topic": "runtime",
            "result": {
                "primary_gpu_seconds": sum(
                    fit["runtime_seconds"]
                    for replicate in primary["inference_health"]
                    for fit in replicate["fits"]
                ),
                "secondary_gpu_seconds": sum(
                    item["runtime_seconds"] for item in secondary["diagnostics"]
                ),
            },
        },
    ]
    result = {
        "phase": "P16",
        "created_at": utc_now(),
        "status": "PASS",
        "final_scientific_decision": "RETAIN_BASELINE",
        "decision_reason": (
            "PRISM passed weighted-RMSE materiality and paired uncertainty but failed the "
            "frozen interval-coverage guardrail; all promotion gates are conjunctive."
        ),
        "primary_verdict": promotion["status"],
        "ordered_analysis": sections,
        "claim_boundary": (
            "Research benchmark evidence only; T2 attribution credit is not causal "
            "incrementality and no production or Ads Data Hub implementation is claimed."
        ),
    }
    publish_json(locked / "final_analysis.json", result)
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
