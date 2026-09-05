# PRISM-Ads

**A governed advertising-measurement research platform for asking when privacy-aware hierarchical
models improve incrementality decisions—and when they should not be promoted.**

PRISM-Ads combines causal inference, user-level differential privacy, hierarchical Bayes,
multi-touch attribution, and reproducible experiment governance over large public advertising
datasets. The central question was whether explicit privacy-noise modeling could outperform the
strongest eligible privacy-aware empirical-Bayes baseline without sacrificing calibrated
uncertainty.

## Locked result at a glance

| Locked endpoint or guardrail | B3 baseline | PRISM-HB | Result |
|---|---:|---:|---|
| Weighted RMSE | 0.004698 | **0.004328** | 7.87% better; paired improvement 0.000123–0.000663 |
| Macro RMSE | 0.005285 | **0.004978** | 5.82% better |
| Bottom-decile weighted RMSE | 0.005359 | **0.004783** | 10.74% better |
| Top-10% normalized decision regret | 1.89% | **0.71%** | Better allocation ranking |
| Top-25% normalized decision regret | 1.05% | **0.65%** | Better allocation ranking |
| Nominal 95% interval coverage | 0.19% | **70.6%** | **Failed frozen 80% minimum** |

**Final decision: `RETAIN_BASELINE`. PRISM-HB is `NON_PROMOTABLE`.** It improved point estimates
and downstream decisions, but mean-field variational intervals failed a preregistered calibration
guardrail. Preserving that negative promotion decision is the important result: accuracy gains do
not justify deploying uncertainty estimates that miss their declared coverage.

## Three evidence tracks

1. **Incrementality (T1):** the public randomized Criteo uplift benchmark anchors causal
   advertising-effectiveness checks.
2. **Attribution (T2):** user/campaign paths support multi-touch attribution and privacy-distortion
   analysis; attribution credit is explicitly not causal incrementality.
3. **Known-truth stress testing (T3):** a real T2 structural backbone with synthetic outcomes and
   sealed truth tests eight effect regimes without exposing truth to candidate code.

The primary release uses contribution-bounded user-level add/remove-one Gaussian DP at
epsilon 1 and delta `1e-7`, independently verified with a pessimistic PLD accountant. B3 was the
strongest eligible development baseline. Thresholding placed disproportionate suppression risk on
small groups, while private attribution rankings were unstable; in contrast, primary bottom-decile
point error improved. Together these results demonstrate an end-to-end measurement workflow that
turns privacy, causal, statistical, and governance evidence into a model-selection recommendation.

## Explore and reproduce

- [Executive memo](reports/EXECUTIVE_MEMO.md) · [technical report](reports/TECHNICAL_REPORT.md) ·
  [measurement readout](reports/MEASUREMENT_READOUT.md)
- **[Live dashboard](https://revivecoding.github.io/prism-ads/dashboard/)** ·
  [dashboard source](dashboard/index.html) · [15-figure index](reports/FIGURE_INDEX.md) ·
  [claim ledger](reports/CLAIM_LEDGER.md)
- [Reproduction runbook](RUNBOOK.md) · [final scientific status](reports/FINAL_STATUS.md) ·
  [post-release hardening record](POST_RELEASE_HARDENING.md)
- [Resume bullets](reports/RESUME_BULLETS.md) · [interview notes](reports/INTERVIEW_NOTES.md) ·
  [clean v2.3 study plan](reports/FUTURE_V23_PLAN.md)
- [Citation metadata](CITATION.cff) · [Apache-2.0 source license](LICENSE) ·
  [security and responsible disclosure](SECURITY.md)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m prism_ads.pipeline verify
.\.venv\Scripts\python.exe -m pytest -q
```

This is an independent research benchmark, not Google experience, Google Ads production use, an
Ads Data Hub implementation, or a production advertiser-lift claim. Public Criteo data is not
redistributed; users must obtain it under the upstream terms.

## License and data terms

[Apache License 2.0](LICENSE) applies only to original PRISM-Ads source code. Criteo datasets are
not redistributed by this repository and remain governed by their upstream
[CC BY-NC-SA 4.0 terms](https://creativecommons.org/licenses/by-nc-sa/4.0/). No license grant is
implied for third-party datasets or other upstream material. See
[Data Terms and Code Licensing](docs/DATA_LICENSES.md) for details.
