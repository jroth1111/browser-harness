import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "domain-skills" / "ai-chat-archive" / "lib" / "cookie_jar_io.py"


def load_cookie_jar_io():
    spec = importlib.util.spec_from_file_location("ai_chat_cookie_jar_io", MODULE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_cookies_from_jar_row_rejects_non_object_cookie_json():
    module = load_cookie_jar_io()

    assert module.cookies_from_jar_row({"cookies_json": json.dumps(["not", "an", "object"])}) == {}


def test_flatten_cookies_skips_malformed_host_jars():
    module = load_cookie_jar_io()

    assert module.flatten_cookies({
        ".bad.example": ["not", "a", "jar"],
        ".example.com": {
            "sid": {"value": "abc"},
            "bool": {"value": True},
            "num": {"value": 123},
            "flat": "xyz",
            "missing": {"path": "/"},
        },
    }) == {
        ".example.com": {"sid": "abc", "flat": "xyz"},
    }


def test_jar_min_expiry_skips_malformed_host_jars():
    module = load_cookie_jar_io()

    assert module.jar_min_expiry({
        ".bad.example": ["not", "a", "jar"],
        ".example.com": {"sid": {"expires": 1_700_000_000}},
    }) == "2023-11-14T22:13:20Z"


def test_jar_min_expiry_rejects_boolean_expiry_values():
    module = load_cookie_jar_io()

    assert module.jar_min_expiry({
        ".example.com": {"sid": {"expires": True}},
    }) is None
