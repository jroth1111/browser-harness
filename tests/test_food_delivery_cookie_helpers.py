import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "domain-skills" / "food-delivery" / "scripts" / "lib"


def load_module(name):
    spec = importlib.util.spec_from_file_location(f"food_delivery_{name}", LIB / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_stealth_session_ignores_malformed_cookie_file(tmp_path, monkeypatch):
    module = load_module("stealth_session")
    monkeypatch.setattr(module, "PRIVATE_DATA", tmp_path)
    (tmp_path / "doordash_cookies.json").write_text(json.dumps("not-a-cookie-list"), encoding="utf-8")
    calls = {"cookies": [], "urls": []}

    class FakeSession:
        def add_cookies(self, cookies):
            calls["cookies"].append(cookies)

        def goto(self, url):
            calls["urls"].append(url)

    fake_session = FakeSession()
    monkeypatch.setattr(module, "stealth_session", lambda headless=False: fake_session)
    monkeypatch.setattr(module.time, "sleep", lambda seconds: None)

    assert module.create_stealth_session("doordash") is fake_session
    assert calls["cookies"] == []
    assert calls["urls"] == ["https://www.doordash.com/"]


def test_stealth_session_ignores_corrupt_cookie_file(tmp_path, monkeypatch):
    module = load_module("stealth_session")
    monkeypatch.setattr(module, "PRIVATE_DATA", tmp_path)
    (tmp_path / "doordash_cookies.json").write_text("{not-json", encoding="utf-8")
    calls = {"cookies": [], "urls": []}

    class FakeSession:
        def add_cookies(self, cookies):
            calls["cookies"].append(cookies)

        def goto(self, url):
            calls["urls"].append(url)

    fake_session = FakeSession()
    monkeypatch.setattr(module, "stealth_session", lambda headless=False: fake_session)
    monkeypatch.setattr(module.time, "sleep", lambda seconds: None)

    assert module.create_stealth_session("doordash") is fake_session
    assert calls["cookies"] == []
    assert calls["urls"] == ["https://www.doordash.com/"]
