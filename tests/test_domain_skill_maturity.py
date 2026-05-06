import json

from browser_harness.domain_skill_maturity import evaluate_domain_skill


def test_domain_skill_maturity_detects_all_tiers(tmp_path):
    skill = tmp_path / "example"
    (skill / "scripts").mkdir(parents=True)
    (skill / "fixtures").mkdir()
    (skill / "tests").mkdir()
    (skill / "receipts").mkdir()
    (skill / "overview.md").write_text("# Example")
    (skill / "surface-map.json").write_text(json.dumps({}))
    (skill / "scripts" / "README.md").write_text("# Scripts")
    (skill / "scripts" / "search.py").write_text("print('ok')")
    (skill / "scripts" / "live_smoke.py").write_text("print('ok')")
    (skill / "fixtures" / "sample.json").write_text("{}")
    (skill / "tests" / "test_primitives.py").write_text("def test_ok(): pass")
    (skill / "receipts" / "live-smoke.json").write_text("{}")

    result = evaluate_domain_skill(skill)

    assert result["highest"] == "packaged-safe"
    assert result["tiers"] == ["documented", "scripted", "fixture-tested", "live-smoked", "packaged-safe"]
    assert result["missing"] == []


def test_domain_skill_maturity_private_dirs_block_packaged_safe(tmp_path):
    skill = tmp_path / "example"
    skill.mkdir()
    (skill / "overview.md").write_text("# Example")
    (skill / "surface-map.json").write_text("{}")
    (skill / ".private-data").mkdir()

    result = evaluate_domain_skill(skill)

    assert "documented" in result["tiers"]
    assert "packaged-safe" not in result["tiers"]
    assert any("packaged-safe" in item for item in result["missing"])


def test_domain_skill_maturity_reports_missing_documentation(tmp_path):
    skill = tmp_path / "example"
    skill.mkdir()

    result = evaluate_domain_skill(skill)

    assert result["highest"] is None
    assert "documented: overview.md or README.md" in result["missing"]
