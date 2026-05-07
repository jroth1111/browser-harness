from unittest.mock import patch, call
from browser_harness import network_capture


def test_capture_network_requests_uses_network_capture_helper():
    class FakeCapture:
        def __init__(self, capture_bodies=False, max_body_chars=0):
            self.capture_bodies = capture_bodies
            self.max_body_chars = max_body_chars
            self._entries = [{
                "url": "https://x.com/api",
                "method": "POST",
                "status": 201,
                "resource_type": "XHR",
                "content_type": "application/json",
                "response_headers": {"x-source": "new-helper"},
            }]
            self._requests = {}
            self.calls = []

        def start(self):
            self.calls.append("start")

        def poll(self):
            self.calls.append("poll")

        def stop(self):
            self.calls.append("stop")

    instances = []

    def fake_capture(*args, **kwargs):
        capture = FakeCapture(*args, **kwargs)
        instances.append(capture)
        return capture

    with patch("browser_harness.network_capture.helpers.NetworkCapture", side_effect=fake_capture), \
         patch("browser_harness.network_capture.helpers.goto_url") as goto_url, \
         patch("browser_harness.network_capture.time.sleep") as sleep:
        result = network_capture.capture_network_requests("https://x.com", timeout=2, capture_bodies=True)

    assert instances[0].capture_bodies is True
    assert instances[0].max_body_chars == network_capture._MAX_BODY_CHARS
    assert instances[0].calls == ["start", "poll", "stop"]
    goto_url.assert_called_once_with("https://x.com")
    sleep.assert_called_once_with(2)
    assert result == [{
        "url": "https://x.com/api",
        "method": "POST",
        "status": 201,
        "resource_type": "XHR",
        "mime_type": "application/json",
        "response_headers": {"x-source": "new-helper"},
    }]


def test_capture_network_requests_parses_events():
    events = [
        {"method": "Network.requestWillBeSent", "params": {
            "requestId": "r1", "request": {"url": "https://x.com/api", "method": "GET"}, "type": "XHR",
        }},
        {"method": "Network.responseReceived", "params": {
            "requestId": "r1", "response": {"status": 200, "mimeType": "application/json", "headers": {"x-foo": "bar"}},
        }},
        {"method": "Network.requestWillBeSent", "params": {
            "requestId": "r2", "request": {"url": "https://x.com/img.png", "method": "GET"}, "type": "Image",
        }},
        {"method": "Network.responseReceived", "params": {
            "requestId": "r2", "response": {"status": 304, "mimeType": "image/png", "headers": {}},
        }},
    ]

    with patch("browser_harness.network_capture.helpers.cdp"), \
         patch("browser_harness.network_capture.helpers.drain_events", return_value=events), \
         patch("browser_harness.network_capture.helpers.goto_url"), \
         patch("browser_harness.network_capture.time.sleep"):
        result = network_capture.capture_network_requests("https://x.com")

    assert len(result) == 2
    api = [r for r in result if r["url"] == "https://x.com/api"][0]
    assert api["method"] == "GET"
    assert api["status"] == 200
    assert api["mime_type"] == "application/json"
    assert api["response_headers"]["x-foo"] == "bar"

    img = [r for r in result if r["url"] == "https://x.com/img.png"][0]
    assert img["resource_type"] == "Image"
    assert img["status"] == 304


def test_capture_with_bodies_fetches_response_body():
    events = [
        {"method": "Network.requestWillBeSent", "params": {
            "requestId": "r1", "request": {"url": "https://x.com/api", "method": "GET"}, "type": "XHR",
        }},
        {"method": "Network.responseReceived", "params": {
            "requestId": "r1", "response": {"status": 200, "mimeType": "application/json", "headers": {}},
        }},
    ]

    def fake_cdp(method, **kwargs):
        if method == "Network.getResponseBody":
            return {"body": '{"key": "value"}', "base64Encoded": False}
        return {}

    with patch("browser_harness.network_capture.helpers.cdp", side_effect=fake_cdp) as cdp, \
         patch("browser_harness.network_capture.helpers.drain_events", return_value=events), \
         patch("browser_harness.network_capture.helpers.goto_url"), \
         patch("browser_harness.network_capture.time.sleep"):
        result = network_capture.capture_network_requests("https://x.com", capture_bodies=True)

    assert result[0]["body"] == '{"key": "value"}'
    assert cdp.mock_calls == [
        call("Network.enable"),
        call("Network.getResponseBody", requestId="r1"),
        call("Network.disable"),
    ]


