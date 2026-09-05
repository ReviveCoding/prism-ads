# Model Card

Candidate: `PRISM-HB-pyro-rate-v2-effect-scale-0.05`.

Purpose: estimate campaign-segment randomized treatment effects from contribution-bounded noisy
aggregates while partially pooling sparse groups. It models campaign and segment response and
treatment-effect hierarchies and propagates Gaussian privacy variance.

Locked point accuracy passed materiality, macro, long-tail, and decision guardrails. Nominal 95%
interval coverage was 70.6%, so the model is **not promotable**. Mean-field VI underdispersion is a
probable contributor. Appropriate next work is simulation-based calibration, richer variational
families or validated MCMC on representative conditions, and pre-lock requalification.
