# Privacy Card

- Neighboring relation: user-level add/remove-one.
- Mechanism: analytic Gaussian vector release of `n0`, `n1`, `y0`, `y1`.
- Primary budget: epsilon 1.0, delta 1e-7, one composed vector release.
- L2 sensitivity: 2.4494897428; standard deviation: 11.4603371777.
- Independent verification: Google `dp-accounting` 0.6.0 pessimistic PLD, accounted epsilon
  0.9999999999998815.
- Bounds: 3 campaigns/user, 7 impressions/user/campaign, 8 impressions/window, 4 clicks, 1
  conversion.

The threshold analysis is an **ADH-inspired local aggregation-threshold stress test**, not an Ads
Data Hub implementation. At k=10 and k=100, released-unit rates were 99.77% and 92.67%, while group
counts fell from 3,055 to 1,498, showing disproportionate suppression of small groups.
