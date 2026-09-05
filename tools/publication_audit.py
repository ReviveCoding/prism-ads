"""Defensible local scanner for a candidate public Git snapshot."""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

SECRET_PATTERNS = {
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "github_token": re.compile(r"\bgh[oprsu]_[A-Za-z0-9]{20,}\b"),
    "openai_key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "assigned_secret": re.compile(
        r"(?i)\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)\b"
        r"\s*[:=]\s*['\"]([^'\"]{8,})['\"]"
    ),
}
SENSITIVE_NAMES = re.compile(
    r"(?i)(^|/)(?:\.env(?:\..*)?|id_rsa|id_ed25519|credentials.*|secrets?.*|.*\.(?:pem|p12|pfx|key))$"
)
TOKEN = re.compile(r"[A-Za-z0-9_+/=-]{32,}")
HEX_DIGEST = re.compile(r"[0-9a-fA-F]{32,64}")


def entropy(value: str) -> float:
    counts = Counter(value)
    return -sum((count / len(value)) * math.log2(count / len(value)) for count in counts.values())


def candidate_files(root: Path) -> list[str]:
    output = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        text=True,
    )
    return sorted(set(output.splitlines()))


def scan(root: Path) -> dict[str, Any]:
    root = root.resolve()
    files = candidate_files(root)
    regex_hits: list[dict[str, object]] = []
    entropy_hits: list[dict[str, object]] = []
    personal_paths: list[dict[str, object]] = []
    binaries: list[dict[str, object]] = []
    large_files: list[dict[str, object]] = []
    sensitive_names = [name for name in files if SENSITIVE_NAMES.search(name)]
    for name in files:
        path = root / name
        if not path.is_file():
            continue
        size = path.stat().st_size
        if size > 1024 * 1024:
            large_files.append({"path": name, "bytes": size})
        content = path.read_bytes()
        if b"\0" in content:
            binaries.append({"path": name, "bytes": size})
            continue
        text = content.decode("utf-8", errors="replace")
        for line_number, line in enumerate(text.splitlines(), 1):
            for kind, pattern in SECRET_PATTERNS.items():
                if pattern.search(line):
                    regex_hits.append({"path": name, "line": line_number, "kind": kind})
            if re.search(r"(?i)[A-Z]:(?:\\\\){1,2}Users(?:\\\\){1,2}[^\\]+", line):
                personal_paths.append({"path": name, "line": line_number})
            for value in TOKEN.findall(line):
                if (
                    entropy(value) >= 4.7
                    and not HEX_DIGEST.fullmatch(value)
                    and not value.startswith(("http", "prism-ads"))
                ):
                    entropy_hits.append({"path": name, "line": line_number, "prefix": value[:8]})
    raw_or_derived = [
        name
        for name in files
        if re.match(r"data/(?:raw|staged|validated|marts|released)/", name)
        or name.endswith((".parquet", ".duckdb"))
    ]
    return {
        "scanner": "project-local regex, filename, entropy, path, binary, and size audit",
        "limitations": [
            "Heuristic scanning cannot prove the absence of every secret.",
            "Entropy matches require manual review and can include scientific identifiers.",
            "Git history and hosting-platform scanners should be reviewed before publication.",
        ],
        "candidate_file_count": len(files),
        "regex_secret_hits": regex_hits,
        "high_entropy_candidates": entropy_hits,
        "sensitive_filenames": sensitive_names,
        "personal_absolute_paths": personal_paths,
        "large_files_over_1MiB": large_files,
        "binary_files": binaries,
        "raw_or_derived_data_candidates": raw_or_derived,
        "status": "PASS"
        if not regex_hits and not sensitive_names and not raw_or_derived
        else "REVIEW",
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = scan(args.root)
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
