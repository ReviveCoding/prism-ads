from __future__ import annotations

import math

import numpy as np

from prism_ads.privacy.engine import (
    ContributionLimits,
    Event,
    account_gaussian,
    bound_user_events,
    calibrate_gaussian,
    gaussian_release,
    l2_sensitivity,
    threshold_release,
)


def test_contribution_bounds_are_enforced() -> None:
    limits = ContributionLimits(2, 2, 3, 1, 1)
    events = [Event(1, campaign, i, i, 1, 1) for i, campaign in enumerate([10, 10, 20, 30])]
    bounded = bound_user_events(events, limits)
    assert len(bounded) == 3
    assert len({event.campaign_id for event in bounded}) == 2
    assert sum(event.click for event in bounded) == 1
    assert sum(event.conversion for event in bounded) == 1


def test_vector_sensitivity_matches_adjacent_difference() -> None:
    sensitivity = l2_sensitivity(4, 2)
    adjacent_difference = np.tile([1.0, 1.0], 4)
    assert math.isclose(np.linalg.norm(adjacent_difference), sensitivity)


def test_gaussian_accounting_independently_verifies_budget() -> None:
    sensitivity = l2_sensitivity(4, 2)
    sigma = calibrate_gaussian(1.0, 1e-6, sensitivity)
    result = account_gaussian(sigma, sensitivity, 1e-6)
    assert result["epsilon"] <= 1.0


def test_gaussian_release_is_seed_reproducible() -> None:
    values = np.arange(4.0)
    assert np.array_equal(gaussian_release(values, 2.0, 7), gaussian_release(values, 2.0, 7))


def test_threshold_grid_is_prespecified() -> None:
    assert threshold_release(np.array([9, 10, 20]), 10).tolist() == [False, True, True]
