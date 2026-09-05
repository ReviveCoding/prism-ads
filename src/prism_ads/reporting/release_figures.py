"""Generate deterministic P17 figures from the locked evidence."""

# SVG and SQL literals are intentionally kept intact for auditability.
# ruff: noqa: E501

from __future__ import annotations

import argparse
import html
import json
import math
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
from scipy.stats import spearmanr  # type: ignore[import-untyped]

from prism_ads.attribution.methods import Touch, attribute_path, markov_removal_effect
from prism_ads.experiments.p13_locked_primary import FREEZE_ID
from prism_ads.experiments.t3_generator import publish_json, sha256_file, utc_now
from prism_ads.privacy.engine import calibrate_gaussian, gaussian_release

DELTA = 1e-7
EPSILONS = (0.25, 0.5, 1.0, 2.0, 4.0, 8.0)
MODELS = ("B3", "PRISM")


def _svg_frame(title: str, subtitle: str, body: str) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="520" '
        'viewBox="0 0 900 520" role="img" aria-labelledby="chart-title chart-desc">'
        f'<title id="chart-title">{html.escape(title)}</title>'
        f'<desc id="chart-desc">{html.escape(subtitle)}. Axes show the ordered setting and metric value.</desc>'
        '<rect width="900" height="520" fill="#0b1020"/>'
        f'<text x="55" y="45" fill="#edf2ff" font-size="24" font-family="sans-serif">{html.escape(title)}</text>'
        f'<text x="55" y="72" fill="#aebbd8" font-size="14.5" font-family="sans-serif">{html.escape(subtitle)}</text>'
        f'{body}<text x="55" y="500" fill="#aebbd8" font-size="13.5" font-family="sans-serif">'
        "Source: locked canonical evidence · research benchmark</text></svg>"
    )


def _line_svg(title: str, subtitle: str, labels: list[str], series: dict[str, list[float]]) -> str:
    values = [value for row in series.values() for value in row if math.isfinite(value)]
    upper = max(values) if values else 1.0
    lower = min(0.0, min(values)) if values else 0.0
    span = max(upper - lower, 1e-12)
    left, top, width, height = 80.0, 105.0, 740.0, 320.0
    colors = ("#f7c873", "#6ea8fe", "#6ed6a0", "#ff7b86", "#c49cff", "#8bd3dd")
    elements = [
        f'<line x1="{left}" y1="{top + height}" x2="{left + width}" y2="{top + height}" stroke="#72809f"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + height}" stroke="#72809f"/>',
    ]
    for tick in range(5):
        value = lower + span * tick / 4
        y = top + height - height * tick / 4
        elements.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{left + width}" y2="{y:.1f}" stroke="#2a3554"/>'
        )
        elements.append(
            f'<text x="{left - 8}" y="{y + 4:.1f}" text-anchor="end" fill="#aebbd8" font-size="12.5" font-family="sans-serif">{value:.3g}</text>'
        )
    for index, label in enumerate(labels):
        x = left + (width * index / max(len(labels) - 1, 1))
        elements.append(
            f'<text x="{x:.1f}" y="450" text-anchor="middle" fill="#aebbd8" font-size="13.5" font-family="sans-serif">{html.escape(label)}</text>'
        )
    for series_index, (name, row) in enumerate(series.items()):
        points = []
        for index, value in enumerate(row):
            x = left + (width * index / max(len(labels) - 1, 1))
            y = top + height - (value - lower) / span * height
            points.append(f"{x:.1f},{y:.1f}")
            elements.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{colors[series_index]}"/>'
            )
        elements.append(
            f'<polyline points="{" ".join(points)}" fill="none" stroke="{colors[series_index]}" stroke-width="3"/>'
        )
        elements.append(
            f'<text x="{660 + 110 * series_index}" y="95" text-anchor="end" fill="{colors[series_index]}" font-size="14.5" font-family="sans-serif">{html.escape(name)}</text>'
        )
    return _svg_frame(title, subtitle, "".join(elements))