def test_capture_without_bodies_omits_body_key():
    events = [
        {"method": "Network.requestWillBeSent", "params": {
            "requestId": "r1", "request": {"url": "https://x.com/api", "method": "GET"}, "type": "XHR",
        }},
        {"method": "Network.responseReceived", "params": {
            "requestId": "r1", "response": {"status": 200, "mimeType": "application/json", "headers": {}},
        }},
    ]

    with patch("browser_harness.network_capture.helpers.cdp"), \
         patch("browser_harness.network_capture.helpers.drain_events", return_value=events), \
         patch("browser_harness.network_capture.helpers.goto_url"), \
         patch("browser_harness.network_capture.time.sleep"):
        result = network_capture.capture_network_requests("https://x.com", capture_bodies=False)

    assert "body" not in result[0]


def test_capture_disables_network_when_navigation_fails():
    with patch("browser_harness.network_capture.helpers.cdp") as cdp, \
         patch("browser_harness.network_capture.helpers.drain_events", return_value=[]), \
         patch("browser_harness.network_capture.helpers.goto_url", side_effect=RuntimeError("navigation failed")), \
         patch("browser_harness.network_capture.time.sleep"):
        try:
            network_capture.capture_network_requests("https://x.com")
        except RuntimeError as exc:
            assert str(exc) == "navigation failed"
        else:
            raise AssertionError("navigation failure was not propagated")

    assert call("Network.disable") in cdp.mock_calls


def test_redacted_capture_entries_omits_body_secret_material():
    entries = [{
        "url": "https://x.com/api",
        "method": "GET",
        "headers": {"Cookie": "sid=secret", "X-Trace": "ok"},
        "response_headers": {"Set-Cookie": "sid=secret", "Content-Type": "application/json"},
        "body": '{"access_token":"secret"}',
    }]

    redacted = network_capture.redacted_capture_entries(entries)[0]

    assert redacted["headers"]["Cookie"] == "REDACTED"
    assert redacted["response_headers"]["Set-Cookie"] == "REDACTED"
    assert redacted["body_omitted"] is True
    assert redacted["body_length"] == len('{"access_token":"secret"}')
    assert "body" not in redacted
    assert "secret" not in repr(redacted)


def test_capture_handles_request_without_response():
    events = [
        {"method": "Network.requestWillBeSent", "params": {
            "requestId": "r1", "request": {"url": "https://x.com/pending", "method": "POST"}, "type": "XHR",
        }},
    ]

    with patch("browser_harness.network_capture.helpers.cdp"), \
         patch("browser_harness.network_capture.helpers.drain_events", return_value=events), \
         patch("browser_harness.network_capture.helpers.goto_url"), \
         patch("browser_harness.network_capture.time.sleep"):
        result = network_capture.capture_network_requests("https://x.com")

    assert len(result) == 1
    assert result[0]["status"] == 0
    assert result[0]["method"] == "POST"


def test_capture_skips_malformed_cdp_event_shapes():
    events = [
        "not an event",
        {"method": "Network.requestWillBeSent", "params": "bad-params"},
        {"method": "Network.requestWillBeSent", "params": {
            "requestId": "r1", "request": "bad-request", "type": "XHR",
        }},
        {"method": "Network.responseReceived", "params": {
            "requestId": "r1", "response": "bad-response",
        }},
    ]

    with patch("browser_harness.network_capture.helpers.cdp"), \
         patch("browser_harness.network_capture.helpers.drain_events", return_value=events), \
         patch("browser_harness.network_capture.helpers.goto_url"), \
         patch("browser_harness.network_capture.time.sleep"):
        result = network_capture.capture_network_requests("https://x.com")

    assert result == [{
        "url": "",
        "method": "",
        "status": 0,
        "resource_type": "XHR",
        "mime_type": "",
        "response_headers": {},
    }]


def test_capture_sanitizes_malformed_response_status_for_body_capture():
    events = [
        {"method": "Network.requestWillBeSent", "params": {
            "requestId": "r1", "request": {"url": "https://x.com/api", "method": "GET"}, "type": "XHR",
        }},
        {"method": "Network.responseReceived", "params": {
            "requestId": "r1", "response": {"status": "ok", "mimeType": "application/json", "headers": {}},
        }},
    ]

    with patch("browser_harness.network_capture.helpers.cdp"), \
         patch("browser_harness.network_capture.helpers.drain_events", return_value=events), \
         patch("browser_harness.network_capture.helpers.goto_url"), \
         patch("browser_harness.network_capture.time.sleep"):
        result = network_capture.capture_network_requests("https://x.com", capture_bodies=True)

    assert result[0]["status"] == 0
    assert "body" not in result[0]


def test_redacted_capture_entries_ignores_scalar_header_maps():
    redacted = network_capture.redacted_capture_entries([{
        "url": "https://x.com/api",
        "headers": "not headers",
        "response_headers": ["not", "headers"],
    }])[0]

    assert redacted["headers"] == {}
    assert redacted["response_headers"] == {}
