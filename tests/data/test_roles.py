from __future__ import annotations

from prism_ads.data.quality_roles import ROLE_THRESHOLDS, role_case


def test_role_thresholds_cover_all_buckets() -> None:
    assert ROLE_THRESHOLDS[-1] == (10000, "locked_final")
    assert [value for value, _ in ROLE_THRESHOLDS] == sorted(
        value for value, _ in ROLE_THRESHOLDS
    )
    assert len({role for _, role in ROLE_THRESHOLDS}) == 6


def test_role_case_is_total() -> None:
    expression = role_case("bucket")
    assert "WHEN bucket < 5000 THEN 'train'" in expression
    assert "WHEN bucket < 10000 THEN 'locked_final'" in expression
