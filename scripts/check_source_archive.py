#!/usr/bin/env python3
"""Fail source archives that contain private/session artifacts or raw auth data."""

from __future__ import annotations

import argparse
import json
import re
import tarfile
import zipfile
from pathlib import Path

FORBIDDEN_PATH_PARTS = {
    ".git",
    ".private-data",
    ".session-store",
    ".env",
}
FORBIDDEN_NAME_RE = re.compile(r"(raw[-_]?capture|browser[-_]?profile)", re.I)
FORBIDDEN_CONTENT_RE = re.compile(
    r'(csrf_token|ddweb_token|cf_clearance)',
    re.I,
)
CONTENT_SCAN_EXTENSIONS = {".json", ".jsonl", ".txt", ".csv", ".har", ".env"}
_SENSITIVE_JSON_KEYS = {"Cookie", "Authorization"}


def _archive_members(path: Path):
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            for member in zf.infolist():
                if member.is_dir():
                    yield member.filename, b""
                    continue
                data = zf.read(member.filename) if member.file_size <= 1_000_000 else b""
                yield member.filename, data
        return
    if tarfile.is_tarfile(path):
        with tarfile.open(path) as tf:
            for member in tf.getmembers():
                data = b""
                if member.isfile() and member.size <= 1_000_000:
                    f = tf.extractfile(member)
                    data = f.read() if f else b""
                yield member.name, data
        return
    raise ValueError(f"unsupported archive type: {path}")


def _json_has_raw_auth(value) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in _SENSITIVE_JSON_KEYS:
                return not (isinstance(item, str) and item.startswith("<redacted:"))
            if _json_has_raw_auth(item):
                return True
    elif isinstance(value, list):
        return any(_json_has_raw_auth(item) for item in value)
    return False


def _has_raw_auth_content(text: str, suffix: str) -> bool:
    if suffix == ".json":
        try:
            return _json_has_raw_auth(json.loads(text)) or bool(FORBIDDEN_CONTENT_RE.search(text))
        except json.JSONDecodeError:
            pass
    if suffix == ".jsonl":
        try:
            parsed_lines = [
                json.loads(line)
                for line in text.splitlines()
                if line.strip()
            ]
        except json.JSONDecodeError:
            pass
        else:
            return any(_json_has_raw_auth(line) for line in parsed_lines) or bool(FORBIDDEN_CONTENT_RE.search(text))
    has_raw_cookie = '"Cookie"' in text and '"Cookie": "<redacted:' not in text
    has_raw_authorization = '"Authorization"' in text and '"Authorization": "<redacted:' not in text
    return has_raw_cookie or has_raw_authorization or bool(FORBIDDEN_CONTENT_RE.search(text))


def archive_violations(path: Path) -> list[str]:
    violations = []
    for name, data in _archive_members(path):
        parts = set(Path(name).parts)
        if parts & FORBIDDEN_PATH_PARTS:
            violations.append(f"{name}: forbidden private path")
            continue
        if FORBIDDEN_NAME_RE.search(Path(name).name):
            violations.append(f"{name}: forbidden sensitive filename")
        if data and Path(name).suffix.lower() in CONTENT_SCAN_EXTENSIONS:
            try:
                text = data.decode("utf-8", "replace")
            except Exception:
                text = ""
            if text and _has_raw_auth_content(text, Path(name).suffix.lower()):
                violations.append(f"{name}: forbidden auth-like content")
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("archives", nargs="+", type=Path)
    args = parser.parse_args(argv)

    results = {str(path): archive_violations(path) for path in args.archives}
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for archive, violations in results.items():
            for violation in violations:
                print(f"{archive}: {violation}")
    return 1 if any(results.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
