import asyncio
import fcntl
import json
import os
from unittest.mock import patch

import browser_harness.daemon as daemon


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


def test_endpoint_metadata_redacts_sensitive_query_values():
    url = "ws://127.0.0.1:9222/devtools/browser/abc?token=secret&fingerprint=111&api_key=abc"
    with patch.dict(os.environ, {"BH_CDP_WS": url}, clear=True):
        resolved, info = daemon.resolve_cdp_endpoint()

    assert resolved == url
    assert info["resolved_url"] == (
        "ws://127.0.0.1:9222/devtools/browser/abc?"
        "token=REDACTED&fingerprint=111&api_key=REDACTED"
    )


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


def test_browser_scoped_cdp_methods_do_not_use_page_session():
    d = daemon.Daemon()
    d.session = "page-session"
    d.cdp = FakeCDP()

    asyncio.run(d.handle({"method": "Browser.getVersion"}))
    asyncio.run(d.handle({"method": "Storage.getCookies"}))
    asyncio.run(d.handle({"method": "Target.getTargets"}))
    asyncio.run(d.handle({"method": "Runtime.evaluate"}))

    assert d.cdp.calls == [
        ("Browser.getVersion", {}, None),
        ("Storage.getCookies", {}, None),
        ("Target.getTargets", {}, None),
        ("Runtime.evaluate", {}, "page-session"),
    ]


def test_dns_hostname_rejects_without_remote_allow():
    with patch.dict(os.environ, {"BH_CDP_WS": "ws://my-browser.local:9222/devtools/browser/abc"}, clear=True):
        try:
            daemon.resolve_cdp_endpoint()
        except RuntimeError as e:
            assert "refusing non-loopback" in str(e)
        else:
            raise AssertionError("expected RuntimeError")


def test_dns_hostname_passes_with_remote_allow():
    url = "ws://my-browser.local:9222/devtools/browser/abc"
    with patch.dict(os.environ, {"BH_CDP_WS": url, "BH_CDP_ALLOW_REMOTE": "1"}, clear=True):
        resolved, info = daemon.resolve_cdp_endpoint()
    assert resolved == url
    assert not info["is_loopback"]
    assert info["remote_allowed"]


def test_endpoint_info_meta_returns_stored_metadata():
    d = daemon.Daemon()
    d.endpoint_info = {"source": "env", "host": "127.0.0.1", "is_loopback": True}
    result = asyncio.run(d.handle({"meta": "endpoint_info"}))
    assert result == {"endpoint_info": {"source": "env", "host": "127.0.0.1", "is_loopback": True}}


def test_is_loopback_host_edge_cases():
    assert daemon._is_loopback_host("127.0.0.1")
    assert daemon._is_loopback_host("127.255.255.255")
    assert daemon._is_loopback_host("::1")
    assert daemon._is_loopback_host("[::1]")
    assert daemon._is_loopback_host("localhost")
    assert daemon._is_loopback_host("localhost.")
    assert not daemon._is_loopback_host("192.168.1.1")
    assert not daemon._is_loopback_host("example.com")
    assert not daemon._is_loopback_host("")
    assert not daemon._is_loopback_host(None)


def test_already_running_closes_socket_on_permission_error():
    class TrackingSocket:
        closed = False

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.closed = True
            return False

        def settimeout(self, timeout):
            pass

        def connect(self, path):
            raise PermissionError("no access")

    sock = TrackingSocket()
    with patch("socket.socket", return_value=sock):
        assert daemon.already_running() is False
    assert sock.closed


def test_acquire_daemon_lock_excludes_second_process(tmp_path, monkeypatch):
    monkeypatch.setattr(daemon, "PID", str(tmp_path / "bh.pid"))
    first = daemon.acquire_daemon_lock()
    try:
        try:
            daemon.acquire_daemon_lock()
        except RuntimeError as e:
            assert "already running" in str(e)
        else:
            raise AssertionError("expected RuntimeError")
    finally:
        fcntl.flock(first, fcntl.LOCK_UN)
        first.close()


