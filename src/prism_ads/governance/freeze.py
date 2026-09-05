"""Scientific-freeze identity verification."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from prism_ads.pipeline.controller import sha256_file


def verify_freeze_manifest(root: Path, manifest_path: Path | None = None) -> dict[str, Any]:
    """Verify every path and digest bound into the freeze manifest."""
    root = root.resolve()
    path = manifest_path or root / "artifacts" / "qualification" / "P12" / "freeze_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []
    freeze_id = manifest.get("freeze_id")
    if not isinstance(freeze_id, str) or not freeze_id:
        errors.append("missing freeze_id")
    for entry in manifest.get("artifacts", []):
        relative = entry.get("path")
        expected = entry.get("sha256")
        if not isinstance(relative, str) or not isinstance(expected, str):
            errors.append("malformed artifact entry")
            continue
        target = (root / relative).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            errors.append(f"path escapes root: {relative}")
            continue
        if not target.is_file():
            errors.append(f"missing: {relative}")
        elif sha256_file(target) != expected:
            errors.append(f"hash mismatch: {relative}")
    return {
        "status": "PASS" if not errors else "FAIL",
        "freeze_id": freeze_id,
        "artifacts_checked": len(manifest.get("artifacts", [])),
        "errors": errors,
    }
