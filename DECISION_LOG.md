# Decision Log

## D0001 — Scientific interpreter

- Decision: Use CPython 3.12, selected explicitly with `py -3.12`; initial version is 3.12.10.
- Alternatives: CPython 3.11 fallback; CPython 3.13 only after explicit dependency qualification.
- Evidence: `py -3.12 --version` succeeded during P00.
- Rationale: Required preferred interpreter in the governing specification.
- Frozen?: No.

Further scientific and engineering decisions are appended; prior records are not rewritten after freeze.

## D0002 — P04 T1 practical covariate-balance threshold

- Decision: Interpret absolute standardized mean differences below 0.10 as practically balanced; retain exact values and the randomization/SRM evidence.
- Alternatives: The initial implementation used an unjustified 0.02 cutoff and produced a preserved failed diagnostic; zero-tolerance based on p-values was rejected by the specification.
- Evidence: Maximum absolute SMD is 0.04884; observed treatment ratio is 0.85000013 versus documented 0.85, with SRM p=0.9989.
- Rationale: 0.10 is a conventional practical-magnitude threshold and avoids confusing detectable imbalance with material invalidity at nearly 14 million rows.
- Frozen?: No.

## D0003 — T2 protected-unit identity

- Decision: Use `(uid, conversion_id)` for conversion-path identity and assign all events for each user to a time-aware role based on the user's final event/conversion time.
- Alternatives: Treat `conversion_id` as globally unique; split non-conversion user-days independently.
- Evidence: 2,910 conversion IDs recur across users, while all 438,730 `(uid, conversion_id)` units have a single consistent conversion timestamp. The initial path split passed path leakage but did not enforce user isolation.
- Rationale: The composite key matches observed data semantics; user-disjoint roles are stronger for later user-level privacy and also guarantee complete conversion paths stay together.
- Frozen?: No.

## D0004 — T3 segmentation identity

- Decision: Define eight segments as the stable hash of `(dominant_cat1, campaign)` modulo 8 in generator `t3-logit-v1.1`.
- Alternatives: Hash `dominant_cat1` alone (`t3-logit-v1`), which realized only six of eight preregistered buckets; use arbitrary fitted clusters.
- Evidence: The preserved first generator pass produced segment counts only for buckets 0, 1, 2, 5, 6, and 7 even though all treatment/outcome reproducibility checks passed.
- Rationale: Binding real context to campaign retains the structural backbone, deterministically realizes the preregistered hierarchy, and avoids outcome/model-driven segmentation.
- Frozen?: No.

## D0005 — Bayesian backend

- Decision: Use Pyro 1.9.1 with PyTorch 2.14.0+cu130 and a non-centered hierarchical model.
- Alternatives: NumPyro/JAX preferred by default; CPU-only PyTorch; non-Bayesian approximation.
- Evidence: Native Windows environment; the initial PyPI PyTorch wheel was CPU-only and rejected. The official PyTorch CUDA index supplied `2.14.0+cu130`, and a synchronized 4096×4096 operation completed on the RTX 4090 Laptop GPU.
- Rationale: Pyro/PyTorch is an explicitly allowed specification fallback and provides qualified Windows CUDA execution plus NUTS inference.
- Frozen?: No.

## D0006 — P10 baseline and PRISM development identity

- Decision: Select B3 empirical-Bayes partial pooling as the strongest eligible privacy-safe baseline using mean population-weighted RMSE across the prespecified epsilon grid. Carry PRISM-HB forward with a HalfNormal(0.05) treatment-heterogeneity scale prior for qualification.
- Alternatives: B1 private difference-in-means; B2 analytical privacy-noise-aware weighting; the original HalfNormal(0.35) treatment-effect scale.
- Evidence: Grid-average weighted RMSE was 0.00335 for B3 versus 0.10847 for B1/B2. The original candidate failed privacy-noise-only interval calibration; the tightened prior and corrected, nondegenerate privacy-only null passed F0–F3, with F3 false-discovery rate 0.00087.
- Rationale: The comparator rule was declared before truth scoring. The prior revision occurred only in development and the two failed attempts are preserved. The corrected F3 fixes an invalid all-zero response construction while retaining the original pass threshold.
- Frozen?: No; requires P11 qualification and Checkpoint B before P12 freeze.

