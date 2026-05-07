import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = ROOT / "domain-skills" / "ai-chat-archive" / "scripts"


def load_script(name):
    path = SCRIPT_ROOT / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"ai_chat_{name}", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_recon_cookies_to_playwright_skips_malformed_host_jars():
    module = load_script("recon")

    assert module._cookies_to_playwright({
        ".example.com": "not-a-cookie-map",
        ".ok.example": {
            "sid": {
                "value": "abc",
                "path": "/",
                "expires": 0,
                "secure": True,
                "http_only": True,
                "same_site": "Lax",
            }
        },
    }) == [
        {
            "name": "sid",
            "value": "abc",
            "domain": ".ok.example",
            "path": "/",
            "httpOnly": True,
            "secure": True,
            "sameSite": "Lax",
        }
    ]


def test_harvest_filter_for_provider_domains_skips_malformed_rich_jars():
    module = load_script("harvest")

    assert module._filter_for_provider_domains(
        "not-a-rich-cookie-jar",
        [".example.com"],
    ) == {}
    assert module._filter_for_provider_domains(
        {
            ".example.com": "not-a-cookie-map",
            ".ok.example": {"sid": {"value": "abc"}},
        },
        [".ok.example"],
    ) == {".ok.example": {"sid": {"value": "abc"}}}
