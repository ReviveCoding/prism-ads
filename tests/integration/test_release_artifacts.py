from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).parents[2]
LOCKED = ROOT / "artifacts" / "locked" / "prism-ads-v2.2-20260904-8d98593fabdf-r2"


class DashboardParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.headings: list[int] = []
        self.image_alts: list[str] = []
        self.title_parts: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag in {"h1", "h2", "h3"}:
            self.headings.append(int(tag[1]))
        elif tag == "img":
            self.image_alts.append(attributes.get("alt") or "")
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)


def test_public_claims_match_locked_results() -> None:
    primary = json.loads((LOCKED / "primary_results.json").read_text(encoding="utf-8"))
    final = json.loads((LOCKED / "final_analysis.json").read_text(encoding="utf-8"))
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert primary["primary"]["relative_improvement"] == 0.07869797376984787
    assert final["final_scientific_decision"] == "RETAIN_BASELINE"
    for text in ("7.87%", "70.6%", "RETAIN_BASELINE", "NON_PROMOTABLE"):
        assert text in readme
    assert "frozen 80%" in readme


def test_all_figure_hashes_and_accessibility_markup() -> None:
    evidence = json.loads((ROOT / "reports" / "figure_data.json").read_text(encoding="utf-8"))
    assert evidence["figure_count"] == 15
    assert evidence["source_analysis_master_sha256"] == (
        "70a4b6ae5c15e4b468c2fe39e4aba446918ef373f5d1dff414b28ff80062897b"
    )
    namespace = {"svg": "http://www.w3.org/2000/svg"}
    for name, expected in evidence["figures"].items():
        path = ROOT / "reports" / "figures" / name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected
        svg = ET.parse(path).getroot()
        assert svg.get("role") == "img"
        assert svg.get("aria-labelledby") == "chart-title chart-desc"
        assert svg.find("svg:title", namespace) is not None
        assert svg.find("svg:desc", namespace) is not None
        text_nodes = svg.findall("svg:text", namespace)
        text_sizes = [float(node.get("font-size", "0")) for node in text_nodes]
        assert text_sizes and min(text_sizes) >= 12.5


def test_dashboard_local_links_resolve_and_boundaries_are_visible() -> None:
    dashboard = ROOT / "dashboard" / "index.html"
    content = dashboard.read_text(encoding="utf-8")
    references = re.findall(r'(?:href|src)="([^"]+)"', content)
    assert references
    assert all((dashboard.parent / reference).resolve().exists() for reference in references)
    assert "RETAIN_BASELINE" in content
    assert "Retain B3 point-estimation baseline" in content
    assert "Attribution credit is not causal incrementality" in content
    required_copy = (
        "30.4M</strong>source rows across two public Criteo datasets",
        "delta = 1e-7</strong>approximate-DP parameter",
        "Locked primary endpoint and promotion guardrails",
        "PRISM improvements were more common in heterogeneous-effect settings",
        "Do not promote PRISM-HB v2.2.",
        "T3 — Semi-Synthetic Known-Truth Causal Benchmark",
        "Private attribution rankings were substantially less stable",
        "Business implication:",
        "Locked T3 known-truth allocation simulation.",
        "Better estimates improved simulated allocation decisions",
        "in the locked T3 decision simulation.",
        (
            "In this benchmark, privacy-safe causal estimates remained useful for simulated "
            "campaign prioritization"
        ),
    )
    assert all(copy in content for copy in required_copy)
    assert "Better estimates improved decisions" not in content
    assert "can remain useful for campaign prioritization" not in content

    required_figures = {
        "privacy_epsilon_weighted_rmse.svg",
        "privacy_epsilon_interval_coverage.svg",
        "privacy_k_suppression.svg",
        "attribution_rank_stability.svg",
        "long_tail_rmse_by_size.svg",
    }
    figure_sources = {Path(reference).name for reference in re.findall(r'src="([^"]+)"', content)}
    assert figure_sources == required_figures
    assert all((ROOT / "reports" / "figures" / name).is_file() for name in required_figures)


