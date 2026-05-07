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


def test_grok_extract_messages_skips_malformed_rows_and_messages():
    messages = GrokHTTPAPI.extract_messages({
        "responses": [
            "not a row",
            {"responseId": "r1", "message": {"not": "text"}},
            {"responseId": "r2", "sender": "human", "message": "Hello"},
        ],
    })

    assert messages == [{
        "role": "user",
        "content": "Hello",
        "ordinal": 1,
        "provider_message_id": "r2",
        "content_type": "text",
        "rich_parts": [],
        "artifact_refs": [],
        "metadata": {
            "create_time": None,
            "manual": None,
            "parent_response_id": None,
        },
    }]


def test_grok_extract_artifacts_ignores_scalar_collections():
    artifacts = GrokHTTPAPI.extract_artifacts({
        "responses": [
            "not a row",
            {
                "responseId": "r1",
                "generatedImageUrls": "https://example.test/image.png",
                "imageEditUris": "https://example.test/edit.png",
                "imageAttachments": "not attachment rows",
                "fileAttachments": "not file rows",
            },
            {
                "responseId": "r2",
                "generatedImageUrls": ["https://example.test/generated.png"],
            },
        ],
    })

    assert artifacts == [{
        "artifact_type": "generated_image",
        "provider_artifact_id": "generated.png",
        "label": "Generated image",
        "parent_message_id": "r2",
        "source_url": "https://example.test/generated.png",
    }]


def test_grok_extract_citations_ignores_scalar_collections():
    citations = GrokHTTPAPI.extract_citations({
        "responses": [
            "not a row",
            {"citedWebSearchResults": "https://example.test/source"},
            {"webSearchResults": [{"url": "https://example.test/source", "title": "Source"}]},
        ],
    })

    assert citations == [{
        "label": "Source",
        "url": "https://example.test/source",
        "source_json": {"url": "https://example.test/source", "title": "Source"},
    }]
