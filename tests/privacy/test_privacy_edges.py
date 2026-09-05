from __future__ import annotations

import numpy as np
import pytest

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


def test_invalid_contribution_limits_and_multiuser_input() -> None:
    with pytest.raises(ValueError, match="positive"):
        ContributionLimits(0, 1, 1, 1, 1).validate()
    with pytest.raises(ValueError, match="campaign capacity"):
        ContributionLimits(1, 1, 2, 1, 1).validate()
    events = [Event(1, 1, 0, 0, 0, 0), Event(2, 1, 1, 1, 0, 0)]
    with pytest.raises(ValueError, match="exactly one user"):
        bound_user_events(events, ContributionLimits(1, 2, 2, 1, 1))


def test_bounding_order_caps_campaigns_counts_and_window() -> None:
    events = [
        Event(1, 30, 4, 4, 1, 1),
        Event(1, 10, 1, 1, 1, 1),
        Event(1, 10, 2, 2, 1, 1),
        Event(1, 20, 3, 3, 1, 1),
    ]
    bounded = bound_user_events(events, ContributionLimits(2, 1, 2, 1, 1))
    assert [(event.campaign_id, event.timestamp) for event in bounded] == [(10, 1), (20, 3)]
    assert sum(event.click for event in bounded) == 1


@pytest.mark.parametrize("args", [(0, 2), (2, 0), (-1, 1)])
def test_sensitivity_rejects_nonpositive_dimensions(args: tuple[int, int]) -> None:
    with pytest.raises(ValueError, match="positive"):
        l2_sensitivity(*args)


@pytest.mark.parametrize(
    "epsilon,delta,sensitivity", [(0, 1e-6, 1), (1, 0, 1), (1, 1, 1), (1, 1e-6, 0)]
)
def test_calibration_rejects_invalid_budget(
    epsilon: float, delta: float, sensitivity: float
) -> None:
    with pytest.raises(ValueError):
        calibrate_gaussian(epsilon, delta, sensitivity)


def test_accounting_composition_and_invalid_inputs() -> None:
    single = account_gaussian(5.0, 1.0, 1e-6)
    composed = account_gaussian(5.0, 1.0, 1e-6, compositions=2)
    assert composed["epsilon"] > single["epsilon"]
    for args in ((0, 1, 1e-6, 1), (1, 0, 1e-6, 1), (1, 1, 1e-6, 0)):
        with pytest.raises(ValueError, match="invalid"):
            account_gaussian(*args)


def test_release_and_threshold_invalid_boundaries() -> None:
    with pytest.raises(ValueError, match="positive"):
        gaussian_release(np.array([1.0]), 0, 1)
    with pytest.raises(ValueError, match="prespecified"):
        threshold_release(np.array([10]), 11)
    assert threshold_release(np.array([99, 100]), 100).tolist() == [False, True]
