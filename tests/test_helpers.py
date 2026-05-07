from unittest.mock import MagicMock, patch
import base64
import gzip
import io
import json
import os
import sys
import tempfile
import time
import urllib.error
import subprocess

import pytest
from PIL import Image

import browser_harness.helpers as helpers


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

    with patch("browser_harness.helpers._send", return_value={"dialog": None}), \
         patch("browser_harness.helpers.cdp", side_effect=fake_cdp):
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


def test_page_info_tolerates_malformed_layout_metric_shapes():
    def fake_cdp(method, **params):
        if method == "Target.getTargetInfo":
            return {"targetInfo": {"url": "https://example.com", "title": "Example"}}
        if method == "Page.getLayoutMetrics":
            return {
                "cssLayoutViewport": "bad-viewport",
                "layoutViewport": {"clientWidth": "wide", "clientHeight": 720},
                "cssContentSize": {"width": "wide", "height": "tall"},
            }
        raise AssertionError(method)

    with patch("browser_harness.helpers._send", return_value={"dialog": None}), \
         patch("browser_harness.helpers.cdp", side_effect=fake_cdp):
        assert helpers.page_info() == {
            "url": "https://example.com",
            "title": "Example",
            "w": 0,
            "h": 720,
            "sx": 0,
            "sy": 0,
            "pw": 0,
            "ph": 0,
        }


def test_goto_url_prepares_page_load_events_before_navigation():
    calls = []

    def fake_cdp(method, **params):
        calls.append((method, params))
        return {"frameId": "frame-1"} if method == "Page.navigate" else {}

    with patch("browser_harness.helpers.cdp", side_effect=fake_cdp), \
         patch("browser_harness.helpers.drain_events", return_value=[]):
        assert helpers.goto_url("https://example.com") == {"frameId": "frame-1"}

    assert calls == [
        ("Page.enable", {}),
        ("Page.navigate", {"url": "https://example.com"}),
    ]


def test_goto_url_discovers_packaged_domain_skill_assets(tmp_path):
    domain_root = tmp_path / "domain-skills"
    skill_dir = domain_root / "airbnb"
    skill_dir.mkdir(parents=True)
    (skill_dir / "overview.md").write_text("# Airbnb\n", encoding="utf-8")

    calls = []

    def fake_cdp(method, **params):
        calls.append((method, params))
        return {"frameId": "frame-1"} if method == "Page.navigate" else {}

    with patch("browser_harness.helpers.cdp", side_effect=fake_cdp), \
         patch("browser_harness.helpers.drain_events", return_value=[]), \
         patch("browser_harness.helpers._asset_dir", return_value=domain_root) as asset_dir:
        result = helpers.goto_url("https://www.airbnb.com/hosting")

    asset_dir.assert_called_once_with("domain-skills", "browser_harness_domain_skills")
    assert result == {"frameId": "frame-1", "domain_skills": ["overview.md"]}


def test_goto_url_resolves_compound_domain_skill_assets(tmp_path):
    domain_root = tmp_path / "domain-skills"
    skill_dir = domain_root / "realestate-com-au"
    skill_dir.mkdir(parents=True)
    (skill_dir / "overview.md").write_text("# REA\n", encoding="utf-8")

    with patch("browser_harness.helpers.cdp", side_effect=lambda method, **params: {"frameId": "frame-1"} if method == "Page.navigate" else {}), \
         patch("browser_harness.helpers.drain_events", return_value=[]), \
         patch("browser_harness.helpers._asset_dir", return_value=domain_root):
        result = helpers.goto_url("https://www.realestate.com.au/buy")

    assert result == {"frameId": "frame-1", "domain_skills": ["overview.md"]}


def test_goto_with_auth_loads_profile_before_navigation():
    with patch("browser_harness.helpers.login_session.load_auth_profile", return_value=True) as mock_load, \
         patch("browser_harness.helpers.cdp", return_value={"frameId": "f1"}), \
         patch("browser_harness.helpers.drain_events", return_value=[]):
        result = helpers.goto_with_auth("https://www.airbnb.com/rooms/123")
    mock_load.assert_called_once()
    assert mock_load.call_args[0][1] == "www.airbnb.com"


def test_goto_with_auth_navigates_even_without_profile():
    with patch("browser_harness.helpers.login_session.load_auth_profile", return_value=False), \
         patch("browser_harness.helpers.cdp", return_value={"frameId": "f1"}), \
         patch("browser_harness.helpers.drain_events", return_value=[]):
        result = helpers.goto_with_auth("https://example.com")
    assert result == {"frameId": "f1"}


def test_switch_tab_does_not_mutate_title():
    calls = []

    def fake_cdp(method, **params):
        calls.append((method, params))
        if method == "Target.attachToTarget":
            return {"sessionId": "session-2"}
        return {}

    with patch("browser_harness.helpers.cdp", side_effect=fake_cdp), \
         patch("browser_harness.helpers._send", return_value={"session_id": "session-2"}) as send:
        assert helpers.switch_tab("target-2") == "session-2"

    assert calls == [
        ("Target.activateTarget", {"targetId": "target-2"}),
        ("Target.attachToTarget", {"targetId": "target-2", "flatten": True}),
    ]
    assert send.call_args.args[0] == {"meta": "set_session", "session_id": "session-2", "target_id": "target-2"}


def test_send_reconnects_on_transport_error():
    class BrokenSocket:
        def __init__(self):
            self.closed = False
        def close(self):
            self.closed = True
        def connect(self, path):
            pass
        def settimeout(self, t):
            pass
        def sendall(self, data):
            raise BrokenPipeError("closed")
        def recv(self, size):
            return b""

    class WorkingSocket:
        def __init__(self):
            self.closed = False
        def close(self):
            self.closed = True
        def connect(self, path):
            pass
        def settimeout(self, t):
            pass
        def sendall(self, data):
            pass
        def recv(self, size):
            return b'{"result":{}}\n'

    broken = BrokenSocket()
    working = WorkingSocket()
    old_sock = helpers._sock
    helpers._sock = broken
    try:
        with patch("browser_harness.helpers.ipc.connect", return_value=(working, None)):
            helpers._send({"method": "Target.getTargets", "params": {}})
        assert broken.closed
        assert helpers._sock is working
    finally:
        helpers._sock = None


def test_send_reuses_persistent_socket():
    class TrackingSocket:
        connect_count = 0
        def __init__(self):
            self.closed = False
        def close(self):
            self.closed = True
        def connect(self, path):
            TrackingSocket.connect_count += 1
        def settimeout(self, t):
            pass
        def sendall(self, data):
            pass
        def recv(self, size):
            return b'{"result":{}}\n'

    TrackingSocket.connect_count = 0
    sock = TrackingSocket()
    helpers._sock = None
    try:
        with patch("browser_harness.helpers.ipc.connect", return_value=(sock, None)):
            helpers._send({"method": "Target.getTargets", "params": {}})
            helpers._send({"method": "Target.getTargets", "params": {}})
        assert TrackingSocket.connect_count == 0
        assert helpers._sock is sock
    finally:
        helpers._sock = None


def test_send_propagates_error_after_reconnect_fails():
    class BrokenSocket:
        def close(self):
            pass
        def connect(self, path):
            raise ConnectionRefusedError("no daemon")
        def settimeout(self, t):
            pass
        def sendall(self, data):
            raise BrokenPipeError("closed")
        def recv(self, size):
            return b""

    old_sock = helpers._sock
    helpers._sock = BrokenSocket()
    try:
        with patch("browser_harness.helpers.ipc.connect", side_effect=ConnectionRefusedError("no daemon")):
            try:
                helpers._send({"method": "Target.getTargets", "params": {}})
            except (BrokenPipeError, ConnectionRefusedError):
                pass
            else:
                raise AssertionError("expected socket error")
    finally:
        helpers._sock = None


def test_send_does_not_replay_runtime_evaluate_after_transport_error():
    class BrokenSocket:
        def close(self):
            pass
        def sendall(self, data):
            raise BrokenPipeError("closed")
        def recv(self, size):
            return b""

    helpers._sock = BrokenSocket()
    try:
        with patch("browser_harness.helpers.ipc.connect") as connect:
            with pytest.raises(RuntimeError, match="Runtime.evaluate"):
                helpers._send({"method": "Runtime.evaluate", "params": {"expression": "window.clicked++"}})
        connect.assert_not_called()
    finally:
        helpers._sock = None


def test_js_detaches_target_session_after_evaluation():
    calls = []

    def fake_cdp(method, **params):
        calls.append((method, params))
        if method == "Target.attachToTarget":
            return {"sessionId": "session-iframe"}
        if method == "Runtime.evaluate":
            return {"result": {"value": 7}}
        if method == "Target.detachFromTarget":
            return {}
        raise AssertionError(method)

    with patch("browser_harness.helpers.cdp", side_effect=fake_cdp):
        assert helpers.js("3 + 4", target_id="target-iframe") == 7

    assert calls == [
        ("Target.attachToTarget", {"targetId": "target-iframe", "flatten": True}),
        ("Runtime.evaluate", {"session_id": "session-iframe", "expression": "3 + 4", "returnByValue": True, "awaitPromise": True}),
        ("Target.detachFromTarget", {"sessionId": "session-iframe"}),
    ]


def test_switch_tab_reports_missing_session_id():
    def fake_cdp(method, **params):
        return {} if method == "Target.attachToTarget" else {}

    with patch("browser_harness.helpers.cdp", side_effect=fake_cdp):
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

    with patch("browser_harness.helpers.cdp", side_effect=fake_cdp), \
         patch("browser_harness.helpers._send", return_value={"session_id": "session-2"}) as send:
        assert helpers.close_tab() is True

    assert calls == [
        ("Target.getTargetInfo", {}),
        ("Target.closeTarget", {"targetId": "target-1"}),
        ("Target.getTargets", {}),
        ("Target.activateTarget", {"targetId": "target-2"}),
        ("Target.attachToTarget", {"targetId": "target-2", "flatten": True}),
        ("Target.getTargetInfo", {}),  # post-switch internal-URL check
    ]
    assert send.call_args.args[0] == {"meta": "set_session", "session_id": "session-2", "target_id": "target-2"}


def test_list_tabs_skips_malformed_and_partial_target_rows():
    with patch("browser_harness.helpers.cdp", return_value={"targetInfos": [
        ["not", "an", "object"],
        {"type": "page", "url": "https://missing-target.example"},
        {"type": "iframe", "targetId": "iframe-1", "url": "https://frame.example"},
        {"type": "page", "targetId": "target-scalar", "url": 12345, "title": 67890},
        {"type": "page", "targetId": "target-1", "url": "https://example.com", "title": "Example"},
    ]}):
        assert helpers.list_tabs(include_chrome=False) == [
            {"targetId": "target-scalar", "title": "67890", "url": "12345"},
            {"targetId": "target-1", "title": "Example", "url": "https://example.com"}
        ]


def test_list_tabs_rejects_malformed_target_infos_envelope():
    with patch("browser_harness.helpers.cdp", return_value={"targetInfos": "not-a-list"}):
        with pytest.raises(RuntimeError, match="targetInfos.*must be a list"):
            helpers.list_tabs()


def test_current_tab_tolerates_malformed_target_info():
    with patch("browser_harness.helpers.cdp", return_value={"targetInfo": "not-an-object"}):
        assert helpers.current_tab() == {"targetId": None, "url": "", "title": ""}


def test_current_tab_stringifies_scalar_target_fields():
    with patch("browser_harness.helpers.cdp", return_value={"targetInfo": {
        "targetId": "target-1",
        "url": 12345,
        "title": 67890,
    }}):
        assert helpers.current_tab() == {"targetId": "target-1", "url": "12345", "title": "67890"}


def test_iframe_target_skips_malformed_and_partial_target_rows():
    with patch("browser_harness.helpers.cdp", return_value={"targetInfos": [
        "not-an-object",
        {"type": "iframe", "url": "https://frame.example/no-id"},
        {"type": "iframe", "targetId": "iframe-1", "url": "https://frame.example/challenge"},
    ]}):
        assert helpers.iframe_target("challenge") == "iframe-1"


