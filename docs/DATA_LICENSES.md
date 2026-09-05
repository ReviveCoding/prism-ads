# Data Terms and Code Licensing

The official [Criteo uplift dataset page](https://ailab.criteo.com/criteo-uplift-prediction-dataset/)
and [attribution dataset page](https://ailab.criteo.com/criteo-attribution-modeling-bidding-dataset/)
publish Criteo Data Terms of Use based on the Creative Commons
[Attribution-NonCommercial-ShareAlike 4.0 International license](https://creativecommons.org/licenses/by-nc-sa/4.0/).
The pages also request citation of their associated papers.

This repository does **not** redistribute raw or row-level derived Criteo data. Those layers and
Parquet/DuckDB outputs are Git-ignored. Hashes, aggregate diagnostics, schemas, and acquisition
metadata are retained for reproducibility. Users must independently review and comply with the
current upstream terms, including attribution, noncommercial use, and ShareAlike requirements,
before acquisition or use.

The [Apache License 2.0](../LICENSE) applies only to original PRISM-Ads source code. It does not
apply to Criteo datasets, third-party datasets, or other upstream material, and no license grant
for that material is implied. Criteo datasets are not redistributed by this repository and remain
governed by their upstream CC BY-NC-SA 4.0 terms. Users remain responsible for reviewing and
complying with all applicable upstream terms.
