# Claim Ledger

The tiers distinguish concise portfolio claims from details that require explanation. Every
quantitative claim remains scoped to the v2.2 research benchmark and freeze
`prism-ads-v2.2-20260904-8d98593fabdf-r2`.

## Tier 1 — resume-safe quantitative claims

| Exact wording | Evidence artifact | Metric source | Scope qualifier |
|---|---|---|---|
| Improved locked weighted RMSE 7.87% versus the strongest eligible B3 baseline (0.004328 vs 0.004698). | `primary_results.json`; P13 receipt | Weighted campaign-segment RMSE | T3 R2 locked-final benchmark; freeze ID above |
| The paired absolute RMSE improvement interval was 0.000123–0.000663. | `primary_results.json` | 1,000 campaign-cluster bootstraps nesting 10 privacy replicates | Locked primary comparison, not a universal effect |
| Improved macro RMSE 5.82% (0.005285 to 0.004978). | `final_analysis.json` | Canonical analysis master | Locked T3 R2 aggregate |
| Improved bottom-decile weighted RMSE 10.74% (0.005359 to 0.004783). | `final_analysis.json` | Campaign-size decile 1 | Locked T3 R2 long-tail point error |
| Reduced normalized decision regret from 1.89% to 0.71% at Top-10% and 1.05% to 0.65% at Top-25%. | `final_analysis.json` | Canonical campaign allocation analysis | Locked synthetic-truth decision simulation |
| Implemented contribution-bounded user-level Gaussian DP at epsilon 1 and delta `1e-7`. | P11 `privacy_release.json` | Add/remove-one vector sensitivity `sqrt(6)` | Research release, not a platform privacy certification |
| Independently verified formal accounting at epsilon 0.9999999999998815. | P11 `privacy_accounting.json` | Google dp-accounting 0.6.0 pessimistic PLD | One declared vector composition |
| Built a 30.4M-row protected public-data pipeline spanning randomized incrementality and multi-touch attribution structures. | T1/T2 role manifests | 13,979,592 T1 + 16,468,027 T2 rows | Local Criteo research datasets; data not redistributed |

Every Tier-1 claim must retain its benchmark qualifier. The final decision was `RETAIN_BASELINE`
because PRISM coverage was 70.6%, below the frozen 80% minimum.

## Tier 2 — interview/detail claims

- T1 randomized diagnostics, T2 user/path isolation, and T3 sealed-truth isolation passed.
- PRISM often improved heterogeneous R3/R4/R7 secondary regimes but was not uniformly better.
- Increasing the study threshold from k=10 to k=100 reduced released groups from 3,055 to 1,498
  while retaining 92.67% of units, showing disproportionate small-group suppression.
- Multi-touch attribution methods A0–A5 were implemented and compared, but private rank stability
  was weak: A0–A4 Spearman correlations were 0.10–0.19.
- All 30 primary objectives were finite and improved; maximum across-seed prediction RMSE was
  0.00494. This is optimization evidence, not interval-calibration evidence.
- Falsification F0–F3 passed in the final development candidate; two earlier failed attempts are
  preserved as negative evidence.
- P17 attribution-by-size figures are descriptive post-hoc reporting derivatives, not locked
  endpoints.

## Tier 3 — prohibited or unsupported claims

- PRISM was promoted, deployed, production-ready, or validated for production advertiser lift.
- The project measured realized advertiser revenue or business lift.
- Private attribution was stable or causal.
- The repository implements Ads Data Hub.
- The work represents Google Ads production use, Google employment, affiliation, or endorsement.
- A statistically favorable point-error result overrides the failed calibration gate.
- Old `locked_final` evidence may be reused to tune a candidate and called independent confirmation.
