import importlib.util
from pathlib import Path


def _load_quality_gate():
    path = Path("scripts/quality_gate.py")
    spec = importlib.util.spec_from_file_location("quality_gate", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_quality_gate_covers_pytest_release_hygiene_and_optional_live_probe():
    quality_gate = _load_quality_gate()
    doc = Path("docs/quality-gates.md").read_text(encoding="utf-8")

    assert quality_gate.DEFAULT_PYTEST == ["uv", "run", "--group", "dev", "pytest", "-q"]
    assert quality_gate.RELEASE_PROOF()[-2:] == ["scripts/release_proof.py", "--json"]
    assert quality_gate.is_generated_status_path("build/lib/data_display.py")
    assert quality_gate.is_generated_status_path("browser_harness.egg-info/PKG-INFO")
    assert quality_gate.is_generated_status_path(".coverage.unit")
    assert not quality_gate.is_generated_status_path("docs/quality-gates.md")
    assert "FORBIDDEN_TRACKED_PARTS" in Path("scripts/quality_gate.py").read_text(encoding="utf-8")
    assert "BROWSER_HARNESS_DATA_DISPLAY_BROWSER_SMOKE" in Path("scripts/quality_gate.py").read_text(encoding="utf-8")

    assert "uv run --group dev pytest -q" in doc
    assert "python3 scripts/release_proof.py --json" in doc
    assert "hygiene scan" in doc
    assert "--live" in doc
