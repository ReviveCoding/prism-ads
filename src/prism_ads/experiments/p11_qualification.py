# mypy: disable-error-code="no-untyped-call"
"""Representative end-to-end qualification and inference stability evidence."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pyarrow as pa  # type: ignore[import-untyped]

from prism_ads.causal.estimators import empirical_bayes, private_aggregate_difference
from prism_ads.decisions.metrics import decision_regret
from prism_ads.experiments.p10_development import (
    EFFECT_SCALE_PRIOR,
    MAX_CAMPAIGNS,
    _aggregate_query,
    _arrays,
    _atomic_parquet,
    _fit_prism,
    _metrics,
    _release,
    _truth,
)
from prism_ads.experiments.t3_generator import publish_json, sha256_file, utc_now
from prism_ads.privacy.engine import account_gaussian, calibrate_gaussian, l2_sensitivity
from prism_ads.warehouse.preprocess import configure

EPSILON = 1.0
DELTA = 1e-7
SEEDS = (20260906, 20260907, 20260908)
REGIME = "R2"


def run(root: Path) -> dict[str, Any]:
    root = root.resolve()
    output = root / "artifacts" / "qualification" / "P11"
    observations = root / "data" / "validated" / "t3_observations.parquet"
    truth_path = (
        root
        / "artifacts"
        / "qualification"
        / "P05"
        / "sealed_truth"
        / "t3_campaign_segment_truth.parquet"
    )
    sensitivity = l2_sensitivity(MAX_CAMPAIGNS, 2)
    sigma = calibrate_gaussian(EPSILON, DELTA, sensitivity)
    connection = duckdb.connect()
    configure(connection, root)
    try:
        raw = _arrays(
            connection,
            _aggregate_query(observations, f"outcome_{REGIME}").replace(
                "role='method_validation'", "role='qualification'"
            ),
        )
        released = _release(raw, sigma, SEEDS[0])
        effects, variances = private_aggregate_difference(
            released["y1"],
            released["n1"],
            released["y0"],
            released["n0"],
            sigma**2,
            sigma**2,
        )
        baseline, hyperparameters = empirical_bayes(effects, variances)
        baseline_variance = 1.0 / (1.0 / variances + 1.0 / hyperparameters["tau2"])
        fits = []
        diagnostics = []
        flags = (True, True, True, True)
        for seed in SEEDS:
            mean, lower, upper, diagnostic = _fit_prism(released, sigma, flags, seed)
            fits.append((mean, lower, upper))
            diagnostics.append({**diagnostic, "seed": seed})
        rows: list[dict[str, Any]] = []
        for index in range(raw["campaign"].size):
            rows.append(
                {
                    "campaign": int(raw["campaign"][index]),
                    "segment": int(raw["segment"][index]),
                    "units": float(raw["units"][index]),
                    "B3_estimate": float(baseline[index]),
                    "B3_lower": float(
                        baseline[index] - 1.9599639845 * np.sqrt(baseline_variance[index])
                    ),
                    "B3_upper": float(
                        baseline[index] + 1.9599639845 * np.sqrt(baseline_variance[index])
                    ),
                    "PRISM_estimate": float(fits[0][0][index]),
                    "PRISM_lower": float(fits[0][1][index]),
                    "PRISM_upper": float(fits[0][2][index]),
                }
            )
        predictions = output / "qualification_predictions_pretruth.parquet"
        _atomic_parquet(pa.Table.from_pylist(rows), predictions)
        prediction_identity = {
            "path": str(predictions.relative_to(root)).replace("\\", "/"),
            "sha256": sha256_file(predictions),
            "bytes": predictions.stat().st_size,
            "status": "frozen_before_truth_scoring",
        }

        truth_map = _truth(connection, truth_path, REGIME)
        truth = np.asarray(
            [
                truth_map[(int(c), int(s))]
                for c, s in zip(raw["campaign"], raw["segment"], strict=True)
            ]
        )
        units = raw["units"].astype(float)
        prism = fits[0][0]
        campaign_units = np.asarray(
            connection.execute(
                "SELECT campaign, sum(units) AS units FROM read_parquet(?) "
                "GROUP BY campaign ORDER BY campaign",
                [str(predictions)],
            ).fetchnumpy()["units"]
        )
        campaign_order = np.argsort(np.unique(raw["campaign"]))
        del campaign_order
        campaign_truth = []
        campaign_baseline = []
        campaign_prism = []
        for campaign in np.unique(raw["campaign"]):
            mask = raw["campaign"] == campaign
            weights = units[mask]
            campaign_truth.append(np.average(truth[mask], weights=weights))
            campaign_baseline.append(np.average(baseline[mask], weights=weights))
            campaign_prism.append(np.average(prism[mask], weights=weights))
        campaign_truth_array = np.asarray(campaign_truth)
        baseline_metrics = _metrics(baseline, truth, units)
        prism_metrics = _metrics(prism, truth, units)
        size_cut = float(np.quantile(campaign_units, 0.2))
        small_campaigns = set(np.unique(raw["campaign"])[campaign_units <= size_cut].tolist())
        small = np.asarray([campaign in small_campaigns for campaign in raw["campaign"]])
        stability = [
            float(np.sqrt(np.mean((fits[left][0] - fits[right][0]) ** 2)))
            for left, right in ((0, 1), (0, 2), (1, 2))
        ]
        interval_coverage = float(np.mean((fits[0][1] <= truth) & (truth <= fits[0][2])))
        baseline_coverage = float(
            np.mean(
                (baseline - 1.9599639845 * np.sqrt(baseline_variance) <= truth)
                & (truth <= baseline + 1.9599639845 * np.sqrt(baseline_variance))
            )
        )
        regrets = {}
        for fraction in (0.10, 0.25):
            selected = max(1, int(round(len(campaign_truth) * fraction)))
            regrets[f"top_{int(fraction * 100)}_percent"] = {
                "B3": decision_regret(
                    campaign_truth_array, np.asarray(campaign_baseline), campaign_units, selected
                ),
                "PRISM": decision_regret(
                    campaign_truth_array, np.asarray(campaign_prism), campaign_units, selected
                ),
            }
    finally:
        connection.close()

    gates = {
        "predictions_frozen_before_truth": True,
        "accounted_epsilon_at_most_declared": account_gaussian(sigma, sensitivity, DELTA)["epsilon"]
        <= EPSILON,
        "all_losses_finite": all(item["finite_loss"] for item in diagnostics),
        "objective_improved_all_seeds": all(
            item["final_loss"] < item["initial_loss"] for item in diagnostics
        ),
        "seed_stability_rmse_below_0_01": max(stability) < 0.01,
        "interval_coverage_at_least_0_80": interval_coverage >= 0.80,
    }
    result = {
        "phase": "P11",
        "created_at": utc_now(),
        "status": "PASS" if all(gates.values()) else "FAIL",
        "role": "qualification",
        "effect_regime": REGIME,
        "candidate_identity": f"PRISM-HB-pyro-rate-v2-effect-scale-{EFFECT_SCALE_PRIOR}",
        "baseline_identity": "B3-empirical-bayes-private-aggregate-v1",
        "privacy": {
            "epsilon": EPSILON,
            "delta": DELTA,
            "neighboring_relation": "user-level add/remove-one",
            "l2_sensitivity": sensitivity,
            "sigma": sigma,
            "accounting": account_gaussian(sigma, sensitivity, DELTA),
        },
        "predictions": prediction_identity,
        "groups": int(raw["campaign"].size),
        "units": int(raw["units"].sum()),
        "metrics": {
            "B3": {**baseline_metrics, "interval_coverage": baseline_coverage},
            "PRISM": {**prism_metrics, "interval_coverage": interval_coverage},
            "small_campaign_bottom_quintile": {
                "size_cut_units": size_cut,
                "B3": _metrics(baseline[small], truth[small], units[small]),
                "PRISM": _metrics(prism[small], truth[small], units[small]),
            },
            "decision_regret": regrets,
        },
        "inference_health": {
            "method": "mean-field variational inference",
            "seed_pairwise_prediction_rmse": stability,
            "runs": diagnostics,
            "mcmc_comparison": "P08 exact latent small-condition GPU NUTS qualification",
        },
        "gates": gates,
    }
    publish_json(output / "qualification_summary.json", result)
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
