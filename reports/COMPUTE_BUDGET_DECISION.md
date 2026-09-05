# Compute Budget Decision

## Qualification evidence

- Representative role: T3 `qualification`, 442,818 bounded analyzed units and 3,268 released campaign-segment groups.
- Three sequential CUDA VI fits took 101.6 seconds total (31.8–37.8 seconds per 300-step fit).
- Observed P10 process working set was approximately 1.5 GB; sampled device use was approximately 288 MiB. Future runs record framework peak allocated/reserved VRAM directly.
- Backend: Pyro 1.9.1, PyTorch 2.14.0+cu130, NVIDIA GeForce RTX 4090 Laptop GPU, Python 3.12.10.

## Frozen-intent primary matrix

- One primary regime: R2 on T3 `locked_final` at epsilon 1.0 and delta 1e-7.
- Ten matched privacy-mechanism replicates.
- Three deterministic VI initializations per privacy replicate; 1,000 SVI steps and 500 posterior draws per initialization (30 primary Bayesian fits).
- Point prediction: median across initialization-specific posterior means. Interval: conservative envelope across initialization-specific 95% intervals.
- Uncertainty: 1,000 outer campaign-cluster bootstrap resamples nesting all ten privacy-mechanism replicates. Privacy draws are not treated as independent datasets.
- One two-chain exact-latent MCMC audit on a prespecified small condition, building on P08 qualification.

## Secondary matrix

- All eight fixed T3 regimes across the six-epsilon grid, one mechanism replicate and one 600-step/300-draw VI fit per cell (48 fits).
- Threshold Study B at k = 10, 20, 50, 100 without a full epsilon-by-k primary factorial.
- Sensitivity dimensions remain epsilon, contribution bounds, prior scale, hierarchy, segmentation, decision budget, and attribution lookback.

## Runtime decision

- Predicted locked primary: approximately 65–90 minutes, including aggregation, 30 GPU fits, bootstrap, validation, and artifact publication.
- Predicted complete locked plus secondary execution: approximately 2.5–3.5 hours.
- Planned Bayesian fits: 30 primary + 48 secondary + 1 small-condition MCMC audit.
- This replication budget is fixed before scientific freeze and must not be reduced because execution is slow.