def test_close_tab_closes_non_current_without_switching():
    calls = []

    def fake_cdp(method, **params):
        calls.append((method, params))
        if method == "Target.getTargetInfo":
            return {"targetInfo": {"targetId": "target-1", "url": "https://current.example"}}
        if method == "Target.closeTarget":
            return {"success": True}
        raise AssertionError(method)

    with patch("browser_harness.helpers.cdp", side_effect=fake_cdp):
        assert helpers.close_tab("target-2") is True

    assert calls == [
        ("Target.getTargetInfo", {}),
        ("Target.closeTarget", {"targetId": "target-2"}),
    ]


def test_close_tab_reports_missing_target_id():
    with patch("browser_harness.helpers.current_tab", return_value={"targetId": "target-1"}):
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

    with patch("browser_harness.helpers.cdp", side_effect=fake_cdp), \
         patch("browser_harness.helpers._send", return_value={"session_id": "session-3"}):
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

    with patch("browser_harness.helpers.cdp", side_effect=fake_cdp):
        assert helpers.close_tabs(["target-2", None, {}]) == {"target-2": True}

    assert calls == [
        ("Target.getTargetInfo", {}),
        ("Target.closeTarget", {"targetId": "target-2"}),
    ]


def test_new_tab_reports_missing_target_id():
    with patch("browser_harness.helpers.cdp", return_value={}), \
         patch("browser_harness.helpers.list_tabs", return_value=[]):
        try:
            helpers.new_tab()
        except RuntimeError as e:
            assert "targetId" in str(e)
            assert "Target.createTarget" in str(e)
        else:
            raise AssertionError("expected RuntimeError")


def test_new_tab_enforces_tab_limit():
    five_tabs = [{"targetId": f"t-{i}"} for i in range(5)]
    with patch("browser_harness.helpers.list_tabs", return_value=five_tabs):
        try:
            helpers.new_tab()
        except RuntimeError as e:
            assert "tab limit" in str(e)
            assert "5/5" in str(e)
        else:
            raise AssertionError("expected RuntimeError")


def test_new_tab_allows_under_limit():
    three_tabs = [{"targetId": f"t-{i}"} for i in range(3)]
    with patch("browser_harness.helpers.list_tabs", return_value=three_tabs), \
         patch("browser_harness.helpers.cdp", return_value={"targetId": "new-1"}), \
         patch("browser_harness.helpers.switch_tab"):
        helpers.new_tab()


def test_new_tab_respects_bh_max_tabs_env(monkeypatch):
    monkeypatch.setattr(helpers, "_MAX_TABS", 2)
    two_tabs = [{"targetId": f"t-{i}"} for i in range(2)]
    with patch("browser_harness.helpers.list_tabs", return_value=two_tabs):
        try:
            helpers.new_tab()
        except RuntimeError as e:
            assert "2/2" in str(e)
        else:
            raise AssertionError("expected RuntimeError")


def test_helpers_import_tolerates_malformed_bh_max_tabs_env():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import browser_harness.helpers as h; print(h._MAX_TABS)",
        ],
        env={**os.environ, "BH_MAX_TABS": "not-a-number"},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "5"


def test_is_recoverable_matches_session_errors():
    assert helpers._is_recoverable(RuntimeError("Session with given id not found"))
    assert helpers._is_recoverable(RuntimeError("Target closed"))
    assert helpers._is_recoverable(RuntimeError("Not attached to target: abc"))
    assert not helpers._is_recoverable(RuntimeError("network timeout"))
    assert not helpers._is_recoverable(RuntimeError("invalid selector"))


def test_with_session_recovery_retries_on_recoverable():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("Session with given id not found")
        return "ok"

    with patch("browser_harness.helpers._reconnect"):
        result = helpers.with_session_recovery(flaky)
    assert result == "ok"
    assert calls["n"] == 2


def test_with_session_recovery_propagates_non_recoverable():
    def bad():
        raise RuntimeError("something else")

    with patch("browser_harness.helpers._reconnect"):
        try:
            helpers.with_session_recovery(bad)
        except RuntimeError as e:
            assert "something else" in str(e)
        else:
            raise AssertionError("expected RuntimeError")


def test_with_session_recovery_no_infinite_retry():
    calls = {"n": 0}

    def always_fails():
        calls["n"] += 1
        raise RuntimeError("Target closed")

    with patch("browser_harness.helpers._reconnect"):
        try:
            helpers.with_session_recovery(always_fails)
        except RuntimeError:
            pass
    assert calls["n"] == 2  # original + 1 retry


def test_smart_wait_resolves_on_load():
    with patch("browser_harness.helpers.page_content_status", return_value={"textLength": 50, "block": {}}), \
         patch("browser_harness.helpers._wait_until_load", return_value={"ok": True, "reason": "load"}), \
         patch("time.sleep"):
        result = helpers.smart_wait(timeout=5.0)
    assert result["phase"] == "load"
    assert result["ok"] is True


def test_smart_wait_resolves_on_network_idle():
    load_fail = {"ok": False, "reason": "timeout"}
    idle_ok = {"ok": True, "reason": "networkidle"}

    def fake_wait_until_load(strategy, timeout=15.0):
        return load_fail

    def fake_wait_until_network_idle(timeout=15.0):
        return idle_ok

    with patch("browser_harness.helpers.page_content_status", return_value={"textLength": 50, "block": {}}), \
         patch("browser_harness.helpers._wait_until_load", side_effect=fake_wait_until_load), \
         patch("browser_harness.helpers._wait_until_network_idle", side_effect=fake_wait_until_network_idle), \
         patch("time.sleep"):
        result = helpers.smart_wait(timeout=5.0)
    assert result["phase"] == "networkidle"
    assert result["ok"] is True


def test_smart_wait_detects_waf_block():
    blocked_status = {"textLength": 0, "block": {"blocked": True, "waf": "cloudflare"}}
    with patch("browser_harness.helpers.page_content_status", return_value=blocked_status), \
         patch("time.sleep"):
        result = helpers.smart_wait(timeout=2.0, waf_timeout=0.5)
    assert result["phase"] == "waf_blocked"
    assert result["ok"] is False


def test_smart_wait_returns_timeout_when_all_phases_fail():
    load_fail = {"ok": False, "reason": "timeout"}
    idle_fail = {"ok": False, "reason": "timeout", "pending_requests": 3}
    content_fail = {"ok": False, "reason": "timeout", "textLength": 0}

    with patch("browser_harness.helpers.page_content_status", return_value={"textLength": 0, "block": {}}), \
         patch("browser_harness.helpers._wait_until_load", return_value=load_fail), \
         patch("browser_harness.helpers._wait_until_network_idle", return_value=idle_fail), \
         patch("browser_harness.helpers.wait_for_content", return_value=content_fail), \
         patch("time.sleep"):
        result = helpers.smart_wait(timeout=5.0)
    assert result["phase"] == "timeout"
    assert result["ok"] is False
    assert "elapsed_ms" in result


def test_wait_for_load_uses_page_events_not_runtime():
    calls = []

    def fake_cdp(method, **params):
        calls.append((method, params))
        return {}

    with patch("browser_harness.helpers.cdp", side_effect=fake_cdp), \
         patch("browser_harness.helpers.drain_events", side_effect=[[], [{"method": "Page.loadEventFired"}]]), \
         patch("time.sleep"):
        assert helpers.wait_for_load(timeout=1)

    assert calls == [("Page.enable", {})]


def test_wait_for_load_sees_already_queued_load_event():
    calls = []

    def fake_cdp(method, **params):
        calls.append((method, params))
        return {}

    with patch("browser_harness.helpers.cdp", side_effect=fake_cdp), \
         patch("browser_harness.helpers.drain_events", return_value=[{"method": "Page.loadEventFired"}]):
        assert helpers.wait_for_load(timeout=0.1)

    assert calls == [("Page.enable", {})]


def test_wait_for_load_skips_malformed_event_rows():
    with patch("browser_harness.helpers.cdp", return_value={}), \
         patch("browser_harness.helpers.drain_events", side_effect=[
             [],
             ["not an event", {"method": "Page.loadEventFired"}],
         ]), \
         patch("time.sleep"):
        assert helpers.wait_for_load(timeout=1)


def test_wait_for_network_idle_skips_malformed_event_rows():
    with patch("browser_harness.helpers.cdp", return_value={}), \
         patch("browser_harness.helpers.drain_events", side_effect=[
             [],
             [
                 "not an event",
                 {"method": "Network.requestWillBeSent", "params": "bad params"},
             ],
             [],
         ]), \
         patch("time.sleep"), \
         patch("time.time", side_effect=[0, 0, 0, 0.2, 0.7, 0.7]):
        assert helpers._wait_until_network_idle(timeout=1) == {"ok": True, "reason": "networkidle"}


def test_click_humanize_is_opt_in():
    calls = []

    def fake_cdp(method, **params):
        calls.append((method, params))
        return {}

    with patch("browser_harness.helpers.cdp", side_effect=fake_cdp):
        helpers.click_at_xy(10, 20)
    assert [params["type"] for _, params in calls] == ["mousePressed", "mouseReleased"]

    calls.clear()
    with patch("browser_harness.helpers.cdp", side_effect=fake_cdp):
        helpers.click_at_xy(10, 20, humanize=True, steps=3)
    assert [params["type"] for _, params in calls] == ["mouseMoved", "mouseMoved", "mouseMoved", "mousePressed", "mouseReleased"]


def test_debug_click_dpr_uses_page_info_not_js():
    with patch("browser_harness.helpers.page_info", return_value={"w": 500}), \
         patch("browser_harness.helpers.js", side_effect=AssertionError("debug overlay must not execute page JS")):
        assert helpers._debug_click_dpr(1000) == 2


def test_debug_click_dpr_falls_back_without_viewport_width():
    with patch("browser_harness.helpers.page_info", return_value={"dialog": {"type": "alert"}}):
        assert helpers._debug_click_dpr(1000) == 1


def test_debug_click_dpr_falls_back_with_malformed_viewport_width():
    with patch("browser_harness.helpers.page_info", return_value={"w": "not-a-width"}):
        assert helpers._debug_click_dpr(1000) == 1


def test_debug_click_dpr_falls_back_when_metrics_fail():
    with patch("browser_harness.helpers.page_info", side_effect=RuntimeError("metrics unavailable")):
        assert helpers._debug_click_dpr(1000) == 1


def test_ax_snapshot_compacts_accessibility_tree():
    with patch("browser_harness.helpers.cdp", return_value={"nodes": [
        {"nodeId": "1", "role": {"value": "button"}, "name": {"value": "Save"}},
        {"nodeId": "2", "role": {"value": ""}, "name": {"value": ""}},
    ]}):
        assert helpers.ax_snapshot() == [{"ref": "1", "role": "button", "name": "Save", "value": ""}]


def test_ax_snapshot_compact_filters_structural_roles():
    nodes = [
        {"backendDOMNodeId": 1, "role": {"value": "button"}, "name": {"value": "OK"}},
        {"backendDOMNodeId": 2, "role": {"value": "generic"}, "name": {"value": ""}},
        {"backendDOMNodeId": 3, "role": {"value": "heading"}, "name": {"value": "Title"}, "properties": [{"name": "level", "value": {"value": 1}}]},
        {"backendDOMNodeId": 4, "role": {"value": "StaticText"}, "name": {"value": ""}},
        {"backendDOMNodeId": 5, "role": {"value": "link"}, "name": {"value": "Home"}},
    ]
    with patch("browser_harness.helpers.cdp", return_value={"nodes": nodes}):
        result = helpers.ax_snapshot(compact=True)
    assert len(result) == 3
    assert result[0].startswith("button")
    assert result[1].startswith("heading")
    assert result[2].startswith("link")


