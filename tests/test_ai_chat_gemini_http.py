import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "domain-skills" / "ai-chat-archive"
sys.path.insert(0, str(SKILL_ROOT))

from providers.gemini.http import GeminiHTTPAPI  # noqa: E402


def test_gemini_cookie_header_skips_malformed_domain_values():
    api = GeminiHTTPAPI({".google.com": "not-a-cookie-map", "google.com": {"SAPISID": "ok"}})

    assert api._cookie_header() == "SAPISID=ok"


def test_gemini_list_chats_rejects_boolean_updated_timestamp():
    api = GeminiHTTPAPI({"google.com": {"SAPISID": "ok"}})
    api._authenticated = True
    api._rpc = lambda _rpc_id, _payload: [None, None, [["c_1", "Title", None, None, None, [True, 0]]]]

    chats, cursor = api.list_chats_page()

    assert cursor is None
    assert chats == [
        {
            "chat_id": "c_1",
            "title": "Title",
            "updated_unix": None,
            "response_id": None,
            "raw": ["c_1", "Title", None, None, None, [True, 0]],
        }
    ]


def test_gemini_turn_timestamp_rejects_boolean_timestamp():
    assert GeminiHTTPAPI._ts([None, None, None, None, [True, 0]]) is None
