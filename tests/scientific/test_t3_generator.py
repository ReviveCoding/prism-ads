from __future__ import annotations

from prism_ads.experiments.t3_generator import REGIMES, probability_expressions


def test_all_preregistered_regimes_are_implemented() -> None:
    assert REGIMES == ("R0", "R1", "R2", "R3", "R4", "R5", "R6", "R7")
    assert set(probability_expressions()) == set(REGIMES)


def test_null_regime_is_exactly_null() -> None:
    _, tau = probability_expressions()["R0"]
    assert tau == "0.0"


def test_regimes_are_distinct() -> None:
    values = list(probability_expressions().values())
    assert len(values) == len(set(values))


def test_generator_identity_is_preregistered() -> None:
    config = open("configs/t3_generator.yaml", encoding="utf-8").read()
    assert "generator_id: t3-logit-v1.1" in config
    assert "campaign) modulo 8" in config
