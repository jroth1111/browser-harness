"""Layout contract: asserts the repo follows standard Python package structure."""

import importlib.resources
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src" / "browser_harness"


_THIS_FILE = Path(__file__).resolve()


def _source_files():
    """Yield .py and .toml files under src/, tests/, and pyproject.toml."""
    for ext in ("*.py", "*.toml"):
        yield from (REPO_ROOT / "src").rglob(ext)
        for p in (REPO_ROOT / "tests").rglob(ext):
            if p != _THIS_FILE:  # contract file names the term; exclude
                yield p
    yield REPO_ROOT / "pyproject.toml"


def test_no_root_py_modules():
    """No importable .py files at repo root (only package lives in src/)."""
    root_py = [
        p for p in REPO_ROOT.glob("*.py")
        if p.name not in {"setup.py", "conftest.py"}
    ]
    assert root_py == [], f"Unexpected root-level .py files: {root_py}"


def test_no_agent_workspace_literal_in_source():
    """No 'agent-workspace' string anywhere in source or test code."""
    hits = []
    for path in _source_files():
        try:
            text = path.read_text(errors="replace")
        except (OSError, IsADirectoryError):
            continue
        if "agent-workspace" in text or "agent_workspace" in text.lower():
            hits.append(str(path.relative_to(REPO_ROOT)))
    assert hits == [], f"'agent-workspace' literals found in: {hits}"


def test_browser_harness_package_importable():
    """browser_harness package imports cleanly from the installed editable tree."""
    import browser_harness  # noqa: F401


def test_domain_skills_package_resolvable():
    """importlib.resources can resolve the browser_harness_domain_skills package."""
    pkg = importlib.resources.files("browser_harness_domain_skills")
    assert pkg is not None
    # At least one domain skill directory must exist
    children = list(pkg.iterdir())
    assert len(children) > 0, "browser_harness_domain_skills appears empty"


def test_entry_points_reference_package():
    """Installed entry-points resolve to browser_harness.* (not bare module names)."""
    result = subprocess.run(
        [sys.executable, "-c",
         "from browser_harness.run import main; from browser_harness.skill_learning_gate import main as slg"],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
