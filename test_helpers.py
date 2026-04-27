from unittest.mock import patch

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
