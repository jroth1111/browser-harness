#!/usr/bin/env python3
"""Build, inspect, and smoke-test the browser-harness wheel."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import textwrap
import venv
import zipfile
from pathlib import Path


FORBIDDEN_MEMBER_PARTS = (
    ".private-data/",
    ".session-store/",
    "/outputs/",
    ".beads/",
    ".dolt/",
    "downloaded_files/",
    ".env",
    ".har",
    "Cookies",
    "Login Data",
)

REQUIRED_MEMBERS = (
    "data_display.py",
    "source_receipts.py",
    "extraction_contracts.py",
    "redaction_scan.py",
    "domain_skill_maturity.py",
    "browser_harness_assets/echarts-5.5.1.min.js",
    "browser_harness_assets/alpinejs-3.14.9-cdn.min.js",
    "browser_harness_docs/robustness-surface-map.json",
)


def run(cmd: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if result.returncode != 0:
        raise SystemExit(
            f"command failed with exit {result.returncode}: {' '.join(cmd)}\n{result.stdout[-4000:]}"
        )
    return result


def inspect_wheel(wheel: Path) -> dict[str, object]:
    with zipfile.ZipFile(wheel) as zf:
        members = zf.namelist()
    forbidden = [
        member
        for member in members
        if any(part in member for part in FORBIDDEN_MEMBER_PARTS)
    ]
    if forbidden:
        joined = "\n".join(forbidden[:40])
        raise SystemExit(f"wheel contains forbidden private/generated members:\n{joined}")

    missing = [required for required in REQUIRED_MEMBERS if required not in members]
    if missing:
        joined = "\n".join(missing)
        raise SystemExit(f"wheel is missing required package members:\n{joined}")

    return {
        "wheel": str(wheel),
        "member_count": len(members),
        "required_members": list(REQUIRED_MEMBERS),
        "forbidden_member_matches": [],
    }


def venv_python(venv_dir: Path) -> Path:
    if sys.platform == "win32":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def venv_bin(venv_dir: Path, name: str) -> Path:
    if sys.platform == "win32":
        return venv_dir / "Scripts" / f"{name}.exe"
    return venv_dir / "bin" / name


def smoke_installed_wheel(venv_dir: Path, wheel: Path, work_dir: Path) -> dict[str, object]:
    venv.EnvBuilder(with_pip=True, clear=True).create(venv_dir)
    python = venv_python(venv_dir)
    run([str(python), "-m", "pip", "install", "--quiet", str(wheel)], cwd=work_dir)

    smoke_code = textwrap.dedent(
        """
        import importlib.resources as resources
        import json
        import pathlib
        import tempfile

        import data_display

        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            src = root / "rows.json"
            src.write_text(json.dumps([{"status": "__UNOBSERVABLE__", "score": None}]), encoding="utf-8")
            out = pathlib.Path(data_display.render_dataset(src, privacy_mode=True))
            html = out.read_text(encoding="utf-8")
            assert "__UNOBSERVABLE__" in html
            assert "tailwindcss v3.4.14" in html
            assert "<script src=" not in html

        assert resources.files("browser_harness_assets").joinpath("echarts-5.5.1.min.js").is_file()
        assert resources.files("browser_harness_docs").joinpath("robustness-surface-map.json").is_file()
        """
    )
    run([str(python), "-c", smoke_code], cwd=work_dir)

    cli = run([str(venv_bin(venv_dir, "browser-harness")), "--help"], cwd=work_dir)
    if "Browser Harness" not in cli.stdout:
        raise SystemExit("browser-harness --help did not print expected heading")

    return {
        "python": str(python),
        "cli": str(venv_bin(venv_dir, "browser-harness")),
        "smoked": ["data_display.render_dataset", "browser_harness_assets", "browser_harness_docs", "browser-harness --help"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit machine-readable proof")
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parents[1]
    egg_info = root / "browser_harness.egg-info"
    build_dir = root / "build"
    with tempfile.TemporaryDirectory(prefix="browser-harness-release-proof-") as td:
        try:
            temp_root = Path(td)
            dist_dir = temp_root / "dist"
            run(["uv", "build", "--wheel", "--out-dir", str(dist_dir)], cwd=root)
            wheels = sorted(dist_dir.glob("*.whl"))
            if len(wheels) != 1:
                raise SystemExit(f"expected exactly one wheel, found {len(wheels)}")
            wheel_info = inspect_wheel(wheels[0])
            smoke_info = smoke_installed_wheel(temp_root / "venv", wheels[0], temp_root)
        finally:
            for generated in (egg_info, build_dir):
                if generated.exists():
                    shutil.rmtree(generated)

    proof = {"wheel": wheel_info, "install_smoke": smoke_info}
    if args.json:
        print(json.dumps(proof, indent=2))
    else:
        print("release proof passed")
        print(json.dumps(proof, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
