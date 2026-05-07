from pathlib import Path


def test_doordash_discovery_fixture_does_not_commit_cookie_material():
    text = Path("domain-skills/food-delivery/scripts/lib/api_discovery_doordash.json").read_text(encoding="utf-8")

    assert "csrf_token" not in text
    assert "ddweb_token" not in text
    assert "cf_clearance" not in text
    assert "/.private-data/" not in text
    assert '"Cookie": "<redacted: never commit cookies>"' in text
    assert '"cookie_file": "<omitted>"' in text
