# PRISM-Ads Reproduction Runbook

This runbook separates inexpensive repository verification from the costly scientific workflow.
The v2.2 release is closed; rerunning it reproduces evidence but does not amend the locked result.

## 1. Repository setup

Requirements: Windows or a compatible Python environment, Python 3.12, Git, sufficient local disk
for roughly 1 GB of compressed source data plus multi-GB derived layers, and acceptance of the
upstream Criteo data terms. Python 3.13 is intentionally unsupported.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m prism_ads.pipeline status
.\.venv\Scripts\python.exe -m prism_ads.pipeline verify
```

The recorded environment used DuckDB 1.5.5, dp-accounting 0.6.0, NumPy 2.5.2, PyArrow 23.0.1,
Pyro 1.9.1, scikit-learn 1.9.0, SciPy 1.18.1, and PyTorch 2.14.0+cu130. `pyproject.toml` contains
compatible bounded ranges; the CUDA build is platform-specific and is not assumed by CPU CI.

## 2. Public dataset acquisition

Review `docs/DATA_LICENSES.md` and obtain the two official Criteo research releases. The downloader
uses Python `urllib` HTTPS, validates response type/archive integrity, resumes partial transfers,
and records bytes and SHA-256 identities.

```powershell
.\.venv\Scripts\python.exe -m prism_ads.data.downloader --dataset T1 --root .
.\.venv\Scripts\python.exe -m prism_ads.data.downloader --dataset T2 --root .
```

Raw and derived data remain local and Git-ignored. Expected source metadata and hashes are in
`data/manifests/`; a mismatch must be investigated, never silently accepted.

## 3. CPU smoke and quality checks

The normal test path does not require CUDA or the full datasets. It uses deterministic local
fixtures and mocks for downloader, DuckDB/Parquet, state, lineage, privacy, and model branches.

```powershell
$env:PYTHONHASHSEED="0"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m coverage run --branch -m pytest -q
.\.venv\Scripts\python.exe -m coverage report --fail-under=80
.\.venv\Scripts\python.exe -m ruff check src tests tools
.\.venv\Scripts\python.exe -m mypy src tools
```

## 4. Full scientific reproduction

Read `docs/MASTER_SPEC_V2.md`, `PROJECT_STATE.json`, the phase ledger, receipts, and active freeze
before any full run. Acquire data, then execute phases in order through the CLI/module commands
recorded in receipts. Useful controller entry points are:

```powershell
.\.venv\Scripts\python.exe -m prism_ads.pipeline run --phase P03
.\.venv\Scripts\python.exe -m prism_ads.pipeline run --resume
.\.venv\Scripts\python.exe -m prism_ads.pipeline qualify
.\.venv\Scripts\python.exe -m prism_ads.pipeline freeze
.\.venv\Scripts\python.exe -m prism_ads.pipeline run-locked
.\.venv\Scripts\python.exe -m prism_ads.pipeline analyze
.\.venv\Scripts\python.exe -m prism_ads.pipeline report
```

The recorded primary used an RTX 4090 Laptop GPU, PyTorch 2.14.0+cu130, 30 SVI fits, 500 posterior
draws per fit, and 1,000 nested campaign bootstraps. Primary plus secondary GPU fitting consumed
about 6,053 seconds, excluding acquisition and data preparation. Treat full reproduction as a
multi-hour, high-memory workflow—not a quickstart. Deterministic privacy, sampling, assignment,
outcome, and optimization seeds are fixed in the protocols and receipts.

GPU qualification requires a CUDA-visible PyTorch build and a synchronized tensor operation on
the intended device. A CPU-only environment is supported for tests and repository verification,
not for claiming reproduction of recorded GPU runtimes.

## 5. Reports and dashboard

Open `dashboard/index.html` directly in a browser; it is static and sends no data. Read
`reports/FINAL_STATUS.md` and `reports/CLAIM_LEDGER.md` before reusing a quantitative statement.
Regenerate presentation-only figures from existing locked local artifacts with:

```powershell
.\.venv\Scripts\python.exe -m prism_ads.reporting.release_figures --root .
```

This does not regenerate locked evidence. The canonical Parquet is intentionally excluded from Git
and must be reproduced or restored locally with its registered SHA-256 identity.
