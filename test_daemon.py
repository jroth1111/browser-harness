import asyncio
import json
import os
from unittest.mock import patch

import daemon


class FakeCDP:
    def __init__(self, responses=None):
        self.calls = []
        self.responses = responses or {}

    async def send_raw(self, method, params=None, session_id=None):
        self.calls.append((method, params or {}, session_id))
        if method in self.responses:
            response = self.responses[method]
            return response() if callable(response) else response
        if method == "Target.getTargets":
            return {"targetInfos": [{"targetId": "page-1", "type": "page", "url": "https://example.com"}]}
        if method == "Target.attachToTarget":
            return {"sessionId": "session-1"}
        if method == "Target.createTarget":
            return {"targetId": "page-new"}
        return {}


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return json.dumps(self.data).encode()


def test_bh_cdp_ws_websocket_passes_through():
    url = "ws://127.0.0.1:9222/devtools/browser/abc"
    with patch.dict(os.environ, {"BH_CDP_WS": url}, clear=False):
        resolved, info = daemon.resolve_cdp_endpoint()
    assert resolved == url
    assert info["source"] == "env"
    assert info["is_loopback"]


def test_bh_cdp_ws_http_base_resolves_json_version():
    opened = []

    def fake_open(url, timeout=0):
        opened.append(url)
        return FakeResponse({"webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/browser/abc"})

    with patch.dict(os.environ, {"BH_CDP_WS": "http://127.0.0.1:9222"}, clear=False), \
         patch("urllib.request.urlopen", side_effect=fake_open):
        resolved, info = daemon.resolve_cdp_endpoint()
    assert resolved == "ws://127.0.0.1:9222/devtools/browser/abc"
    assert info["http_base"] == "http://127.0.0.1:9222"
    assert opened == ["http://127.0.0.1:9222/json/version"]


def test_bh_cdp_ws_http_base_preserves_query_for_json_version():
    opened = []

    def fake_open(url, timeout=0):
        opened.append(url)
        return FakeResponse({"webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/browser/abc"})

    with patch.dict(os.environ, {"BH_CDP_WS": "http://127.0.0.1:9222?fingerprint=111"}, clear=False), \
         patch("urllib.request.urlopen", side_effect=fake_open):
        resolved, info = daemon.resolve_cdp_endpoint()
    assert resolved == "ws://127.0.0.1:9222/devtools/browser/abc"
    assert info["http_base"] == "http://127.0.0.1:9222?fingerprint=111"
    assert opened == ["http://127.0.0.1:9222/json/version?fingerprint=111"]


def test_public_endpoint_rejects_without_remote_allow():
    with patch.dict(os.environ, {"BH_CDP_WS": "ws://203.0.113.10:9222/devtools/browser/abc"}, clear=True):
        try:
            daemon.resolve_cdp_endpoint()
        except RuntimeError as e:
            assert "refusing non-loopback" in str(e)
        else:
            raise AssertionError("expected RuntimeError")


def test_zero_host_rejects_even_with_remote_allow():
    with patch.dict(os.environ, {"BH_CDP_WS": "ws://0.0.0.0:9222/devtools/browser/abc", "BH_CDP_ALLOW_REMOTE": "1"}, clear=True):
        try:
            daemon.resolve_cdp_endpoint()
        except RuntimeError as e:
            assert "0.0.0.0 is unsafe" in str(e)
        else:
            raise AssertionError("expected RuntimeError")


def test_ipv6_unspecified_host_rejects_even_with_remote_allow():
    with patch.dict(os.environ, {"BH_CDP_WS": "ws://[::]:9222/devtools/browser/abc", "BH_CDP_ALLOW_REMOTE": "1"}, clear=True):
        try:
            daemon.resolve_cdp_endpoint()
        except RuntimeError as e:
            assert ":: is unsafe" in str(e)
        else:
            raise AssertionError("expected RuntimeError")


def test_public_endpoint_warns_with_remote_allow():
    url = "ws://203.0.113.10:9222/devtools/browser/abc"
    with patch.dict(os.environ, {"BH_CDP_WS": url, "BH_CDP_ALLOW_REMOTE": "1"}, clear=True):
        resolved, info = daemon.resolve_cdp_endpoint()
    assert resolved == url
    assert info["remote_allowed"]
    assert info["warnings"]


