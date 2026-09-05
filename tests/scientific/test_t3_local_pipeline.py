from __future__ import annotations

from pathlib import Path

import duckdb

from prism_ads.experiments.t3_generator import (
    build_generated,
    build_group_truth,
    build_individual_truth,
    build_observations,
    build_structure,
    copy_atomic,
    relation,
    scalar,
)
from prism_ads.warehouse.preprocess import quote_path


def t2_fixture(connection: duckdb.DuckDBPyConnection, target: Path) -> None:
    connection.execute(
        "CREATE TABLE events(row_id BIGINT, uid BIGINT, campaign BIGINT, role VARCHAR, "
        "click INTEGER, path_key VARCHAR, cost DOUBLE, cat1 BIGINT)"
    )
    for index, role in enumerate(
        ("train", "validation", "calibration", "policy", "qualification", "locked_final")
    ):
        connection.execute(
            "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [index, index, index % 3, role, index % 2, f"p{index}", 0.1 + index, index % 4],
        )
    connection.execute(f"COPY events TO '{quote_path(target)}' (FORMAT PARQUET)")


def test_t3_generation_helpers_preserve_truth_boundary(tmp_path: Path) -> None:
    connection = duckdb.connect()
    try:
        t2 = tmp_path / "t2.parquet"
        structure = tmp_path / "structure.parquet"
        generated = tmp_path / "generated.parquet"
        observations = tmp_path / "observations.parquet"
        truth = tmp_path / "truth.parquet"
        grouped = tmp_path / "grouped.parquet"
        t2_fixture(connection, t2)
        build_structure(connection, t2, structure)
        build_generated(connection, structure, generated)
        build_observations(connection, generated, observations)
        build_individual_truth(connection, generated, truth)
        build_group_truth(connection, truth, ("campaign", "segment"), grouped)
        assert scalar(connection, f"SELECT count(*) FROM {relation(structure)}") == 6
        columns = {
            row[0]
            for row in connection.execute(
                f"DESCRIBE SELECT * FROM {relation(observations)}"
            ).fetchall()
        }
        assert not any(name.startswith(("p0_", "p1_", "ite_")) for name in columns)
        assert (
            scalar(connection, f"SELECT count(DISTINCT effect_regime) FROM {relation(grouped)}")
            == 8
        )
        copy_atomic(connection, "SELECT 1 AS x", tmp_path / "existing.parquet")
        copy_atomic(connection, "SELECT 2 AS x", tmp_path / "existing.parquet")
        assert scalar(connection, f"SELECT x FROM {relation(tmp_path / 'existing.parquet')}") == 1
    finally:
        connection.close()