def test_ax_snapshot_compact_assigns_sequential_refs():
    nodes = [
        {"backendDOMNodeId": 10, "role": {"value": "button"}, "name": {"value": "A"}},
        {"backendDOMNodeId": 20, "role": {"value": "textbox"}, "name": {"value": "Email"}},
        {"backendDOMNodeId": 30, "role": {"value": "link"}, "name": {"value": "Help"}},
    ]
    with patch("browser_harness.helpers.cdp", return_value={"nodes": nodes}):
        result = helpers.ax_snapshot(compact=True)
    assert "[ref=e0]" in result[0]
    assert "[ref=e1]" in result[1]
    assert "[ref=e2]" in result[2]
    assert helpers._ref_map == {
        "e0": {"backend_node_id": 10, "role": "button", "name": "A", "nth": 0},
        "e1": {"backend_node_id": 20, "role": "textbox", "name": "Email", "nth": 1},
        "e2": {"backend_node_id": 30, "role": "link", "name": "Help", "nth": 2},
    }


def test_ax_snapshot_compact_includes_props():
    nodes = [
        {"backendDOMNodeId": 1, "role": {"value": "checkbox"}, "name": {"value": "Agree"},
         "properties": [{"name": "checked", "value": {"value": True}}]},
    ]
    with patch("browser_harness.helpers.cdp", return_value={"nodes": nodes}):
        result = helpers.ax_snapshot(compact=True)
    assert "checked=True" in result[0]


def test_ax_snapshot_default_unchanged():
    nodes = [
        {"nodeId": "1", "role": {"value": "button"}, "name": {"value": "Save"}},
        {"nodeId": "2", "role": {"value": ""}, "name": {"value": ""}},
    ]
    with patch("browser_harness.helpers.cdp", return_value={"nodes": nodes}):
        result = helpers.ax_snapshot()
    assert result == [{"ref": "1", "role": "button", "name": "Save", "value": ""}]


def test_ax_snapshot_skips_malformed_nodes_and_properties():
    nodes = [
        "bad-node",
        {"nodeId": "1", "role": {"value": "button"}, "name": {"value": "Save"}, "properties": ["bad-prop"]},
    ]
    with patch("browser_harness.helpers.cdp", return_value={"nodes": nodes}):
        assert helpers.ax_snapshot() == [{"ref": "1", "role": "button", "name": "Save", "value": ""}]
        result = helpers.ax_snapshot(compact=True)
    assert result == ['button "Save" [ref=e0]']


def test_click_ref_tolerates_malformed_box_model():
    def fake_cdp(method, **params):
        if method == "Accessibility.getFullAXTree":
            return {"nodes": [
                {"backendDOMNodeId": 1, "role": {"value": "button"}, "name": {"value": "Save"}},
            ]}
        if method == "DOM.getBoxModel":
            return {"model": "not-an-object"}
        raise AssertionError(method)

    with patch("browser_harness.helpers.cdp", side_effect=fake_cdp):
        helpers.ax_snapshot(compact=True)
        with pytest.raises(RuntimeError, match="DOM.getBoxModel returned no content quad"):
            helpers.click_ref("e0")


def test_screenshot_trace_is_opt_in(tmp_path):
    trace_dir = tmp_path / "trace"
    with patch("browser_harness.helpers.capture_screenshot", side_effect=lambda path, full=False: path) as capture, \
         patch("time.sleep"):
        paths = helpers.capture_screenshot_trace(directory=trace_dir, frames=2, interval=0.01)
    assert paths == [str(trace_dir / "frame-000.png"), str(trace_dir / "frame-001.png")]
    assert capture.call_count == 2


def test_capture_screenshot_writes_with_context_manager(tmp_path):
    path = tmp_path / "shot.png"
    encoded = base64.b64encode(b"png-data").decode()
    with patch("browser_harness.helpers.cdp", return_value={"data": encoded}):
        assert helpers.capture_screenshot(str(path)) == str(path)
    assert path.read_bytes() == b"png-data"


def test_capture_screenshot_decodes_before_opening_file(tmp_path):
    path = tmp_path / "shot.png"
    with patch("browser_harness.helpers.cdp", return_value={"data": "not-base64!!"}):
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


def test_discover_local_cdp_endpoints_skips_malformed_json_version_shape():
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return json.dumps(["not", "an", "object"]).encode()

    with patch("urllib.request.urlopen", return_value=Response()):
        assert helpers.discover_local_cdp_endpoints(ports=(9222,)) == []


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
    with patch("browser_harness.helpers.cdp", return_value={"result": {}}):
        try:
            helpers.page_info_js()
        except RuntimeError as e:
            assert "value" in str(e)
            assert "Runtime.evaluate" in str(e)
        else:
            raise AssertionError("expected RuntimeError")


def test_send_rejects_non_object_ipc_response():
    class Sock:
        def __init__(self):
            self.closed = False

        def sendall(self, _payload):
            pass

        def close(self):
            self.closed = True

    sock = Sock()
    helpers._sock = sock
    helpers._sock_token = None
    try:
        with patch("browser_harness.helpers._recv", return_value=b"[]\n"):
            try:
                helpers._send({"method": "Browser.getVersion"})
            except RuntimeError as e:
                assert "invalid CDP response shape: expected object, got list" in str(e)
            else:
                raise AssertionError("expected RuntimeError")
        assert sock.closed is True
        assert helpers._sock is None
    finally:
        helpers._sock = None
        helpers._sock_token = None


def test_endpoint_info_reads_daemon_metadata():
    with patch("browser_harness.helpers._send", return_value={"endpoint_info": {"browser": "Chrome/135"}}):
        assert helpers.endpoint_info() == {"browser": "Chrome/135"}


def test_detect_block_page_identifies_kasada_shell():
    html = """<html><body><script>window.KPSDK={}</script>
    <script src="/abc/def/ips.js?KP_UIDz=token&x-kpsdk-im=token"></script></body></html>"""
    assert helpers.detect_block_page(html=html, text="") == {
        "blocked": True,
        "kind": "kasada_kpsdk",
        "evidence": ["window.kpsdk", "x-kpsdk", "kp_uidz", "/ips.js"],
    }


def test_detect_block_page_does_not_flag_normal_content_with_kpsdk_marker():
    html = "<html>" + ("x" * 9000) + "window.KPSDK /ips.js</html>"
    result = helpers.detect_block_page(html=html, text="28 Chantelle Parade\n$600,000\nProperty ID: 143160680")
    assert result == {"blocked": False, "kind": None, "evidence": []}


def test_detect_block_page_identifies_akamai_denial():
    html = "Access Denied https://errors.edgesuite.net/18.abc failover-waf"
    assert helpers.detect_block_page(html=html)["kind"] == "akamai"


def test_page_content_status_reports_block_state():
    state = {
        "url": "https://www.realestate.com.au/property-house-vic-test-1",
        "title": "",
        "readyState": "complete",
        "textLength": 0,
        "htmlLength": 140,
        "text": "",
        "html": "<script>window.KPSDK={}</script><script src='/ips.js?KP_UIDz=x&x-kpsdk-im=y'></script>",
    }
    with patch("browser_harness.helpers.js", return_value=state):
        result = helpers.page_content_status()
    assert result["block"]["blocked"] is True
    assert result["block"]["kind"] == "kasada_kpsdk"


def test_page_content_status_treats_scalar_js_result_as_empty_state():
    with patch("browser_harness.helpers.js", return_value="bad-state"):
        result = helpers.page_content_status()
    assert result == {
        "block": {"blocked": False, "kind": None, "evidence": []}
    }


def test_wait_for_content_stops_on_block_without_waiting_for_timeout():
    state = {
        "url": "https://www.realestate.com.au/property-house-vic-test-1",
        "title": "",
        "readyState": "complete",
        "textLength": 0,
        "htmlLength": 140,
        "text": "",
        "html": "<script>window.KPSDK={}</script><script src='/ips.js?KP_UIDz=x&x-kpsdk-im=y'></script>",
    }
    with patch("browser_harness.helpers.page_content_status", return_value={
        **state,
        "block": helpers.detect_block_page(html=state["html"], text=state["text"], url=state["url"]),
    }), patch("time.sleep", side_effect=AssertionError("blocked pages should return immediately")):
        result = helpers.wait_for_content(timeout=5)
    assert result["ok"] is False
    assert result["reason"] == "blocked"


def test_wait_for_content_accepts_useful_text():
    with patch("browser_harness.helpers.page_content_status", return_value={
        "url": "https://example.com",
        "textLength": 250,
        "htmlLength": 500,
        "text": "x" * 250,
        "html": "<html></html>",
        "block": {"blocked": False, "kind": None, "evidence": []},
    }):
        result = helpers.wait_for_content(min_text=200)
    assert result["ok"] is True
    assert result["reason"] == "content"


def test_wait_for_content_tolerates_non_numeric_text_length():
    with patch("browser_harness.helpers.page_content_status", return_value={
        "url": "https://example.com",
        "textLength": "not-a-count",
        "block": {"blocked": False, "kind": None, "evidence": []},
    }), patch("time.sleep"):
        result = helpers.wait_for_content(min_text=200, timeout=0.01, poll=0)
    assert result["ok"] is False
    assert result["reason"] == "timeout"


def test_wait_for_content_tolerates_malformed_block_metadata():
    with patch("browser_harness.helpers.page_content_status", return_value={
        "url": "https://example.com",
        "textLength": 250,
        "block": "not-a-block",
    }):
        result = helpers.wait_for_content(min_text=200)
    assert result["ok"] is True
    assert result["reason"] == "content"


def test_detect_block_page_tolerates_scalar_inputs():
    result = helpers.detect_block_page(html=12345, text=67890, url=98765)

    assert result == {"blocked": False, "kind": None, "evidence": []}


def test_cookie_matches_url_respects_domain_path_and_secure():
    assert helpers._cookie_matches_url(
        {"domain": ".realestate.com.au", "path": "/", "secure": True},
        "https://www.realestate.com.au/property/1",
    )
    assert helpers._cookie_matches_url(
        {"domain": "www.realestate.com.au", "path": "/property", "secure": True},
        "https://www.realestate.com.au/property/1",
    )
    assert not helpers._cookie_matches_url(
        {"domain": ".realestate.com.au", "path": "/", "secure": True},
        "https://www.property.com.au/property/1",
    )
    assert not helpers._cookie_matches_url(
        {"domain": ".realestate.com.au", "path": "/buy", "secure": False},
        "https://www.realestate.com.au/property/1",
    )
    assert not helpers._cookie_matches_url(
        {"domain": ".realestate.com.au", "path": "/", "secure": True},
        "http://www.realestate.com.au/property/1",
    )


def test_browser_cookie_header_filters_to_target_domain():
    cookies = [
        {"name": "KP_UIDz", "value": "rea", "domain": ".realestate.com.au", "path": "/", "secure": True},
        {"name": "other", "value": "prop", "domain": ".property.com.au", "path": "/", "secure": True},
        {"name": "empty", "value": "", "domain": ".realestate.com.au", "path": "/", "secure": True},
    ]
    with patch("browser_harness.helpers.login_session.browser_cookies", return_value=cookies):
        assert helpers.browser_cookie_header("https://www.realestate.com.au/property/1") == "KP_UIDz=rea; empty="


def test_http_get_browser_session_sends_browser_ua_and_matching_cookies():
    opened = []

    class Response:
        headers = {"Content-Encoding": "gzip"}

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return gzip.compress(b"<html>ok</html>")

    def fake_open(req, timeout=0):
        opened.append((req, timeout))
        return Response()

    with patch("browser_harness.login_session.browser_user_agent", return_value="Browser UA"), \
         patch("browser_harness.login_session.cookie_header", return_value="KP_UIDz=rea"), \
         patch("urllib.request.OpenerDirector.open", side_effect=fake_open):
        assert helpers.http_get_browser_session("https://www.realestate.com.au/property/1") == "<html>ok</html>"

    req, timeout = opened[0]
    assert timeout == 20.0
    assert req.headers["User-agent"] == "Browser UA"
    assert req.headers["Cookie"] == "KP_UIDz=rea"


