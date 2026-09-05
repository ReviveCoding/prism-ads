from __future__ import annotations

import math

import numpy as np

from prism_ads.attribution.methods import Touch, attribute_path, markov_removal_effect
from prism_ads.decisions.metrics import decision_regret, reference_decision_deviation


def path() -> list[Touch]:
    return [Touch(1, 0), Touch(2, 10), Touch(3, 20)]


def test_a0_through_a4_conserve_credit() -> None:
    methods = [
        "A0_last_click",
        "A1_first_click",
        "A2_linear",
        "A3_time_decay",
        "A4_position_based",
    ]
    for method in methods:
        credit = attribute_path(path(), method, conversion_timestamp=30)
        assert math.isclose(sum(credit.values()), 1.0)
    assert attribute_path(path(), "A0_last_click", 30) == {1: 0.0, 2: 0.0, 3: 1.0}


def test_a5_markov_conserves_credit() -> None:
    credit = markov_removal_effect(
        [([1, 2], True), ([1, 3], True), ([2, 3], False), ([3], False)]
    )
    assert math.isclose(sum(credit.values()), 1.0)
    assert set(credit) == {1, 2, 3}


def test_true_decision_regret_is_nonnegative_and_zero_for_oracle() -> None:
    truth = np.array([0.1, 0.4, -0.2, 0.3])
    weights = np.ones(4)
    assert decision_regret(truth, truth, weights, 2) == 0
    assert decision_regret(truth, -truth, weights, 2) > 0


def test_reference_deviation_uses_top_k_overlap() -> None:
    assert reference_decision_deviation(np.array([3, 2, 1]), np.array([3, 1, 2]), 2) == 0.5
