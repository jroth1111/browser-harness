from unittest.mock import patch
import base64
import gzip
import json

import helpers


def test_page_info_uses_target_and_layout_metrics_not_runtime():
    calls = []

    def fake_cdp(method, **params):
        calls.append((method, params))
        if method == "Target.getTargetInfo":
            return {"targetInfo": {"url": "https://example.com", "title": "Example"}}
        if method == "Page.getLayoutMetrics":
            return {
                "cssLayoutViewport": {"clientWidth": 1280, "clientHeight": 720, "pageX": 3, "pageY": 7},
                "cssContentSize": {"width": 1280, "height": 1600},
            }
        raise AssertionError(method)

    with patch("helpers._send", return_value={"dialog": None}), \
         patch("helpers.cdp", side_effect=fake_cdp):
        assert helpers.page_info() == {
            "url": "https://example.com",
            "title": "Example",
            "w": 1280,
            "h": 720,
            "sx": 3,
            "sy": 7,
            "pw": 1280,
            "ph": 1600,
        }

    assert [method for method, _ in calls] == ["Target.getTargetInfo", "Page.getLayoutMetrics"]
    assert "Runtime.evaluate" not in [method for method, _ in calls]


def test_goto_url_prepares_page_load_events_before_navigation():
    calls = []

    def fake_cdp(method, **params):
        calls.append((method, params))
        return {"frameId": "frame-1"} if method == "Page.navigate" else {}

    with patch("helpers.cdp", side_effect=fake_cdp), \
         patch("helpers.drain_events", return_value=[]):
        assert helpers.goto_url("https://example.com") == {"frameId": "frame-1"}

    assert calls == [
        ("Page.enable", {}),
        ("Page.navigate", {"url": "https://example.com"}),
    ]


def test_switch_tab_does_not_mutate_title():
    calls = []

    def fake_cdp(method, **params):
        calls.append((method, params))
        if method == "Target.attachToTarget":
            return {"sessionId": "session-2"}
        return {}

    with patch("helpers.cdp", side_effect=fake_cdp), \
         patch("helpers._send", return_value={"session_id": "session-2"}) as send:
        assert helpers.switch_tab("target-2") == "session-2"

    assert calls == [
        ("Target.activateTarget", {"targetId": "target-2"}),
        ("Target.attachToTarget", {"targetId": "target-2", "flatten": True}),
    ]
    assert send.call_args.args[0] == {"meta": "set_session", "session_id": "session-2"}


def test_send_closes_socket_on_transport_error():
    class TrackingSocket:
        closed = False

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.closed = True
            return False

        def connect(self, path):
            pass

        def sendall(self, data):
            raise BrokenPipeError("closed")

    sock = TrackingSocket()
    with patch("socket.socket", return_value=sock):
        try:
            helpers._send({"meta": "session"})
        except BrokenPipeError:
            pass
        else:
            raise AssertionError("expected BrokenPipeError")
    assert sock.closed


def test_switch_tab_reports_missing_session_id():
    def fake_cdp(method, **params):
        return {} if method == "Target.attachToTarget" else {}

    with patch("helpers.cdp", side_effect=fake_cdp):
        try:
            helpers.switch_tab("target-2")
        except RuntimeError as e:
            assert "sessionId" in str(e)
            assert "Target.attachToTarget" in str(e)
        else:
            raise AssertionError("expected RuntimeError")


def test_close_tab_closes_current_and_switches_to_remaining_real_tab():
    calls = []

    def fake_cdp(method, **params):
        calls.append((method, params))
        if method == "Target.getTargetInfo":
            return {"targetInfo": {"targetId": "target-1", "url": "https://old.example", "title": "Old"}}
        if method == "Target.closeTarget":
            return {"success": True}
        if method == "Target.getTargets":
            return {"targetInfos": [
                {"type": "page", "targetId": "target-2", "url": "https://new.example", "title": "New"}
            ]}
        if method == "Target.attachToTarget":
            return {"sessionId": "session-2"}
        return {}

    with patch("helpers.cdp", side_effect=fake_cdp), \
         patch("helpers._send", return_value={"session_id": "session-2"}) as send:
        assert helpers.close_tab() is True

    assert calls == [
        ("Target.getTargetInfo", {}),
        ("Target.closeTarget", {"targetId": "target-1"}),
        ("Target.getTargets", {}),
        ("Target.activateTarget", {"targetId": "target-2"}),
        ("Target.attachToTarget", {"targetId": "target-2", "flatten": True}),
    ]
    assert send.call_args.args[0] == {"meta": "set_session", "session_id": "session-2"}


def test_close_tab_closes_non_current_without_switching():
    calls = []

    def fake_cdp(method, **params):
        calls.append((method, params))
        if method == "Target.getTargetInfo":
            return {"targetInfo": {"targetId": "target-1", "url": "https://current.example"}}
        if method == "Target.closeTarget":
            return {"success": True}
        raise AssertionError(method)

    with patch("helpers.cdp", side_effect=fake_cdp):
        assert helpers.close_tab("target-2") is True

    assert calls == [
        ("Target.getTargetInfo", {}),
        ("Target.closeTarget", {"targetId": "target-2"}),
    ]


