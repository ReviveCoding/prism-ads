"""Resume-safe downloader for official Criteo AI Lab releases."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
import zipfile
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO, cast

USER_AGENT = "PRISM-Ads/0.1 (+public scientific benchmark)"
CHUNK_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class DatasetSpec:
    dataset_id: str
    title: str
    official_page: str
    official_link: str
    filename: str
    archive_type: str
    expected_content_types: tuple[str, ...]


DATASETS = {
    "T1": DatasetSpec(
        dataset_id="T1",
        title="Criteo Uplift Modeling Dataset, corrected release v2.1",
        official_page="https://ailab.criteo.com/criteo-uplift-prediction-dataset/",
        official_link="http://go.criteo.net/criteo-research-uplift-v2.1.csv.gz",
        filename="criteo-uplift-v2.1.csv.gz",
        archive_type="gzip",
        expected_content_types=(
            "application/x-gzip",
            "application/gzip",
            "application/octet-stream",
        ),
    ),
    "T2": DatasetSpec(
        dataset_id="T2",
        title="Criteo Attribution Modeling for Bidding Dataset",
        official_page="https://ailab.criteo.com/criteo-attribution-modeling-bidding-dataset/",
        official_link="http://go.criteo.net/criteo-research-attribution-dataset.zip",
        filename="criteo_attribution_dataset.zip",
        archive_type="zip",
        expected_content_types=("application/zip", "application/octet-stream"),
    ),
}


class DownloadValidationError(RuntimeError):
    """Raised when a response or downloaded object is not the requested dataset."""


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _looks_like_html(prefix: bytes, content_type: str) -> bool:
    sample = prefix.lstrip().lower()
    return "text/html" in content_type.lower() or sample.startswith((b"<!doctype html", b"<html"))


def _copy_response(response: BinaryIO, target: BinaryIO, first: bytes) -> None:
    target.write(first)
    while chunk := response.read(CHUNK_BYTES):
        target.write(chunk)


def download(spec: DatasetSpec, raw_dir: Path, retries: int = 5) -> dict[str, object]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    final_path = raw_dir / spec.filename
    part_path = raw_dir / f"{spec.filename}.part"
    if final_path.exists():
        return {
            "path": str(final_path),
            "bytes": final_path.stat().st_size,
            "sha256": _sha256(final_path),
            "retrieval_status": "existing_file_verified",
        }

    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        offset = part_path.stat().st_size if part_path.exists() else 0
        headers = {"User-Agent": USER_AGENT, "Accept": "application/octet-stream,*/*"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        request = urllib.request.Request(spec.official_link, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                status = response.status
                resolved_url = response.geturl()
                content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip()
                if content_type and content_type not in spec.expected_content_types:
                    raise DownloadValidationError(f"unexpected content type {content_type!r}")
                if offset and status != 206:
                    offset = 0
                mode = "ab" if offset and status == 206 else "wb"
                first = response.read(min(CHUNK_BYTES, 65536))
                if _looks_like_html(first, content_type):
                    raise DownloadValidationError("HTML/error response masquerades as dataset")
                content_range = response.headers.get("Content-Range")
                with part_path.open(mode) as raw_target:
                    target = cast(BinaryIO, raw_target)
                    _copy_response(response, target, first)
                    target.flush()
                    os.fsync(target.fileno())
                expected_remaining = response.headers.get("Content-Length")
                if expected_remaining is not None:
                    expected_total = offset + int(expected_remaining)
                    if part_path.stat().st_size != expected_total:
                        raise DownloadValidationError(
                            f"truncated transfer: {part_path.stat().st_size} != {expected_total}"
                        )
                os.replace(part_path, final_path)
                return {
                    "path": str(final_path),
                    "bytes": final_path.stat().st_size,
                    "sha256": _sha256(final_path),
                    "retrieval_status": "downloaded",
                    "resolved_url": resolved_url,
                    "http_status": status,
                    "content_type": content_type,
                    "content_range": content_range,
                    "etag": response.headers.get("ETag"),
                    "last_modified": response.headers.get("Last-Modified"),
                    "retrieved_at": _utc_now(),
                }
        except (OSError, urllib.error.URLError, DownloadValidationError) as exc:
            last_error = exc
            if attempt == retries:
                break
            time.sleep(min(2 ** (attempt - 1), 16))
    raise DownloadValidationError(f"download failed after {retries} attempts: {last_error}")


def validate_archive(path: Path, archive_type: str) -> dict[str, object]:
    uncompressed_bytes = 0
    member_names: list[str] = []
    nested_gzip_uncompressed_bytes: dict[str, int] = {}
    if archive_type == "gzip":
        with gzip.open(path, "rb") as handle:
            while chunk := handle.read(CHUNK_BYTES):
                uncompressed_bytes += len(chunk)
        member_names = [path.name.removesuffix(".gz")]
    elif archive_type == "zip":
        with zipfile.ZipFile(path) as archive:
            bad_member = archive.testzip()
            if bad_member is not None:
                raise DownloadValidationError(f"ZIP CRC failure: {bad_member}")
            infos = [info for info in archive.infolist() if not info.is_dir()]
            member_names = [info.filename for info in infos]
            uncompressed_bytes = sum(info.file_size for info in infos)
            for info in infos:
                if info.filename.lower().endswith(".gz"):
                    nested_bytes = 0
                    with archive.open(info) as compressed_member:
                        with gzip.GzipFile(fileobj=compressed_member) as nested:
                            while chunk := nested.read(CHUNK_BYTES):
                                nested_bytes += len(chunk)
                    nested_gzip_uncompressed_bytes[info.filename] = nested_bytes
    else:
        raise DownloadValidationError(f"unknown archive type: {archive_type}")
    return {
        "archive_integrity": "PASS",
        "archive_type": archive_type,
        "members": member_names,
        "uncompressed_bytes": uncompressed_bytes,
        "nested_gzip_integrity": "PASS" if nested_gzip_uncompressed_bytes else "NOT_APPLICABLE",
        "nested_gzip_uncompressed_bytes": nested_gzip_uncompressed_bytes,
    }


def acquire_dataset(spec: DatasetSpec, root: Path) -> dict[str, object]:
    result = download(spec, root / "data" / "raw")
    path = Path(str(result["path"]))
    archive = validate_archive(path, spec.archive_type)
    manifest_path = root / "data" / "manifests" / f"{spec.dataset_id.lower()}_raw_manifest.json"
    if manifest_path.is_file() and result.get("retrieval_status") == "existing_file_verified":
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        previous_acquisition = previous.get("acquisition", {})
        if previous_acquisition.get("sha256") == result["sha256"]:
            result = {**previous_acquisition, **result}
    manifest = {
        "manifest_version": 1,
        "dataset": asdict(spec),
        "acquisition": result,
        "validation": archive,
        "logical_immutability": "read_only_after_validation",
    }
    staged = manifest_path.with_suffix(".json.tmp")
    staged.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(staged, manifest_path)
    path.chmod(0o444)
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", choices=["T1", "T2", "all"], default="all")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    selected = DATASETS.values() if args.dataset == "all" else [DATASETS[args.dataset]]
    for spec in selected:
        manifest = acquire_dataset(spec, args.root.resolve())
        print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