def test_login_session_manifest_uses_redacted_generic_module():
    with patch("browser_harness.helpers.login_session.session_manifest", return_value={"cookie_names": ["sid"]}) as manifest:
        assert helpers.login_session_manifest("https://example.com", site="example") == {"cookie_names": ["sid"]}
    manifest.assert_called_once_with(
        helpers.cdp,
        "https://example.com",
        site="example",
        profile_label=None,
        account_label=None,
        backend=None,
    )


def test_prompt_user_login_delegates_to_generic_module():
    with patch("browser_harness.helpers.login_session.prompt_user_login", return_value={"ok": True}) as prompt:
        assert helpers.prompt_user_login("https://example.com/login", success_url_contains="/account") == {"ok": True}
    prompt.assert_called_once_with(
        helpers.cdp,
        "https://example.com/login",
        success_url_contains="/account",
        min_text=200,
        timeout=180.0,
        poll=2.0,
    )


def test_http_get_browser_session_response_captures_blocking_http_error():
    html = "<script>window.KPSDK={}</script><script src='/ips.js?KP_UIDz=x&x-kpsdk-im=y'></script>"
    err = urllib.error.HTTPError(
        "https://www.realestate.com.au/property/1",
        429,
        "Too Many Requests",
        {"Content-Encoding": "gzip"},
        io.BytesIO(gzip.compress(html.encode())),
    )

    with patch("browser_harness.login_session.browser_user_agent", return_value="Browser UA"), \
         patch("browser_harness.login_session.cookie_header", return_value="KP_UIDz=rea"), \
         patch("urllib.request.urlopen", side_effect=err):
        result = helpers.http_get_browser_session_response("https://www.realestate.com.au/property/1")

    assert result["ok"] is False
    assert result["http_ok"] is False
    assert result["status"] == 429
    assert result["block"]["kind"] == "kasada_kpsdk"
    assert "window.KPSDK" in result["text"]


def test_seed_browser_session_closes_tab_and_returns_cookie_names():
    with patch("browser_harness.helpers.new_tab", return_value="target-1") as new_tab, \
         patch("browser_harness.helpers.wait_for_load", return_value=True) as wait_for_load, \
         patch("browser_harness.helpers.wait_for_content", return_value={
             "ok": True,
             "reason": "content",
             "textLength": 800,
             "block": {"blocked": False, "kind": None, "evidence": []},
         }) as wait_for_content, \
         patch("browser_harness.helpers.browser_cookies", return_value=[
             {"name": "KP_UIDz", "value": "rea", "domain": ".realestate.com.au", "path": "/", "secure": True},
             {"name": "other", "value": "prop", "domain": ".property.com.au", "path": "/", "secure": True},
         ]), \
         patch("browser_harness.helpers.close_tab") as close_tab:
        result = helpers.seed_browser_session("https://www.realestate.com.au/property/1", min_text=500, timeout=7)

    new_tab.assert_called_once_with("https://www.realestate.com.au/property/1")
    wait_for_load.assert_called_once_with(timeout=7)
    wait_for_content.assert_called_once_with(min_text=500, timeout=7)
    close_tab.assert_called_once_with("target-1")
    assert result["ok"] is True
    assert result["targetId"] == "target-1"
    assert result["cookieNames"] == ["KP_UIDz"]


def test_browser_backend_info_detects_lightpanda_risks():
    with patch("browser_harness.helpers.endpoint_info", return_value={"browser": "Lightpanda/1.0"}), \
         patch("browser_harness.helpers.cdp", return_value={"product": "Lightpanda/1.0", "userAgent": "Lightpanda"}), \
         patch("browser_harness.helpers.js", return_value={
             "userAgent": "Lightpanda",
             "webdriver": False,
             "plugins": 0,
         }):
        info = helpers.browser_backend_info()

    assert info["kind"] == "lightpanda"
    assert "lightpanda may not satisfy full browser fingerprint challenges" in info["risks"]
    assert "navigator.plugins is empty" in info["risks"]


def test_browser_backend_info_detects_headless_chrome():
    with patch("browser_harness.helpers.endpoint_info", return_value={"browser": "Chrome/135"}), \
         patch("browser_harness.helpers.cdp", return_value={"product": "Chrome/135", "userAgent": "HeadlessChrome/135"}), \
         patch("browser_harness.helpers.js", return_value={
             "userAgent": "Mozilla/5.0 HeadlessChrome/135",
             "webdriver": True,
             "plugins": 3,
         }):
        info = helpers.browser_backend_info()

    assert info["kind"] == "headless_chrome"
    assert "headless_chrome may not satisfy full browser fingerprint challenges" in info["risks"]
    assert "navigator.webdriver is true" in info["risks"]


def test_diagnose_url_capability_reports_backend_recommendation_and_closes_tab():
    with patch("browser_harness.helpers.new_tab", return_value="target-1"), \
         patch("browser_harness.helpers.wait_for_load", return_value=True), \
         patch("browser_harness.helpers.wait_for_content", return_value={
             "ok": False,
             "reason": "blocked",
             "url": "https://www.realestate.com.au/property/1",
             "title": "",
             "textLength": 0,
             "htmlLength": 800,
             "block": {"blocked": True, "kind": "kasada_kpsdk", "evidence": []},
         }), \
         patch("browser_harness.helpers.browser_backend_info", return_value={"kind": "headless_chrome", "risks": []}), \
         patch("browser_harness.helpers.close_tab") as close_tab:
        result = helpers.diagnose_url_capability("https://www.realestate.com.au/property/1", timeout=4)

    assert result["ok"] is False
    assert result["reason"] == "blocked"
    assert "persistent headful Chrome" in result["recommendation"]
    close_tab.assert_called_once_with("target-1")


def test_extract_argonaut_exchange_decodes_nested_json_strings():
    nested = {"propertyProfile": {"address": "3003/500 Elizabeth Street", "beds": 3}}
    exchange = {"resi-property_property-profile": {"property_detail_data": json.dumps(nested)}}
    html = f"<script>window.ArgonautExchange={json.dumps(exchange)};</script>"

    assert helpers.extract_argonaut_exchange(html) == {
        "resi-property_property-profile": {"property_detail_data": nested}
    }


def test_extract_argonaut_exchange_handles_braces_inside_strings():
    exchange = {"app": {"value": "literal } brace", "nested": json.dumps({"x": "{brace}"})}}
    html = f"<script>window.ArgonautExchange={json.dumps(exchange)};</script><div>after</div>"

    assert helpers.extract_argonaut_exchange(html) == {
        "app": {"value": "literal } brace", "nested": {"x": "{brace}"}}
    }


def test_extract_argonaut_exchange_returns_empty_dict_when_missing():
    assert helpers.extract_argonaut_exchange("<html></html>") == {}


def test_js_reports_missing_iframe_session_id():
    with patch("browser_harness.helpers.cdp", return_value={}):
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

    with patch("browser_harness.helpers.cdp", side_effect=fake_cdp):
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


def test_detect_block_page_identifies_auth_gate():
    assert helpers.detect_block_page(
        html='<p>Please sign in to continue</p>',
        text='Please sign in to continue',
        url='https://example.com/login?redirect=/dashboard',
    )["blocked"] is True
    assert helpers.detect_block_page(
        html='<p>Please sign in to continue</p>',
        text='Please sign in to continue',
        url='https://example.com/login?redirect=/dashboard',
    )["kind"] == "auth_gate"


def test_detect_block_page_identifies_cloudflare_challenge():
    result = helpers.detect_block_page(
        html='<html><head><title>Just a moment...</title></head><body></body></html>',
        text='',
        url='https://example.com/page',
    )
    assert result["blocked"] is True
    assert result["kind"] == "waf_generic"


def test_detect_block_page_passes_normal_content():
    result = helpers.detect_block_page(
        html='<html><body><h1>Welcome</h1><p>Article content here</p></body></html>',
        text='Welcome Article content here',
        url='https://example.com/article',
    )
    assert result["blocked"] is False


def test_js_returns_none_for_undefined():
    with patch("browser_harness.helpers.cdp", return_value={"result": {"type": "undefined"}}):
        assert helpers.js("void 0") is None


def test_js_raises_on_exception_details():
    with patch("browser_harness.helpers.cdp", return_value={
        "result": {"type": "undefined"},
        "exceptionDetails": {"text": "SyntaxError", "exception": {"description": "SyntaxError: bad"}},
    }):
        with pytest.raises(RuntimeError, match="SyntaxError"):
            helpers.js("bad syntax }}}")


def test_js_tolerates_malformed_exception_details():
    with patch("browser_harness.helpers.cdp", return_value={
        "result": {"type": "undefined"},
        "exceptionDetails": "not-an-object",
    }):
        with pytest.raises(RuntimeError, match="JavaScript evaluation failed"):
            helpers.js("bad syntax }}}")


def test_detect_turnstile_returns_not_found_when_no_targets():
    with patch("browser_harness.helpers.cdp", return_value={"targetInfos": []}), \
         patch("browser_harness.helpers.js", return_value=None), \
         patch("time.sleep"):
        result = helpers.detect_turnstile(timeout=0.1)
        assert result["found"] is False
        assert result["challenge_type"] is None


def test_detect_turnstile_skips_malformed_target_rows():
    with patch("browser_harness.helpers.cdp", return_value={"targetInfos": [
        ["not", "an", "object"],
        {"type": "iframe", "url": "https://challenges.cloudflare.com/no-id"},
    ]}), \
         patch("browser_harness.helpers.js", return_value=None), \
         patch("time.sleep"):
        result = helpers.detect_turnstile(timeout=0.1)
        assert result == {"found": False, "challenge_type": None, "iframe_target_id": None}


def test_detect_turnstile_rejects_malformed_target_infos_envelope():
    with patch("browser_harness.helpers.cdp", return_value={"targetInfos": "not-a-list"}):
        with pytest.raises(RuntimeError, match="targetInfos.*must be a list"):
            helpers.detect_turnstile(timeout=0.1)


def test_detect_turnstile_finds_cloudflare_iframe():
    with patch("browser_harness.helpers.cdp", return_value={"targetInfos": [
        {"type": "iframe", "url": "https://challenges.cloudflare.com/cdn-cgi/challenge-platform/turnstile", "targetId": "abc123"},
    ]}):
        result = helpers.detect_turnstile(timeout=0.1)
        assert result["found"] is True
        assert result["challenge_type"] == "turnstile_iframe"
        assert result["iframe_target_id"] == "abc123"


def test_solve_turnstile_tolerates_malformed_block_metadata():
    js_results = iter([
        "",
        {"x": 10, "y": 20, "w": 300, "h": 65},
        "Example",
    ])

    with patch("browser_harness.helpers.detect_turnstile", return_value={"found": True}), \
         patch("browser_harness.helpers.js", side_effect=lambda *args, **kwargs: next(js_results)), \
         patch("browser_harness.helpers.click_at_xy"), \
         patch("browser_harness.helpers.page_content_status", return_value={"textLength": 500, "block": "not-an-object"}), \
         patch("browser_harness.helpers.wait"), \
         patch("time.sleep"):
        assert helpers.solve_turnstile(timeout=0.1, poll=0.0, max_attempts=1) == {
            "solved": True,
            "reason": "content_appeared",
            "attempts": 1,
        }


def test_response_turnstile_solved_flag():
    from browser_harness.response import Response
    r = Response(html="<html></html>", text="", url="https://example.com",
                 status=200, source="browser", turnstile_solved=True)
    assert r.turnstile_solved is True
    r2 = Response(html="<html></html>", text="", url="https://example.com",
                  status=200, source="browser")
    assert r2.turnstile_solved is False


def test_response_preserves_readiness_reason_and_block_state():
    from browser_harness.response import Response

    block = {"blocked": True, "kind": "auth_gate", "evidence": ["/login"]}
    r = Response(
        html="<html>login</html>",
        text="log in to continue",
        url="https://example.com/login",
        status=403,
        source="browser",
        reason="blocked",
        block=block,
    )

    assert r.reason == "blocked"
    assert r.block == block
    assert "reason='blocked'" in r.summary()