def test_close_tab_reports_missing_target_id():
    with patch("helpers.current_tab", return_value={"targetId": "target-1"}):
        try:
            helpers.close_tab({})
        except RuntimeError as e:
            assert "targetId" in str(e)
        else:
            raise AssertionError("expected RuntimeError")


def test_close_tabs_closes_many_and_switches_once_if_current_closed():
    calls = []

    def fake_cdp(method, **params):
        calls.append((method, params))
        if method == "Target.getTargetInfo":
            return {"targetInfo": {"targetId": "target-1", "url": "https://old.example"}}
        if method == "Target.closeTarget":
            return {"success": True}
        if method == "Target.getTargets":
            return {"targetInfos": [
                {"type": "page", "targetId": "target-3", "url": "https://new.example", "title": "New"}
            ]}
        if method == "Target.attachToTarget":
            return {"sessionId": "session-3"}
        return {}

    with patch("helpers.cdp", side_effect=fake_cdp), \
         patch("helpers._send", return_value={"session_id": "session-3"}):
        assert helpers.close_tabs(["target-1", {"targetId": "target-2"}]) == {
            "target-1": True,
            "target-2": True,
        }

    assert calls == [
        ("Target.getTargetInfo", {}),
        ("Target.closeTarget", {"targetId": "target-1"}),
        ("Target.closeTarget", {"targetId": "target-2"}),
        ("Target.getTargets", {}),
        ("Target.activateTarget", {"targetId": "target-3"}),
        ("Target.attachToTarget", {"targetId": "target-3", "flatten": True}),
    ]


def test_close_tabs_does_not_switch_when_current_survives():
    calls = []

    def fake_cdp(method, **params):
        calls.append((method, params))
        if method == "Target.getTargetInfo":
            return {"targetInfo": {"targetId": "target-1"}}
        if method == "Target.closeTarget":
            return {"success": True}
        raise AssertionError(method)

    with patch("helpers.cdp", side_effect=fake_cdp):
        assert helpers.close_tabs(["target-2", None, {}]) == {"target-2": True}

    assert calls == [
        ("Target.getTargetInfo", {}),
        ("Target.closeTarget", {"targetId": "target-2"}),
    ]


def test_new_tab_reports_missing_target_id():
    with patch("helpers.cdp", return_value={}):
        try:
            helpers.new_tab()
        except RuntimeError as e:
            assert "targetId" in str(e)
            assert "Target.createTarget" in str(e)
        else:
            raise AssertionError("expected RuntimeError")


def test_wait_for_load_uses_page_events_not_runtime():
    calls = []

    def fake_cdp(method, **params):
        calls.append((method, params))
        return {}

    with patch("helpers.cdp", side_effect=fake_cdp), \
         patch("helpers.drain_events", side_effect=[[], [{"method": "Page.loadEventFired"}]]), \
         patch("time.sleep"):
        assert helpers.wait_for_load(timeout=1)

    assert calls == [("Page.enable", {})]


def test_wait_for_load_sees_already_queued_load_event():
    calls = []

    def fake_cdp(method, **params):
        calls.append((method, params))
        return {}

    with patch("helpers.cdp", side_effect=fake_cdp), \
         patch("helpers.drain_events", return_value=[{"method": "Page.loadEventFired"}]):
        assert helpers.wait_for_load(timeout=0.1)

    assert calls == [("Page.enable", {})]


def test_click_humanize_is_opt_in():
    calls = []

    def fake_cdp(method, **params):
        calls.append((method, params))
        return {}

    with patch("helpers.cdp", side_effect=fake_cdp):
        helpers.click_at_xy(10, 20)
    assert [params["type"] for _, params in calls] == ["mousePressed", "mouseReleased"]

    calls.clear()
    with patch("helpers.cdp", side_effect=fake_cdp):
        helpers.click_at_xy(10, 20, humanize=True, steps=3)
    assert [params["type"] for _, params in calls] == ["mouseMoved", "mouseMoved", "mouseMoved", "mousePressed", "mouseReleased"]


def test_debug_click_dpr_uses_page_info_not_js():
    with patch("helpers.page_info", return_value={"w": 500}), \
         patch("helpers.js", side_effect=AssertionError("debug overlay must not execute page JS")):
        assert helpers._debug_click_dpr(1000) == 2


def test_debug_click_dpr_falls_back_without_viewport_width():
    with patch("helpers.page_info", return_value={"dialog": {"type": "alert"}}):
        assert helpers._debug_click_dpr(1000) == 1


def test_debug_click_dpr_falls_back_when_metrics_fail():
    with patch("helpers.page_info", side_effect=RuntimeError("metrics unavailable")):
        assert helpers._debug_click_dpr(1000) == 1


