#!/usr/bin/env python3
"""Run the repo-native browser-harness quality gate."""

from __future__ import annotations

import argparse
import fnmatch
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


DEFAULT_PYTEST = ["uv", "run", "--group", "dev", "pytest", "-q"]


def release_proof_command() -> list[str]:
    candidates = [
        sys.executable,
        getattr(sys, "_base_executable", None),
        shutil.which("python3"),
        shutil.which("python"),
        "/opt/homebrew/bin/python3",
        "/usr/bin/python3",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        result = subprocess.run(
            [candidate, "-c", "import venv"],
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            return [candidate, "scripts/release_proof.py", "--json"]
    raise SystemExit("no Python interpreter with stdlib venv module found for release proof")


RELEASE_PROOF = release_proof_command
LIVE_BROWSER_SMOKE = [
    "uv",
    "run",
    "--group",
    "dev",
    "pytest",
    "-q",
    "test_data_display.py::test_render_dataset_browser_smoke_table_profile_and_chart",
]

FORBIDDEN_TRACKED_PARTS = (
    ".private-data/",
    ".session-store/",
    "/outputs/",
    ".beads/",
    ".dolt/",
    "downloaded_files/",
    ".har",
    "Cookies",
    "Login Data",
)

FORBIDDEN_STATUS_DIRS = (
    "build",
    "dist",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "htmlcov",
)


def run(
    cmd: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    echo: bool = True,
) -> subprocess.CompletedProcess[str]:
    started = time.time()
    result = subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    elapsed = time.time() - started
    if echo:
        print(f"$ {' '.join(cmd)}")
        print(result.stdout[-6000:])
        print(f"exit={result.returncode} elapsed={elapsed:.2f}s")
    if result.returncode != 0:
        raise SystemExit(result.returncode)
    return result


def git_paths(root: Path) -> list[str]:
    result = run(["git", "ls-files", "-z"], cwd=root, echo=False)
    return [path for path in result.stdout.split("\0") if path]


def git_status_paths(root: Path) -> list[str]:
    result = run(["git", "status", "--short", "--untracked-files=all"], cwd=root, echo=False)
    paths: list[str] = []
    for line in result.stdout.splitlines():
        if not line:
            continue
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        paths.append(path)
    return paths


def assert_hygiene(root: Path) -> None:
    tracked = git_paths(root)
    forbidden_tracked = [
        path
        for path in tracked
        if any(part in path for part in FORBIDDEN_TRACKED_PARTS)
    ]
    if forbidden_tracked:
        joined = "\n".join(forbidden_tracked[:60])
        raise SystemExit(f"tracked private/generated artifacts found:\n{joined}")

    status_paths = git_status_paths(root)
    generated_status = [path for path in status_paths if is_generated_status_path(path)]
    if generated_status:
        joined = "\n".join(generated_status[:60])
        raise SystemExit(f"generated build/test artifacts present in git status:\n{joined}")

    print("hygiene scan passed")


def is_generated_status_path(path: str) -> bool:
    parts = path.split("/")
    if any(part in FORBIDDEN_STATUS_DIRS for part in parts):
        return True
    if any(part.endswith(".egg-info") for part in parts):
        return True
    return fnmatch.fnmatch(path, ".coverage") or fnmatch.fnmatch(path, ".coverage.*")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-pytest", action="store_true", help="skip the default pytest suite")
    parser.add_argument("--skip-release-proof", action="store_true", help="skip wheel build/install proof")
    parser.add_argument("--live", action="store_true", help="run optional browser-backed live probes")
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parents[1]
    if not args.skip_pytest:
        run(DEFAULT_PYTEST, cwd=root)
    if not args.skip_release_proof:
        run(RELEASE_PROOF(), cwd=root)
    assert_hygiene(root)
    if args.live:
        env = dict(os.environ)
        env["BROWSER_HARNESS_DATA_DISPLAY_BROWSER_SMOKE"] = "1"
        run(LIVE_BROWSER_SMOKE, cwd=root, env=env)
    print("quality gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
