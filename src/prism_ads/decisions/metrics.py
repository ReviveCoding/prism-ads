"""True T3 regret and public-data reference deviation."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]


def decision_regret(
    true_effect: FloatArray,
    estimated_effect: FloatArray,
    value_weight: FloatArray,
    selected_count: int,
) -> float:
    """Oracle value minus realized true value under an estimated fixed-budget ranking."""
    truth = np.asarray(true_effect, dtype=float)
    estimate = np.asarray(estimated_effect, dtype=float)
    weight = np.asarray(value_weight, dtype=float)
    if truth.shape != estimate.shape or truth.shape != weight.shape:
        raise ValueError("decision arrays must share a shape")
    if not 1 <= selected_count <= truth.size:
        raise ValueError("selected_count is outside the campaign set")
    true_value = truth * weight
    oracle = np.argpartition(true_value, -selected_count)[-selected_count:]
    chosen = np.argpartition(estimate * weight, -selected_count)[-selected_count:]
    return float(true_value[oracle].sum() - true_value[chosen].sum())


def reference_decision_deviation(reference: FloatArray, candidate: FloatArray, k: int) -> float:
    """One minus Top-K overlap for public-data reference comparisons."""
    reference = np.asarray(reference, dtype=float)
    candidate = np.asarray(candidate, dtype=float)
    if reference.shape != candidate.shape or not 1 <= k <= reference.size:
        raise ValueError("invalid reference-deviation inputs")
    reference_top = set(np.argpartition(reference, -k)[-k:].tolist())
    candidate_top = set(np.argpartition(candidate, -k)[-k:].tolist())
    return 1.0 - len(reference_top & candidate_top) / k
