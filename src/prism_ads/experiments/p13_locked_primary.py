# mypy: disable-error-code="no-untyped-call"
"""Immutable P13 locked-primary execution for the frozen PRISM protocol."""

from __future__ import annotations

import argparse
import json
import os
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]
import pyro
import torch
from pyro.infer import SVI, Predictive, Trace_ELBO
from pyro.infer.autoguide import AutoNormal
from pyro.optim import ClippedAdam

from prism_ads.causal.estimators import empirical_bayes, private_aggregate_difference
from prism_ads.experiments.p10_development import _aggregate_query, _arrays, _release, _truth
from prism_ads.experiments.t3_generator import publish_json, sha256_file, utc_now
from prism_ads.governance.freeze import verify_freeze_manifest
from prism_ads.models.prism_hb import prism_hb_rate_model
from prism_ads.privacy.engine import account_gaussian, calibrate_gaussian, l2_sensitivity
from prism_ads.warehouse.preprocess import configure

FREEZE_ID = "prism-ads-v2.2-20260904-8d98593fabdf-r2"
REPLICATES = 10
SEEDS_PER_REPLICATE = 3
SVI_STEPS = 1000
POSTERIOR_DRAWS = 500
EPSILON = 1.0
DELTA = 1e-7
EFFECT_SCALE = 0.05


