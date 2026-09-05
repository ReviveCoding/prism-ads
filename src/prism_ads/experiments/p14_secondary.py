# mypy: disable-error-code="no-untyped-call"
"""Prespecified locked secondary evidence; cannot alter the primary verdict."""

from __future__ import annotations

import argparse
import json
import math
import os
import time
from collections import Counter, defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

import duckdb
import numpy as np
import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]
import pyro
import torch
from pyro.infer import SVI, Predictive, Trace_ELBO
from pyro.infer.autoguide import AutoNormal
from pyro.optim import ClippedAdam
from scipy.stats import kendalltau, spearmanr  # type: ignore[import-untyped]

from prism_ads.attribution.methods import Touch, attribute_path, markov_removal_effect
from prism_ads.causal.estimators import (
    cross_fitted_doubly_robust,
    empirical_bayes,
    private_aggregate_difference,
    randomized_difference,
    regression_adjusted,
)
from prism_ads.experiments.p10_development import _aggregate_query, _arrays, _release, _truth
from prism_ads.experiments.t3_generator import publish_json, relation, sha256_file, utc_now
from prism_ads.governance.freeze import verify_freeze_manifest
from prism_ads.models.prism_hb import prism_hb_rate_model
from prism_ads.privacy.engine import calibrate_gaussian, gaussian_release, l2_sensitivity
from prism_ads.warehouse.preprocess import configure

FREEZE_ID = "prism-ads-v2.2-20260904-8d98593fabdf-r2"
EPSILONS = (0.25, 0.5, 1.0, 2.0, 4.0, 8.0)
REGIMES = tuple(f"R{i}" for i in range(8))
DELTA = 1e-7


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
        0.05,
    )
    pyro.clear_param_store()
    pyro.set_rng_seed(seed)
    guide = AutoNormal(prism_hb_rate_model)
    svi = SVI(prism_hb_rate_model, guide, ClippedAdam({"lr": 0.025}), Trace_ELBO())
    started = time.perf_counter()
    losses = [float(svi.step(*args)) for _ in range(600)]
    samples = (
        Predictive(prism_hb_rate_model, guide=guide, num_samples=300, return_sites=("effect",))(
            *args
        )["effect"]
        .detach()
        .cpu()
        .numpy()
    )
    torch.cuda.synchronize()
    return (
        samples.mean(axis=0),
        np.quantile(samples, 0.025, axis=0),
        np.quantile(samples, 0.975, axis=0),
        {
            "seed": seed,
            "initial_loss": losses[0],
            "final_loss": losses[-1],
            "finite_loss": bool(np.isfinite(losses).all()),
            "runtime_seconds": time.perf_counter() - started,
        },
    )


