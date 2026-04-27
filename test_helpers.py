from unittest.mock import patch
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


def test_wait_for_load_uses_page_events_not_runtime():
    calls = []

    def fake_cdp(method, **params):
        calls.append((method, params))
        return {}

    with patch("helpers.cdp", side_effect=fake_cdp), \
         patch("helpers.drain_events", side_effect=[[], [{"method": "Page.loadEventFired"}]]):
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
