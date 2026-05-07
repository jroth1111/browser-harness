import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "domain-skills" / "ai-chat-archive"
sys.path.insert(0, str(SKILL_ROOT))

from providers.grok.http import GrokHTTPAPI  # noqa: E402


def test_grok_all_conversations_skips_malformed_rows(monkeypatch):
    api = GrokHTTPAPI({})

    monkeypatch.setattr(api, "_fetch_json", lambda path, timeout=30: {
        "conversations": [
            ["not", "an", "object"],
            {"conversationId": "conv-1", "title": "Thread"},
        ],
    })

    assert api.all_conversations() == [{"conversationId": "conv-1", "title": "Thread"}]


def test_grok_conversation_detail_filters_malformed_response_rows(monkeypatch):
    api = GrokHTTPAPI({})

    def fake_fetch(path, timeout=30):
        if path.endswith("/responses"):
            return {
                "responses": [
                    "not a row",
                    {"responseId": "r1", "message": "Hello"},
                ],
            }
        return {"conversationId": "conv-1", "title": "Thread"}

    monkeypatch.setattr(api, "_fetch_json", fake_fetch)

    assert api.conversation_detail("conv-1") == {
        "meta": {"conversationId": "conv-1", "title": "Thread"},
        "responses": [{"responseId": "r1", "message": "Hello"}],
    }


def test_grok_conversation_detail_rejects_non_list_responses_field(monkeypatch):
    api = GrokHTTPAPI({})

    def fake_fetch(path, timeout=30):
        if path.endswith("/responses"):
            return {"responses": "not-a-list"}
        return {"conversationId": "conv-1", "title": "Thread"}

    monkeypatch.setattr(api, "_fetch_json", fake_fetch)

    assert api.conversation_detail("conv-1") == {
        "meta": {"conversationId": "conv-1", "title": "Thread"},
        "responses": [],
    }
