from __future__ import annotations

from prism_ads.warehouse.preprocess import T1_COLUMNS, T2_COLUMNS, columns_literal


def test_expected_raw_schemas() -> None:
    expected = [
        *(f"f{i}" for i in range(12)),
        "treatment",
        "conversion",
        "visit",
        "exposure",
    ]
    assert list(T1_COLUMNS) == expected
    assert len(T2_COLUMNS) == 22
    assert list(T2_COLUMNS)[-1] == "cat9"


def test_duckdb_columns_literal() -> None:
    assert columns_literal({"x": "BIGINT"}) == "{'x': 'BIGINT'}"