def test_remote_http_base_does_not_duplicate_warning():
    def fake_open(url, timeout=0):
        return FakeResponse({
            "webSocketDebuggerUrl": "ws://10.0.0.10:9222/devtools/browser/abc",
            "Browser": "Chrome/123",
            "Protocol-Version": "1.3",
        })

    env = {"BH_CDP_WS": "http://10.0.0.10:9222", "BH_CDP_ALLOW_REMOTE": "1"}
    with patch.dict(os.environ, env, clear=True), \
         patch("urllib.request.urlopen", side_effect=fake_open):
        _, info = daemon.resolve_cdp_endpoint()
    remote_warnings = [w for w in info["warnings"] if "BH_CDP_ALLOW_REMOTE" in w]
    assert len(remote_warnings) == 1, info["warnings"]


def test_credentials_in_endpoint_rejected():
    with patch.dict(os.environ, {"BH_CDP_WS": "ws://user:pass@127.0.0.1:9222/devtools/browser/x"}, clear=True):
        try:
            daemon.resolve_cdp_endpoint()
        except RuntimeError as e:
            assert "must not contain credentials" in str(e)
        else:
            raise AssertionError("expected RuntimeError")


def test_wss_loopback_accepted_with_warning():
    url = "wss://127.0.0.1:9222/devtools/browser/abc"
    with patch.dict(os.environ, {"BH_CDP_WS": url}, clear=True):
        resolved, info = daemon.resolve_cdp_endpoint()
    assert resolved == url
    assert info["is_loopback"]
    assert any("wss on loopback is unusual" in w for w in info["warnings"])


def test_https_base_resolves_through_json_version():
    def fake_open(url, timeout=0):
        return FakeResponse({"webSocketDebuggerUrl": "wss://127.0.0.1:9222/devtools/browser/abc"})

    with patch.dict(os.environ, {"BH_CDP_WS": "https://127.0.0.1:9222"}, clear=True), \
         patch("urllib.request.urlopen", side_effect=fake_open):
        resolved, info = daemon.resolve_cdp_endpoint()
    assert resolved == "wss://127.0.0.1:9222/devtools/browser/abc"
    assert info["http_base"] == "https://127.0.0.1:9222"
    assert any("https on loopback is unusual" in w for w in info["warnings"])
    assert any("wss on loopback is unusual" in w for w in info["warnings"])


def test_wss_to_remote_host_still_requires_allowance():
    with patch.dict(os.environ, {"BH_CDP_WS": "wss://203.0.113.10:9222/devtools/browser/abc"}, clear=True):
        try:
            daemon.resolve_cdp_endpoint()
        except RuntimeError as e:
            assert "refusing non-loopback" in str(e)
        else:
            raise AssertionError("expected RuntimeError")


def test_unknown_scheme_rejected():
    with patch.dict(os.environ, {"BH_CDP_WS": "ftp://127.0.0.1:9222"}, clear=True):
        try:
            daemon.resolve_cdp_endpoint()
        except RuntimeError as e:
            assert "unsupported" in str(e) and "ftp" in str(e)
        else:
            raise AssertionError("expected RuntimeError")


def test_attach_first_page_is_cdp_minimal():
    d = daemon.Daemon()
    d.cdp = FakeCDP()
    asyncio.run(d.attach_first_page())
    assert d.cdp.calls == [
        ("Target.getTargets", {}, None),
        ("Target.attachToTarget", {"targetId": "page-1", "flatten": True}, None),
    ]


def test_attach_first_page_creates_blank_when_no_real_page():
    d = daemon.Daemon()
    d.cdp = FakeCDP({"Target.getTargets": {"targetInfos": []}})
    asyncio.run(d.attach_first_page())
    assert d.cdp.calls == [
        ("Target.getTargets", {}, None),
        ("Target.createTarget", {"url": "about:blank"}, None),
        ("Target.attachToTarget", {"targetId": "page-new", "flatten": True}, None),
    ]


def test_set_session_does_not_enable_domains_or_evaluate_js():
    d = daemon.Daemon()
    d.cdp = FakeCDP()
    result = asyncio.run(d.handle({"meta": "set_session", "session_id": "session-2"}))
    assert result == {"session_id": "session-2"}
    assert d.cdp.calls == []
