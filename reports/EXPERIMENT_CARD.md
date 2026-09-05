# Experiment Card

- Freeze: `prism-ads-v2.2-20260904-8d98593fabdf-r2` (23/23 bound hashes pass).
- Locked run: `locked-r2-20260904-001`.
- Primary: T3 R2 `locked_final`, population-weighted campaign-segment RMSE.
- Replication: 10 privacy draws × 3 VI seeds; 1,000 campaign-cluster bootstraps.
- Comparator: B3 empirical Bayes.
- Materiality: at least 5% relative RMSE improvement.
- Guardrails: macro/long-tail deterioration, interval coverage, normalized decision regret.
- Multiplicity: none for primary, Holm for guardrails, Benjamini-Hochberg for exploratory slices.
- Final decision: `RETAIN_BASELINE` because coverage failed.
