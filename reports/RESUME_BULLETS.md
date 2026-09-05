# Resume Bullets

## Two-bullet version — Research Data Scientist / Ads Measurement

- Built an end-to-end advertising measurement research platform over 30.4M public Criteo rows,
  spanning randomized incrementality, multi-touch attribution, sealed-truth simulation, user-level
  differential privacy, GPU hierarchical Bayes, protected splits, and auditable experiment gates.
- Improved locked weighted RMSE 7.87% versus the strongest eligible baseline, with 5.82% macro,
  10.74% bottom-decile, and decision-regret gains; retained the baseline when PRISM's 70.6%
  interval coverage failed the preregistered 80% gate, demonstrating rigorous model governance.

## Three-bullet version

- Engineered a reproducible 30.4M-row public-data pipeline for causal incrementality, attribution,
  and eight-regime known-truth stress testing with user/path-isolated roles and sealed outcomes.
- Implemented contribution-bounded user-level Gaussian DP (epsilon 1, delta `1e-7`), independent
  PLD accounting, privacy-aware empirical Bayes, and GPU hierarchical Bayesian inference.
- Delivered a 7.87% locked weighted-RMSE improvement plus macro, long-tail, and allocation-regret
  gains, but recommended `RETAIN_BASELINE` after 70.6% coverage missed the frozen 80% threshold.

## Concise project line

PRISM-Ads — governed privacy-aware advertising measurement benchmark; improved locked RMSE 7.87%
but retained the baseline after a preregistered uncertainty-calibration failure.