def _fit(
    released: dict[str, np.ndarray], sigma: float, seed: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    device = torch.device("cuda")
    _, campaign = np.unique(released["campaign"], return_inverse=True)
    _, segment = np.unique(released["segment"], return_inverse=True)

    def tensor(name: str) -> torch.Tensor:
        return torch.as_tensor(released[name], dtype=torch.float32, device=device)

    args = (
        tensor("n0"),
        tensor("n1"),
        tensor("y0"),
        tensor("y1"),
        torch.as_tensor(campaign, device=device),
        torch.as_tensor(segment, device=device),
        int(campaign.max() + 1),
        int(segment.max() + 1),
        torch.tensor(sigma, dtype=torch.float32, device=device),
        True,
        True,
        True,
        True,
        EFFECT_SCALE,
    )
    pyro.clear_param_store()
    pyro.set_rng_seed(seed)
    guide = AutoNormal(prism_hb_rate_model)
    svi = SVI(prism_hb_rate_model, guide, ClippedAdam({"lr": 0.025}), Trace_ELBO())
    torch.cuda.reset_peak_memory_stats()
    started = time.perf_counter()
    losses = [float(svi.step(*args)) for _ in range(SVI_STEPS)]
    samples = (
        Predictive(
            prism_hb_rate_model,
            guide=guide,
            num_samples=POSTERIOR_DRAWS,
            return_sites=("effect",),
        )(*args)["effect"]
        .detach()
        .cpu()
        .numpy()
    )
    torch.cuda.synchronize()
    diagnostics = {
        "seed": seed,
        "initial_loss": losses[0],
        "final_loss": losses[-1],
        "finite_loss": bool(np.isfinite(losses).all()),
        "runtime_seconds": time.perf_counter() - started,
        "peak_vram_allocated_bytes": int(torch.cuda.max_memory_allocated()),
        "peak_vram_reserved_bytes": int(torch.cuda.max_memory_reserved()),
    }
    return (
        samples.mean(axis=0),
        np.quantile(samples, 0.025, axis=0),
        np.quantile(samples, 0.975, axis=0),
        diagnostics,
    )


def _publish_table(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    pq.write_table(pa.Table.from_pylist(rows), temporary, compression="zstd")
    os.replace(temporary, path)
    path.chmod(0o444)


def _score(rows: list[dict[str, Any]], truth_map: dict[tuple[int, int], float]) -> dict[str, Any]:
    truth = np.asarray([truth_map[(r["campaign"], r["segment"])] for r in rows])
    units = np.asarray([r["units"] for r in rows])
    output: dict[str, Any] = {}
    for model in ("B3", "PRISM"):
        estimate = np.asarray([r[f"{model}_estimate"] for r in rows])
        lower = np.asarray([r[f"{model}_lower"] for r in rows])
        upper = np.asarray([r[f"{model}_upper"] for r in rows])
        error = estimate - truth
        output[model] = {
            "weighted_rmse": float(np.sqrt(np.sum(units * error**2) / np.sum(units))),
            "macro_rmse": float(np.sqrt(np.mean(error**2))),
            "mae": float(np.mean(np.abs(error))),
            "bias": float(np.average(error, weights=units)),
            "interval_coverage": float(np.mean((lower <= truth) & (truth <= upper))),
            "mean_interval_width": float(np.mean(upper - lower)),
        }
    return output


def _bootstrap(
    replicate_rows: list[list[dict[str, Any]]],
    truth_map: dict[tuple[int, int], float],
) -> dict[str, Any]:
    campaigns = np.unique([row["campaign"] for row in replicate_rows[0]])
    generator = np.random.default_rng(2026091500)
    differences = []
    for _ in range(1000):
        sampled = generator.choice(campaigns, size=campaigns.size, replace=True)
        multiplicity = {int(c): int(np.sum(sampled == c)) for c in np.unique(sampled)}
        replicate_differences = []
        for rows in replicate_rows:
            chosen = [row for row in rows if row["campaign"] in multiplicity]
            truth = np.asarray([truth_map[(r["campaign"], r["segment"])] for r in chosen])
            weight = np.asarray([r["units"] * multiplicity[r["campaign"]] for r in chosen])
            losses = []
            for model in ("B3", "PRISM"):
                estimate = np.asarray([r[f"{model}_estimate"] for r in chosen])
                losses.append(
                    float(np.sqrt(np.sum(weight * (estimate - truth) ** 2) / np.sum(weight)))
                )
            replicate_differences.append(losses[0] - losses[1])
        differences.append(float(np.mean(replicate_differences)))
    return {
        "method": "1000 campaign-cluster bootstraps nesting 10 privacy replicates",
        "mean_difference": float(np.mean(differences)),
        "median_difference": float(np.median(differences)),
        "lower_95": float(np.quantile(differences, 0.025)),
        "upper_95": float(np.quantile(differences, 0.975)),
    }


def run(root: Path) -> dict[str, Any]:
    root = root.resolve()
    locked = root / "artifacts" / "locked" / FREEZE_ID
    locked.mkdir(parents=True, exist_ok=True)
    integrity_before = verify_freeze_manifest(
        root, root / "artifacts" / "qualification" / "P12" / "freeze_manifest_v2.json"
    )
    if integrity_before["status"] != "PASS":
        raise RuntimeError(f"freeze integrity failed: {integrity_before['errors']}")
    observations = root / "data" / "validated" / "t3_observations.parquet"
    truth_path = (
        root
        / "artifacts"
        / "qualification"
        / "P05"
        / "sealed_truth"
        / "t3_campaign_segment_truth.parquet"
    )
    sensitivity = l2_sensitivity(3, 2)
    sigma = calibrate_gaussian(EPSILON, DELTA, sensitivity)
    connection = duckdb.connect()
    configure(connection, root)
    try:
        raw = _arrays(
            connection,
            _aggregate_query(observations, "outcome_R2").replace(
                "role='method_validation'", "role='locked_final'"
            ),
        )
        all_rows: list[list[dict[str, Any]]] = []
        all_diagnostics: list[dict[str, Any]] = []
        for replicate in range(REPLICATES):
            path = locked / f"replicate_{replicate:02d}_pretruth.parquet"
            diagnostic_path = locked / f"replicate_{replicate:02d}_diagnostics.json"
            if path.is_file() and diagnostic_path.is_file():
                all_rows.append(pq.read_table(path).to_pylist())
                all_diagnostics.append(json.loads(diagnostic_path.read_text(encoding="utf-8")))
                continue
            released = _release(raw, sigma, 2026091300 + replicate)
            effects, variances = private_aggregate_difference(
                released["y1"],
                released["n1"],
                released["y0"],
                released["n0"],
                sigma**2,
                sigma**2,
            )
            baseline, hyper = empirical_bayes(effects, variances)
            baseline_var = 1 / (1 / variances + 1 / hyper["tau2"])
            fits = [
                _fit(released, sigma, 2026091400 + replicate * 10 + index)
                for index in range(SEEDS_PER_REPLICATE)
            ]
            prism = np.median(np.stack([fit[0] for fit in fits]), axis=0)
            lower = np.min(np.stack([fit[1] for fit in fits]), axis=0)
            upper = np.max(np.stack([fit[2] for fit in fits]), axis=0)
            rows = [
                {
                    "replicate": replicate,
                    "campaign": int(released["campaign"][i]),
                    "segment": int(released["segment"][i]),
                    "units": float(released["units"][i]),
                    "B3_estimate": float(baseline[i]),
                    "B3_lower": float(baseline[i] - 1.9599639845 * np.sqrt(baseline_var[i])),
                    "B3_upper": float(baseline[i] + 1.9599639845 * np.sqrt(baseline_var[i])),
                    "PRISM_estimate": float(prism[i]),
                    "PRISM_lower": float(lower[i]),
                    "PRISM_upper": float(upper[i]),
                }
                for i in range(raw["campaign"].size)
            ]
            diagnostics = {
                "replicate": replicate,
                "privacy_seed": 2026091300 + replicate,
                "fits": [fit[3] for fit in fits],
                "seed_stability_rmse": float(
                    max(
                        np.sqrt(np.mean((fits[a][0] - fits[b][0]) ** 2))
                        for a, b in ((0, 1), (0, 2), (1, 2))
                    )
                ),
            }
            _publish_table(path, rows)
            publish_json(diagnostic_path, diagnostics)
            all_rows.append(rows)
            all_diagnostics.append(diagnostics)
        predictions = locked / "primary_predictions_pretruth.parquet"
        if not predictions.is_file():
            _publish_table(predictions, [row for rows in all_rows for row in rows])
        prediction_identity = {
            "path": str(predictions.relative_to(root)).replace("\\", "/"),
            "sha256": sha256_file(predictions),
            "bytes": predictions.stat().st_size,
            "status": "frozen_before_truth_scoring",
        }
        truth_map = _truth(connection, truth_path, "R2")
        scores = [_score(rows, truth_map) for rows in all_rows]
        bootstrap = _bootstrap(all_rows, truth_map)
    finally:
        connection.close()
    baseline_rmse = float(np.mean([score["B3"]["weighted_rmse"] for score in scores]))
    prism_rmse = float(np.mean([score["PRISM"]["weighted_rmse"] for score in scores]))
    result = {
        "phase": "P13",
        "created_at": utc_now(),
        "status": "PASS",
        "freeze_id": FREEZE_ID,
        "integrity_before": integrity_before,
        "integrity_after": verify_freeze_manifest(
            root, root / "artifacts" / "qualification" / "P12" / "freeze_manifest_v2.json"
        ),
        "privacy": {
            "epsilon": EPSILON,
            "delta": DELTA,
            "sigma": sigma,
            "accounting": account_gaussian(sigma, sensitivity, DELTA),
        },
        "predictions": prediction_identity,
        "replicate_scores": scores,
        "primary": {
            "B3_weighted_rmse": baseline_rmse,
            "PRISM_weighted_rmse": prism_rmse,
            "absolute_difference": baseline_rmse - prism_rmse,
            "relative_improvement": (baseline_rmse - prism_rmse) / baseline_rmse,
            "paired_uncertainty": bootstrap,
        },
        "inference_health": all_diagnostics,
    }
    publish_json(locked / "primary_results.json", result)
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
