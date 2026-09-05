# Post-Release Portfolio Hardening

This record describes publication and software-quality work performed **after** the closed v2.2
scientific experiment. It is not a phase, amendment, or result of the locked experiment.

## Immutable scientific record

- Freeze: `prism-ads-v2.2-20260904-8d98593fabdf-r2`.
- Locked run: `locked-r2-20260904-001`.
- Final decision: `RETAIN_BASELINE`; PRISM-HB remains `NON_PROMOTABLE`.
- Locked result: weighted RMSE improved 7.87%, while 70.6% coverage failed the frozen 80% gate.
- Original scientific source Git identity: unborn HEAD.
- First post-study publication snapshot: `b751e67` (`PRISM-Ads v2.2 locked research release`).
- Local provenance tag: `prism-ads-v2.2-locked`.
- Original repository branch coverage: 55%.

## Freeze-bound exclusion set

The active verifier passed 23/23 before hardening. These paths are excluded from modification:

| Freeze-bound path | Starting SHA-256 |
|---|---|
| `configs/frozen_protocol_v2.yaml` | `edf86c90adab3efdccdb78648f52151c060d0d52c20ae73ed290c4492124a243` |
| `artifacts/qualification/P12/freeze_manifest.json` | `9c00ab603e67997f014cb4dee65e5d5d29145bb24431b2a1b5ed3d37150ee2c6` |
| `src/prism_ads/experiments/p13_locked_primary.py` | `7ccfcdc55bceea2993231eb5f37ee267b458d9900de87743ba58760aafe0afb4` |
| `configs/frozen_protocol.yaml` | `6bdcc05577e42aa26dd19d644ff0005b267e326be13d660e47844f8f00e38329` |
| `configs/analysis_plan.yaml` | `abf9c8396186d5c131964298cc28eeae87ac830e0140ed2eccea5e1b40a004bc` |
| `configs/role_definitions.yaml` | `71efe56ff4194205ff33395c5b024b834ead50989f71a2a78440e890f6c7cf5c` |
| `configs/t3_generator.yaml` | `470ff3359e40062d5e5e1d29e1179f7f88df84bfeb75496ef8fc087fea0176ed` |
| `data/validated/t1_uplift_roles.parquet` | `14190421e3f8103815ba4e4c4b58d6d194dcde3137cd3ce8e2b273a777499c9c` |
| `data/validated/t2_attribution_roles.parquet` | `77378feff7cd6b20d83eb9a2d44850779399f877b07185485550fbf96b63cd09` |
| `data/validated/t3_structure.parquet` | `9094a79407a8f3d717701c83e9fc14ca776691b846da23307115a460f60e3a9f` |
| `data/validated/t3_observations.parquet` | `9e2d34f5760512a97bf5bb1bf195ce340266c3a8eb26e2d9f4b1d92867bf717b` |
| `artifacts/qualification/P05/sealed_truth/t3_campaign_segment_truth.parquet` | `cff782270843a4d8fef2a75ed7f27752164686d96f1f5c8a8076379ffaf806f2` |
| `artifacts/development/P10/contribution_bound_analysis.json` | `a98c073aaaa7e19e3be4e9903caaae55c5f213c79cb6de1a7222893edc433aa7` |
| `artifacts/development/P10/method_selection_v3.json` | `04c13739ee208565bbe4d99a1f0fa4143f88a0fe8044fbc61a5f8011397839c9` |
| `artifacts/qualification/P11/qualification_summary.json` | `8d98593fabdf83e0563a0daf6db7535557c7b9d24aeed009f7ba0c1f8cf9e341` |
| `artifacts/qualification/P11/privacy_release.json` | `16ae3196efad9ff9e3ee9701f5b37cb743ee0b7865561999b046314e2eb93939` |
| `artifacts/qualification/P11/privacy_accounting.json` | `a06d637081967f26b54919c1cb57474fb0735366425ca0052c8ed7e03df893d5` |
| `reports/COMPUTE_BUDGET_DECISION.md` | `3310266ee2dd1dd1fa6e611e085065ae3d3000103ccb9bf5095e97544061b63c` |
| `src/prism_ads/models/prism_hb.py` | `51299c8be69ec54c8bd53cec16e5e899aaedc016c1f0d92629e52dd39628636c` |
| `src/prism_ads/privacy/engine.py` | `4a504ff3e377146114d2d23107a09acbf6dbb875e3a93794d5b2f52f3dea1d4b` |
| `src/prism_ads/causal/estimators.py` | `7cdf3e41e9aa320959e6228d93024684b9c759f2b020972d2c6880d4d3c17f3a` |
| `src/prism_ads/experiments/p10_development.py` | `560fd21e087ac7b46fd20dd8db201d05446132250218b7d481ceb58566272fb4` |
| `src/prism_ads/experiments/p11_qualification.py` | `eedf9ae2fd0b6a3f9543eb77dfc96a528a8fb6196913a8f8480f6e2ebf4d5209` |

Locked result artifacts are also treated as immutable even where the manifest binds their input
runner rather than listing each output directly.

## Hardening goals and work

- Add deterministic edge, failure, resume, lineage, privacy, attribution, and model tests.
- Raise meaningful coverage without changing any scientific implementation.
- Audit secrets, public data redistribution, file size, local paths, dependencies, and licenses.
- Improve README, runbook, claim ledger, interview notes, resume bullets, and dashboard QA.
- Design—but do not execute—a clean v2.3 calibration study.

## Closeout

- Added 38 meaningful deterministic tests covering controller/resume failures, registry/hash
  corruption, freeze edge cases, downloader retry/resume validation, local DuckDB/Parquet lineage,
  split-role helpers, contribution/privacy boundaries, attribution/decision errors, T3 truth
  separation, all hierarchical-model branches, and release claims/accessibility.
- Final suite: 69 passed; measured branch/line coverage: **90%**, up from 55% and above the 80%
  target. Coverage was raised only through tests and unbound testing infrastructure.
- Ruff: PASS. Strict mypy over `src` and `tools`: PASS. Dependency consistency: PASS.
- Publication scanner: PASS with zero secret, entropy, sensitive-filename, binary, large-file, or
  raw/derived-data candidates. Four absolute local paths remain as required historical provenance.
- Data terms: upstream CC BY-NC-SA 4.0 terms and citation requirements documented; row-level data
  remains ignored and untracked.
- Presentation: README/runbook/claims/resume/interview packages hardened; 15 SVGs received ordered
  axes, numeric ticks, accessible descriptions, hash/lineage checks, and dashboard integration.
- Browser limitation: no in-app browser backend was available, so live cross-browser rendering
  remains a manual check; deterministic HTML/XML/link/accessibility tests pass.
- V2.3: design-only uncertainty-calibration plan created; no old locked-final tuning or new
  scientific execution occurred.
- Git: initial post-study snapshot `b751e67` and `prism-ads-v2.2-locked` tag preserved. The second
  hardening commit is this record's containing commit; local tag `prism-ads-v2.2-portfolio` marks
  it. Nothing was pushed.

Publication disposition: Apache-2.0 now covers original PRISM-Ads source code only; Criteo and
other third-party materials remain under upstream terms with no implied license grant. The
repository is technically ready, but public push should wait for confirmation that exposure of the
configured author email is intentional.