## D0007 — P11 privacy operating point and locked compute design

- Decision: Use epsilon 1.0, delta 1e-7, user-level add/remove-one adjacency, the analytic Gaussian mechanism, and the P10 p99 contribution bounds. Use R2 on `locked_final` as the primary endpoint condition with ten privacy replicates, three VI initializations per replicate, and 1,000 outer campaign-cluster bootstrap resamples.
- Alternatives: Select epsilon by best model performance; use delta 1e-6; run a full epsilon-by-threshold factorial; reduce to one VI initialization.
- Evidence: Delta is below 1 / 6,142,256 protected users. The independent PLD accountant reports epsilon 0.9999999999998815. Three qualification seeds had pairwise prediction RMSE at most 0.00319, all objectives improved, and PRISM interval coverage was 0.9979. Estimated primary runtime is 65–90 minutes.
- Rationale: Epsilon is the moderate-privacy policy ceiling and was chosen independently of PRISM performance. The nested design separates campaign sampling and privacy-mechanism uncertainty without treating privacy draws as independent datasets.
- Frozen?: No; becomes frozen in P12 after Checkpoint B.

## D0008 — Scientific freeze

- Decision: Freeze protocol identity `prism-ads-v2.2-20260904-8d98593fabdf` after successful Checkpoint B and bind twenty data, truth, configuration, evidence, report, and implementation artifacts by SHA-256.
- Alternatives: Continue tuning after qualification; defer replication decisions until runtime.
- Evidence: The independent freeze verifier checked 20 of 20 identities, 31 tests passed, and Ruff and strict mypy passed.
- Rationale: The manifest makes any post-freeze change to scientific inputs or implementation detectable before locked execution.
- Frozen?: Yes.

## D0009 — Pre-lock freeze amendment

- Decision: Supersede the initial freeze with `prism-ads-v2.2-20260904-8d98593fabdf-r2`, adding only the dedicated P13 runner to the bound implementation set.
- Alternatives: Start locked execution with an unbound orchestrator; modify the original freeze in place.
- Evidence: The omission was detected before locked start; `locked_started` remained false. The superseding manifest verifies 23 of 23 hashes and preserves the original protocol and manifest unchanged.
- Rationale: Locked orchestration is scientifically material implementation and must be hash-bound. No data, model, privacy, endpoint, guardrail, or replication choice changed.
- Frozen?: Yes; this is the active freeze identity.

## D0010 — Locked primary promotion verdict

- Decision: Mark PRISM-HB non-promotable under the frozen protocol.
- Alternatives: Promote based on weighted-RMSE materiality alone; recalibrate intervals after observing locked results.
- Evidence: PRISM improved weighted RMSE by 7.87% versus B3 and the paired difference interval excluded zero, but mean 95% interval coverage was 70.6% against the frozen 80% minimum.
- Rationale: All frozen guardrails are conjunctive. Post-lock tuning or overriding the failed coverage guardrail would invalidate the experiment.
- Frozen?: Locked result; immutable.

## D0011 — Final scientific decision

- Decision: `RETAIN_BASELINE` and iterate on calibrated posterior uncertainty before reconsidering PRISM-HB.
- Alternatives: `PROMOTE_PRISM`, `ITERATE` without a deployable baseline decision, or `INVALID_EXPERIMENT`.
- Evidence: Artifact/data/privacy/inference gates passed. PRISM improved locked weighted RMSE by 7.87%, macro RMSE by 5.82%, bottom-decile weighted RMSE by 10.74%, and locked normalized decision regret. Its mean 95% interval coverage was only 70.6%, below the frozen 80% guardrail.
- Rationale: The experiment is valid and informative, but PRISM failed a conjunctive promotion guardrail. B3 remains the eligible baseline despite its own very poor plug-in interval coverage; neither model's current intervals should be used for high-stakes uncertainty claims.
- Frozen?: Final locked decision.
