from __future__ import annotations

import json
from pathlib import Path

from prism_ads.pipeline.controller import ProjectController, sha256_file


def test_sha256_file(tmp_path: Path) -> None:
    target = tmp_path / "value.txt"
    target.write_bytes(b"abc")
    assert sha256_file(target) == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_discover_and_validate_state(tmp_path: Path) -> None:
    state = {
        "spec_version": "2.2",
        "state_version": 1,
        "current_phase": "P00",
        "last_completed_phase": None,
        "status": "in_progress",
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
    (tmp_path / "PROJECT_STATE.json").write_text(json.dumps(state), encoding="utf-8")
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    controller = ProjectController.discover(nested)
    assert controller.root == tmp_path
    assert controller.validate_state() == []


def test_repository_controller_verifies() -> None:
    controller = ProjectController.discover()
    result = controller.verify()
    assert result["status"] == "PASS", result["errors"]
