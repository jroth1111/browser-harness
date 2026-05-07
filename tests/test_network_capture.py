from unittest.mock import patch, call
from browser_harness import network_capture


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