def test_fetch_browser_preserves_blocked_readiness_state():
    block = {"blocked": True, "kind": "auth_gate", "evidence": ["/login"]}
    with patch("browser_harness.helpers.new_tab", return_value="target-1"), \
         patch("browser_harness.helpers.wait_for_load"), \
         patch("browser_harness.helpers.wait_for_content", return_value={
             "ok": False,
             "reason": "blocked",
             "url": "https://example.com/login",
             "text": "log in to continue",
             "block": block,
         }), \
         patch("browser_harness.helpers.js", return_value="<html>log in to continue</html>"), \
         patch("browser_harness.helpers.close_tab") as close_tab:
        response = helpers.fetch("https://example.com/private", source="browser")

    assert response.status == 403
    assert response.reason == "blocked"
    assert response.block == block
    assert response.text == "log in to continue"
    close_tab.assert_called_once_with("target-1")


def test_fetch_browser_timeout_is_not_reported_as_empty_success():
    with patch("browser_harness.helpers.new_tab", return_value="target-1"), \
         patch("browser_harness.helpers.wait_for_load"), \
         patch("browser_harness.helpers.wait_for_content", return_value={
             "ok": False,
             "reason": "timeout",
             "url": "https://example.com/slow",
             "text": "",
             "block": {"blocked": False, "kind": None, "evidence": []},
         }), \
         patch("browser_harness.helpers.js", return_value="<html></html>"), \
         patch("browser_harness.helpers.close_tab"):
        response = helpers.fetch("https://example.com/slow", source="browser")

    assert response.status == 504
    assert response.reason == "timeout"
    assert response.block == {"blocked": False, "kind": None, "evidence": []}


def test_fetch_auto_tolerates_scalar_session_text():
    with patch("browser_harness.helpers.http_get", side_effect=RuntimeError("plain http failed")), \
         patch("browser_harness.helpers.http_get_browser_session_response", return_value={
             "ok": True,
             "text": 12345,
             "url": "https://example.com/session",
             "status": 200,
             "headers": {},
         }), \
         patch("browser_harness.helpers.new_tab") as new_tab:
        response = helpers.fetch("https://example.com/session", min_text=1)

    assert response.source == "session"
    assert response.text == "12345"
    new_tab.assert_not_called()


def test_response_repr():
    from browser_harness.response import Response
    r = Response(html="<html></html>", text="content", url="https://example.com",
                 status=200, source="http")
    assert "example.com" in repr(r)
    assert "status=200" in repr(r)


def test_response_tolerates_scalar_bodies():
    from browser_harness.response import Response

    r = Response(html=12345, text=67890, url=98765, status=200, source="session")

    assert r.html == "12345"
    assert r.text == "67890"
    assert r.url == "98765"
    assert "text=5" in r.summary()


def test_send_passes_timeout_to_recv():
    import browser_harness.helpers as helpers
    calls = []
    original_send = helpers._send

    def fake_send(req, timeout=30):
        calls.append(timeout)
        return {"result": {}}

    with patch("browser_harness.helpers._send", side_effect=fake_send):
        helpers.cdp("Page.navigate", url="https://example.com", timeout=60)
    assert 60 in calls


def test_crawl_state_add_returns_true_for_new_keys():
    state = helpers.CrawlState(key_field="id")
    assert state.add({"id": "a", "name": "Alice"}) is True
    assert state.add({"id": "b", "name": "Bob"}) is True
    assert state.summary()["records"] == 2


def test_crawl_state_add_returns_false_for_duplicates():
    state = helpers.CrawlState(key_field="id")
    state.add({"id": "a", "name": "Alice"})
    assert state.add({"id": "a", "name": "Alice v2"}) is False
    assert state.summary()["records"] == 1
    assert state.summary()["deduped"] == 1


def test_crawl_state_add_skips_none_key():
    state = helpers.CrawlState(key_field="id")
    assert state.add({"name": "No ID"}) is False
    assert state.summary()["records"] == 0
    assert state.summary()["missing_key"] == 1


def test_crawl_state_saturation_reached():
    state = helpers.CrawlState(key_field="id")
    assert state.saturation_reached(k=3) is False
    state.page_done(5)
    assert state.saturation_reached(k=3) is False
    state.page_done(0)
    state.page_done(0)
    state.page_done(0)
    assert state.saturation_reached(k=3) is True


def test_crawl_state_saturation_not_reached_with_mixed_counts():
    state = helpers.CrawlState(key_field="id")
    state.page_done(0)
    state.page_done(1)
    state.page_done(0)
    assert state.saturation_reached(k=3) is False


def test_crawl_state_scope_totals_accumulate():
    state = helpers.CrawlState(key_field="id")
    state.record_scope_total("cat_a", 10)
    state.record_scope_total("cat_a", 5)
    state.record_scope_total("cat_b", 20)
    assert state.summary()["scope_totals"] == {"cat_a": 15, "cat_b": 20}


def test_crawl_state_record_blocked():
    state = helpers.CrawlState(key_field="id")
    state.record_blocked("https://example.com/page1", "WAF")
    state.record_blocked("https://example.com/page2", "timeout")
    assert state.summary()["blocked"] == 2


def test_crawl_state_summary_reports_saturation():
    state = helpers.CrawlState(key_field="id")
    assert state.summary()["saturated"] is False
    state.page_done(0)
    state.page_done(0)
    state.page_done(0)
    assert state.summary()["saturated"] is True


def test_crawl_state_occurrence_tracking():
    state = helpers.CrawlState(key_field="id")
    state.add({"id": "a"})
    state.add({"id": "b"})
    state.add({"id": "a"})  # dup, occurrence -> 2
    state.add({"id": "a"})  # dup, occurrence -> 3
    assert state._occurrences == {"a": 3, "b": 1}


def test_crawl_state_estimated_unseen_no_singletons():
    state = helpers.CrawlState(key_field="id")
    state.add({"id": "a"})
    state.add({"id": "a"})  # seen twice
    assert state.estimated_unseen() == 0


def test_crawl_state_estimated_unseen_with_singletons():
    state = helpers.CrawlState(key_field="id")
    for c in "abcdef":  # 6 singletons
        state.add({"id": c})
    # f1=6, f2=0 → estimated = 6*5/2 = 15
    assert state.estimated_unseen() == 15


def test_crawl_state_estimated_unseen_mixed():
    state = helpers.CrawlState(key_field="id")
    state.add({"id": "a"})
    state.add({"id": "b"})
    state.add({"id": "c"})
    state.add({"id": "c"})  # seen twice
    # f1=2 (a,b), f2=1 (c) → 2*2/(2*1) = 2
    assert state.estimated_unseen() == 2


def test_crawl_state_summary_includes_estimated_unseen():
    state = helpers.CrawlState(key_field="id")
    state.add({"id": "a"})
    assert "estimated_unseen" in state.summary()


def test_crawl_state_receipt_includes_marginal_blocked_and_safety():
    state = helpers.CrawlState(key_field="id", marginal_window=3)
    gate = helpers.SafetyGate(max_requests=5, consecutive_block_threshold=2)
    assert gate.ok() is True
    gate.record(429, blocked=True)
    state.add({"id": "a"})
    state.add({"id": "a"})
    state.add({"name": "missing key"})
    state.record_blocked("https://example.com/page", "auth_gate")
    state.page_done(1)
    receipt = state.receipt(
        source_context={"domain": "example.com", "query": "widgets"},
        safety=gate,
    )

    assert receipt["key_field"] == "id"
    assert receipt["source_context"]["domain"] == "example.com"
    assert receipt["summary"]["records"] == 1
    assert receipt["summary"]["deduped"] == 1
    assert receipt["summary"]["missing_key"] == 1
    assert receipt["blocked_sample"] == [{"url": "https://example.com/page", "reason": "auth_gate"}]
    assert receipt["marginal"] == [1]
    assert receipt["safety"]["429_count"] == 1


def test_fill_rate_triage_returns_empty_for_no_records():
    assert helpers.fill_rate_triage([]) == {}


def test_fill_rate_triage_computes_fill_rates():
    records = [
        {"name": "Alice", "age": 30, "city": None},
        {"name": "Bob", "age": None, "city": None},
        {"name": "Carol", "age": 25, "city": "__UNOBSERVABLE__"},
    ]
    triage = helpers.fill_rate_triage(records)
    assert triage["name"]["status"] == "OK"
    assert triage["name"]["fill_rate"] == 1.0
    assert triage["age"]["fill_rate"] == round(2 / 3, 3)
    assert triage["age"]["status"] == "LOW"
    assert triage["city"]["status"] == "BLOCKED"


def test_fill_rate_triage_all_null_is_ok():
    records = [{"name": "Alice", "seller": None}, {"name": "Bob", "seller": None}]
    triage = helpers.fill_rate_triage(records)
    assert triage["seller"]["status"] == "OK"


def test_fill_rate_triage_broken_selector():
    records = [{"name": "A", "price": 10}, {"name": "B", "price": None}, {"name": "C", "price": None}]
    triage = helpers.fill_rate_triage(records)
    assert triage["price"]["status"] == "BROKEN"


# --- CrawlState save/load ---

def test_crawl_state_save_load_roundtrip(tmp_path):
    state = helpers.CrawlState("id")
    state.add({"id": "a", "name": "Alice"})
    state.add({"id": "b", "name": "Bob"})
    state.record_blocked("https://example.com/x", "WAF")
    state.record_scope_total("cat", 10)
    state.page_done(2)
    path = str(tmp_path / "crawl.json")
    state.save(path)

    loaded = helpers.CrawlState.load(path)
    assert loaded.key_field == "id"
    assert len(loaded._records) == 2
    assert loaded._records[0]["name"] == "Alice"
    assert loaded._dup_attempts == 0
    assert loaded._missing_key == 0
    assert len(loaded._blocked) == 1
    assert loaded._scope_totals == {"cat": 10}
    assert list(loaded._marginal) == [2]


def test_crawl_state_save_load_preserves_marginal_window(tmp_path):
    state = helpers.CrawlState("id", marginal_window=3)
    state.page_done(5)
    state.page_done(0)
    path = str(tmp_path / "crawl.json")
    state.save(path)

    loaded = helpers.CrawlState.load(path)
    assert loaded._marginal.maxlen == 3
    assert list(loaded._marginal) == [5, 0]


def test_crawl_state_load_rejects_malformed_checkpoint_shapes(tmp_path):
    path = tmp_path / "checkpoint.json"
    path.write_text(json.dumps({"key_field": "id", "records": {"id": 1}}), encoding="utf-8")

    with pytest.raises(ValueError, match="records.*list"):
        helpers.CrawlState.load(path)


def test_crawl_state_load_rejects_boolean_integer_fields(tmp_path):
    path = tmp_path / "checkpoint.json"
    path.write_text(json.dumps({"key_field": "id", "dup_attempts": True}), encoding="utf-8")

    with pytest.raises(ValueError, match="dup_attempts.*int"):
        helpers.CrawlState.load(path)


def test_crawl_state_save_handles_non_serializable(tmp_path):
    state = helpers.CrawlState("id")
    state.add({"id": "a", "ts": object()})
    path = str(tmp_path / "crawl.json")
    state.save(path)
    loaded = helpers.CrawlState.load(path)
    assert len(loaded._records) == 1


# --- SafetyGate ---

def test_safety_gate_ok_with_no_limits():
    gate = helpers.SafetyGate()
    for _ in range(100):
        assert gate.ok() is True


def test_safety_gate_max_requests():
    gate = helpers.SafetyGate(max_requests=3)
    assert gate.ok() is True
    assert gate.ok() is True
    assert gate.ok() is True
    assert gate.ok() is False


