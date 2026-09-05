from __future__ import annotations

import hashlib
import json
from pathlib import Path

from prism_ads.governance.freeze import verify_freeze_manifest


def test_freeze_manifest_detects_hash_change(tmp_path: Path) -> None:
    artifact = tmp_path / "value.txt"
    artifact.write_text("frozen", encoding="utf-8")
    digest = hashlib.sha256(b"frozen").hexdigest()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "freeze_id": "test-freeze",
                "artifacts": [{"path": "value.txt", "sha256": digest}],
            }
        ),
        encoding="utf-8",
    )
    assert verify_freeze_manifest(tmp_path, manifest)["status"] == "PASS"
    artifact.write_text("changed", encoding="utf-8")
    assert verify_freeze_manifest(tmp_path, manifest)["status"] == "FAIL"


def test_repository_freeze_manifest() -> None:
    result = verify_freeze_manifest(Path.cwd())
    assert result["status"] == "PASS", result["errors"]
