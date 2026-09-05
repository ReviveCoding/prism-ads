from __future__ import annotations

import gzip
import io
import json
import urllib.error
import zipfile
from pathlib import Path

import pytest

from prism_ads.data import downloader
from prism_ads.data.downloader import DatasetSpec, DownloadValidationError

SPEC = DatasetSpec(
    "X",
    "fixture",
    "https://example.test",
    "https://example.test/x",
    "x.gz",
    "gzip",
    ("application/gzip",),
)


class Response(io.BytesIO):
    def __init__(
        self, body: bytes, status: int = 200, headers: dict[str, str] | None = None
    ) -> None:
        super().__init__(body)
        self.status = status
        self.headers = headers or {
            "Content-Type": "application/gzip",
            "Content-Length": str(len(body)),
        }

    def geturl(self) -> str:
        return "https://cdn.example.test/x"

    def __enter__(self) -> Response:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def test_download_existing_file_is_hashed(tmp_path: Path) -> None:
    target = tmp_path / SPEC.filename
    target.write_bytes(b"existing")
    result = downloader.download(SPEC, tmp_path)
    assert result["retrieval_status"] == "existing_file_verified"
    assert result["bytes"] == 8


def test_download_rejects_html_content_type_and_truncation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    responses = [
        Response(b"<html>error</html>", headers={"Content-Type": "text/html"}),
        Response(b"short", headers={"Content-Type": "application/gzip", "Content-Length": "99"}),
    ]
    monkeypatch.setattr(
        downloader.urllib.request, "urlopen", lambda *_args, **_kwargs: responses.pop(0)
    )
    monkeypatch.setattr(downloader.time, "sleep", lambda _seconds: None)
    with pytest.raises(DownloadValidationError, match="truncated transfer"):
        downloader.download(SPEC, tmp_path, retries=2)


def test_download_resumes_206_and_restarts_on_200(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    part = tmp_path / f"{SPEC.filename}.part"
    part.write_bytes(b"abc")
    response = Response(
        b"def",
        status=206,
        headers={
            "Content-Type": "application/gzip",
            "Content-Length": "3",
            "Content-Range": "bytes 3-5/6",
        },
    )
    monkeypatch.setattr(downloader.urllib.request, "urlopen", lambda *_args, **_kwargs: response)
    result = downloader.download(SPEC, tmp_path, retries=1)
    assert Path(str(result["path"])).read_bytes() == b"abcdef"
    (tmp_path / SPEC.filename).unlink()
    part.write_bytes(b"stale")
    response2 = Response(b"fresh")
    monkeypatch.setattr(downloader.urllib.request, "urlopen", lambda *_args, **_kwargs: response2)
    downloader.download(SPEC, tmp_path, retries=1)
    assert (tmp_path / SPEC.filename).read_bytes() == b"fresh"


def test_download_exhausts_network_retries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        downloader.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(urllib.error.URLError("offline")),
    )
    monkeypatch.setattr(downloader.time, "sleep", lambda _seconds: None)
    with pytest.raises(DownloadValidationError, match="after 3 attempts"):
        downloader.download(SPEC, tmp_path, retries=3)


def test_validate_nested_gzip_and_unknown_archive(tmp_path: Path) -> None:
    nested = io.BytesIO()
    with gzip.GzipFile(fileobj=nested, mode="wb") as handle:
        handle.write(b"nested")
    archive_path = tmp_path / "sample.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("folder/", b"")
        archive.writestr("data.tsv.gz", nested.getvalue())
    result = downloader.validate_archive(archive_path, "zip")
    assert result["nested_gzip_uncompressed_bytes"] == {"data.tsv.gz": 6}
    with pytest.raises(DownloadValidationError, match="unknown archive"):
        downloader.validate_archive(archive_path, "tar")


def test_acquire_reuses_verified_manifest_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = tmp_path / "data" / "raw" / SPEC.filename
    raw.parent.mkdir(parents=True)
    with gzip.open(raw, "wb") as handle:
        handle.write(b"x")
    digest = downloader._sha256(raw)
    manifest_path = tmp_path / "data" / "manifests" / "x_raw_manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps({"acquisition": {"sha256": digest, "etag": "old"}}), encoding="utf-8"
    )
    monkeypatch.setattr(
        downloader,
        "download",
        lambda *_args, **_kwargs: {
            "path": str(raw),
            "sha256": digest,
            "bytes": raw.stat().st_size,
            "retrieval_status": "existing_file_verified",
        },
    )
    result = downloader.acquire_dataset(SPEC, tmp_path)
    assert result["acquisition"]["etag"] == "old"  # type: ignore[index]
    assert result["validation"]["archive_integrity"] == "PASS"  # type: ignore[index]