def test_safety_gate_consecutive_blocks():
    gate = helpers.SafetyGate(consecutive_block_threshold=2)
    assert gate.ok() is True
    gate.record(403, blocked=True)
    assert gate.ok() is True
    gate.record(403, blocked=True)
    assert gate.ok() is False


def test_safety_gate_consecutive_blocks_resets_on_success():
    gate = helpers.SafetyGate(consecutive_block_threshold=2)
    gate.ok()
    gate.record(403, blocked=True)
    gate.record(200)  # resets consecutive blocks
    assert gate.ok() is True


def test_safety_gate_429_backoff():
    import time
    gate = helpers.SafetyGate(backoff_on_429=True)
    gate.ok()
    gate.record(429)
    gate._backoff_until = time.time() + 10  # force future backoff
    assert gate.ok() is False


def test_safety_gate_raise_on_fail():
    gate = helpers.SafetyGate(max_requests=1, raise_on_fail=True)
    assert gate.ok() is True
    try:
        gate.ok()
        raise AssertionError("expected RuntimeError")
    except RuntimeError as e:
        assert "max_requests" in str(e)


def test_safety_gate_reset():
    gate = helpers.SafetyGate(max_requests=1)
    assert gate.ok() is True
    assert gate.ok() is False
    gate.reset()
    assert gate.ok() is True


def test_safety_gate_summary():
    gate = helpers.SafetyGate(max_requests=10)
    gate.ok()
    gate.record(200)
    s = gate.summary()
    assert s["requests"] == 1
    assert s["elapsed_seconds"] >= 0
    assert s["limits_reached"] == []


# --- NetworkCapture ---

def test_network_capture_start_enables_network_domain():
    with patch("browser_harness.helpers.cdp") as mock_cdp:
        cap = helpers.NetworkCapture()
        cap.start()
    mock_cdp.assert_called_with("Network.enable")


def test_network_capture_stop_disables_network_domain():
    with patch("browser_harness.helpers.cdp") as mock_cdp:
        cap = helpers.NetworkCapture()
        cap.stop()
    assert ("Network.disable",) in [c.args for c in mock_cdp.call_args_list]


def test_network_capture_poll_processes_request_events():
    events = [
        {"method": "Network.requestWillBeSent", "params": {
            "requestId": "r1",
            "request": {"url": "https://api.example.com/users", "method": "GET", "headers": {}},
            "type": "XHR",
        }},
        {"method": "Network.responseReceived", "params": {
            "requestId": "r1",
            "response": {"status": 200, "headers": {"content-type": "application/json"}, "mimeType": "application/json"},
        }},
        {"method": "Page.loadEventFired", "params": {}},
    ]
    with patch("browser_harness.helpers.drain_events", return_value=events):
        cap = helpers.NetworkCapture()
        cap.poll()

    eps = cap.endpoints()
    assert len(eps) == 1
    assert eps[0]["url"] == "https://api.example.com/users"
    assert eps[0]["count"] == 1


def test_network_capture_poll_skips_malformed_cdp_event_shapes():
    events = [
        "not an event",
        {"method": "Network.requestWillBeSent", "params": "bad-params"},
        {"method": "Network.requestWillBeSent", "params": {
            "requestId": "r1",
            "request": "bad-request",
            "type": "XHR",
        }},
        {"method": "Network.responseReceived", "params": {
            "requestId": "r1",
            "response": "bad-response",
        }},
    ]
    with patch("browser_harness.helpers.drain_events", return_value=events):
        cap = helpers.NetworkCapture()
        assert cap.poll() == 2

    entries = cap.responses_for("")
    assert entries == [{
        "url": "",
        "method": "GET",
        "headers": {},
        "resource_type": "XHR",
        "status": 0,
        "response_headers": {},
        "content_type": "",
    }]


def test_network_capture_redacted_entries_ignore_scalar_header_maps():
    cap = helpers.NetworkCapture()
    cap._entries.append({
        "url": "https://api.example.com/private",
        "method": "GET",
        "headers": "not headers",
        "response_headers": ["not", "headers"],
    })

    redacted = cap.redacted_entries()[0]
    assert redacted["headers"] == {}
    assert redacted["response_headers"] == {}


def test_network_capture_endpoints_deduplicates():
    events_a = [
        {"method": "Network.requestWillBeSent", "params": {
            "requestId": "r1", "request": {"url": "https://api.example.com/users", "method": "GET", "headers": {}}, "type": "XHR",
        }},
        {"method": "Network.responseReceived", "params": {
            "requestId": "r1", "response": {"status": 200, "headers": {}, "mimeType": "json"},
        }},
    ]
    events_b = [
        {"method": "Network.requestWillBeSent", "params": {
            "requestId": "r2", "request": {"url": "https://api.example.com/users", "method": "GET", "headers": {}}, "type": "XHR",
        }},
        {"method": "Network.responseReceived", "params": {
            "requestId": "r2", "response": {"status": 200, "headers": {}, "mimeType": "json"},
        }},
    ]
    cap = helpers.NetworkCapture()
    with patch("browser_harness.helpers.drain_events", side_effect=[events_a, events_b]):
        cap.poll()
        cap.poll()

    eps = cap.endpoints()
    assert len(eps) == 1
    assert eps[0]["count"] == 2


def test_network_capture_responses_for_filters():
    events = [
        {"method": "Network.requestWillBeSent", "params": {
            "requestId": "r1", "request": {"url": "https://api.example.com/users", "method": "GET", "headers": {}}, "type": "XHR",
        }},
        {"method": "Network.responseReceived", "params": {
            "requestId": "r1", "response": {"status": 200, "headers": {}, "mimeType": "json"},
        }},
        {"method": "Network.requestWillBeSent", "params": {
            "requestId": "r2", "request": {"url": "https://cdn.example.com/bundle.js", "method": "GET", "headers": {}}, "type": "Script",
        }},
        {"method": "Network.responseReceived", "params": {
            "requestId": "r2", "response": {"status": 200, "headers": {}, "mimeType": "js"},
        }},
    ]
    with patch("browser_harness.helpers.drain_events", return_value=events):
        cap = helpers.NetworkCapture()
        cap.poll()

    api = cap.responses_for(r"api\.example")
    assert len(api) == 1
    assert api[0]["url"] == "https://api.example.com/users"


def test_network_capture_responses_for_tolerates_scalar_urls():
    events = [
        {"method": "Network.requestWillBeSent", "params": {
            "requestId": "r1", "request": {"url": 12345, "method": "GET", "headers": {}}, "type": "XHR",
        }},
        {"method": "Network.responseReceived", "params": {
            "requestId": "r1", "response": {"status": 200, "headers": {}, "mimeType": "json"},
        }},
    ]
    with patch("browser_harness.helpers.drain_events", return_value=events):
        cap = helpers.NetworkCapture()
        cap.poll()

    assert cap.responses_for("12345")[0]["url"] == "12345"


def test_network_capture_handles_redirect():
    events = [
        {"method": "Network.requestWillBeSent", "params": {
            "requestId": "r1", "request": {"url": "http://example.com/old", "method": "GET", "headers": {}}, "type": "Document",
        }},
        {"method": "Network.requestWillBeSent", "params": {
            "requestId": "r1", "request": {"url": "https://example.com/new", "method": "GET", "headers": {}}, "type": "Document",
            "redirectResponse": {"status": 301, "headers": {"location": "/new"}, "mimeType": ""},
        }},
        {"method": "Network.responseReceived", "params": {
            "requestId": "r1", "response": {"status": 200, "headers": {}, "mimeType": "text/html"},
        }},
    ]
    with patch("browser_harness.helpers.drain_events", return_value=events):
        cap = helpers.NetworkCapture()
        cap.poll()

    assert len(cap._entries) == 2  # redirect + final
    assert cap._entries[0]["url"] == "http://example.com/old"
    assert cap._entries[1]["url"] == "https://example.com/new"


def test_network_capture_max_entries_evicts_oldest():
    cap = helpers.NetworkCapture(max_entries=2)
    for i in range(4):
        cap._entries.append({"url": f"https://example.com/{i}", "method": "GET",
                             "status": 200, "response_headers": {}, "content_type": ""})
    assert len(cap._entries) == 2
    assert cap._entries[0]["url"] == "https://example.com/2"


def test_network_capture_summary():
    cap = helpers.NetworkCapture()
    cap._entries = [
        {"url": "https://api.example.com/a", "resource_type": "XHR", "status": 200},
        {"url": "https://api.example.com/b", "resource_type": "XHR", "status": 404},
    ]
    cap._requests = {"r3": {"url": "pending"}}
    s = cap.summary()
    assert s["total_requests"] == 3
    assert s["total_responses"] == 2
    assert s["by_resource_type"]["XHR"] == 2
    assert s["by_status"][200] == 1
    assert s["pending_requests"] == 1


def test_network_capture_redacted_entries_hide_sensitive_headers():
    cap = helpers.NetworkCapture()
    cap._entries.append({
        "url": "https://api.example.com/private",
        "method": "GET",
        "headers": {
            "Authorization": "Bearer abcdefghijklmnopqrstuvwxyz012345",
            "Cookie": "sid=secret-session-value",
            "Accept": "application/json",
        },
        "response_headers": {
            "Set-Cookie": "sid=secret-session-value",
            "Content-Type": "application/json",
        },
        "status": 200,
        "content_type": "application/json",
    })

    redacted = cap.redacted_entries()[0]
    assert redacted["headers"]["Authorization"] == "REDACTED"
    assert redacted["headers"]["Cookie"] == "REDACTED"
    assert redacted["headers"]["Accept"] == "application/json"
    assert redacted["response_headers"]["Set-Cookie"] == "REDACTED"
    assert redacted["response_headers"]["Content-Type"] == "application/json"


def test_network_capture_body_capture_is_bounded():
    events = [
        {"method": "Network.requestWillBeSent", "params": {
            "requestId": "r1",
            "request": {"url": "https://api.example.com/private", "method": "GET", "headers": {}},
            "type": "XHR",
        }},
        {"method": "Network.responseReceived", "params": {
            "requestId": "r1",
            "response": {"status": 200, "headers": {}, "mimeType": "application/json"},
        }},
    ]

    def fake_cdp(method, **params):
        assert method == "Network.getResponseBody"
        return {"body": "abcdef"}

    with patch("browser_harness.helpers.drain_events", return_value=events), \
         patch("browser_harness.helpers.cdp", side_effect=fake_cdp):
        cap = helpers.NetworkCapture(capture_bodies=True, max_body_chars=3)
        cap.poll()

    entry = cap.responses_for("private")[0]
    assert entry["body"] == "abc"
    assert entry["body_truncated"] is True


# --- url_cluster ---

def test_url_cluster_replaces_numeric_ids():
    result = helpers.url_cluster(["https://api.example.com/users/123/posts/456"])
    assert result[0]["pattern"] == "https://api.example.com/users/{id}/posts/{id}"


def test_url_cluster_replaces_uuids():
    result = helpers.url_cluster(["https://api.example.com/items/a1b2c3d4-e5f6-7890-abcd-ef1234567890"])
    assert result[0]["pattern"] == "https://api.example.com/items/{uuid}"


def test_url_cluster_groups_by_pattern():
    result = helpers.url_cluster([
        "https://api.example.com/users/10",
        "https://api.example.com/users/20",
        "https://api.example.com/users/30",
    ])
    assert len(result) == 1
    assert result[0]["count"] == 3
    assert result[0]["pattern"] == "https://api.example.com/users/{id}"


def test_url_cluster_slug_with_number():
    result = helpers.url_cluster(["https://example.com/item-12345"])
    assert result[0]["pattern"] == "https://example.com/item-{id}"


def test_url_cluster_empty():
    assert helpers.url_cluster([]) == []


# --- discover_api_endpoints ---

def test_discover_api_endpoints_extracts_fetch_urls():
    html = '<html><script>fetch("/api/data"); fetch("/api/users");</script></html>'
    with patch("browser_harness.helpers.http_get", return_value=html):
        result = helpers.discover_api_endpoints("https://example.com/page")
    urls = [e["url"] for e in result["endpoints"]]
    assert "https://example.com/api/data" in urls
    assert "https://example.com/api/users" in urls


