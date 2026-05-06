import tomllib
from pathlib import Path


def test_package_config_installs_runtime_modules_and_skill_assets():
    root = Path(__file__).resolve().parent.parent
    config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    setuptools = config["tool"]["setuptools"]

    # All runtime modules now live inside the browser_harness package; no py-modules.
    assert "py-modules" not in setuptools
    assert "browser_harness" in setuptools["packages"]

    # Entry-points reference the package, not bare module names.
    assert config["project"]["scripts"]["browser-harness"] == "browser_harness.run:main"
    assert config["project"]["scripts"]["browser-harness-skill-learning-gate"] == "browser_harness.skill_learning_gate:main"

    assert set(setuptools["packages"]) >= {
        "browser_harness",
        "browser_harness_domain_skills",
        "browser_harness_interaction_skills",
        "browser_harness_docs",
        "browser_harness_assets",
    }
    assert setuptools["package-dir"]["browser_harness"] == "src/browser_harness"
    assert setuptools["package-dir"]["browser_harness_domain_skills"] == "domain-skills"
    assert setuptools["package-dir"]["browser_harness_assets"] == "browser_harness_assets"
    assert "**/*.md" in setuptools["package-data"]["browser_harness_domain_skills"]
    assert "**/*.json" in setuptools["package-data"]["browser_harness_docs"]
    assert "*.js" in setuptools["package-data"]["browser_harness_assets"]
    excluded_domain_data = setuptools["exclude-package-data"]["browser_harness_domain_skills"]
    assert "**/receipts/**" not in excluded_domain_data
    assert "**/outputs/**" in excluded_domain_data
    assert "SKILL.md" in setuptools["data-files"]["share/browser-harness"]
