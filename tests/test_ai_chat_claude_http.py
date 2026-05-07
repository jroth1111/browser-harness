import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "domain-skills" / "ai-chat-archive"
sys.path.insert(0, str(SKILL_ROOT))

from providers.claude.http import ClaudeHTTPAPI  # noqa: E402


def test_claude_auth_skips_malformed_org_rows(monkeypatch):
    api = ClaudeHTTPAPI({})

    def fake_fetch(path, timeout=30):
        if path == "/api/auth/current_account":
            return {}
        if path == "/api/organizations":
            return [["not", "an", "object"], {"uuid": "org-1", "name": "Main Org"}]
        raise AssertionError(path)

    monkeypatch.setattr(api, "_fetch_json", fake_fetch)

    assert api.authenticate() == {
        "authenticated": True,
        "email": "",
        "name": "Main Org",
        "user_id": "",
        "org_uuid": "org-1",
    }


def test_claude_all_conversations_skips_malformed_rows(monkeypatch):
    api = ClaudeHTTPAPI({})
    api._org_uuid = "org-1"

    monkeypatch.setattr(api, "_fetch_json", lambda path, timeout=30: [
        "not a row",
        {"name": "missing uuid"},
        {"uuid": "conv-1", "name": "Thread"},
    ])

    assert api.all_conversations() == [{
        "uuid": "conv-1",
        "name": "Thread",
        "summary": "",
        "created_at": None,
        "updated_at": None,
        "model": None,
    }]
