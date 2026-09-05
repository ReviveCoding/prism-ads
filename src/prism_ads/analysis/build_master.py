"""Build the canonical long-form analysis table from locked predictions."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import duckdb

from prism_ads.experiments.t3_generator import publish_json, sha256_file, utc_now
from prism_ads.warehouse.preprocess import configure, quote_path

FREEZE_ID = "prism-ads-v2.2-20260904-8d98593fabdf-r2"


def _count(connection: duckdb.DuckDBPyConnection, query: str) -> int:
    row = connection.execute(query).fetchone()
    if row is None:
        raise RuntimeError("count query returned no row")
    return int(row[0])


def run(root: Path) -> dict[str, Any]:
    root = root.resolve()
    locked = root / "artifacts" / "locked" / FREEZE_ID
    primary = locked / "primary_predictions_pretruth.parquet"
    secondary = locked / "secondary" / "epsilon_regime_predictions_pretruth.parquet"
    truth = (
        root
        / "artifacts"
        / "qualification"
        / "P05"
        / "sealed_truth"
        / "t3_campaign_segment_truth.parquet"
    )
    target = locked / "analysis_master.parquet"
    temporary = target.with_suffix(".parquet.tmp")
    connection = duckdb.connect()
    try:
        configure(connection, root)
        query = f"""
        WITH predictions AS (
          SELECT 'primary' AS evidence_scope, replicate, 'R2' AS effect_regime,
                 1.0 AS epsilon, campaign, segment, units, 'B3' AS model,
                 B3_estimate AS estimate, B3_lower AS lower_95, B3_upper AS upper_95
          FROM read_parquet('{quote_path(primary)}')
          UNION ALL
          SELECT 'primary', replicate, 'R2', 1.0, campaign, segment, units,
                 'PRISM', PRISM_estimate, PRISM_lower, PRISM_upper
          FROM read_parquet('{quote_path(primary)}')
          UNION ALL
          SELECT 'secondary', NULL::INTEGER, regime, epsilon, campaign, segment, units,
                 'B3', B3_estimate, NULL::DOUBLE, NULL::DOUBLE
          FROM read_parquet('{quote_path(secondary)}')
          UNION ALL
          SELECT 'secondary', NULL::INTEGER, regime, epsilon, campaign, segment, units,
                 'PRISM', PRISM_estimate, PRISM_lower, PRISM_upper
          FROM read_parquet('{quote_path(secondary)}')
        ), sizes AS (
          SELECT campaign, sum(units) campaign_units,
                 ntile(10) OVER (ORDER BY sum(units), campaign) campaign_size_decile
          FROM (SELECT DISTINCT campaign, segment, units
                FROM read_parquet('{quote_path(primary)}'))
          GROUP BY campaign
        )
        SELECT p.*, t.true_ate, p.estimate-t.true_ate AS estimation_error,
               pow(p.estimate-t.true_ate,2) AS squared_error,
               abs(p.estimate-t.true_ate) AS absolute_error,
               s.campaign_units, s.campaign_size_decile
        FROM predictions p
        JOIN read_parquet('{quote_path(truth)}') t
          ON p.campaign=t.campaign AND p.segment=t.segment
          AND p.effect_regime=t.effect_regime
        JOIN sizes s ON p.campaign=s.campaign
        ORDER BY evidence_scope, effect_regime, epsilon, replicate, model, campaign, segment
        """
        connection.execute(
            f"COPY ({query}) TO '{quote_path(temporary)}' "
            "(FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 131072)"
        )
        rows = _count(connection, f"SELECT count(*) FROM read_parquet('{quote_path(temporary)}')")
        expected = 2 * _count(
            connection, f"SELECT count(*) FROM read_parquet('{quote_path(primary)}')"
        ) + 2 * _count(connection, f"SELECT count(*) FROM read_parquet('{quote_path(secondary)}')")
        null_truth = _count(
            connection,
            f"SELECT count(*) FROM read_parquet('{quote_path(temporary)}') WHERE true_ate IS NULL",
        )
    finally:
        connection.close()
    os.replace(temporary, target)
    target.chmod(0o444)
    result = {
        "phase": "P15",
        "created_at": utc_now(),
        "status": "PASS" if rows == expected and null_truth == 0 else "FAIL",
        "rows": rows,
        "expected_rows": expected,
        "null_truth": null_truth,
        "path": str(target.relative_to(root)).replace("\\", "/"),
        "sha256": sha256_file(target),
        "bytes": target.stat().st_size,
        "source_identities": {
            "primary": sha256_file(primary),
            "secondary": sha256_file(secondary),
        },
    }
    publish_json(locked / "analysis_master_validation.json", result)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    result = run(args.root)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
