# Executive Memo

## Decision

**RETAIN_BASELINE.** PRISM-HB is not promotable in this experiment.

PRISM reduced locked population-weighted campaign-segment RMSE from 0.004698 to 0.004328, a
7.87% improvement. The paired campaign-cluster bootstrap interval for the absolute improvement
was 0.000123 to 0.000663, so the primary materiality criterion passed. Macro RMSE improved 5.82%,
bottom-decile weighted RMSE improved 10.74%, and normalized decision regret was below 1%.

The blocking result is uncertainty calibration: nominal 95% PRISM intervals covered truth only
70.6% of the time versus the frozen 80% minimum. All promotion gates were conjunctive. The next
iteration should target calibrated posterior uncertainty, not further point-estimate optimization.

This is research-benchmark evidence, not a production advertiser-lift claim.
