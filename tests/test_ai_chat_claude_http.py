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


def test_claude_extract_messages_skips_malformed_rows_and_collections():
    messages = ClaudeHTTPAPI.extract_messages({
        "chat_messages": [
            "not a message",
            {
                "uuid": "msg-1",
                "sender": "human",
                "content": ["not a content block", {"type": "text", "text": "Hello"}],
                "attachments": "not attachment rows",
                "files": "not file rows",
            },
        ],
    })

    assert messages == [{
        "role": "user",
        "content": "Hello",
        "ordinal": 1,
        "provider_message_id": "msg-1",
        "content_type": "text",
        "rich_parts": [],
        "artifact_refs": [],
        "metadata": {
            "model": None,
            "stop_reason": None,
            "created_at": None,
            "attachments": [],
            "files": [],
        },
    }]


def test_claude_extract_artifacts_skips_malformed_rows_and_collections():
    artifacts = ClaudeHTTPAPI.extract_artifacts({
        "chat_messages": [
            "not a message",
            {
                "uuid": "msg-1",
                "attachments": "not attachment rows",
                "files": ["not a file", {"file_uuid": "file-1", "file_name": "File"}],
                "content": [
                    "not a content block",
                    {
                        "type": "tool_use",
                        "name": "artifacts",
                        "id": "artifact-1",
                        "input": {"title": "Panel"},
                    },
                ],
            },
        ],
    })

    assert artifacts == [
        {
            "artifact_type": "file",
            "provider_artifact_id": "file-1",
            "label": "File",
            "parent_message_id": "msg-1",
            "byte_length": None,
            "mime_type": None,
            "rich_part": {"file_uuid": "file-1", "file_name": "File"},
        },
        {
            "artifact_type": "claude_artifact",
            "provider_artifact_id": "artifact-1",
            "label": "Panel",
            "parent_message_id": "msg-1",
            "rich_part": {
                "type": "tool_use",
                "name": "artifacts",
                "id": "artifact-1",
                "input": {"title": "Panel"},
            },
        },
    ]
