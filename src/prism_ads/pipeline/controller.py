"""Read-only verification primitives for the persistent project controller."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REQUIRED_STATE_FIELDS = {
    "spec_version",
    "state_version",
    "current_phase",
    "last_completed_phase",
    "status",
    "scientific_status",
    "freeze_id",
    "locked_run_id",
    "locked_started",
    "locked_completed",
    "datasets",
    "environment",
    "mandatory_blockers",
    "optional_skips",
    "updated_at",
}


class StateValidationError(RuntimeError):
    """Raised when persisted governance state is inconsistent."""


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StateValidationError(f"cannot read valid JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise StateValidationError(f"expected JSON object in {path}")
    return value


@dataclass
class ProjectController:
    root: Path
    state: dict[str, Any]

    @classmethod
    def discover(cls, start: Path | None = None) -> ProjectController:
        cursor = (start or Path.cwd()).resolve()
        for root in (cursor, *cursor.parents):
            state_path = root / "PROJECT_STATE.json"
            if state_path.is_file():
                return cls(root=root, state=_load_json(state_path))
        raise StateValidationError("PROJECT_STATE.json not found in current path or its parents")

    def validate_state(self) -> list[str]:
        errors: list[str] = []
        missing = sorted(REQUIRED_STATE_FIELDS - self.state.keys())
        if missing:
            errors.append(f"missing state fields: {', '.join(missing)}")
        if self.state.get("spec_version") != "2.2":
            errors.append("spec_version must equal 2.2")
        current = self.state.get("current_phase")
        if current not in {f"P{i:02d}" for i in range(18)}:
            errors.append(f"invalid current_phase: {current!r}")
        if not isinstance(self.state.get("mandatory_blockers"), list):
            errors.append("mandatory_blockers must be a list")
        return errors

    def _registry_entries(self) -> list[dict[str, Any]]:
        registry = _load_json(self.root / "ARTIFACT_REGISTRY.json")
        entries = registry.get("artifacts")
        if not isinstance(entries, list):
            raise StateValidationError("artifact registry must contain an artifacts list")
        return entries

    def verify(self) -> dict[str, Any]:
        errors = self.validate_state()
        checked = 0
        for entry in self._registry_entries():
            relative = entry.get("path")
            expected = entry.get("sha256")
            if not isinstance(relative, str) or not isinstance(expected, str):
                errors.append("registry entry lacks string path/sha256")
                continue
            path = (self.root / relative).resolve()
            try:
                path.relative_to(self.root)
            except ValueError:
                errors.append(f"registry path escapes project root: {relative}")
                continue
            if not path.is_file():
                errors.append(f"registered artifact missing: {relative}")
                continue
            actual = sha256_file(path)
            checked += 1
            if actual != expected.lower():
                errors.append(f"hash mismatch: {relative}")

        ledger_path = self.root / "PHASE_LEDGER.jsonl"
        try:
            lines = ledger_path.read_text(encoding="utf-8").splitlines()
            ledger_rows = [json.loads(line) for line in lines if line]
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"invalid phase ledger: {exc}")
            ledger_rows = []
        if not ledger_rows:
            errors.append("phase ledger is empty")

        return {
            "status": "PASS" if not errors else "FAIL",
            "registered_artifacts_checked": checked,
            "ledger_records": len(ledger_rows),
            "errors": errors,
        }

    def status(self) -> dict[str, Any]:
        verification = self.verify()
        return {
            "project": "PRISM-Ads",
            "root": str(self.root),
            "state": self.state,
            "controller_verification": verification,
        }

    def assert_runnable(self, phase: str) -> None:
        verification = self.verify()
        if verification["status"] != "PASS":
            raise StateValidationError("controller verification failed")
        if self.state.get("mandatory_blockers"):
            raise StateValidationError("mandatory blockers must be resolved before execution")
        if phase != self.state.get("current_phase"):
            raise StateValidationError(
                f"phase {phase} is not the first incomplete phase {self.state.get('current_phase')}"
            )
