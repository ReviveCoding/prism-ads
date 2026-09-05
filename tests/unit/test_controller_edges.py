from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from prism_ads.pipeline import __main__ as pipeline_main
from prism_ads.pipeline.controller import ProjectController, StateValidationError


def state(**updates: object) -> dict[str, object]:
    value: dict[str, object] = {
        "spec_version": "2.2",
        "state_version": 1,
        "current_phase": "P03",
        "last_completed_phase": "P02",
        "status": "ready",
        "scientific_status": "UNFROZEN",
        "freeze_id": None,
        "locked_run_id": None,
        "locked_started": False,
        "locked_completed": False,
        "datasets": {},
        "environment": {},
        "mandatory_blockers": [],
        "optional_skips": [],
        "updated_at": "2026-01-01T00:00:00Z",
    }
    value.update(updates)
    return value


def repository(tmp_path: Path, state_value: object | None = None) -> Path:
    (tmp_path / "PROJECT_STATE.json").write_text(
        json.dumps(state() if state_value is None else state_value), encoding="utf-8"
    )
    (tmp_path / "ARTIFACT_REGISTRY.json").write_text(
        json.dumps({"artifacts": []}), encoding="utf-8"
    )
    (tmp_path / "PHASE_LEDGER.jsonl").write_text('{"phase":"P02"}\n', encoding="utf-8")
    return tmp_path


def test_discover_rejects_missing_or_malformed_state(tmp_path: Path) -> None:
    with pytest.raises(StateValidationError, match="not found"):
        ProjectController.discover(tmp_path)
    (tmp_path / "PROJECT_STATE.json").write_text("[1]", encoding="utf-8")
    with pytest.raises(StateValidationError, match="expected JSON object"):
        ProjectController.discover(tmp_path)
    (tmp_path / "PROJECT_STATE.json").write_text("{", encoding="utf-8")
    with pytest.raises(StateValidationError, match="cannot read valid JSON"):
        ProjectController.discover(tmp_path)


def test_validate_state_reports_all_structural_errors(tmp_path: Path) -> None:
    broken = state(spec_version="2.1", current_phase="P99", mandatory_blockers="none")
    del broken["updated_at"]
    controller = ProjectController(tmp_path, broken)
    errors = controller.validate_state()
    assert any("missing state fields" in error for error in errors)
    assert "spec_version must equal 2.2" in errors
    assert any("invalid current_phase" in error for error in errors)
    assert "mandatory_blockers must be a list" in errors


def test_registry_and_ledger_failure_modes_are_reported(tmp_path: Path) -> None:
    root = repository(tmp_path)
    good = root / "good.txt"
    good.write_text("good", encoding="utf-8")
    entries = [
        {"path": "good.txt", "sha256": hashlib.sha256(b"bad").hexdigest()},
        {"path": "missing.txt", "sha256": "0" * 64},
        {"path": "../escape.txt", "sha256": "0" * 64},
        {"path": 1, "sha256": None},
    ]
    (root / "ARTIFACT_REGISTRY.json").write_text(
        json.dumps({"artifacts": entries}), encoding="utf-8"
    )
    result = ProjectController.discover(root).verify()
    assert result["status"] == "FAIL"
    assert any("hash mismatch" in error for error in result["errors"])
    assert any("missing" in error for error in result["errors"])
    assert any("escapes" in error for error in result["errors"])
    assert any("lacks string" in error for error in result["errors"])
    (root / "PHASE_LEDGER.jsonl").write_text("not-json", encoding="utf-8")
    assert any(
        "invalid phase ledger" in error
        for error in ProjectController.discover(root).verify()["errors"]
    )


def test_registry_shape_and_empty_ledger_are_rejected(tmp_path: Path) -> None:
    root = repository(tmp_path)
    (root / "ARTIFACT_REGISTRY.json").write_text("{}", encoding="utf-8")
    with pytest.raises(StateValidationError, match="artifacts list"):
        ProjectController.discover(root).verify()
    (root / "ARTIFACT_REGISTRY.json").write_text('{"artifacts":[]}', encoding="utf-8")
    (root / "PHASE_LEDGER.jsonl").write_text("", encoding="utf-8")
    assert "phase ledger is empty" in ProjectController.discover(root).verify()["errors"]


def test_assert_runnable_enforces_integrity_blockers_and_phase(tmp_path: Path) -> None:
    root = repository(tmp_path)
    controller = ProjectController.discover(root)
    controller.assert_runnable("P03")
    with pytest.raises(StateValidationError, match="first incomplete"):
        controller.assert_runnable("P04")
    controller.state["mandatory_blockers"] = ["stop"]
    with pytest.raises(StateValidationError, match="blockers"):
        controller.assert_runnable("P03")
    controller.state["mandatory_blockers"] = []
    (root / "PHASE_LEDGER.jsonl").write_text("", encoding="utf-8")
    with pytest.raises(StateValidationError, match="verification failed"):
        controller.assert_runnable("P03")


def test_pipeline_cli_status_verify_resume_and_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = repository(tmp_path)
    monkeypatch.chdir(root)
    assert pipeline_main.main(["status"]) == 0
    assert '"project": "PRISM-Ads"' in capsys.readouterr().out
    assert pipeline_main.main(["verify"]) == 0
    assert pipeline_main.main(["run", "--resume"]) == 0
    assert '"phase": "P03"' in capsys.readouterr().out
    assert pipeline_main.main(["run", "--phase", "P04"]) == 1
    assert '"status": "FAIL"' in capsys.readouterr().out
