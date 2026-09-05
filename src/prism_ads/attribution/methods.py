"""A0-A5 attribution methods; attribution credit is not causal incrementality."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass


@dataclass(frozen=True)
class Touch:
    campaign: int
    timestamp: int


def _normalize(values: list[float]) -> list[float]:
    total = sum(values)
    if total <= 0:
        raise ValueError("attribution weights must have positive mass")
    return [value / total for value in values]


def attribute_path(
    path: list[Touch], method: str, conversion_timestamp: int, half_life_seconds: float = 86400.0
) -> dict[int, float]:
    """Allocate one conversion across touches using A0-A4."""
    if not path:
        raise ValueError("a conversion path must contain at least one touch")
    ordered = sorted(path, key=lambda touch: touch.timestamp)
    if ordered[-1].timestamp > conversion_timestamp:
        raise ValueError("touches cannot occur after conversion")
    count = len(ordered)
    if method == "A0_last_click":
        weights = [0.0] * (count - 1) + [1.0]
    elif method == "A1_first_click":
        weights = [1.0] + [0.0] * (count - 1)
    elif method == "A2_linear":
        weights = [1.0 / count] * count
    elif method == "A3_time_decay":
        if half_life_seconds <= 0:
            raise ValueError("half life must be positive")
        weights = _normalize(
            [
                math.exp(
                    -math.log(2)
                    * (conversion_timestamp - touch.timestamp)
                    / half_life_seconds
                )
                for touch in ordered
            ]
        )
    elif method == "A4_position_based":
        if count == 1:
            weights = [1.0]
        elif count == 2:
            weights = [0.5, 0.5]
        else:
            weights = [0.4, *([0.2 / (count - 2)] * (count - 2)), 0.4]
    else:
        raise ValueError(f"unknown path method: {method}")
    credits: defaultdict[int, float] = defaultdict(float)
    for touch, weight in zip(ordered, weights, strict=True):
        credits[touch.campaign] += weight
    return dict(credits)


def _conversion_probability(
    paths: list[tuple[list[int], bool]], removed: int | None = None
) -> float:
    transitions: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for original, converted in paths:
        path = [campaign for campaign in original if campaign != removed]
        terminal = "CONVERSION" if converted else "NULL"
        states = ["START", *(f"C{campaign}" for campaign in path), terminal]
        for left, right in zip(states, states[1:], strict=False):
            transitions[left][right] += 1
    states = sorted(state for state in transitions if state != "CONVERSION")
    probabilities = {state: 0.0 for state in states}
    for _ in range(500):
        updated: dict[str, float] = {}
        for state in reversed(states):
            counts = transitions[state]
            total = sum(counts.values())
            updated[state] = sum(
                count / total * (1.0 if target == "CONVERSION" else probabilities.get(target, 0.0))
                for target, count in counts.items()
            )
        if max(abs(updated[state] - probabilities[state]) for state in states) < 1e-12:
            probabilities = updated
            break
        probabilities = updated
    return probabilities.get("START", 0.0)


def markov_removal_effect(paths: list[tuple[list[int], bool]]) -> dict[int, float]:
    """A5 normalized campaign removal effects from conversion paths."""
    if not paths or any(not path for path, _ in paths):
        raise ValueError("Markov attribution requires nonempty paths")
    if not any(converted for _, converted in paths) or all(converted for _, converted in paths):
        raise ValueError("Markov attribution requires converted and non-converted paths")
    campaigns = sorted({campaign for path, _ in paths for campaign in path})
    baseline = _conversion_probability(paths)
    effects = {
        campaign: max(baseline - _conversion_probability(paths, removed=campaign), 0.0)
        for campaign in campaigns
    }
    total = sum(effects.values())
    if total == 0:
        return {campaign: 1.0 / len(campaigns) for campaign in campaigns}
    return {campaign: value / total for campaign, value in effects.items()}
