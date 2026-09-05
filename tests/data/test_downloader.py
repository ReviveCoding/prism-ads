from __future__ import annotations

import gzip
import zipfile
from pathlib import Path

from prism_ads.data.downloader import validate_archive


def test_validate_gzip(tmp_path: Path) -> None:
    target = tmp_path / "sample.csv.gz"
    with gzip.open(target, "wb") as handle:
        handle.write(b"x,y\n1,2\n")
    result = validate_archive(target, "gzip")
    assert result["archive_integrity"] == "PASS"
    assert result["uncompressed_bytes"] == 8


def test_validate_zip(tmp_path: Path) -> None:
    target = tmp_path / "sample.zip"
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("sample.csv", "x,y\n1,2\n")
    result = validate_archive(target, "zip")
    assert result["archive_integrity"] == "PASS"
    assert result["members"] == ["sample.csv"]


def test_validate_nested_gzip_in_zip(tmp_path: Path) -> None:
    compressed = gzip.compress(b"x,y\n1,2\n")
    target = tmp_path / "sample.zip"
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("sample.tsv.gz", compressed)
    result = validate_archive(target, "zip")
    assert result["nested_gzip_integrity"] == "PASS"
    assert result["nested_gzip_uncompressed_bytes"] == {"sample.tsv.gz": 8}
