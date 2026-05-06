from unittest.mock import MagicMock, patch

import lightpanda_control


def test_evaluate_field_contract_requires_page_text_and_named_fields():
    class Client:
        def __init__(self):
            self.calls = []

        def send_raw(self, method, params, session_id=None):
            self.calls.append((method, params, session_id))
            expression = params["expression"]
            if "textLength" in expression:
                return {"result": {"value": {
                    "url": "https://www.airbnb.com.au/s/Melbourne/homes",
                    "title": "Airbnb",
                    "textLength": 1189,
                    "linkCount": 50,
                }}}
            if "rooms" in expression:
                return {"result": {"value": False}}
            if "AUD" in expression:
                return {"result": {"value": True}}
            return {"result": {"value": None}}

    result = lightpanda_control.evaluate_field_contract(
        Client(),
        {
            "room_links": 'Array.from(document.querySelectorAll("a[href]")).some(a => /rooms/.test(a.href))',
            "aud_prices": '/AUD/.test(document.body.innerText)',
        },
        min_text=1500,
        session_id="SID-1",
    )

    assert result["ok"] is False
    assert result["passed"] == {"room_links": False, "aud_prices": True}
    assert result["missing"] == ["min_text", "room_links"]


def test_wait_for_field_contract_polls_until_fields_present():
    results = [
        {"ok": False, "missing": ["room_links"]},
        {"ok": True, "missing": []},
    ]

    with patch("lightpanda_control.evaluate_field_contract", side_effect=results) as evaluate:
        result = lightpanda_control.wait_for_field_contract(
            object(),
            {"room_links": "true"},
            timeout=1.0,
            poll=0.0,
        )

    assert result["ok"] is True
    assert result["reason"] == "fields_present"
    assert evaluate.call_count == 2


def test_lightpanda_cdp_routes_browser_and_page_scoped_methods():
    client = lightpanda_control.LightpandaCDP.__new__(lightpanda_control.LightpandaCDP)
    client.page_session_id = "SID-1"
    client.calls = []

    def request(method, params=None, session_id=None):
        client.calls.append((method, params, session_id))
        return {}

    client._request = request

    client.send_raw("Runtime.evaluate", {"expression": "1"})
    client.send_raw("Browser.getVersion", {})
    client.send_raw("Storage.getCookies", {})
    client.send_raw("Network.getCookies", {"urls": ["https://example.com/"]})
    client.send_raw("Runtime.evaluate", {"expression": "2"}, session_id="SID-2")

    assert client.calls == [
        ("Runtime.evaluate", {"expression": "1"}, "SID-1"),
        ("Browser.getVersion", {}, None),
        ("Storage.getCookies", {}, None),
        ("Network.getCookies", {"urls": ["https://example.com/"]}, "SID-1"),
        ("Runtime.evaluate", {"expression": "2"}, "SID-2"),
    ]


def test_lightpanda_cdp_ensure_page_creates_and_attaches_target():
    client = lightpanda_control.LightpandaCDP.__new__(lightpanda_control.LightpandaCDP)
    client.page_session_id = None
    client.target_id = None
    client.calls = []

    def request(method, params=None, session_id=None):
        client.calls.append((method, params, session_id))
        if method == "Target.createTarget":
            return {"targetId": "FID-1"}
        if method == "Target.attachToTarget":
            return {"sessionId": "SID-1"}
        return {}

    client._request = request

    assert client.ensure_page("about:blank") == "SID-1"
    assert client.target_id == "FID-1"
    assert client.calls == [
        ("Target.createTarget", {"url": "about:blank"}, None),
        ("Target.attachToTarget", {"targetId": "FID-1", "flatten": True}, None),
        ("Page.enable", {}, "SID-1"),
        ("Runtime.enable", {}, "SID-1"),
        ("Network.enable", {}, "SID-1"),
    ]


def test_lightpanda_server_launches_serve_and_closes_process(tmp_path):
    proc = MagicMock()
    proc.pid = 12345

    with patch("subprocess.Popen", return_value=proc) as popen, \
         patch("lightpanda_control.wait_json_version", return_value={"webSocketDebuggerUrl": "ws://127.0.0.1:9222/"}) as wait_version, \
         patch("lightpanda_control.LightpandaCDP") as cdp_class:
        cdp_class.return_value.ensure_page.return_value = "SID-1"
        server = lightpanda_control.LightpandaServer("/bin/lightpanda", port=9222, log_path=tmp_path / "lp.log")
        server.start()
        server.close()

    popen.assert_called_once()
    assert popen.call_args.args[0] == [
        "/bin/lightpanda",
        "serve",
        "--host",
        "127.0.0.1",
        "--port",
        "9222",
    ]
    wait_version.assert_called_once_with(9222, timeout=20.0)
    cdp_class.assert_called_once_with("ws://127.0.0.1:9222/")
    cdp_class.return_value.ensure_page.assert_called_once_with()
    cdp_class.return_value.close.assert_called_once_with()
    proc.terminate.assert_called_once()
    proc.wait.assert_called_once_with(timeout=5)
