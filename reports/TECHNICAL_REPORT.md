# Technical Report

## Design

PRISM-Ads combines public Criteo uplift and attribution datasets with T3, a deterministic
real-structure synthetic benchmark containing eight sealed-truth effect regimes. Protected roles
are deterministic and user-disjoint where required. Candidate code never reads truth; scoring
opens truth only after predictions are written read-only and hashed.

The private release is one vector of arm counts and binary successes under user-level
add/remove-one adjacency. Contributions are bounded to 3 campaigns per user, 7 impressions per
user-campaign, 8 impressions per window, 4 clicks, and 1 conversion. At epsilon 1 and delta 1e-7,
the analytic Gaussian standard deviation is 11.46034 for L2 sensitivity sqrt(6). Google's
pessimistic PLD accountant independently reports epsilon 0.9999999999998815.

## Models and inference

B3 is point-hyperparameter normal-normal empirical Bayes with privacy-variance plug-in weighting.
PRISM-HB uses non-centered campaign and segment response/effect hierarchies, a HalfNormal(0.05)
treatment-effect scale prior, and numerator/denominator privacy variance propagation. Pyro 1.9.1
and PyTorch 2.14.0+cu130 ran on an RTX 4090 Laptop GPU. Thirty primary fits used 1,000 SVI steps
and 500 posterior draws; all objectives were finite and improved. Maximum seed prediction RMSE was
0.00494. P08 provided a two-chain exact-latent NUTS smoke comparison.

## Results and interpretation

The primary paired result favored PRISM in point accuracy, but nominal interval coverage was only
70.6%. Because the frozen minimum was 80%, the final decision is `RETAIN_BASELINE`. B3's plug-in
coverage was also extremely poor, so the retention decision concerns the eligible point-estimate
baseline; neither model's present intervals support high-stakes uncertainty claims.

Across the secondary eight-regime grid, PRISM often improved heterogeneous R3/R4/R7 conditions but
was worse on null R0 and several homogeneous/long-tail cells. This heterogeneity reinforces the
need for calibration and regime-robust validation rather than selecting favorable epsilon cells.

## Limitations

T3 is synthetic-outcome evidence on a real structural backbone. T2 has no causal attribution
truth. The private attribution sample is small. Mean-field VI undercoverage is the decisive model
limitation. Repository-wide coverage was 55% at P17; post-release tests raised it to 90% without
modifying freeze-bound scientific code. Both the original gap and hardening result are disclosed.
