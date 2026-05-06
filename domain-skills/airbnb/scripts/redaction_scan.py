"""Scan committed Airbnb skill artifacts for raw private identifiers."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


DEFAULT_TARGETS = [
    Path("agent-workspace/domain-skills/airbnb/fixtures"),
    Path("agent-workspace/domain-skills/airbnb/schemas"),
    Path("agent-workspace/domain-skills/airbnb"),
]

SKIP_DIRS = {
    ".private-data",
    ".session-store",
    "__pycache__",
}

TEXT_SUFFIXES = {".json", ".jsonl", ".csv", ".md", ".txt", ".schema", ".py"}


def _load_local_module(module_filename, module_name):
    path = Path("agent-workspace/domain-skills/airbnb/scripts") / module_filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_integrity = _load_local_module("run_integrity.py", "airbnb_run_integrity")


def iter_scan_files(paths):
    seen = set()
    for root in paths:
        root = Path(root)
        if not root.exists():
            continue
        candidates = root.rglob("*") if root.is_dir() else [root]
        for path in candidates:
            if not path.is_file():
                continue
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            if path.suffix.lower() not in TEXT_SUFFIXES and not path.name.endswith(".schema.json"):
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            yield path


def scan_paths(paths):
    findings = []
    for path in iter_scan_files(paths):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        findings.extend(_integrity.scan_text_for_redaction_findings(text, source_path=path))
    return _integrity.redaction_scan_record(findings)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    paths = [Path(arg) for arg in argv] if argv else DEFAULT_TARGETS
    result = scan_paths(paths)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if result["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
