# Future V2.3 Uncertainty-Calibration Plan

This is a design document only. It does not reopen v2.2, tune against its `locked_final` role, or
change the `RETAIN_BASELINE` decision.

## Objective and candidate family

V2.3 would target calibrated campaign-segment intervals while retaining point accuracy. Candidate
families should compare low-rank multivariate normal, structured block covariance, and richer
normalizing-flow variational posteriors against mean-field VI. The selection objective should be
conjunctive: weighted RMSE materiality, nominal-95% coverage, interval width, calibration curves,
and decision regret—not RMSE alone.

## Calibration audit

- Run simulation-based calibration across parameter draws and all prespecified effect regimes.
- Expand exact or high-fidelity MCMC audits beyond the v2.2 smoke condition, with multiple chains,
  rank diagnostics, effective sample size, divergences, and posterior predictive checks.
- Compare VI and MCMC marginal location, scale, correlation, coverage, and tail behavior.
- Stress privacy variance, sparse denominators, hierarchy depth, and long-tail campaign cells.

## Clean protocol

1. Create new development, validation, policy, and qualification evidence without reading any new
   final truth.
2. Use a newly generated truth realization or a genuinely new held-out structural/time partition;
   never tune against v2.2 `locked_final` outcomes.
3. Prespecify calibration and point-error gates, stopping rules, compute budget, seeds, posterior
   family, MCMC audit size, and multiplicity handling.
4. Require full representative qualification before freeze.
5. Issue a new protocol, source/data manifest, candidate identity, freeze identity, and locked run
   ID. Preserve v2.2 hashes and results unchanged.
6. Execute once, score only after predictions are immutable and hashed, and accept a second
   non-promotion if any conjunctive gate fails.

Old v2.2 locked evidence may be used only as historical context and to motivate the design—not as
training, tuning, qualification, or independent confirmation evidence.