def test_discover_api_endpoints_extracts_from_external_scripts():
    html = '<html><script src="/app.js"></script></html>'
    js_code = 'fetch("/api/v2/items"); axios.get("/api/products");'
    with patch("browser_harness.helpers.http_get", side_effect=[html, js_code]):
        result = helpers.discover_api_endpoints("https://example.com/page")
    urls = [e["url"] for e in result["endpoints"]]
    assert "https://example.com/api/v2/items" in urls
    assert "https://example.com/api/products" in urls


def test_discover_api_endpoints_handles_fetch_failure():
    with patch("browser_harness.helpers.http_get", side_effect=Exception("fail")), \
         patch("browser_harness.helpers.http_get_browser_session_response", side_effect=Exception("also fail")):
        result = helpers.discover_api_endpoints("https://example.com")
    assert result["endpoints"] == []
    assert len(result["errors"]) == 1


def test_block_resources_skips_paused_fetch_events_with_malformed_params():
    calls = []

    def fake_cdp(method, **params):
        calls.append((method, params))
        return {}

    events = [
        {"method": "Fetch.requestPaused", "params": "bad-params"},
        {"method": "Fetch.requestPaused", "params": {"requestId": "r1"}},
    ]

    with patch("browser_harness.helpers.cdp", side_effect=fake_cdp), \
         patch("browser_harness.helpers.drain_events", side_effect=[events, []]), \
         patch("time.sleep"):
        assert helpers.block_resources(ad_domains=False, resource_types=["Image"]) == 1

    assert ("Fetch.failRequest", {"requestId": "r1", "errorReason": "BlockedByClient"}) in calls
    assert calls[-1] == ("Fetch.disable", {})


def test_discover_api_endpoints_skips_template_literals():
    html = '<script>fetch(`/api/${id}`);</script>'
    with patch("browser_harness.helpers.http_get", return_value=html):
        result = helpers.discover_api_endpoints("https://example.com")
    assert result["endpoints"] == []


# --- replay_endpoints ---

def test_replay_endpoints_status_match():
    cap = helpers.NetworkCapture()
    cap._entries = [
        {"url": "https://api.example.com/a", "method": "GET", "status": 200,
         "content_type": "application/json", "response_headers": {}, "resource_type": "XHR"},
    ]
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.headers.get.return_value = "application/json"
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)
    with patch("browser_harness.helpers.urllib.request.urlopen", return_value=mock_resp), \
         patch("browser_harness.helpers._real_user_agent", return_value="TestAgent/1.0"), \
         patch("time.sleep"):
        result = helpers.replay_endpoints(cap)
    assert result["results"][0]["status_match"] is True
    assert result["summary"]["matched"] == 1


def test_replay_endpoints_skips_non_get():
    cap = helpers.NetworkCapture()
    cap._entries = [
        {"url": "https://api.example.com/a", "method": "POST", "status": 200,
         "content_type": "json", "response_headers": {}, "resource_type": "XHR"},
    ]
    with patch("time.sleep"):
        result = helpers.replay_endpoints(cap)
    assert result["results"][0]["skipped"] is True
    assert result["summary"]["total"] == 1


def test_replay_endpoints_captures_errors():
    cap = helpers.NetworkCapture()
    cap._entries = [
        {"url": "https://api.example.com/a", "method": "GET", "status": 200,
         "content_type": "json", "response_headers": {}, "resource_type": "XHR"},
    ]
    with patch("browser_harness.helpers.urllib.request.urlopen", side_effect=urllib.error.HTTPError(
        "https://api.example.com/a", 403, "Forbidden", {}, io.BytesIO(b""))), \
         patch("browser_harness.helpers._real_user_agent", return_value="TestAgent/1.0"), \
         patch("time.sleep"):
        result = helpers.replay_endpoints(cap)
    assert result["results"][0]["status_match"] is False
    assert result["results"][0]["replay_status"] == 403
    assert result["summary"]["errors"] == 0


def test_replay_endpoints_tolerates_malformed_session_headers():
    cap = helpers.NetworkCapture()
    cap._entries = [
        {"url": "https://api.example.com/a", "method": "GET", "status": 200,
         "content_type": "application/json", "response_headers": {}, "resource_type": "XHR"},
    ]
    with patch("browser_harness.helpers.http_get_browser_session_response", return_value={
        "status": 200,
        "headers": "not-a-dict",
    }), patch("time.sleep"):
        result = helpers.replay_endpoints(cap, use_session=True)

    assert result["results"][0] == {
        "url": "https://api.example.com/a",
        "original_status": 200,
        "replay_status": 200,
        "status_match": True,
        "content_type_match": False,
    }
    assert result["summary"] == {"total": 1, "matched": 1, "mismatched": 0, "errors": 0}


def test_replay_endpoints_skips_malformed_endpoint_rows():
    class Capture:
        @staticmethod
        def endpoints():
            return [
                "not an endpoint",
                {"method": "GET"},
                {"url": "https://api.example.com/a", "method": "POST", "status": 200},
            ]

    with patch("time.sleep"):
        result = helpers.replay_endpoints(Capture())

    assert result["results"] == [
        {"url": "", "skipped": True, "reason": "missing-url"},
        {"url": "https://api.example.com/a", "skipped": True, "reason": "non-GET"},
    ]
    assert result["summary"] == {"total": 2, "matched": 0, "mismatched": 0, "errors": 0}


def test_install_blocker_probe_enables_page_and_injects_script():
    calls = []
    with patch("browser_harness.helpers.cdp", side_effect=lambda m, **kw: calls.append(m) or {"identifier": "1"}):
        result = helpers.install_blocker_probe()
    assert calls == ["Page.enable", "Page.addScriptToEvaluateOnNewDocument"]
    assert result["identifier"] == "1"


def test_pending_blockers_returns_cdp_and_js_sides():
    cdp_blockers = [{"kind": "dialog", "params": {"type": "alert"}, "t": 1.0}]
    js_blockers = [{"kind": "geolocation", "t": 2.0}]
    with patch("browser_harness.helpers._send", return_value={"blockers": cdp_blockers}), \
         patch("browser_harness.helpers.js", return_value=js_blockers):
        result = helpers.pending_blockers()
    assert result["cdp"] == cdp_blockers
    assert result["js"] == js_blockers


def test_pending_blockers_clears_js_when_requested():
    with patch("browser_harness.helpers._send", return_value={"blockers": []}), \
         patch("browser_harness.helpers.js", return_value=[]) as mock_js:
        helpers.pending_blockers(clear_js=True)
    expr = mock_js.call_args[0][0]
    assert "window.__bh_blockers__=[]" in expr


def test_pending_blockers_handles_js_frozen_gracefully():
    with patch("browser_harness.helpers._send", return_value={"blockers": []}), \
         patch("browser_harness.helpers.js", side_effect=RuntimeError("JS frozen")):
        result = helpers.pending_blockers()
    assert result == {"cdp": [], "js": []}


def test_pending_blockers_empty_when_no_blockers():
    with patch("browser_harness.helpers._send", return_value={"blockers": []}), \
         patch("browser_harness.helpers.js", return_value=None):
        result = helpers.pending_blockers()
    assert result == {"cdp": [], "js": []}


def test_pending_blockers_ignores_malformed_rows():
    cdp_blockers = ["bad-blocker", {"kind": "dialog", "params": {"type": "alert"}, "t": 1.0}]
    js_blockers = ["bad-js", {"kind": "geolocation", "t": 2.0}]
    with patch("browser_harness.helpers._send", return_value={"blockers": cdp_blockers}), \
         patch("browser_harness.helpers.js", return_value=js_blockers):
        result = helpers.pending_blockers()
    assert result == {"cdp": [cdp_blockers[1]], "js": [js_blockers[1]]}


def test_dismiss_dialog_accepts_and_returns_info():
    dialog_event = {
        "method": "Page.javascriptDialogOpening",
        "params": {"type": "confirm", "message": "Are you sure?", "url": "https://example.com"},
    }
    with patch("browser_harness.helpers.drain_events", return_value=[dialog_event]), \
         patch("browser_harness.helpers.cdp", return_value={}):
        info = helpers.dismiss_dialog(accept=True)
    assert info["type"] == "confirm"
    assert info["message"] == "Are you sure?"
    assert helpers.cdp == helpers.cdp  # sanity


def test_dismiss_dialog_returns_none_when_no_dialog():
    with patch("browser_harness.helpers.drain_events", return_value=[]), \
         patch("browser_harness.helpers.cdp", side_effect=Exception("no dialog")):
        info = helpers.dismiss_dialog()
    assert info is None


def test_dismiss_dialog_skips_malformed_events_and_params():
    events = [
        "bad-event",
        {"method": "Page.javascriptDialogOpening", "params": "bad-params"},
        {"method": "Page.javascriptDialogOpening", "params": {"type": "alert", "message": "Hi"}},
    ]
    with patch("browser_harness.helpers.drain_events", return_value=events), \
         patch("browser_harness.helpers.cdp", return_value={}):
        info = helpers.dismiss_dialog()
    assert info == {"type": "alert", "message": "Hi", "url": ""}


def test_capture_dialogs_stubs_window_methods():
    with patch("browser_harness.helpers.js") as mock_js:
        helpers.capture_dialogs()
    expr = mock_js.call_args[0][0]
    assert "window.__bh_dialogs__" in expr
    assert "window.alert" in expr
    assert "window.confirm" in expr
    assert "window.prompt" in expr


def test_dialogs_returns_captured_messages():
    with patch("browser_harness.helpers.js", return_value=["hello", "world"]):
        result = helpers.dialogs()
    assert result == ["hello", "world"]


def test_grant_permissions_calls_browser_grantPermissions():
    with patch("browser_harness.helpers.cdp", return_value={}) as mock_cdp:
        helpers.grant_permissions("https://example.com", ["geolocation", "notifications"])
    mock_cdp.assert_called_once_with(
        "Browser.grantPermissions",
        origin="https://example.com",
        permissions=["geolocation", "notifications"],
    )


def test_set_geolocation_calls_emulation_setGeolocationOverride():
    with patch("browser_harness.helpers.cdp", return_value={}) as mock_cdp:
        helpers.set_geolocation(37.7749, -122.4194, accuracy=50)
    mock_cdp.assert_called_once_with(
        "Emulation.setGeolocationOverride",
        latitude=37.7749,
        longitude=-122.4194,
        accuracy=50,
    )


# --- capture_screenshot resize ---

def _run_capture(fake_png, width, height, **kwargs):
    fake = lambda method, **_: {"data": fake_png(width, height)}
    with patch("browser_harness.helpers.cdp", side_effect=fake), tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "shot.png")
        helpers.capture_screenshot(path, **kwargs)
        return Image.open(path).size


def test_max_dim_downsizes_oversized_image(fake_png):
    assert max(_run_capture(fake_png, 4592, 2286, max_dim=1800)) == 1800


def test_max_dim_skips_when_image_already_small(fake_png):
    assert _run_capture(fake_png, 800, 400, max_dim=1800) == (800, 400)


def test_max_dim_default_is_no_resize(fake_png):
    assert _run_capture(fake_png, 4592, 2286) == (4592, 2286)


# --- goto_url domain-skill discovery ---

def test_goto_url_omits_domain_skills_when_no_skill_dir(tmp_path):
    # tmp_path has no "example" subdirectory → domain_skills absent from result
    with patch("browser_harness.helpers.cdp", return_value={"frameId": "f"}), \
         patch("browser_harness.helpers.drain_events", return_value=[]), \
         patch("browser_harness.helpers._asset_dir", return_value=tmp_path):
        result = helpers.goto_url("https://www.example.com/")
    assert result == {"frameId": "f"}


