# Public-Repository Readiness Audit

Scope: the first local Git snapshot plus current post-release hardening candidates. This is a
publication/security audit, not scientific evidence.

## Secrets and local state

The project-local scanner checks sensitive filenames, common key/token/password formats,
high-entropy non-hash strings, binary files, file size, personal absolute paths, and candidate data
extensions. Result: **PASS**—zero regex secret hits, high-entropy candidates, sensitive filenames,
or hidden binary candidates. The exact machine-readable result is
`artifacts/post_release/publication_scan.json`.

This heuristic is defensible but not exhaustive. A hosting platform's secret scanner and a manual
review of the final snapshot remain required. The public branch is constructed as a sanitized root
commit using the authenticated GitHub account's noreply address; local preservation history and
its author metadata are not published.

## Data governance and tracked files

- No `data/raw`, `data/staged`, `data/validated`, `data/marts`, or `data/released` file is tracked
  or a current candidate.
- No Parquet, DuckDB, Criteo ZIP/GZIP, model checkpoint, virtual environment, cache, coverage data,
  crash dump, or log is a current candidate.
- Tracked data consists only of a tiny synthetic fixture, manifests, schemas, hashes, and aggregate
  diagnostics/results.
- `.gitignore` explicitly excludes source/derived data, local environments, package/model caches,
  partial downloads, checkpoints, secrets filenames, logs, dumps, and test/tool caches.

The scanner found four personal absolute-path occurrences: the immutable governing prompt and its
copy name the original project root, while two raw manifests preserve acquisition provenance. They
contain only the local username/path—not a credential—and are retained for historical integrity.

## Large files

No tracked or untracked publication candidate exceeds 1 MiB. The large raw and intermediate Criteo
files remain local and ignored. This reduces accidental redistribution and ordinary Git-hosting
limits; aggregate JSON diagnostics are retained.

## License and data terms

The official [uplift dataset](https://ailab.criteo.com/criteo-uplift-prediction-dataset/) and
[attribution dataset](https://ailab.criteo.com/criteo-attribution-modeling-bidding-dataset/) pages
publish Criteo Data Terms of Use based on
[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) and request paper citation.
The repository does not redistribute the datasets. Any user must independently accept and follow
the current upstream terms.

The original PRISM-Ads source code is licensed under Apache-2.0, declared with SPDX metadata in
`pyproject.toml` and accompanied by the unmodified license text in `LICENSE`. This grant applies
only to original PRISM-Ads source code. It does not apply to Criteo datasets, third-party datasets,
or upstream material, and no license grant for those materials is implied.

## Remaining manual checks and disposition

1. Review the repository host's secret/dependency scanners and security settings after upload.
2. Monitor ordinary CI, CodeQL, and Dependabot after the sanitized snapshot reaches GitHub.
3. Browser automation was unavailable during the final pass. The user supplied and approved a
   successful live rendering inspection; deterministic markup/link/SVG checks were also completed.

**Disposition: ready for sanitized public-repository publication.** Remote outcomes are recorded in
`PUBLICATION_PROVENANCE.md` after GitHub reports them.