def test_ax_snapshot_compacts_accessibility_tree():
    with patch("helpers.cdp", return_value={"nodes": [
        {"nodeId": "1", "role": {"value": "button"}, "name": {"value": "Save"}},
        {"nodeId": "2", "role": {"value": ""}, "name": {"value": ""}},
    ]}):
        assert helpers.ax_snapshot() == [{"ref": "1", "role": "button", "name": "Save", "value": ""}]


def test_screenshot_trace_is_opt_in(tmp_path):
    trace_dir = tmp_path / "trace"
    with patch("helpers.capture_screenshot", side_effect=lambda path, full=False: path) as capture, \
         patch("time.sleep"):
        paths = helpers.capture_screenshot_trace(directory=trace_dir, frames=2, interval=0.01)
    assert paths == [str(trace_dir / "frame-000.png"), str(trace_dir / "frame-001.png")]
    assert capture.call_count == 2


def test_capture_screenshot_writes_with_context_manager(tmp_path):
    path = tmp_path / "shot.png"
    encoded = base64.b64encode(b"png-data").decode()
    with patch("helpers.cdp", return_value={"data": encoded}):
        assert helpers.capture_screenshot(str(path)) == str(path)
    assert path.read_bytes() == b"png-data"


def test_capture_screenshot_decodes_before_opening_file(tmp_path):
    path = tmp_path / "shot.png"
    with patch("helpers.cdp", return_value={"data": "not-base64!!"}):
        try:
            helpers.capture_screenshot(str(path))
        except Exception:
            pass
        else:
            raise AssertionError("expected decode failure")
    assert not path.exists()


def test_discover_local_cdp_endpoints_requires_loopback():
    try:
        helpers.discover_local_cdp_endpoints(host="example.com")
    except ValueError as e:
        assert "loopback" in str(e)
    else:
        raise AssertionError("expected ValueError")


def test_discover_local_cdp_endpoints_reads_json_version():
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return json.dumps({
                "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/browser/abc",
                "Browser": "Chrome/123",
                "Protocol-Version": "1.3",
            }).encode()

    with patch("urllib.request.urlopen", return_value=Response()):
        assert helpers.discover_local_cdp_endpoints(ports=(9222,)) == [{
            "http_base": "http://127.0.0.1:9222",
            "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/browser/abc",
            "browser": "Chrome/123",
            "protocol_version": "1.3",
        }]


def test_discover_local_cdp_endpoints_brackets_ipv6_loopback():
    opened = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return json.dumps({
                "webSocketDebuggerUrl": "ws://[::1]:9222/devtools/browser/abc",
                "Browser": "Chrome/123",
                "Protocol-Version": "1.3",
            }).encode()

    def fake_open(url, timeout=0):
        opened.append(url)
        return Response()

    with patch("urllib.request.urlopen", side_effect=fake_open):
        assert helpers.discover_local_cdp_endpoints(ports=(9222,), host="::1") == [{
            "http_base": "http://[::1]:9222",
            "webSocketDebuggerUrl": "ws://[::1]:9222/devtools/browser/abc",
            "browser": "Chrome/123",
            "protocol_version": "1.3",
        }]
    assert opened == ["http://[::1]:9222/json/version"]


def test_page_info_js_reports_missing_runtime_value():
    with patch("helpers.cdp", return_value={"result": {}}):
        try:
            helpers.page_info_js()
        except RuntimeError as e:
            assert "value" in str(e)
            assert "Runtime.evaluate" in str(e)
        else:
            raise AssertionError("expected RuntimeError")


def test_js_reports_missing_iframe_session_id():
    with patch("helpers.cdp", return_value={}):
        try:
            helpers.js("document.title", target_id="frame-1")
        except RuntimeError as e:
            assert "sessionId" in str(e)
            assert "Target.attachToTarget" in str(e)
        else:
            raise AssertionError("expected RuntimeError")


def test_upload_file_reports_missing_node_id():
    def fake_cdp(method, **params):
        if method == "DOM.getDocument":
            return {"root": {"nodeId": 1}}
        if method == "DOM.querySelector":
            return {}
        raise AssertionError(method)

    with patch("helpers.cdp", side_effect=fake_cdp):
        try:
            helpers.upload_file("input[type=file]", "/tmp/file.txt")
        except RuntimeError as e:
            assert "nodeId" in str(e)
            assert "DOM.querySelector" in str(e)
        else:
            raise AssertionError("expected RuntimeError")


def test_http_get_decodes_valid_gzip():
    class Response:
        headers = {"Content-Encoding": "gzip"}

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return gzip.compress(b"hello")

    with patch("urllib.request.urlopen", return_value=Response()):
        assert helpers.http_get("https://example.com") == "hello"


def test_http_get_falls_back_when_gzip_header_lies():
    class Response:
        headers = {"Content-Encoding": "gzip"}

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b"plain text"

    with patch("urllib.request.urlopen", return_value=Response()):
        assert helpers.http_get("https://example.com") == "plain text"
