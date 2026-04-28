import tomllib
from pathlib import Path


def test_package_config_installs_runtime_modules_and_skill_assets():
    config = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    setuptools = config["tool"]["setuptools"]

    assert "data_display" in setuptools["py-modules"]
    assert set(setuptools["packages"]) >= {
        "browser_harness_domain_skills",
        "browser_harness_interaction_skills",
        "browser_harness_docs",
        "browser_harness_assets",
    }
    assert setuptools["package-dir"]["browser_harness_domain_skills"] == "domain-skills"
    assert setuptools["package-dir"]["browser_harness_assets"] == "browser_harness_assets"
    assert "**/*.md" in setuptools["package-data"]["browser_harness_domain_skills"]
    assert "*.js" in setuptools["package-data"]["browser_harness_assets"]
    excluded_domain_data = setuptools["exclude-package-data"]["browser_harness_domain_skills"]
    assert "**/receipts/**" not in excluded_domain_data
    assert "SKILL.md" in setuptools["data-files"]["share/browser-harness"]
