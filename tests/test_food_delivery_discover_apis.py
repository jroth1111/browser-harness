import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "domain-skills" / "food-delivery" / "scripts" / "discover_apis.py"


def load_module():
    sys.path.insert(0, str(MODULE_PATH.parent))
    for name in list(sys.modules):
        if name == "lib" or name.startswith("lib."):
            sys.modules.pop(name)
    spec = importlib.util.spec_from_file_location("food_delivery_discover_apis", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_dedup_endpoints_skips_malformed_rows():
    module = load_module()

    assert module.dedup_endpoints([
        "not an endpoint",
        {"url": ""},
        {"url": "https://example.test/api"},
        {"url": "https://example.test/api"},
    ]) == [{"url": "https://example.test/api"}]


def test_try_http_replay_skips_malformed_endpoint_and_cookie_rows(tmp_path, monkeypatch):
    module = load_module()
    cookie_dir = tmp_path / ".private-data"
    cookie_dir.mkdir()
    (cookie_dir / "doordash_cookies.json").write_text(json.dumps([
        "not a cookie",
        {"name": "sid", "value": "secret"},
        {"name": "missing-value"},
    ]), encoding="utf-8")

    monkeypatch.setattr(module, "__file__", str(tmp_path / "scripts" / "discover_apis.py"))

    class Response:
        status = 200

        class headers:
            @staticmethod
            def get(name, default=""):
                return "application/json"

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self, _limit):
            return b'{"ok": true}'

    seen = {}

    def fake_urlopen(req, timeout=10):
        seen["cookie"] = req.headers.get("Cookie")
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    results = module.try_http_replay([
        "not an endpoint",
        {"url": ""},
        {"url": "/relative"},
        {"url": "https://example.test/api"},
    ], "doordash", {})

    assert seen["cookie"] == "sid=secret"
    assert results == [{
        "source": "http_replay",
        "url": "https://example.test/api",
        "method": "GET",
        "status": 200,
        "content_type": "application/json",
        "http_replay_ok": True,
        "body_preview": '{"ok": true}',
    }]