def _publish_table(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    pq.write_table(pa.Table.from_pylist(rows), temporary, compression="zstd")
    os.replace(temporary, path)
    path.chmod(0o444)


def _t1(connection: duckdb.DuckDBPyConnection, path: Path) -> dict[str, Any]:
    arrays = connection.execute(
        "SELECT treatment, conversion, "
        + ",".join(f"f{i}" for i in range(12))
        + f" FROM {relation(path)} WHERE role='locked_final' AND row_id % 100=0 ORDER BY row_id"
    ).fetchnumpy()
    treatment = arrays.pop("treatment").astype(float)
    outcome = arrays.pop("conversion").astype(float)
    features = np.column_stack([arrays[f"f{i}"] for i in range(12)]).astype(float)
    estimators = {
        "NR0": randomized_difference(outcome, treatment),
        "NR1": regression_adjusted(outcome, treatment, features),
        "NR2": cross_fitted_doubly_robust(outcome, treatment, features, float(treatment.mean())),
    }
    return {"rows": int(outcome.size), **{key: value.__dict__ for key, value in estimators.items()}}


def _t2_attribution(connection: duckdb.DuckDBPyConnection, paths: Path) -> dict[str, Any]:
    source = connection.execute(
        f"SELECT campaigns,touch_timestamps,terminal_timestamp,converted FROM {relation(paths)} "
        "WHERE role='locked_final' AND md5_number_lower(uid::VARCHAR || ':' || path_key) % 500=0"
    ).fetchall()
    converted = [row for row in source if row[3] == 1]
    credits: defaultdict[tuple[str, int], float] = defaultdict(float)
    for campaigns, timestamps, terminal, _ in converted:
        touches = [
            Touch(int(c), int(t)) for c, t in zip(campaigns[:3], timestamps[:3], strict=True)
        ]
        for method in (
            "A0_last_click",
            "A1_first_click",
            "A2_linear",
            "A3_time_decay",
            "A4_position_based",
        ):
            for campaign, value in attribute_path(touches, method, int(terminal)).items():
                credits[(method, campaign)] += value
    frequency = Counter(int(c) for row in source for c in row[0][:3])
    top = {campaign for campaign, _ in frequency.most_common(20)}
    markov_paths = [
        ([int(c) if int(c) in top else -1 for c in row[0][:3]], bool(row[3])) for row in source
    ]
    if (
        markov_paths
        and any(value for _, value in markov_paths)
        and not all(value for _, value in markov_paths)
    ):
        for campaign, value in markov_removal_effect(markov_paths).items():
            credits[("A5_markov_removal", campaign)] = value * len(converted)
    sigma = calibrate_gaussian(1.0, DELTA, math.sqrt(3))
    metrics = {}
    for index, method in enumerate(sorted({key[0] for key in credits})):
        values = sorted(
            (campaign, value) for (name, campaign), value in credits.items() if name == method
        )
        reference = np.asarray([value for _, value in values])
        private = gaussian_release(reference, sigma, 2026091600 + index)
        k = min(10, reference.size)
        left = set(np.argpartition(reference, -k)[-k:])
        right = set(np.argpartition(private, -k)[-k:])
        metrics[method] = {
            "campaigns": int(reference.size),
            "spearman": float(spearmanr(reference, private).statistic),
            "kendall": float(kendalltau(reference, private).statistic),
            "top10_overlap": len(left & right) / k,
            "attribution_share_l1": float(
                np.sum(
                    np.abs(
                        reference / reference.sum()
                        - np.maximum(private, 0) / max(np.maximum(private, 0).sum(), 1e-12)
                    )
                )
            ),
        }
    return {
        "sample_paths": len(source),
        "conversion_paths": len(converted),
        "methods": metrics,
        "claim_boundary": "attribution credit is not causal incrementality",
    }


def run(root: Path) -> dict[str, Any]:
    root = root.resolve()
    locked = root / "artifacts" / "locked" / FREEZE_ID / "secondary"
    locked.mkdir(parents=True, exist_ok=True)
    integrity = verify_freeze_manifest(
        root, root / "artifacts" / "qualification" / "P12" / "freeze_manifest_v2.json"
    )
    if integrity["status"] != "PASS":
        raise RuntimeError("freeze integrity failure")
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
    connection = duckdb.connect()
    configure(connection, root)
    rows_all: list[dict[str, Any]] = []
    diagnostics = []
    try:
        t1 = _t1(connection, root / "data" / "validated" / "t1_uplift_roles.parquet")
        t2 = _t2_attribution(connection, root / "data" / "marts" / "t2_paths.parquet")
        for regime_index, regime in enumerate(REGIMES):
            raw = _arrays(
                connection,
                _aggregate_query(observations, f"outcome_{regime}").replace(
                    "role='method_validation'", "role='locked_final'"
                ),
            )
            for epsilon_index, epsilon in enumerate(EPSILONS):
                cell = locked / f"{regime}_eps{epsilon:g}_pretruth.parquet"
                diagnostic = locked / f"{regime}_eps{epsilon:g}_diagnostics.json"
                if cell.is_file() and diagnostic.is_file():
                    rows_all.extend(pq.read_table(cell).to_pylist())
                    diagnostics.append(json.loads(diagnostic.read_text(encoding="utf-8")))
                    continue
                sigma = calibrate_gaussian(epsilon, DELTA, sensitivity)
                released = _release(raw, sigma, 2026091700 + regime_index * 10 + epsilon_index)
                effects, variances = private_aggregate_difference(
                    released["y1"],
                    released["n1"],
                    released["y0"],
                    released["n0"],
                    sigma**2,
                    sigma**2,
                )
                baseline, _ = empirical_bayes(effects, variances)
                mean, lower, upper, diag = _fit(
                    released, sigma, 2026091800 + regime_index * 10 + epsilon_index
                )
                rows = [
                    {
                        "regime": regime,
                        "epsilon": epsilon,
                        "campaign": int(released["campaign"][i]),
                        "segment": int(released["segment"][i]),
                        "units": float(released["units"][i]),
                        "B3_estimate": float(baseline[i]),
                        "PRISM_estimate": float(mean[i]),
                        "PRISM_lower": float(lower[i]),
                        "PRISM_upper": float(upper[i]),
                    }
                    for i in range(raw["campaign"].size)
                ]
                _publish_table(cell, rows)
                publish_json(diagnostic, {"regime": regime, "epsilon": epsilon, **diag})
                rows_all.extend(rows)
                diagnostics.append({"regime": regime, "epsilon": epsilon, **diag})
        combined = locked / "epsilon_regime_predictions_pretruth.parquet"
        if not combined.is_file():
            _publish_table(combined, rows_all)
        scores = {}
        for regime in REGIMES:
            truth_map = _truth(connection, truth_path, regime)
            for epsilon in EPSILONS:
                rows = [
                    row for row in rows_all if row["regime"] == regime and row["epsilon"] == epsilon
                ]
                truth = np.asarray(
                    [truth_map[(cast(int, r["campaign"]), cast(int, r["segment"]))] for r in rows]
                )
                units = np.asarray([r["units"] for r in rows])
                cell_scores = {}
                for model in ("B3", "PRISM"):
                    estimate = np.asarray([r[f"{model}_estimate"] for r in rows])
                    cell_scores[model] = {
                        "weighted_rmse": float(
                            np.sqrt(np.sum(units * (estimate - truth) ** 2) / np.sum(units))
                        ),
                        "macro_rmse": float(np.sqrt(np.mean((estimate - truth) ** 2))),
                    }
                scores[f"{regime}@{epsilon:g}"] = cell_scores
        threshold = {
            str(k): {
                "released_groups": int(np.sum(raw["units"] >= k)),
                "released_unit_rate": float(
                    np.sum(raw["units"][raw["units"] >= k]) / np.sum(raw["units"])
                ),
            }
            for k in (10, 20, 50, 100)
        }
    finally:
        connection.close()
    result = {
        "phase": "P14",
        "created_at": utc_now(),
        "status": "PASS",
        "primary_verdict_immutable": "NON_PROMOTABLE",
        "freeze_integrity": integrity,
        "T1_randomized": t1,
        "T2_private_attribution": t2,
        "epsilon_regime_predictions": {
            "path": str(combined.relative_to(root)).replace("\\", "/"),
            "sha256": sha256_file(combined),
            "status": "frozen_before_truth_scoring",
        },
        "scores": scores,
        "threshold_study": threshold,
        "falsification": "P10 F0-F3 PASS; frozen evidence",
        "ablation": "P10 C0-C4; frozen evidence",
        "sensitivity": [
            "epsilon",
            "threshold",
            "contribution limits",
            "prior scale",
            "hierarchy",
            "segmentation",
            "decision budget",
            "attribution lookback",
        ],
        "diagnostics": diagnostics,
    }
    publish_json(locked / "secondary_results.json", result)
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
