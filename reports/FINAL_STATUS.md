# Final Status

## Completion and identities

- Specification: 2.2.
- Completion: P00–P17 complete; final audit passed with the disclosed coverage exception.
- Python: 3.12.10; acquisition used Python `urllib` HTTPS with OpenSSL 3.0.16.
- Hardware: Intel i9-13900HX, 32 logical processors, 34,086,969,344 bytes RAM;
  NVIDIA GeForce RTX 4090 Laptop GPU, 16,376 MiB VRAM, driver 610.62.
- Active freeze: `prism-ads-v2.2-20260904-8d98593fabdf-r2`.
- Locked run: `locked-r2-20260904-001`.
- Selected baseline: B3, point-hyperparameter normal-normal empirical Bayes with
  privacy-variance plug-in weighting.
- Candidate: `PRISM-HB-pyro-rate-v2-effect-scale-0.05`.

## Data and protected roles

| Dataset | Source/use | Rows or units | Stored bytes | SHA-256 |
|---|---|---:|---:|---|
| T1 raw | Criteo Uplift Modeling Dataset v2.1 | 13,979,592 staged rows | 311,422,618 | `2716e1bf0fd157a93b5bf86924d9088419dfbac2022c6cd90030220634f616dc` |
| T2 raw | Criteo Attribution Modeling for Bidding Dataset | 16,468,027 staged rows | 653,128,946 | `242acae50d9eadda739da1dab7c5fec6f4aee3e4e17b315e2c42c2d42f339d09` |
| T3 structure | Real-structure synthetic benchmark from T2 | 7,813,401 units | 94,035,377 | `9094a79407a8f3d717701c83e9fc14ca776691b846da23307115a460f60e3a9f` |
| Analysis master | Canonical locked primary and secondary evidence | 399,040 rows | 13,016,443 | `70a4b6ae5c15e4b468c2fe39e4aba446918ef373f5d1dff414b28ff80062897b` |

T1 roles are assigned by a deterministic observation-key hash. T2 roles are assigned at the
user level, with zero user or path overlap across roles. T3 inherits the protected role and keeps
candidate observations separate from sealed truth. Candidate code cannot read truth; scoring
opens it only after predictions are made read-only and hashed.

## Privacy design

- Neighboring relation: user-level add/remove-one.
- Mechanism: one Gaussian vector release of arm counts and binary successes.
- Primary parameters: epsilon 1, delta `1e-7`, L2 sensitivity `sqrt(6)`, noise standard deviation
  11.46033717766397.
- Bounds: at most 3 campaigns per user, 7 impressions per user-campaign, 8 impressions per
  window, 4 clicks, and 1 conversion.
- Accountant: Google `dp-accounting` 0.6.0 pessimistic PLD; independently accounted epsilon
  0.9999999999998815.

## Locked scientific results

| Measure | B3 | PRISM-HB |
|---|---:|---:|
| Primary weighted RMSE | 0.004697832 | 0.004328122 |
| Macro RMSE | 0.005285240 | 0.004977769 |
| Nominal 95% interval coverage | 0.19% | 70.64% |
| Bottom-decile weighted RMSE | 0.005358563 | 0.004783212 |
| Top-10% normalized decision regret | 1.89% | 0.71% |
| Top-25% normalized decision regret | 1.05% | 0.65% |

PRISM-HB improved the primary weighted RMSE by 7.87%. The paired absolute improvement interval
was 0.000123–0.000663. It nevertheless failed the frozen 80% coverage guardrail, so the final
scientific decision is **`RETAIN_BASELINE`** and the candidate is **non-promotable**.

Privacy utility was heterogeneous over the 48-cell epsilon-by-regime grid: PRISM often helped in
heterogeneous R3/R4/R7 regimes but lost on the null R0 and several homogeneous/long-tail cells.
Thresholding disproportionately suppressed small groups: increasing k from 10 to 100 reduced
released groups from 3,055 to 1,498 while released unit share fell from 99.77% to 92.67%. In the
primary causal endpoint, bottom-decile point error improved rather than deteriorated.

Private T2 attribution was unstable at epsilon 1: A0–A4 Spearman correlations were 0.10–0.19
and Top-10 overlap was 0.20–0.50; A5 Spearman was 0.37 on only 21 campaigns. Attribution credit
is not causal incrementality. The study is ADH-inspired, not an Ads Data Hub implementation.

Falsification checks F0–F3 passed. The ordered C0–C4 ablation showed the largest development
improvement when the explicit numerator/denominator privacy likelihood was introduced at C3;
the full hierarchy was not uniformly best across epsilon values. Primary GPU fit time was
3,175.51 seconds and secondary GPU fit time was 2,877.52 seconds (6,053.03 seconds total).

## Quality, skips, and limitations

- Tests: 31 passed on Python 3.12.
- Ruff lint: pass. Strict mypy: pass. Controller: 87 registered artifacts verified before P17
  publication; active freeze: 23/23 identities verified.
- Branch coverage at P17 was 55%, below the specification's approximate 80% target. Post-release
  hardening added meaningful tests and raised current measured coverage to 90% (69 tests), without
  changing freeze-bound science. The original gap remains historical, not a scientific gate override.
- Optional skips: none.
- Major limitations: T3 outcomes are synthetic; T2 lacks causal attribution truth; the private
  attribution sample is small; mean-field VI undercoverage is decisive; the repository has an
  unborn Git HEAD; the initial freeze required a documented pre-lock amendment to bind the P13
  runner; the P14 orchestrator was declared and hashed only immediately before secondary
  execution, so secondary results are supplemental and cannot alter the primary verdict.

## Reproduction

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m prism_ads.pipeline status
.\.venv\Scripts\python.exe -m prism_ads.pipeline verify
.\.venv\Scripts\python.exe -m prism_ads.reporting.release_figures --root .
.\.venv\Scripts\python.exe -m pytest -q
```

This is research-benchmark evidence, not a production deployment or advertiser-revenue claim.