def test_dashboard_metrics_reconcile_to_locked_evidence() -> None:
    content = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
    primary = json.loads((LOCKED / "primary_results.json").read_text(encoding="utf-8"))
    final = json.loads((LOCKED / "final_analysis.json").read_text(encoding="utf-8"))
    gate = json.loads((LOCKED / "promotion_gate.json").read_text(encoding="utf-8"))
    topics = {item["topic"]: item["result"] for item in final["ordered_analysis"]}

    expected = {
        f'{primary["primary"]["B3_weighted_rmse"]:.6f}',
        f'{primary["primary"]["PRISM_weighted_rmse"]:.6f}',
        f'{primary["primary"]["relative_improvement"]:.2%}',
        f'{primary["primary"]["paired_uncertainty"]["lower_95"]:.6f}',
        f'{primary["primary"]["paired_uncertainty"]["upper_95"]:.6f}',
        f'{topics["macro_rmse"]["B3"]:.6f}',
        f'{topics["macro_rmse"]["PRISM"]:.6f}',
        f'{topics["long_tail_result"]["B3"]["weighted_rmse"]:.6f}',
        f'{topics["long_tail_result"]["PRISM"]["weighted_rmse"]:.6f}',
        f'{topics["decision_regret"]["top10"]["B3"]:.2%}',
        f'{topics["decision_regret"]["top10"]["PRISM"]:.2%}',
        f'{topics["decision_regret"]["top25"]["B3"]:.2%}',
        f'{topics["decision_regret"]["top25"]["PRISM"]:.2%}',
        f'{topics["interval_coverage"]["B3"]:.2%}',
        f'{topics["interval_coverage"]["PRISM"]:.1%}',
        f'{gate["guardrails"]["interval_coverage"]["required_minimum"]:.0%}',
    }
    assert final["final_scientific_decision"] == "RETAIN_BASELINE"
    assert final["primary_verdict"] == "NON_PROMOTABLE"
    assert all(value in content for value in expected)
    for required_text in ("5.82%", "10.74%", "1.89%", "0.71%", "70.6%", "80%"):
        assert required_text in content


def test_dashboard_semantics_and_figure_alternatives() -> None:
    content = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
    parser = DashboardParser()
    parser.feed(content)
    assert "PRISM-Ads" in "".join(parser.title_parts)
    assert parser.headings[0] == 1
    assert parser.headings.count(1) == 1
    heading_pairs = zip(parser.headings, parser.headings[1:], strict=False)
    assert all(current <= previous + 1 for previous, current in heading_pairs)
    assert len(parser.image_alts) == 5
    assert all(alternative.strip() for alternative in parser.image_alts)
    assert "a:focus-visible" in content
    assert "@media(max-width:620px)" in content
    assert ".insight-grid{grid-template-columns:repeat(6,minmax(0,1fr))" in content
    assert ".insight:nth-child(n+4){grid-column:span 3}" in content
    assert 'class="business-implication"' in content
    assert 'role="region"' in content and 'tabindex="0"' in content


def test_required_hardening_documents_are_present_and_nonempty() -> None:
    paths = (
        "POST_RELEASE_HARDENING.md",
        "reports/PUBLICATION_AUDIT.md",
        "reports/RESUME_BULLETS.md",
        "reports/INTERVIEW_NOTES.md",
        "reports/FUTURE_V23_PLAN.md",
        "reports/FIGURE_QA.md",
        "SECURITY.md",
        "CITATION.cff",
        "PUBLICATION_PROVENANCE.md",
    )
    for relative in paths:
        assert (ROOT / relative).stat().st_size > 500


def test_publication_metadata_is_scoped_and_automated() -> None:
    citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    provenance = (ROOT / "PUBLICATION_PROVENANCE.md").read_text(encoding="utf-8")
    dependabot = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
    codeql = (ROOT / ".github" / "workflows" / "codeql.yml").read_text(encoding="utf-8")

    assert 'version: "2.2"' in citation and "license: Apache-2.0" in citation
    assert "https://github.com/ReviveCoding/prism-ads" in citation
    assert "2026-09-04" in citation and "doi" not in citation.lower()
    assert "private vulnerability reporting" in security
    assert "Do not disclose sensitive security details in a public issue" in security
    assert "prism-ads-v2.2-20260904-8d98593fabdf-r2" in provenance
    assert "unborn" in provenance and "parentless root commit" in provenance
    assert 'package-ecosystem: "pip"' in dependabot and 'interval: "weekly"' in dependabot
    assert "github/codeql-action/init@v4" in codeql
    assert "security-events: write" in codeql and "branches: [main]" in codeql
