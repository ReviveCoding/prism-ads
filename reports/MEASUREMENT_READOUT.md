# Measurement Readout

The locked primary used T3 R2 on the protected `locked_final` role, ten Gaussian privacy draws,
three fixed VI initializations per draw, and 1,000 campaign-cluster bootstraps. B3 was selected in
development as the strongest eligible aggregate-only baseline.

| Measure | B3 | PRISM-HB | Verdict |
|---|---:|---:|---|
| Weighted RMSE | 0.004698 | 0.004328 | PRISM 7.87% better; materiality pass |
| Macro RMSE | 0.005285 | 0.004978 | Guardrail pass |
| Bottom-decile weighted RMSE | 0.005359 | 0.004783 | Guardrail pass |
| 95% interval coverage | 0.19% | 70.64% | PRISM guardrail fail |
| Top-10% normalized regret | 1.89% | 0.71% | Guardrail pass |
| Top-25% normalized regret | 1.05% | 0.65% | Guardrail pass |

Privacy reduced reliability most visibly in sparse attribution and threshold settings. At k=100,
only 1,498 groups remained, although they represented 92.67% of units. This is evidence that small
groups bear disproportionate suppression risk. For the primary causal estimator, bottom-decile
point-error did not deteriorate relative to B3; PRISM improved it.

Attribution credit is not causal incrementality. Under the locked private attribution sample,
A0–A4 Spearman correlations were only 0.10–0.19 and Top-10 overlap was 0.20–0.50.
