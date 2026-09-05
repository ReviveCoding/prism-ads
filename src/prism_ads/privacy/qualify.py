"""Create P07 mechanism/accounting evidence without selecting the primary epsilon."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from prism_ads.experiments.t3_generator import publish_json, utc_now
from prism_ads.privacy.engine import (
    NEIGHBORING_RELATION,
    ContributionLimits,
    account_gaussian,
    calibrate_gaussian,
    gaussian_release,
    l2_sensitivity,
    threshold_release,
)


def run(root: Path) -> dict[str, object]:
    root = root.resolve()
    limits = ContributionLimits(4, 10, 20, 4, 1)
    sensitivity = l2_sensitivity(limits.max_campaigns_per_user, 2)
    epsilon = 1.0
    delta = 1e-6
    sigma = calibrate_gaussian(epsilon, delta, sensitivity)
    accounting = account_gaussian(sigma, sensitivity, delta)
    vector = np.array([[100.0, 5.0], [80.0, 2.0], [12.0, 1.0]])
    release = gaussian_release(vector, sigma, seed=2026090407)
    thresholds = {
        str(k): int(threshold_release(np.array([100, 80, 12]), k).sum())
        for k in (10, 20, 50, 100)
    }
    release_record = {
        "phase": "P07",
        "created_at": utc_now(),
        "status": "QUALIFICATION_ONLY_NOT_PRIMARY",
        "neighboring_relation": NEIGHBORING_RELATION,
        "epsilon": epsilon,
        "delta": delta,
        "sensitivity": sensitivity,
        "contribution_limits": limits.__dict__,
        "mechanism": "analytic Gaussian vector mechanism",
        "noise_standard_deviation": sigma,
        "composition": "single vector release",
        "release_schema": ["bounded_user_count", "bounded_binary_success_count"],
        "input_vector": vector.tolist(),
        "released_vector": release.tolist(),
        "seed": 2026090407,
    }
    accounting_record = {
        **accounting,
        "declared_epsilon": epsilon,
        "verification": "PASS" if accounting["epsilon"] <= epsilon else "FAIL",
        "calibration": "exact analytic Gaussian; independently checked by pessimistic PLD",
    }
    result: dict[str, object] = {
        "status": "PASS" if accounting_record["verification"] == "PASS" else "FAIL",
        "privacy_release": release_record,
        "privacy_accounting": accounting_record,
        "threshold_released_cells": thresholds,
    }
    output = root / "artifacts" / "qualification" / "P07"
    publish_json(output / "privacy_release.json", release_record)
    publish_json(output / "privacy_accounting.json", accounting_record)
    publish_json(output / "qualification.json", result)
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
