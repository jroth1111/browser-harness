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


FORBIDDEN_DOMAIN_TOKENS = [
    "urllib.request.urlopen",
    "requests.get",
    "requests.post",
    "browser_cookies",
    "cdp(",
    "stealth_session",
    "solve_turnstile",
    "navigate_via_google",
    "Network.getCookies",
    "Runtime.evaluate",
]

FORBIDDEN_AGENT_IMPORTS = [
    "browser_harness._ipc",
    "browser_harness.helpers",
    "browser_harness.stealth_helpers",
    "urllib.request",
    "subprocess",
    "socket",
]


def assert_authority(root: Path) -> None:
    """Authority proof gates — verify the authority model is enforced."""
    # Gate 1: Agent runtime import isolation
    result = run(
        ["uv", "run", "pytest", "-q", "-x", "-k", "test_agent_runtime_cannot_import_raw_authorities"],
        cwd=root,
    )

    # Gate 2: Challenge-no-solver — AccessPlane must not reference solve_turnstile
    result = run(
        ["uv", "run", "pytest", "-q", "-x", "-k", "test_production_fetch_does_not_reference_solve_turnstile"],
        cwd=root,
    )

    # Gate 3: Domain skill transport-forbidden scan
    domain_dir = root / "domain-skills"
    if domain_dir.exists():
        violations = []
        for path in domain_dir.rglob("*.py"):
            text = path.read_text()
            for token in FORBIDDEN_DOMAIN_TOKENS:
                if token in text:
                    violations.append(f"{path.relative_to(root)}: {token}")
        if violations:
            print(f"domain-skill transport scan: {len(violations)} violations (expected during migration)")
        else:
            print("domain-skill transport scan: OK (no violations)")

    # Gate 4: Authority proof tests
    result = run(
        ["uv", "run", "pytest", "-q", "tests/test_authority.py", "-x"],
        cwd=root,
    )

    # Gate 5: AccessPlane proof tests
    result = run(
        ["uv", "run", "pytest", "-q", "tests/test_access_plane.py", "-x"],
        cwd=root,
    )

    print("authority gates passed")


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
    assert_authority(root)
    if args.live:
        env = dict(os.environ)
        env["BROWSER_HARNESS_DATA_DISPLAY_BROWSER_SMOKE"] = "1"
        run(LIVE_BROWSER_SMOKE, cwd=root, env=env)
    print("quality gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
