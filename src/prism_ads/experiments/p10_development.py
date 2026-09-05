# mypy: disable-error-code="no-untyped-call"
"""Development-only private baseline selection, PRISM ablation, and falsification."""

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
from prism_ads.experiments.t3_generator import publish_json, relation, sha256_file, utc_now
from prism_ads.models.prism_hb import prism_hb_rate_model
from prism_ads.privacy.engine import (
    account_gaussian,
    calibrate_gaussian,
    gaussian_release,
    l2_sensitivity,
)
from prism_ads.warehouse.preprocess import configure

EPSILONS = (0.25, 0.5, 1.0, 2.0, 4.0, 8.0)
DELTA = 1e-6
MAX_CAMPAIGNS = 3
SEED = 2026090410
SVI_STEPS = 300
POSTERIOR_DRAWS = 160
EFFECT_SCALE_PRIOR = 0.05


def _atomic_parquet(table: pa.Table, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    pq.write_table(table, temporary, compression="zstd")
    os.replace(temporary, path)
    path.chmod(0o444)


def _aggregate_query(observations: Path, outcome: str, treatment: str = "treatment") -> str:
    return (
        "WITH ranked AS (SELECT *, row_number() OVER (PARTITION BY uid ORDER BY campaign, "
        "unit_id) AS campaign_rank FROM "
        f"{relation(observations)} WHERE role='method_validation'), bounded AS (SELECT * FROM "
        f"ranked WHERE campaign_rank <= {MAX_CAMPAIGNS}) SELECT campaign, segment, "
        "count(*)::DOUBLE AS units, "
        f"sum(1-({treatment}))::DOUBLE AS n0, sum({treatment})::DOUBLE AS n1, "
        f"sum((1-({treatment}))*({outcome}))::DOUBLE AS y0, "
        f"sum(({treatment})*({outcome}))::DOUBLE AS y1 FROM bounded "
        "GROUP BY campaign, segment HAVING n0 > 0 AND n1 > 0 ORDER BY campaign, segment"
    )


def _arrays(connection: duckdb.DuckDBPyConnection, query: str) -> dict[str, np.ndarray]:
    return {key: np.asarray(value) for key, value in connection.execute(query).fetchnumpy().items()}


def _release(raw: dict[str, np.ndarray], sigma: float, seed: int) -> dict[str, np.ndarray]:
    values = np.column_stack([raw[name] for name in ("n0", "n1", "y0", "y1")])
    noisy = gaussian_release(values, sigma, seed)
    return {
        **{name: raw[name] for name in ("campaign", "segment", "units")},
        **{name: noisy[:, index] for index, name in enumerate(("n0", "n1", "y0", "y1"))},
    }


def _baseline(released: dict[str, np.ndarray], sigma: float) -> dict[str, np.ndarray]:
    effects, variances = private_aggregate_difference(
        released["y1"], released["n1"], released["y0"], released["n0"], sigma**2, sigma**2
    )
    pooled, _ = empirical_bayes(effects, variances)
    return {"B1": effects, "B2": effects, "B3": pooled}


def _indices(released: dict[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray, int, int]:
    _, campaign = np.unique(released["campaign"], return_inverse=True)
    _, segment = np.unique(released["segment"], return_inverse=True)
    return campaign, segment, int(campaign.max() + 1), int(segment.max() + 1)


def _fit_prism(
    released: dict[str, np.ndarray],
    sigma: float,
    flags: tuple[bool, bool, bool, bool],
    seed: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    if not torch.cuda.is_available():
        raise RuntimeError("P10 requires the qualified CUDA backend")
    device = torch.device("cuda")
    campaign, segment, campaign_count, segment_count = _indices(released)

    def tensor(value: np.ndarray) -> torch.Tensor:
        return torch.as_tensor(value, dtype=torch.float32, device=device)

    args = (
        tensor(released["n0"]),
        tensor(released["n1"]),
        tensor(released["y0"]),
        tensor(released["y1"]),
        torch.as_tensor(campaign, device=device),
        torch.as_tensor(segment, device=device),
        campaign_count,
        segment_count,
        torch.tensor(sigma, dtype=torch.float32, device=device),
        *flags,
        EFFECT_SCALE_PRIOR,
    )
    pyro.clear_param_store()
    pyro.set_rng_seed(seed)
    guide = AutoNormal(prism_hb_rate_model)
    svi = SVI(prism_hb_rate_model, guide, ClippedAdam({"lr": 0.025}), Trace_ELBO())
    torch.cuda.reset_peak_memory_stats()
    started = time.perf_counter()
    losses = [float(svi.step(*args)) for _ in range(SVI_STEPS)]
    samples = Predictive(
        prism_hb_rate_model,
        guide=guide,
        num_samples=POSTERIOR_DRAWS,
        return_sites=("effect",),
    )(*args)["effect"]
    torch.cuda.synchronize()
    runtime = time.perf_counter() - started
    effects = samples.detach().cpu().numpy()
    diagnostics = {
        "backend": f"Pyro {pyro.__version__} / PyTorch {torch.__version__}",
        "device": torch.cuda.get_device_name(0),
        "svi_steps": SVI_STEPS,
        "posterior_draws": POSTERIOR_DRAWS,
        "initial_loss": losses[0],
        "final_loss": losses[-1],
        "finite_loss": bool(np.isfinite(losses).all()),
        "runtime_seconds": runtime,
        "peak_vram_allocated_bytes": int(torch.cuda.max_memory_allocated()),
        "peak_vram_reserved_bytes": int(torch.cuda.max_memory_reserved()),
    }
    return (
        effects.mean(axis=0),
        np.quantile(effects, 0.025, axis=0),
        np.quantile(effects, 0.975, axis=0),
        diagnostics,
    )


def _metrics(estimate: np.ndarray, truth: np.ndarray, units: np.ndarray) -> dict[str, float]:
    error = estimate - truth
    return {
        "weighted_rmse": float(np.sqrt(np.sum(units * error**2) / np.sum(units))),
        "macro_rmse": float(np.sqrt(np.mean(error**2))),
        "mae": float(np.mean(np.abs(error))),
        "bias": float(np.average(error, weights=units)),
    }


def _truth(
    connection: duckdb.DuckDBPyConnection, path: Path, regime: str
) -> dict[tuple[int, int], float]:
    rows = connection.execute(
        f"SELECT campaign, segment, true_ate FROM {relation(path)} WHERE effect_regime='{regime}'"
    ).fetchall()
    return {(int(c), int(s)): float(value) for c, s, value in rows}


def run(root: Path) -> dict[str, Any]:
    root = root.resolve()
    output = root / "artifacts" / "development" / "P10"
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
    sigmas = {epsilon: calibrate_gaussian(epsilon, DELTA, sensitivity) for epsilon in EPSILONS}
    connection = duckdb.connect()
    configure(connection, root)
    try:
        raw_r2 = _arrays(connection, _aggregate_query(observations, "outcome_R2"))
        release_by_epsilon = {
            epsilon: _release(raw_r2, sigma, SEED + index)
            for index, (epsilon, sigma) in enumerate(sigmas.items())
        }
        prediction_rows: list[dict[str, Any]] = []
        gpu_runs: list[dict[str, Any]] = []
        full_flags = (True, True, True, True)
        for index, epsilon in enumerate(EPSILONS):
            released = release_by_epsilon[epsilon]
            for model, estimate in _baseline(released, sigmas[epsilon]).items():
                for row, value in enumerate(estimate):
                    prediction_rows.append(
                        {
                            "epsilon": epsilon,
                            "model": model,
                            "campaign": int(released["campaign"][row]),
                            "segment": int(released["segment"][row]),
                            "units": float(released["units"][row]),
                            "estimate": float(value),
                            "lower": None,
                            "upper": None,
                        }
                    )
            mean, lower, upper, diag = _fit_prism(
                released, sigmas[epsilon], full_flags, SEED + 100 + index
            )
            diag.update({"purpose": "epsilon_feasibility", "epsilon": epsilon, "model": "C4"})
            gpu_runs.append(diag)
            for row, value in enumerate(mean):
                prediction_rows.append(
                    {
                        "epsilon": epsilon,
                        "model": "C4",
                        "campaign": int(released["campaign"][row]),
                        "segment": int(released["segment"][row]),
                        "units": float(released["units"][row]),
                        "estimate": float(value),
                        "lower": float(lower[row]),
                        "upper": float(upper[row]),
                    }
                )

        ablation_flags = {
            "C1": (True, False, False, False),
            "C2": (True, True, False, False),
            "C3": (True, True, True, False),
        }
        released_primary = release_by_epsilon[1.0]
        for index, (model, flags) in enumerate(ablation_flags.items()):
            mean, lower, upper, diag = _fit_prism(
                released_primary, sigmas[1.0], flags, SEED + 200 + index
            )
            diag.update({"purpose": "ablation", "epsilon": 1.0, "model": model})
            gpu_runs.append(diag)
            for row, value in enumerate(mean):
                prediction_rows.append(
                    {
                        "epsilon": 1.0,
                        "model": model,
                        "campaign": int(released_primary["campaign"][row]),
                        "segment": int(released_primary["segment"][row]),
                        "units": float(released_primary["units"][row]),
                        "estimate": float(value),
                        "lower": float(lower[row]),
                        "upper": float(upper[row]),
                    }
                )

        table = pa.Table.from_pylist(prediction_rows)
        predictions_path = output / "private_predictions_pretruth_v3.parquet"
        _atomic_parquet(table, predictions_path)
        prediction_identity = {
            "path": str(predictions_path.relative_to(root)).replace("\\", "/"),
            "sha256": sha256_file(predictions_path),
            "bytes": predictions_path.stat().st_size,
            "status": "frozen_before_truth_scoring",
        }

        # Truth is deliberately opened only after all selection/ablation predictions are immutable.
        truth = _truth(connection, truth_path, "R2")
        scores: dict[str, dict[str, float]] = {}
        for epsilon in EPSILONS:
            for model in ("B1", "B2", "B3", "C4"):
                subset = [
                    row
                    for row in prediction_rows
                    if row["epsilon"] == epsilon and row["model"] == model
                ]
                estimates = np.asarray([row["estimate"] for row in subset])
                truths = np.asarray([truth[(row["campaign"], row["segment"])] for row in subset])
                units = np.asarray([row["units"] for row in subset])
                scores[f"{model}@{epsilon:g}"] = _metrics(estimates, truths, units)
        for model in ablation_flags:
            subset = [
                row for row in prediction_rows if row["epsilon"] == 1.0 and row["model"] == model
            ]
            scores[f"{model}@1"] = _metrics(
                np.asarray([row["estimate"] for row in subset]),
                np.asarray([truth[(row["campaign"], row["segment"])] for row in subset]),
                np.asarray([row["units"] for row in subset]),
            )
        baseline_means = {
            model: float(
                np.mean([scores[f"{model}@{epsilon:g}"]["weighted_rmse"] for epsilon in EPSILONS])
            )
            for model in ("B1", "B2", "B3")
        }
        selected_baseline = min(baseline_means, key=baseline_means.get)  # type: ignore[arg-type]

        # Mandatory development falsification, each using a distinct matched private release.
        falsification_specs = {
            "F0_known_null_R0": ("outcome_R0", "treatment"),
            "F1_treatment_permutation": (
                "outcome_R2",
                "CASE WHEN md5_number_lower('p10-permute:' || uid::VARCHAR) "
                "% 2 = 0 THEN 1 ELSE 0 END",
            ),
            "F2_negative_control": (
                "CASE WHEN md5_number_lower('p10-negative:' || uid::VARCHAR) "
                "% 20 = 0 THEN 1 ELSE 0 END",
                "treatment",
            ),
            "F3_privacy_noise_only": ("PRIVACY_ONLY_R0", "treatment"),
        }
        falsification: dict[str, Any] = {}
        for index, (name, (outcome, treatment)) in enumerate(falsification_specs.items()):
            if outcome == "PRIVACY_ONLY_R0":
                raw = _arrays(connection, _aggregate_query(observations, "outcome_R0", treatment))
                pooled_rate = (raw["y0"] + raw["y1"]) / (raw["n0"] + raw["n1"])
                raw["y0"] = raw["n0"] * pooled_rate
                raw["y1"] = raw["n1"] * pooled_rate
            else:
                raw = _arrays(connection, _aggregate_query(observations, outcome, treatment))
            released = _release(raw, sigmas[1.0], SEED + 500 + index)
            mean, lower, upper, diag = _fit_prism(
                released, sigmas[1.0], full_flags, SEED + 600 + index
            )
            gpu_runs.append({**diag, "purpose": "falsification", "model": name, "epsilon": 1.0})
            weighted_mean = float(np.average(mean, weights=released["units"]))
            false_discovery = float(np.mean((lower > 0) | (upper < 0)))
            passed = abs(weighted_mean) <= 0.01 and false_discovery <= 0.10
            falsification[name] = {
                "weighted_mean_effect": weighted_mean,
                "interval_false_discovery_rate": false_discovery,
                "limits": {"absolute_weighted_mean": 0.01, "false_discovery_rate": 0.10},
                "status": "PASS" if passed else "FAIL",
            }
    finally:
        connection.close()

    accounting = {
        str(epsilon): account_gaussian(sigma, sensitivity, DELTA)
        for epsilon, sigma in sigmas.items()
    }
    status = (
        "PASS"
        if all(value["status"] == "PASS" for value in falsification.values())
        and all(run["finite_loss"] for run in gpu_runs)
        else "FAIL"
    )
    result = {
        "phase": "P10",
        "created_at": utc_now(),
        "status": status,
        "development_role": "method_validation",
        "effect_regime": "R2",
        "baseline_selection": {
            "eligible": ["B1", "B2", "B3"],
            "prespecified_metric": (
                "mean population-weighted RMSE across the full epsilon feasibility grid"
            ),
            "metric_values": baseline_means,
            "selected": selected_baseline,
        },
        "privacy": {
            "neighboring_relation": "user-level add/remove-one",
            "epsilon_grid": list(EPSILONS),
            "delta": DELTA,
            "max_groups_per_user": MAX_CAMPAIGNS,
            "l2_sensitivity": sensitivity,
            "noise_scales": sigmas,
            "accounting": accounting,
            "matched_release_seed_family": SEED,
        },
        "predictions": prediction_identity,
        "scores": scores,
        "falsification": falsification,
        "ablation_order": {
            "C0": selected_baseline,
            "C1": "+campaign response hierarchy",
            "C2": "+segment response hierarchy",
            "C3": "+explicit numerator/denominator privacy likelihood",
            "C4": "+treatment-effect hierarchy (full PRISM-HB)",
        },
        "candidate_tuning": {
            "effect_scale_prior": EFFECT_SCALE_PRIOR,
            "basis": (
                "development falsification response to preserved v1 interval "
                "overconfidence; no locked or qualification outcomes used"
            ),
            "negative_evidence": [
                "artifacts/development/P10/method_selection.json",
                "artifacts/development/P10/method_selection_v2.json",
            ],
            "f3_definition": (
                "group base rates fixed from R0, zero treatment effect and zero sampling "
                "variation, then DP noise added; tests privacy-noise-only discoveries"
            ),
        },
        "gpu_runs": gpu_runs,
    }
    publish_json(output / "method_selection_v3.json", result)
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
