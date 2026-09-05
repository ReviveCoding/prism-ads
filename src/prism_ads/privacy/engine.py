"""Formal user-level add/remove-one Gaussian release primitives."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
from dp_accounting.pld import privacy_loss_distribution as pld  # type: ignore[import-untyped]
from scipy.optimize import brentq  # type: ignore[import-untyped]
from scipy.special import ndtr  # type: ignore[import-untyped]

NEIGHBORING_RELATION = "user-level add/remove-one"


@dataclass(frozen=True)
class ContributionLimits:
    max_campaigns_per_user: int
    max_impressions_per_user_per_campaign: int
    max_impressions_per_user_per_window: int
    max_clicks_per_user: int
    max_conversions_per_user: int

    def validate(self) -> None:
        if min(asdict(self).values()) < 1:
            raise ValueError("all contribution limits must be positive")
        campaign_capacity = (
            self.max_campaigns_per_user * self.max_impressions_per_user_per_campaign
        )
        if self.max_impressions_per_user_per_window > campaign_capacity:
            raise ValueError("total-impression bound cannot exceed campaign capacity")


@dataclass(frozen=True)
class Event:
    user_id: int
    campaign_id: int
    timestamp: int
    row_id: int
    click: int
    conversion: int


def bound_user_events(events: list[Event], limits: ContributionLimits) -> list[Event]:
    """Deterministically cap one user's ordered event contributions."""
    limits.validate()
    if len({event.user_id for event in events}) > 1:
        raise ValueError("bound_user_events accepts events for exactly one user")
    selected: list[Event] = []
    campaign_counts: dict[int, int] = {}
    clicks = 0
    conversions = 0
    for event in sorted(events, key=lambda value: (value.timestamp, value.row_id)):
        if event.campaign_id not in campaign_counts:
            if len(campaign_counts) >= limits.max_campaigns_per_user:
                continue
            campaign_counts[event.campaign_id] = 0
        if campaign_counts[event.campaign_id] >= limits.max_impressions_per_user_per_campaign:
            continue
        if len(selected) >= limits.max_impressions_per_user_per_window:
            break
        bounded_click = event.click if clicks < limits.max_clicks_per_user else 0
        bounded_conversion = (
            event.conversion if conversions < limits.max_conversions_per_user else 0
        )
        selected.append(
            Event(
                user_id=event.user_id,
                campaign_id=event.campaign_id,
                timestamp=event.timestamp,
                row_id=event.row_id,
                click=bounded_click,
                conversion=bounded_conversion,
            )
        )
        campaign_counts[event.campaign_id] += 1
        clicks += bounded_click
        conversions += bounded_conversion
    return selected


def l2_sensitivity(max_groups_per_user: int, released_fields_per_group: int = 2) -> float:
    """L2 sensitivity for bounded [count, binary-success] group vectors."""
    if max_groups_per_user < 1 or released_fields_per_group < 1:
        raise ValueError("sensitivity dimensions must be positive")
    return math.sqrt(max_groups_per_user * released_fields_per_group)


def _analytic_gaussian_delta(
    epsilon: float, standard_deviation: float, sensitivity: float
) -> float:
    ratio = sensitivity / standard_deviation
    upper = ndtr(ratio / 2 - epsilon / ratio)
    lower = math.exp(epsilon) * ndtr(-ratio / 2 - epsilon / ratio)
    return float(upper - lower)


def calibrate_gaussian(epsilon: float, delta: float, sensitivity: float) -> float:
    """Calibrate the exact analytic Gaussian mechanism for one vector release."""
    if epsilon <= 0 or not 0 < delta < 1 or sensitivity <= 0:
        raise ValueError("epsilon/sensitivity must be positive and delta must lie in (0,1)")
    def objective(sigma: float) -> float:
        return _analytic_gaussian_delta(epsilon, sigma, sensitivity) - delta

    lower = sensitivity * 1e-6
    upper = sensitivity
    while objective(upper) > 0:
        upper *= 2
    sigma = float(brentq(objective, lower, upper, xtol=1e-12))
    for _ in range(20):
        accounted = account_gaussian(sigma, sensitivity, delta, compositions=1)
        if accounted["epsilon"] <= epsilon:
            return sigma
        sigma *= 1.0005
    raise RuntimeError("could not calibrate a pessimistically accounted Gaussian mechanism")


def account_gaussian(
    standard_deviation: float,
    sensitivity: float,
    delta: float,
    compositions: int = 1,
) -> dict[str, Any]:
    """Independently account with Google's pessimistic PLD implementation."""
    if standard_deviation <= 0 or sensitivity <= 0 or compositions < 1:
        raise ValueError("invalid Gaussian accounting inputs")
    distribution = pld.from_gaussian_mechanism(
        standard_deviation=standard_deviation,
        sensitivity=sensitivity,
        pessimistic_estimate=True,
    )
    if compositions > 1:
        distribution = distribution.self_compose(compositions)
    epsilon = float(distribution.get_epsilon_for_delta(delta))
    return {
        "accountant": "google-dp-accounting PLD",
        "accountant_version": "0.6.0",
        "neighboring_relation": NEIGHBORING_RELATION,
        "epsilon": epsilon,
        "delta": delta,
        "standard_deviation": standard_deviation,
        "l2_sensitivity": sensitivity,
        "compositions": compositions,
        "pessimistic_estimate": True,
    }


def gaussian_release(values: np.ndarray, standard_deviation: float, seed: int) -> np.ndarray:
    """Apply independent Gaussian noise to a bounded numeric release vector."""
    array = np.asarray(values, dtype=np.float64)
    if standard_deviation <= 0:
        raise ValueError("standard deviation must be positive")
    generator = np.random.default_rng(seed)
    return array + generator.normal(0.0, standard_deviation, size=array.shape)


def threshold_release(user_counts: np.ndarray, k: int) -> np.ndarray:
    """STUDY B only: local ADH-inspired threshold eligibility mask."""
    counts = np.asarray(user_counts)
    if k not in (10, 20, 50, 100):
        raise ValueError("k must be one of the prespecified threshold values")
    return counts >= k
