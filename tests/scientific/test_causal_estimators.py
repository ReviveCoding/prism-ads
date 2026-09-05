from __future__ import annotations

import numpy as np

from prism_ads.causal.estimators import (
    cross_fitted_doubly_robust,
    empirical_bayes,
    private_aggregate_difference,
    randomized_difference,
    regression_adjusted,
)


def randomized_fixture() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(7)
    x = rng.normal(size=(4000, 3))
    treatment = rng.binomial(1, 0.5, size=4000).astype(float)
    y = 0.4 * x[:, 0] - 0.2 * x[:, 1] + 0.3 * treatment + rng.normal(0, 0.2, 4000)
    return y, treatment, x


def test_randomized_references_recover_effect() -> None:
    y, treatment, x = randomized_fixture()
    assert abs(randomized_difference(y, treatment).value - 0.3) < 0.04
    assert abs(regression_adjusted(y, treatment, x).value - 0.3) < 0.02
    assert abs(cross_fitted_doubly_robust(y, treatment, x, 0.5).value - 0.3) < 0.02


def test_aggregate_difference_and_privacy_variance() -> None:
    effect, variance = private_aggregate_difference(
        np.array([30.0]), np.array([100.0]), np.array([10.0]), np.array([100.0]), 4.0, 4.0
    )
    assert np.isclose(effect[0], 0.2)
    assert variance[0] > 0


def test_empirical_bayes_pools_noisy_groups() -> None:
    effects = np.array([-0.5, 0.1, 0.2, 0.9])
    variances = np.full(4, 0.2)
    pooled, hyperparameters = empirical_bayes(effects, variances)
    assert np.var(pooled) < np.var(effects)
    assert hyperparameters["tau2"] > 0
