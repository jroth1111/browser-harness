import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "domain-skills" / "ai-chat-archive"
sys.path.insert(0, str(SKILL_ROOT))

from providers.gemini.http import GeminiHTTPAPI  # noqa: E402


def test_gemini_cookie_header_skips_malformed_domain_values():
    api = GeminiHTTPAPI({".google.com": "not-a-cookie-map", "google.com": {"SAPISID": "ok"}})

    assert api._cookie_header() == "SAPISID=ok"