def _bar_svg(title: str, subtitle: str, labels: list[str], values: list[float]) -> str:
    upper = max(values) if values else 1.0
    lower = min(0.0, min(values)) if values else 0.0
    span = max(upper - lower, 1e-12)
    left, top, width, height = 80.0, 105.0, 740.0, 320.0
    slot = width / max(len(labels), 1)
    elements = [
        f'<line x1="{left}" y1="{top + height}" x2="{left + width}" y2="{top + height}" stroke="#72809f"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + height}" stroke="#72809f"/>',
    ]
    for tick in range(5):
        value = lower + span * tick / 4
        y = top + height - height * tick / 4
        elements.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{left + width}" y2="{y:.1f}" stroke="#2a3554"/>'
        )
        elements.append(
            f'<text x="{left - 8}" y="{y + 4:.1f}" text-anchor="end" fill="#aebbd8" font-size="12.5" font-family="sans-serif">{value:.3g}</text>'
        )
    for index, (label, value) in enumerate(zip(labels, values, strict=True)):
        bar_height = (value - lower) / span * height
        x = left + index * slot + slot * 0.18
        y = top + height - bar_height
        elements.extend(
            [
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{slot * 0.64:.1f}" height="{bar_height:.1f}" fill="#6ea8fe"/>',
                f'<text x="{x + slot * 0.32:.1f}" y="{max(y - 7, 92):.1f}" text-anchor="middle" fill="#edf2ff" font-size="12.5" font-family="sans-serif">{value:.3g}</text>',
                f'<text x="{x + slot * 0.32:.1f}" y="450" text-anchor="middle" fill="#aebbd8" font-size="12.5" font-family="sans-serif">{html.escape(label)}</text>',
            ]
        )
    return _svg_frame(title, subtitle, "".join(elements))


def _attribution_detail(root: Path) -> dict[str, Any]:
    connection = duckdb.connect()
    try:
        source = connection.execute(
            "SELECT campaigns,touch_timestamps,terminal_timestamp,converted "
            "FROM read_parquet(?) WHERE role='locked_final' "
            "AND md5_number_lower(uid::VARCHAR || ':' || path_key) % 500=0",
            [str(root / "data" / "marts" / "t2_paths.parquet")],
        ).fetchall()
    finally:
        connection.close()
    converted = [row for row in source if row[3] == 1]
    credits: defaultdict[tuple[str, int], float] = defaultdict(float)
    for campaigns, timestamps, terminal, _ in converted:
        touches = [
            Touch(int(c), int(t)) for c, t in zip(campaigns[:3], timestamps[:3], strict=True)
        ]
        for method in (
            "A0_last_click",
            "A1_first_click",
            "A2_linear",
            "A3_time_decay",
            "A4_position_based",
        ):
            for campaign, value in attribute_path(touches, method, int(terminal)).items():
                credits[(method, campaign)] += value
    frequency: defaultdict[int, int] = defaultdict(int)
    for row in source:
        for campaign in row[0][:3]:
            frequency[int(campaign)] += 1
    top = {
        campaign
        for campaign, _ in sorted(frequency.items(), key=lambda item: item[1], reverse=True)[:20]
    }
    markov_paths = [
        ([int(c) if int(c) in top else -1 for c in row[0][:3]], bool(row[3])) for row in source
    ]
    for campaign, value in markov_removal_effect(markov_paths).items():
        credits[("A5_markov_removal", campaign)] = value * len(converted)
    sigma = calibrate_gaussian(1.0, DELTA, math.sqrt(3))
    detail: dict[str, Any] = {}
    for index, method in enumerate(sorted({key[0] for key in credits})):
        pairs = sorted(
            (campaign, value) for (name, campaign), value in credits.items() if name == method
        )
        campaigns = np.asarray([pair[0] for pair in pairs])
        reference = np.asarray([pair[1] for pair in pairs])
        private = gaussian_release(reference, sigma, 2026091600 + index)
        sizes = np.asarray([frequency[int(campaign)] for campaign in campaigns])
        cuts = np.quantile(sizes, [1 / 3, 2 / 3]) if sizes.size > 2 else np.asarray([0, 0])
        bins = np.digitize(sizes, cuts, right=True)
        distortion = []
        rank_distortion = []
        for size_bin in range(3):
            mask = bins == size_bin
            if np.sum(mask) < 2:
                distortion.append(float("nan"))
                rank_distortion.append(float("nan"))
                continue
            scale = max(float(reference.sum()), 1e-12)
            distortion.append(float(np.mean(np.abs(private[mask] - reference[mask])) / scale))
            if np.ptp(reference[mask]) == 0 or np.ptp(private[mask]) == 0:
                correlation = float("nan")
            else:
                correlation = float(spearmanr(reference[mask], private[mask]).statistic)
            rank_distortion.append(1.0 if not math.isfinite(correlation) else 1 - correlation)
        detail[method] = {
            "reference": reference.tolist(),
            "private": private.tolist(),
            "distortion_by_size": distortion,
            "rank_distortion_by_size": rank_distortion,
        }
    return detail


