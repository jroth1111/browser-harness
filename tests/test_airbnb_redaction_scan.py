import importlib.util
from pathlib import Path


def load_module():
    path = Path("agent-workspace/domain-skills/airbnb/scripts/redaction_scan.py")
    spec = importlib.util.spec_from_file_location("airbnb_redaction_scan", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_redaction_scan_passes_redacted_fixture_directory():
    module = load_module()

    result = module.scan_paths([Path("agent-workspace/domain-skills/airbnb/fixtures/parser-contracts")])

    assert result["status"] == "pass"
    assert result["finding_count"] == 0


def test_redaction_scan_flags_local_secret_patterns(tmp_path):
    module = load_module()
    path = tmp_path / "receipt.json"
    path.write_text('{"Authorization":"Bearer abcdefghijklmnopqrstuvwxyz012345"}')

    result = module.scan_paths([path])

    assert result["status"] == "fail"
    assert result["finding_count"] == 1
    assert result["findings"][0]["kind"] == "bearer_token"