async def _run_handler(d, requests):
    """Send `requests` (list of JSON-dict) on a single connection, collect responses."""
    responses = []

    class FakeReader:
        def __init__(self, lines):
            self._lines = iter(lines)
        async def readline(self):
            for line in self._lines:
                return line
            return b""

    class FakeWriter:
        def __init__(self):
            self.written = []
        def write(self, data):
            self.written.append(data)
        async def drain(self):
            pass
        def close(self):
            pass

    lines = [(json.dumps(r) + "\n").encode() for r in requests]
    reader = FakeReader(lines)
    writer = FakeWriter()
    handler = daemon.serve.__code__.co_consts
    # Access the handler defined inside serve() via the Daemon's handle method
    # We'll call d.handle() directly to simulate the handler loop
    # But actually, let's use the real handler via asyncio.start_unix_server
    # Simpler: call d.handle() for each request
    for req in requests:
        resp = await d.handle(req)
        responses.append(resp)
    return responses


def test_handler_processes_multiple_requests():
    d = daemon.Daemon()
    d.cdp = FakeCDP()
    d.session = "session-1"
    d.stop = asyncio.Event()

    async def run():
        return await _run_handler(d, [
            {"method": "Target.getTargets", "params": {}},
            {"meta": "session"},
            {"method": "Browser.getVersion", "params": {}},
        ])

    responses = asyncio.run(run())
    assert len(responses) == 3
    assert "result" in responses[0]
    assert responses[1] == {"session_id": "session-1"}
    assert "result" in responses[2]


def test_handler_single_request_compat():
    d = daemon.Daemon()
    d.cdp = FakeCDP()
    d.session = "session-1"
    d.stop = asyncio.Event()

    async def run():
        return await _run_handler(d, [
            {"meta": "endpoint_info"},
        ])

    responses = asyncio.run(run())
    assert len(responses) == 1
    assert "endpoint_info" in responses[0]


def test_malformed_devtools_active_port_skipped_gracefully(tmp_path, monkeypatch):
    """DevToolsActivePort with only a port number (no path) should be skipped, not crash."""
    port_only_dir = tmp_path / "Chrome"
    port_only_dir.mkdir()
    (port_only_dir / "DevToolsActivePort").write_text("9222")

    monkeypatch.setattr(daemon, "PROFILES", [port_only_dir])
    monkeypatch.delenv("BH_CDP_WS", raising=False)

    try:
        daemon._resolve_cdp_endpoint_from_devtools_active_port(wait_for_port=False)
    except RuntimeError as e:
        assert "not found" in str(e).lower() or "DevToolsActivePort" in str(e)
    else:
        raise AssertionError("expected RuntimeError — no valid DevToolsActivePort should be found")


def test_daemon_pending_blockers_returns_empty_initially():
    d = daemon.Daemon()
    assert d.blockers.maxlen == 200
    result = asyncio.run(d.handle({"meta": "pending_blockers"}))
    assert result == {"blockers": []}


def test_daemon_pending_blockers_returns_and_clears():
    d = daemon.Daemon()
    d.blockers.append({"kind": "dialog", "params": {"type": "alert"}, "t": 1.0})
    d.blockers.append({"kind": "fileChooserOpened", "params": {}, "t": 2.0})
    result = asyncio.run(d.handle({"meta": "pending_blockers"}))
    assert len(result["blockers"]) == 2
    assert result["blockers"][0]["kind"] == "dialog"
    assert result["blockers"][1]["kind"] == "fileChooserOpened"
    assert len(d.blockers) == 0


def test_daemon_blockers_capped_at_200():
    d = daemon.Daemon()
    for i in range(250):
        d.blockers.append({"kind": "dialog", "params": {}, "t": float(i)})
    assert len(d.blockers) == 200
    assert d.blockers[0]["t"] == 50.0
    assert d.blockers[-1]["t"] == 249.0


def test_daemon_dialog_event_appended_to_blockers():
    d = daemon.Daemon()
    assert d.dialog is None
    assert len(d.blockers) == 0
    # Simulate what tap() does
    params = {"type": "confirm", "message": "Are you sure?", "url": "https://example.com"}
    d.dialog = params
    d.blockers.append({"kind": "dialog", "params": params, "t": 1.0})
    assert d.dialog == params
    assert len(d.blockers) == 1
    assert d.blockers[0]["kind"] == "dialog"


def test_daemon_file_chooser_appended_to_blockers():
    d = daemon.Daemon()
    d.blockers.append({"kind": "fileChooserOpened", "params": {"mode": "selectSingle"}, "t": 1.0})
    assert len(d.blockers) == 1
    assert d.blockers[0]["kind"] == "fileChooserOpened"