def run(root: Path) -> dict[str, Any]:
    root = root.resolve()
    locked = root / "artifacts" / "locked" / FREEZE_ID
    master = locked / "analysis_master.parquet"
    secondary = json.loads(
        (locked / "secondary" / "secondary_results.json").read_text(encoding="utf-8")
    )
    output = root / "reports" / "figures"
    output.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect()
    try:
        rows = connection.execute(
            "SELECT epsilon,model,sqrt(sum(units*squared_error)/sum(units)),sqrt(avg(squared_error)),"
            "avg(CASE WHEN lower_95<=true_ate AND true_ate<=upper_95 THEN 1.0 ELSE 0 END) "
            "FROM read_parquet(?) WHERE evidence_scope='secondary' GROUP BY epsilon,model ORDER BY epsilon,model",
            [str(master)],
        ).fetchall()
        tail = connection.execute(
            "SELECT epsilon,model,sqrt(sum(units*squared_error)/sum(units)) FROM read_parquet(?) "
            "WHERE evidence_scope='secondary' AND campaign_size_decile=1 GROUP BY epsilon,model ORDER BY epsilon,model",
            [str(master)],
        ).fetchall()
        by_size = connection.execute(
            "SELECT campaign_size_decile,model,sqrt(sum(units*squared_error)/sum(units)),"
            "avg(CASE WHEN lower_95<=true_ate AND true_ate<=upper_95 THEN 1.0 ELSE 0 END) "
            "FROM read_parquet(?) WHERE evidence_scope='secondary' GROUP BY campaign_size_decile,model ORDER BY campaign_size_decile,model",
            [str(master)],
        ).fetchall()
        decision = connection.execute(
            "WITH c AS (SELECT effect_regime,epsilon,model,campaign,sum(units*true_ate)/sum(units) truth,"
            "sum(units*estimate)/sum(units) estimate,sum(units) w FROM read_parquet(?) "
            "WHERE evidence_scope='secondary' GROUP BY ALL), r AS (SELECT *,row_number() OVER "
            "(PARTITION BY effect_regime,epsilon,model ORDER BY estimate*w DESC) er, row_number() OVER "
            "(PARTITION BY effect_regime,epsilon,model ORDER BY truth*w DESC) tr,count(*) OVER "
            "(PARTITION BY effect_regime,epsilon,model) n FROM c) SELECT epsilon,model,avg(regret) FROM "
            "(SELECT effect_regime,epsilon,model,(sum(CASE WHEN tr<=greatest(1,round(n*.1)) THEN truth*w ELSE 0 END)-"
            "sum(CASE WHEN er<=greatest(1,round(n*.1)) THEN truth*w ELSE 0 END))/nullif(sum(CASE WHEN tr<=greatest(1,round(n*.1)) THEN truth*w ELSE 0 END),0) regret "
            "FROM r GROUP BY effect_regime,epsilon,model) GROUP BY epsilon,model ORDER BY epsilon,model",
            [str(master)],
        ).fetchall()
    finally:
        connection.close()
    metrics: dict[str, dict[str, list[float]]] = {
        "weighted_rmse": {model: [] for model in MODELS},
        "macro_rmse": {model: [] for model in MODELS},
        "coverage": {model: [] for model in MODELS},
        "decision_regret": {model: [] for model in MODELS},
        "long_tail_rmse": {model: [] for model in MODELS},
    }
    for _, model, weighted, macro, coverage in rows:
        metrics["weighted_rmse"][str(model)].append(float(weighted))
        metrics["macro_rmse"][str(model)].append(float(macro))
        metrics["coverage"][str(model)].append(float(coverage))
    for _, model, value in decision:
        metrics["decision_regret"][str(model)].append(float(value))
    for _, model, value in tail:
        metrics["long_tail_rmse"][str(model)].append(float(value))
    size_metrics: dict[str, dict[str, list[float]]] = {
        "rmse": {model: [] for model in MODELS},
        "coverage": {model: [] for model in MODELS},
    }
    for _, model, rmse, coverage in by_size:
        size_metrics["rmse"][str(model)].append(float(rmse))
        size_metrics["coverage"][str(model)].append(float(coverage))
    attribution = secondary["T2_private_attribution"]["methods"]
    detail = _attribution_detail(root)
    methods = list(attribution)
    method_labels = [name.split("_", 1)[0] for name in methods]
    threshold_labels = ["10", "20", "50", "100"]
    epsilon_labels = [f"{value:g}" for value in EPSILONS]
    figures = {
        "privacy_epsilon_weighted_rmse.svg": _line_svg(
            "Epsilon vs weighted RMSE",
            "Mean across eight locked T3 regimes",
            epsilon_labels,
            metrics["weighted_rmse"],
        ),
        "privacy_epsilon_macro_rmse.svg": _line_svg(
            "Epsilon vs macro RMSE",
            "Mean across eight locked T3 regimes",
            epsilon_labels,
            metrics["macro_rmse"],
        ),
        "privacy_epsilon_decision_regret.svg": _line_svg(
            "Epsilon vs decision regret",
            "Top-10% campaign allocation; lower is better",
            epsilon_labels,
            metrics["decision_regret"],
        ),
        "privacy_epsilon_interval_coverage.svg": _line_svg(
            "Epsilon vs interval coverage",
            "Empirical nominal-95% coverage",
            epsilon_labels,
            metrics["coverage"],
        ),
        "privacy_epsilon_released_data_rate.svg": _line_svg(
            "Epsilon vs released-data rate",
            "Gaussian vector release has no epsilon-dependent suppression",
            epsilon_labels,
            {"released": [1.0] * 6},
        ),
        "privacy_k_suppression.svg": _line_svg(
            "k vs suppression",
            "Share of units suppressed by the ADH-inspired threshold",
            threshold_labels,
            {
                "suppressed": [
                    1 - value["released_unit_rate"]
                    for key in threshold_labels
                    for value in [secondary["threshold_study"][key]]
                ]
            },
        ),
        "privacy_long_tail_error.svg": _line_svg(
            "Privacy vs long-tail error",
            "Bottom campaign-size decile across eight regimes",
            epsilon_labels,
            metrics["long_tail_rmse"],
        ),
        "attribution_reference_private.svg": _bar_svg(
            "Reference vs private attribution",
            "L1 distortion between normalized reference and private credit",
            method_labels,
            [float(attribution[name]["attribution_share_l1"]) for name in methods],
        ),
        "attribution_rank_stability.svg": _line_svg(
            "Campaign-rank stability",
            "Correlation of reference and private campaign credit",
            method_labels,
            {
                "Spearman": [float(attribution[name]["spearman"]) for name in methods],
                "Kendall": [float(attribution[name]["kendall"]) for name in methods],
            },
        ),
        "attribution_topk_overlap.svg": _bar_svg(
            "Top-K overlap",
            "Top-10 campaign overlap at epsilon 1",
            method_labels,
            [float(attribution[name]["top10_overlap"]) for name in methods],
        ),
        "attribution_distortion_by_size.svg": _line_svg(
            "Attribution distortion by campaign size",
            "Mean normalized absolute error; post-hoc reporting derivation",
            ["small", "medium", "large"],
            {name: detail[name]["distortion_by_size"] for name in methods[:3]},
        ),
        "long_tail_suppression_by_size.svg": _bar_svg(
            "Suppression by size",
            "Unit suppression at k=10, 20, 50, 100",
            threshold_labels,
            [
                1 - secondary["threshold_study"][key]["released_unit_rate"]
                for key in threshold_labels
            ],
        ),
        "long_tail_rmse_by_size.svg": _line_svg(
            "RMSE by campaign size",
            "Secondary evidence pooled across epsilon and regime",
            [str(i) for i in range(1, 11)],
            size_metrics["rmse"],
        ),
        "long_tail_coverage_by_size.svg": _line_svg(
            "Coverage by campaign size",
            "Secondary empirical nominal-95% interval coverage",
            [str(i) for i in range(1, 11)],
            size_metrics["coverage"],
        ),
        "long_tail_rank_distortion_by_size.svg": _line_svg(
            "Rank distortion by size",
            "1-Spearman for attribution credit; post-hoc reporting derivation",
            ["small", "medium", "large"],
            {name: detail[name]["rank_distortion_by_size"] for name in methods[:3]},
        ),
    }
    for name, content in figures.items():
        (output / name).write_text(content, encoding="utf-8", newline="\n")
    result = {
        "phase": "P17",
        "created_at": utc_now(),
        "status": "PASS",
        "source_analysis_master_sha256": sha256_file(master),
        "figure_count": len(figures),
        "figures": {name: sha256_file(output / name) for name in figures},
        "metrics": metrics,
        "size_metrics": size_metrics,
        "attribution_reporting_derivation": detail,
    }
    publish_json(root / "reports" / "figure_data.json", result)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    result = run(args.root)
    print(json.dumps({"status": result["status"], "figure_count": result["figure_count"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
