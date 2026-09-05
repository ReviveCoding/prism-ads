"""Numerically explicit causal references and aggregate-only baseline ladder."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from sklearn.linear_model import Ridge  # type: ignore[import-untyped]
from sklearn.model_selection import KFold  # type: ignore[import-untyped]

FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class Estimate:
    value: float
    standard_error: float
    lower_95: float
    upper_95: float


def _estimate(value: float, standard_error: float) -> Estimate:
    return Estimate(
        value=value,
        standard_error=standard_error,
        lower_95=value - 1.959963984540054 * standard_error,
        upper_95=value + 1.959963984540054 * standard_error,
    )


def _vectors(y: FloatArray, treatment: FloatArray) -> tuple[FloatArray, FloatArray]:
    y = np.asarray(y, dtype=np.float64).reshape(-1)
    treatment = np.asarray(treatment, dtype=np.float64).reshape(-1)
    if y.shape != treatment.shape or y.size < 4:
        raise ValueError("outcome and treatment must have the same length >= 4")
    if not np.all(np.isin(treatment, (0.0, 1.0))):
        raise ValueError("treatment must be binary")
    if treatment.sum() == 0 or treatment.sum() == treatment.size:
        raise ValueError("both treatment arms are required")
    return y, treatment


def randomized_difference(y: FloatArray, treatment: FloatArray) -> Estimate:
    """NR0: randomized difference in arm means with an unpooled standard error."""
    y, treatment = _vectors(y, treatment)
    treated = y[treatment == 1]
    control = y[treatment == 0]
    value = float(treated.mean() - control.mean())
    variance = treated.var(ddof=1) / treated.size + control.var(ddof=1) / control.size
    return _estimate(value, float(np.sqrt(variance)))


def regression_adjusted(
    y: FloatArray, treatment: FloatArray, features: FloatArray
) -> Estimate:
    """NR1: Lin-style interacted OLS adjustment with HC1 robust uncertainty."""
    y, treatment = _vectors(y, treatment)
    x = np.asarray(features, dtype=np.float64)
    if x.ndim != 2 or x.shape[0] != y.size:
        raise ValueError("features must be a two-dimensional row-aligned matrix")
    centered = x - x.mean(axis=0)
    design = np.column_stack(
        (np.ones(y.size), treatment, centered, centered * treatment[:, None])
    )
    coefficients = np.linalg.lstsq(design, y, rcond=None)[0]
    residual = y - design @ coefficients
    bread = np.linalg.pinv(design.T @ design)
    score = design * residual[:, None]
    covariance = bread @ (score.T @ score) @ bread
    covariance *= y.size / max(y.size - design.shape[1], 1)
    return _estimate(float(coefficients[1]), float(np.sqrt(max(covariance[1, 1], 0.0))))


def cross_fitted_doubly_robust(
    y: FloatArray,
    treatment: FloatArray,
    features: FloatArray,
    propensity: float,
    folds: int = 5,
    seed: int = 20260904,
) -> Estimate:
    """NR2: cross-fitted AIPW estimator using the known randomized propensity."""
    y, treatment = _vectors(y, treatment)
    x = np.asarray(features, dtype=np.float64)
    if x.ndim != 2 or x.shape[0] != y.size:
        raise ValueError("features must be a two-dimensional row-aligned matrix")
    if not 0 < propensity < 1:
        raise ValueError("propensity must be strictly between zero and one")
    m0 = np.empty(y.size, dtype=np.float64)
    m1 = np.empty(y.size, dtype=np.float64)
    splitter = KFold(n_splits=folds, shuffle=True, random_state=seed)
    for train, test in splitter.split(x):
        for arm, target in ((0, m0), (1, m1)):
            arm_train = train[treatment[train] == arm]
            if arm_train.size < 2:
                raise ValueError("each training fold must contain both treatment arms")
            model = Ridge(alpha=1.0)
            model.fit(x[arm_train], y[arm_train])
            target[test] = model.predict(x[test])
    influence = (
        m1
        - m0
        + treatment * (y - m1) / propensity
        - (1.0 - treatment) * (y - m0) / (1.0 - propensity)
    )
    value = float(influence.mean())
    standard_error = float(influence.std(ddof=1) / np.sqrt(influence.size))
    return _estimate(value, standard_error)


def private_aggregate_difference(
    noisy_success_treated: FloatArray,
    noisy_count_treated: FloatArray,
    noisy_success_control: FloatArray,
    noisy_count_control: FloatArray,
    success_noise_variance: float = 0.0,
    count_noise_variance: float = 0.0,
) -> tuple[FloatArray, FloatArray]:
    """B1/B2 point estimates and delta-method variances from aggregate releases only."""
    y1 = np.asarray(noisy_success_treated, dtype=np.float64)
    n1 = np.asarray(noisy_count_treated, dtype=np.float64)
    y0 = np.asarray(noisy_success_control, dtype=np.float64)
    n0 = np.asarray(noisy_count_control, dtype=np.float64)
    if not (y1.shape == n1.shape == y0.shape == n0.shape):
        raise ValueError("aggregate arrays must share a shape")
    safe_n1 = np.maximum(n1, 1.0)
    safe_n0 = np.maximum(n0, 1.0)
    p1 = np.clip(y1 / safe_n1, 0.0, 1.0)
    p0 = np.clip(y0 / safe_n0, 0.0, 1.0)
    effect = p1 - p0
    sampling = p1 * (1.0 - p1) / safe_n1 + p0 * (1.0 - p0) / safe_n0
    privacy = (
        success_noise_variance / safe_n1**2
        + success_noise_variance / safe_n0**2
        + count_noise_variance * y1**2 / safe_n1**4
        + count_noise_variance * y0**2 / safe_n0**4
    )
    return effect, np.maximum(sampling + privacy, 1e-12)


def empirical_bayes(
    effects: FloatArray, variances: FloatArray
) -> tuple[FloatArray, dict[str, float]]:
    """B3: point-hyperparameter normal-normal partial pooling with plug-in variance."""
    effects = np.asarray(effects, dtype=np.float64)
    variances = np.asarray(variances, dtype=np.float64)
    if effects.shape != variances.shape or effects.size < 2:
        raise ValueError("effects and variances must share a nontrivial shape")
    if np.any(variances <= 0):
        raise ValueError("variances must be positive")
    tau2 = max(float(np.var(effects, ddof=1) - np.mean(variances)), 1e-10)
    marginal_precision = 1.0 / (variances + tau2)
    mu = float(np.sum(marginal_precision * effects) / np.sum(marginal_precision))
    posterior_variance = 1.0 / (1.0 / variances + 1.0 / tau2)
    posterior_mean = posterior_variance * (effects / variances + mu / tau2)
    return posterior_mean, {"mu": mu, "tau2": tau2}
