# Data Card

- T1 Criteo uplift: 13,979,592 rows; protected role split, randomized-assignment diagnostics pass.
- T2 Criteo attribution: 16,468,027 events, 6,142,256 users, 675 campaigns; user-disjoint,
  time-aware roles and intact conversion paths.
- T3: 7,813,401 user-campaign units, 8 segments, regimes R0–R7; generator `t3-logit-v1.1`.
- T1 validated SHA-256: `14190421e3f8103815ba4e4c4b58d6d194dcde3137cd3ce8e2b273a777499c9c`.
- T2 validated SHA-256: `77378feff7cd6b20d83eb9a2d44850779399f877b07185485550fbf96b63cd09`.
- T3 observations SHA-256: `9e2d34f5760512a97bf5bb1bf195ce340266c3a8eb26e2d9f4b1d92867bf717b`.

Raw and derived data are excluded from Git. Candidate observations contain no truth columns.
Public-data limitations and upstream licenses remain applicable.
