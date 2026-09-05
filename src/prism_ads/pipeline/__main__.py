"""Run the PRISM-Ads persistent pipeline controller."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from prism_ads.pipeline.controller import ProjectController, StateValidationError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m prism_ads.pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status", help="show persisted project state")
    subparsers.add_parser("verify", help="verify controller and registered artifacts")

    run = subparsers.add_parser("run", help="run a phase or resume the first incomplete phase")
    choice = run.add_mutually_exclusive_group(required=True)
    choice.add_argument("--phase", choices=[f"P{i:02d}" for i in range(18)])
    choice.add_argument("--resume", action="store_true")

    subparsers.add_parser("qualify", help="run the P11 qualification gate")
    subparsers.add_parser("freeze", help="create and verify the P12 scientific freeze")
    subparsers.add_parser("run-locked", help="execute the immutable P13 locked primary")
    subparsers.add_parser("analyze", help="run canonical post-processing and analysis")
    subparsers.add_parser("report", help="generate portfolio release artifacts")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    controller = ProjectController.discover()
    try:
        if args.command == "status":
            print(json.dumps(controller.status(), indent=2, sort_keys=True))
            return 0
        if args.command == "verify":
            result = controller.verify()
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0 if result["status"] == "PASS" else 1

        target = {
            "qualify": "P11",
            "freeze": "P12",
            "run-locked": "P13",
            "analyze": "P15",
            "report": "P17",
        }.get(args.command)
        if args.command == "run":
            target = controller.state["current_phase"] if args.resume else args.phase
        assert target is not None
        controller.assert_runnable(target)
        print(json.dumps({"status": "READY", "phase": target}, indent=2))
        return 0
    except StateValidationError as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
