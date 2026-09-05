# Interview Notes

Use these as research narratives, not memorized claims. The evidence is the closed v2.2 benchmark;
none of it represents production deployment or Google affiliation.

## Why this problem?

**Situation/task:** Advertising teams need incrementality estimates and allocation decisions even
when user-level data must be protected. Privacy noise is not just an engineering constraint; it
changes the statistical observation process. **Action:** I built a benchmark joining causal,
privacy, attribution, and decision evidence under a frozen protocol. **Result:** PRISM improved
point accuracy but failed interval coverage, producing a defensible retain-baseline recommendation.

## Why three tracks?

T1 provides a public randomized anchor, T2 provides realistic user/campaign path structure for
attribution and privacy stress, and T3 adds known truth while preserving that real structure. No
single track can establish randomization validity, path behavior, and estimator error against truth.

## Why is causal incrementality different from attribution?

Incrementality compares potential outcomes under treatment and control; randomized assignment can
identify that causal contrast. Attribution divides observed conversion credit among prior touches.
It can describe paths and rankings but cannot, by itself, identify what would have happened without
the ads. That is why unstable private T2 rankings do not become causal-lift claims.

## Why does privacy change the estimator?

Gaussian noise perturbs successes and denominators, so the observed rate has extra uncertainty and
can be unstable in sparse cells. PRISM explicitly propagated numerator and denominator privacy
variance instead of pretending the released aggregates were exact.

## Why contribution bounding?

User-level DP needs a finite maximum change when one user is added or removed. Deterministically
bounding a user to three campaign groups and the declared event limits yields vector L2 sensitivity
`sqrt(6)` for count/success pairs and prevents heavy users from dominating privacy sensitivity.

## Why epsilon 1 and delta `1e-7`?

They were selected before lock after development/qualification privacy-utility work—not optimized
on final evidence. Epsilon 1 is the primary operating point; delta is small relative to the user
population. Google dp-accounting's pessimistic PLD independently returned epsilon
0.9999999999998815 for the declared one-vector mechanism.

## Why B3?

B3 won the prespecified eligible development comparison across the epsilon grid. It is a serious
privacy-aware normal-normal empirical-Bayes baseline with partial pooling, not a weak straw model.
Using the strongest eligible baseline made the 7.87% point-error improvement meaningful.

## Why hierarchical Bayes?

Campaign and segment cells are uneven and long-tailed. A hierarchy can share information while
allowing heterogeneous response and treatment effects; a posterior can also represent uncertainty
that point empirical Bayes does not. The experiment showed the point-estimation benefit, while the
approximate posterior exposed the calibration limitation.

## Why did mean-field VI become the main limitation?

Mean-field VI is computationally tractable for the locked matrix but cannot represent important
posterior dependence and often underestimates dispersion. The observed symptom was 70.6% empirical
coverage for nominal 95% intervals, below the frozen 80% minimum, even though all optimization
objectives were finite and improved.

## What did falsification catch?

The final candidate passed known-null, treatment-permutation, negative-control, and privacy-only
checks. More importantly, two earlier candidate attempts failed and remain preserved. Those failures
prevented a superficially attractive but falsification-invalid implementation from advancing.

## Why did PRISM improve RMSE but fail coverage?

Posterior means can benefit from shrinkage and a better privacy likelihood even when posterior
scale is too narrow. RMSE evaluates point location; coverage evaluates uncertainty calibration.
They are different properties, and the conjunctive protocol required both.

## Why retain the baseline?

The protocol required every promotion gate to pass. PRISM delivered weighted, macro, bottom-decile,
and decision-regret improvements but missed coverage. Retaining B3 avoided moving forward with
miscalibrated uncertainty and demonstrated that governance controlled the decision—not enthusiasm
for the new model.

## What would you do in a new iteration?

Use structured or low-rank VI, expand representative MCMC comparisons, add simulation-based
calibration, and optimize a joint calibration/accuracy objective during development. Then generate
new truth or a genuinely new held-out partition, requalify, and issue a new freeze. I would not tune
against the old locked-final outcomes.

## How would production-scale data change the design?

I would define the privacy unit with product/legal partners, implement distributed bounded
aggregation, version schemas and lineage, monitor sample-ratio and contribution distributions,
calibrate on repeated experiments, and define decision-specific loss and uncertainty service-level
objectives. I would also separate descriptive attribution from causal experimentation in both data
contracts and stakeholder reporting.

## What business recommendation follows from unstable attribution?

Do not use noisy private attribution ranks as a sole budget-allocation signal. Aggregate decisions
to more stable levels, report uncertainty and overlap, combine attribution with randomized lift
evidence, and collect more signal before acting on small campaign differences.

## What did the long-tail analysis show?

Thresholding imposed disproportionate suppression on small groups: k=10 retained 3,055 groups and
99.77% of units, while k=100 retained 1,498 groups and 92.67% of units. Yet in the locked primary
causal endpoint, PRISM improved bottom-decile weighted RMSE from 0.005359 to 0.004783. Privacy's
long-tail cost therefore appeared in availability/suppression, not a universal point-error loss.
