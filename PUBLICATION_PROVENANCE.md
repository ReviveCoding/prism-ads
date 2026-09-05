# Publication Provenance

PRISM-Ads v2.2 is a closed scientific record. The scientific execution originally froze while
Git `HEAD` was unborn. Its scientific identity is therefore the SHA-256-bound freeze
`prism-ads-v2.2-20260904-8d98593fabdf-r2`, not a Git commit. The corresponding locked run is
`locked-r2-20260904-001`, and its final decision remains `RETAIN_BASELINE`; PRISM-HB remains
`NON_PROMOTABLE`.

Local Git history was created after the study solely to preserve and harden the repository. The
public GitHub `main` branch is a sanitized publication snapshot constructed separately from that
history. Its parentless root commit does not retroactively become the original scientific freeze
identity. Existing local scientific and post-release commits and tags remain private and are not
part of the public branch.

The sanitized snapshot changes neither locked scientific results nor their SHA-256 identities. It
contains publication-safe source, tests, aggregate evidence, reports, and presentation assets; it
does not redistribute row-level Criteo data, Parquet/DuckDB data, credentials, or local caches.

## Publication receipt

- Public repository: <https://github.com/ReviveCoding/prism-ads>
- Sanitized public root commit: `b487f9574f5242c7ca9641375faf3f29899ee9f3`
- Published: `2026-09-05T17:31:44Z`
- Scientific freeze: `prism-ads-v2.2-20260904-8d98593fabdf-r2`
- Locked run: `locked-r2-20260904-001`
- GitHub Pages dashboard: <https://revivecoding.github.io/prism-ads/dashboard/>
- Initial root CodeQL: PASS. Initial CPU CI exposed two local-only integrity checks that require
  intentionally unpublished data/state; the public workflow excludes only those checks while
  retaining the complete local gate.
- Public verification commit: `adf8f415b8da652640fbc47809b7f29e37685c34`.
- Remote verification on that commit: CPU CI PASS, CodeQL PASS, and Pages deployment PASS.
- Security: vulnerability alerts, Dependabot security updates, private vulnerability reporting,
  secret scanning, and secret-scanning push protection enabled; initial alert queries returned zero.

The full local Git history and scientific/post-release tags remain private/local. Only the
sanitized `public-main` lineage is published.
