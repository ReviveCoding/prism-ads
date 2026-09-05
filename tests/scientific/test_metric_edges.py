from __future__ import annotations

import numpy as np
import pytest

from prism_ads.attribution.methods import Touch, attribute_path, markov_removal_effect
from prism_ads.causal.estimators import (
    cross_fitted_doubly_robust,
    empirical_bayes,
    private_aggregate_difference,
    randomized_difference,
    regression_adjusted,
)
from prism_ads.decisions.metrics import decision_regret, reference_decision_deviation


def test_attribution_path_validation_and_short_position_cases() -> None:
    with pytest.raises(ValueError, match="at least one"):
        attribute_path([], "A0_last_click", 10)
    with pytest.raises(ValueError, match="after conversion"):
        attribute_path([Touch(1, 11)], "A0_last_click", 10)
    with pytest.raises(ValueError, match="half life"):
        attribute_path([Touch(1, 1)], "A3_time_decay", 10, 0)
    with pytest.raises(ValueError, match="unknown"):
        attribute_path([Touch(1, 1)], "unknown", 10)
    assert attribute_path([Touch(1, 1)], "A4_position_based", 10) == {1: 1.0}
    assert attribute_path([Touch(1, 1), Touch(2, 2)], "A4_position_based", 10) == {1: 0.5, 2: 0.5}
    assert attribute_path([Touch(1, 1), Touch(1, 2)], "A2_linear", 10) == {1: 1.0}


def test_markov_validation_and_zero_effect_fallback() -> None:
    for paths in ([], [([], True)], [([1], True)], [([1], False)]):
        with pytest.raises(ValueError, match="Markov"):
            markov_removal_effect(paths)
    result = markov_removal_effect([([1], True), ([2], False)])
    assert np.isclose(sum(result.values()), 1.0)


def test_decision_metrics_reject_shape_and_budget_errors() -> None:
    a = np.array([1.0, 2.0])
    with pytest.raises(ValueError, match="share a shape"):
        decision_regret(a, a[:1], a, 1)
    with pytest.raises(ValueError, match="outside"):
        decision_regret(a, a, a, 0)
    with pytest.raises(ValueError, match="invalid"):
        reference_decision_deviation(a, a[:1], 1)
    with pytest.raises(ValueError, match="invalid"):
        reference_decision_deviation(a, a, 3)


def test_causal_input_validation_edges() -> None:
    y = np.arange(6.0)
    with pytest.raises(ValueError, match="same length"):
        randomized_difference(y, np.ones(3))
    with pytest.raises(ValueError, match="binary"):
        randomized_difference(y, np.array([0, 1, 0, 1, 0, 2]))
    with pytest.raises(ValueError, match="both treatment arms"):
        randomized_difference(y, np.ones(6))
    treatment = np.array([0, 1, 0, 1, 0, 1], dtype=float)
    with pytest.raises(ValueError, match="row-aligned"):
        regression_adjusted(y, treatment, np.ones(6))
    with pytest.raises(ValueError, match="propensity"):
        cross_fitted_doubly_robust(y, treatment, np.ones((6, 1)), 1.0, folds=2)
    sparse_treatment = np.array([0, 0, 0, 0, 1, 1], dtype=float)
    with pytest.raises(ValueError, match="both treatment arms"):
        cross_fitted_doubly_robust(y, sparse_treatment, np.ones((6, 1)), 0.5, folds=2, seed=2)


def test_aggregate_and_empirical_bayes_validation_and_clipping() -> None:
    with pytest.raises(ValueError, match="share a shape"):
        private_aggregate_difference(np.ones(2), np.ones(1), np.ones(2), np.ones(2))
    effect, variance = private_aggregate_difference(
        np.array([5.0]), np.array([-2.0]), np.array([-1.0]), np.array([0.0])
    )
    assert effect.tolist() == [1.0]
    assert variance[0] >= 1e-12
    with pytest.raises(ValueError, match="nontrivial"):
        empirical_bayes(np.ones(1), np.ones(1))
    with pytest.raises(ValueError, match="positive"):
        empirical_bayes(np.ones(2), np.array([1.0, 0.0]))