def test_goto_url_includes_domain_skills_when_skill_dir_present(tmp_path):
    site = tmp_path / "example"
    site.mkdir()
    (site / "scraping.md").write_text("hi")
    with patch("browser_harness.helpers.cdp", return_value={"frameId": "f"}), \
         patch("browser_harness.helpers.drain_events", return_value=[]), \
         patch("browser_harness.helpers._asset_dir", return_value=tmp_path):
        result = helpers.goto_url("https://www.example.com/")
    assert result == {"frameId": "f", "domain_skills": ["scraping.md"]}


# --- page_info JS exception surfacing ---

def test_page_info_raises_clear_error_on_js_exception():
    def fake_send(req):
        return {}

    def fake_cdp(method, **kwargs):
        return {
            "result": {
                "type": "object",
                "subtype": "error",
                "description": "ReferenceError: location is not defined",
            },
            "exceptionDetails": {
                "text": "Uncaught",
                "lineNumber": 0,
                "columnNumber": 16,
            },
        }

    with patch("browser_harness.helpers._send", side_effect=fake_send), \
         patch("browser_harness.helpers.cdp", side_effect=fake_cdp):
        with pytest.raises(RuntimeError, match="ReferenceError"):
            helpers.page_info()


def test_page_info_tolerates_malformed_exception_details():
    def fake_cdp(method, **kwargs):
        return {
            "result": "not-an-object",
            "exceptionDetails": "not-an-object",
        }

    with patch("browser_harness.helpers._send", return_value={}), \
         patch("browser_harness.helpers.cdp", side_effect=fake_cdp):
        with pytest.raises(RuntimeError, match="page_info: JS exception"):
            helpers.page_info()


# --- fill_input ---

def test_fill_input_focuses_types_and_fires_events():
    cdp_calls = []
    js_calls = []

    def fake_cdp(method, **kwargs):
        cdp_calls.append((method, kwargs))
        return {}

    def fake_js(expr, **kwargs):
        js_calls.append(expr)
        return True  # focus call must return True (element found)

    with patch("browser_harness.helpers.cdp", side_effect=fake_cdp), \
         patch("browser_harness.helpers.js", side_effect=fake_js):
        helpers.fill_input("#my-input", "hello")

    assert any("#my-input" in e for e in js_calls)
    key_downs = [m for m, _ in cdp_calls if m == "Input.dispatchKeyEvent"]
    assert len(key_downs) > 0
    assert any("input" in e and "change" in e for e in js_calls)


def test_fill_input_raises_when_element_not_found():
    def fake_js(expr, **kwargs):
        return False  # element not found

    with patch("browser_harness.helpers.js", side_effect=fake_js):
        with pytest.raises(RuntimeError, match="element not found"):
            helpers.fill_input("#missing", "hello")


def test_fill_input_clear_first_sends_select_all_then_backspace():
    key_events = []

    def fake_cdp(method, **kwargs):
        if method == "Input.dispatchKeyEvent":
            key_events.append(kwargs)
        return {}

    def fake_js(expr, **kwargs):
        return True  # element found

    with patch("browser_harness.helpers.cdp", side_effect=fake_cdp), \
         patch("browser_harness.helpers.js", side_effect=fake_js):
        helpers.fill_input("#inp", "x", clear_first=True)

    # The "a" must be dispatched with the platform-correct modifier (Meta=4 on
    # macOS, Ctrl=2 elsewhere). Without the modifier, the field would never get
    # selected — it would just receive a literal "a".
    expected_mod = 4 if sys.platform == "darwin" else 2
    a_events = [e for e in key_events if e.get("key") == "a"]
    assert a_events, "expected an 'a' key event for select-all"
    assert all(e.get("modifiers") == expected_mod for e in a_events), \
        f"select-all 'a' must carry modifiers={expected_mod}; got {[e.get('modifiers') for e in a_events]}"

    # Crucial: no `char` event for the "a" — emitting one makes Chrome treat
    # Cmd/Ctrl+A as a printable letter instead of a shortcut.
    assert not any(e.get("type") == "char" and e.get("text") == "a" for e in key_events), \
        "select-all must not emit a 'char' event with text='a' (would cancel the shortcut)"

    # Backspace still fires (via press_key, which uses keyDown).
    keys_down = [e.get("key") for e in key_events if e.get("type") in ("keyDown", "rawKeyDown")]
    assert "Backspace" in keys_down


def test_fill_input_no_clear_skips_ctrl_a():
    key_events = []

    def fake_cdp(method, **kwargs):
        if method == "Input.dispatchKeyEvent":
            key_events.append(kwargs)
        return {}

    def fake_js(expr, **kwargs):
        return True  # element found

    with patch("browser_harness.helpers.cdp", side_effect=fake_cdp), \
         patch("browser_harness.helpers.js", side_effect=fake_js):
        helpers.fill_input("#inp", "x", clear_first=False)

    keys_seen = [e.get("key") for e in key_events if e.get("type") == "keyDown"]
    assert "Backspace" not in keys_seen


# --- wait_for_element ---

def test_wait_for_element_returns_true_when_found_immediately():
    def fake_js(expr, **kwargs):
        return True

    with patch("browser_harness.helpers.js", side_effect=fake_js):
        assert helpers.wait_for_element("#target", timeout=2.0) is True


def test_wait_for_element_returns_false_on_timeout():
    def fake_js(expr, **kwargs):
        return False

    with patch("browser_harness.helpers.js", side_effect=fake_js), \
         patch("browser_harness.helpers.time") as mock_time:
        # simulate time advancing past the deadline immediately
        start = time.time()
        mock_time.time.side_effect = [start, start + 5.0]
        mock_time.sleep = lambda _: None
        assert helpers.wait_for_element("#missing", timeout=1.0) is False


def test_wait_for_element_visible_uses_check_visibility():
    js_exprs = []

    def fake_js(expr, **kwargs):
        js_exprs.append(expr)
        return True

    with patch("browser_harness.helpers.js", side_effect=fake_js):
        helpers.wait_for_element("#btn", visible=True)

    # Prefers checkVisibility (walks ancestor chain) with a computed-style
    # fallback for older Chrome.
    assert any("checkVisibility" in e for e in js_exprs)
    assert any("getComputedStyle" in e for e in js_exprs)
    # must NOT use offsetParent (fails for position:fixed elements)
    assert not any("offsetParent" in e for e in js_exprs)


def test_wait_for_element_non_visible_uses_simple_check():
    js_exprs = []

    def fake_js(expr, **kwargs):
        js_exprs.append(expr)
        return True

    with patch("browser_harness.helpers.js", side_effect=fake_js):
        helpers.wait_for_element("#btn", visible=False)

    assert any("querySelector" in e and "offsetParent" not in e for e in js_exprs)


# --- wait_for_network_idle ---

def test_wait_for_network_idle_returns_true_when_no_events():
    def fake_send(req):
        return {"events": []}

    with patch("browser_harness.helpers._send", side_effect=fake_send), \
         patch("browser_harness.helpers.time") as mock_time:
        start = 1000.0
        # first call: not idle yet; second call: idle window elapsed
        mock_time.time.side_effect = [start, start, start, start + 0.6, start + 0.6]
        mock_time.sleep = lambda _: None
        result = helpers.wait_for_network_idle(timeout=5.0, idle_ms=500)

    assert result is True


def test_wait_for_network_idle_waits_for_inflight_request():
    # Verifies inflight tracking: must not return True until loadingFinished,
    # even though >idle_ms elapses between requestWillBeSent and loadingFinished.
    # An event-silence-only implementation would return True at iter2 (wrong).
    events_seq = [
        [{"method": "Network.requestWillBeSent", "params": {"requestId": "req1"}}],
        [],   # >500ms elapsed — old impl returns True here; new must NOT
        [{"method": "Network.loadingFinished",   "params": {"requestId": "req1"}}],
        [],   # idle_ms after loadingFinished → return True
    ]
    idx = 0

    def fake_send(req):
        nonlocal idx
        evs = events_seq[min(idx, len(events_seq) - 1)]
        idx += 1
        return {"events": evs}

    with patch("browser_harness.helpers._send", side_effect=fake_send), \
         patch("browser_harness.helpers.time") as mock_time:
        start = 1000.0
        # inflight non-empty → short-circuit skips time.time() in idle check for iter1/iter2
        mock_time.time.side_effect = [
            start, start,       # deadline + last_activity init
            start + 0.1,        # iter1 while-check
            start + 0.1,        # iter1 rWS last_activity update
                                # iter1 idle-check: inflight non-empty → short-circuit
            start + 0.7,        # iter2 while-check (>500ms since rWS but request still in flight)
                                # iter2 idle-check: inflight non-empty → short-circuit
            start + 0.8,        # iter3 while-check
            start + 0.8,        # iter3 lF last_activity update
            start + 0.8,        # iter3 idle-check: 0ms < 500 → not idle
            start + 1.4,        # iter4 while-check
            start + 1.4,        # iter4 idle-check: 600ms >= 500 → True
        ]
        mock_time.sleep = lambda _: None
        result = helpers.wait_for_network_idle(timeout=5.0, idle_ms=500)

    assert result is True
    assert idx == 4  # did not short-circuit at iter2 despite silence > idle_ms


def test_wait_for_network_idle_returns_false_on_timeout():
    # Continuous rWS keeps inflight non-empty → idle check short-circuits every iteration.
    # time.time() is only called for while-check and rWS last_activity (not idle check).
    def fake_send(req):
        return {"events": [{"method": "Network.requestWillBeSent", "params": {"requestId": "r"}}]}

    with patch("browser_harness.helpers._send", side_effect=fake_send), \
         patch("browser_harness.helpers.time") as mock_time:
        start = 1000.0
        mock_time.time.side_effect = [
            start, start,       # deadline + last_activity init
            start + 0.1,        # iter1 while-check (in deadline)
            start + 0.1,        # iter1 rWS last_activity update
                                # iter1 idle-check: inflight non-empty → short-circuit
            start + 20.0,       # iter2 while-check (past deadline → exit)
        ]
        mock_time.sleep = lambda _: None
        result = helpers.wait_for_network_idle(timeout=10.0, idle_ms=500)

    assert result is False


def test_wait_for_network_idle_filters_events_to_active_session():
    """Background tabs (e.g. a polling page the agent switched away from) keep
    emitting Network events into the daemon's global buffer. The wait must
    filter by session_id of the currently-attached tab — otherwise it would
    see the background tab's traffic and either fail to return idle or wait
    on the wrong tab's requests."""
    active = "session-ACTIVE"
    background = "session-BACKGROUND"

    # First /drain_events/ payload: rWS + lF on the BACKGROUND session that we
    # must ignore, plus zero events on the active session. With filtering, the
    # active session sees no traffic and the idle window can elapse.
    events_seq = [
        [
            {"session_id": background, "method": "Network.requestWillBeSent", "params": {"requestId": "bg1"}},
            {"session_id": background, "method": "Network.loadingFinished",   "params": {"requestId": "bg1"}},
        ],
        [],  # second drain — quiet on both sessions; idle window should fire here
    ]
    drain_idx = 0

    def fake_send(req):
        nonlocal drain_idx
        if req.get("meta") == "session":
            return {"session_id": active}
        if req.get("meta") == "drain_events":
            evs = events_seq[min(drain_idx, len(events_seq) - 1)]
            drain_idx += 1
            return {"events": evs}
        return {}

    with patch("browser_harness.helpers._send", side_effect=fake_send), \
         patch("browser_harness.helpers.time") as mock_time:
        start = 1000.0
        # No inflight on active session → idle check uses time.time().
        mock_time.time.side_effect = [start, start, start, start + 0.6, start + 0.6]
        mock_time.sleep = lambda _: None
        result = helpers.wait_for_network_idle(timeout=5.0, idle_ms=500)

    assert result is True, (
        "wait_for_network_idle must return True even when the BACKGROUND "
        "session is busy, as long as the ACTIVE session is idle. Without the "
        "session filter, the background rWS/lF pair would have updated "
        "last_activity and prevented the idle window from elapsing."
    )
