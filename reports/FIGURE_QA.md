# Figure and Dashboard QA

Scope: 15 presentation-only SVGs and `dashboard/index.html`. No locked data was regenerated.

- **Lineage:** `reports/figure_data.json` names the canonical analysis-master SHA-256
  `70a4b6ae5c15e4b468c2fe39e4aba446918ef373f5d1dff414b28ff80062897b` and records every SVG
  hash. Locked values come from P13/P14/P15; attribution-size panels remain labeled descriptive
  post-hoc derivations.
- **Labels and units:** titles name each metric; subtitles define pooling, nominal coverage,
  Top-10 selection, suppression share, or epsilon. Ordered x settings and numeric y ticks are
  visible. Attribution methods use A0–A5 labels defined in the technical material.
- **Accessibility:** SVGs include `<title>`, `<desc>`, `role="img"`, and high-contrast text; the
  dashboard uses semantic sections/tables, descriptive image alternatives, keyboard-visible links,
  and a responsive layout.
- **Claim boundaries:** every view is labeled research evidence. Attribution is not described as
  causal; the threshold study is not represented as an Ads Data Hub implementation; the failed
  70.6% coverage gate and `RETAIN_BASELINE` decision remain prominent.
- **Metric reconciliation:** primary RMSE, macro RMSE, bottom-decile RMSE, decision regret,
  coverage, threshold counts/rates, and attribution stability were checked against
  `final_analysis.json` and `secondary_results.json`. No stale or mismatched primary number remains.

QA disposition: PASS after ordering threshold values numerically, shortening overlapping method
labels, adding numeric grid/tick labels and accessible descriptions, and expanding the dashboard
figure gallery.

Interactive in-app-browser inspection was attempted but no browser backend was available. The QA
therefore includes deterministic XML/HTML, link, hash, accessibility-markup, and metric checks but
not a live cross-browser rendering pass; that remains a manual publication check.

## Post-release dashboard hierarchy refinement

- **Information hierarchy:** the page now moves from context to the exact locked decision, primary
  KPIs, complete locked scorecard, synthesized findings, supporting evidence, recommendation, and
  secondary methods/scope/reproducibility material. The calibration failure remains visible in the
  dominant decision block rather than competing with equally weighted plots.
- **Metric reconciliation:** dashboard assertions cover the exact locked decision and B3/PRISM
  weighted, macro, bottom-decile, regret, and coverage values. The paired RMSE-improvement bootstrap
  interval is explicitly distinguished from posterior interval coverage.
- **Accessibility:** semantic heading order, table headers/caption, a labeled keyboard-focusable
  horizontal table region, meaningful links, visible focus styles, textual PASS/FAIL states, and
  nonempty figure alternatives are verified. Status is not conveyed by color alone.
- **Responsive behavior:** four-card and five-card grids collapse at 900 px and to one column at
  620 px; the scorecard scrolls horizontally; figures remain fluid; and long freeze/run identifiers
  wrap without overlap.
- **Links and lineage:** all local dashboard destinations resolve, all five required previews exist,
  and the underlying 15 audited SVG hashes remain tied to `reports/figure_data.json`.

Deterministic markup, metric, link, accessibility, and responsive-CSS checks pass. Live visual and
cross-browser inspection is still a manual publication check and is not claimed by this QA record.

## Final publication presentation pass

- The five insight cards use a 3+2 desktop grid, a two-column tablet grid, and a one-column mobile
  grid without changing their order or content.
- The approved business implication is presented in a subdued blue callout below the evidence
  gallery and remains visually secondary to the decision and recommendation blocks.
- Axis ticks, category labels, legends, subtitles, and source lines in all 15 presentation SVGs
  increased by approximately 10–15%. Plot coordinates, data values, curves, ordering, titles,
  descriptions, and source lineage were unchanged.
- Deterministic XML tests confirm nonempty SVG titles/descriptions, ARIA naming, a minimum 12.5 px
  chart text size, exact hashes, and the unchanged canonical analysis-master identity.

Browser automation was unavailable during this final pass, and direct SVG preview through the
local image viewer was unsupported. Automated cross-browser QA is therefore not claimed. The user
previously supplied and approved a successful live dashboard rendering inspection; final
publication QA additionally relies on deterministic HTML, responsive-CSS, link, SVG, and metric
tests.
