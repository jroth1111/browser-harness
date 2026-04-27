import gzip
import io
import urllib.error
from unittest.mock import patch

import login_session


def test_send_cdp_supports_callable_client():
    calls = []

    def client(method, session_id=None, **params):
        calls.append((method, session_id, params))
        return {"ok": True}

    assert login_session.send_cdp(client, "Runtime.evaluate", {"expression": "1"}, session_id="s1") == {"ok": True}
    assert calls == [("Runtime.evaluate", "s1", {"expression": "1"})]


def test_send_cdp_supports_send_raw_client():
    class Client:
        def __init__(self):
            self.calls = []

        def send_raw(self, method, params, session_id=None):
            self.calls.append((method, params, session_id))
            return {"ok": True}

    client = Client()
    assert login_session.send_cdp(client, "Network.getCookies", {"urls": ["https://example.com"]}) == {"ok": True}
    assert client.calls == [("Network.getCookies", {"urls": ["https://example.com"]}, None)]


def test_send_cdp_supports_send_method_params_client():
    class Client:
        def __init__(self):
            self.calls = []

        def send(self, method, params):
            self.calls.append((method, params))
            return {"ok": True}

    client = Client()
    assert login_session.send_cdp(client, "Network.getCookies", {"urls": ["https://example.com"]}) == {"ok": True}
    assert client.calls == [("Network.getCookies", {"urls": ["https://example.com"]})]


def test_send_cdp_supports_send_keyword_client():
    class Client:
        def __init__(self):
            self.calls = []

        def send(self, method, **params):
            self.calls.append((method, params))
            return {"ok": True}

    client = Client()
    assert login_session.send_cdp(client, "Runtime.evaluate", {"expression": "1"}) == {"ok": True}
    assert client.calls == [("Runtime.evaluate", {"expression": "1"})]


def test_cookie_header_filters_cookie_scope():
    cookies = [
        {"name": "sid", "value": "abc", "domain": ".example.com", "path": "/", "secure": True},
        {"name": "other", "value": "bad", "domain": ".other.test", "path": "/", "secure": True},
        {"name": "path", "value": "bad", "domain": ".example.com", "path": "/admin", "secure": True},
    ]

    assert login_session.cookie_header(None, "https://www.example.com/page", cookies=cookies) == "sid=abc"


def test_session_manifest_redacts_cookie_and_storage_values():
    def client(method, **params):
        if method == "Network.getCookies":
            return {"cookies": [
                {"name": "sid", "value": "secret", "domain": ".example.com", "path": "/", "secure": True},
            ]}
        if method == "Runtime.evaluate":
            return {"result": {"value": {
                "url": "https://www.example.com/account",
                "origin": "https://www.example.com",
                "localStorageKeys": ["token"],
                "sessionStorageKeys": ["state"],
            }}}
        raise AssertionError(method)

    manifest = login_session.session_manifest(
        client,
        "https://www.example.com/account",
        site="example",
        profile_label="main",
        account_label="acct",
        backend="chromium",
    )

    assert manifest["cookie_names"] == ["sid"]
    assert manifest["cookie_domains"] == [".example.com"]
    assert manifest["local_storage_keys"] == ["token"]
    assert manifest["session_storage_keys"] == ["state"]
    assert "secret" not in repr(manifest)


def test_session_manifest_redacts_identifiers_from_storage_key_names():
    def client(method, **params):
        if method == "Network.getCookies":
            return {"cookies": []}
        if method == "Runtime.evaluate":
            return {"result": {"value": {
                "url": "https://www.example.com/account",
                "origin": "https://www.example.com",
                "localStorageKeys": [
                    "/v2/get-data-layer-variables/-userId-117563320-bevId-1777262403-EAZmVkYjhlMjgzZG-listingId-1603434441736660031-",
                    "tab-tracking-v2-tabTimestamp-1baecc2d-a158-4d95-9daf-2d6e1c640211",
                ],
                "sessionStorageKeys": ["reservationId=ABC123456789"],
            }}}
        raise AssertionError(method)

    manifest = login_session.session_manifest(client, "https://www.example.com/account")

    rendered = repr(manifest)
    assert "117563320" not in rendered
    assert "1777262403" not in rendered
    assert "EAZmVkYjhlMjgzZG" not in rendered
    assert "1603434441736660031" not in rendered
    assert "1baecc2d-a158-4d95-9daf-2d6e1c640211" not in rendered
    assert "ABC123456789" not in rendered
    assert "/v2/get-data-layer-variables/-userId-<redacted>-bevId-<redacted>-listingId-<redacted>" in rendered
    assert "tab-tracking-v2-tabTimestamp-<uuid>" in rendered
    assert "reservationId=<redacted>" in rendered


def test_session_state_keeps_values_for_private_restore_bundle():
    def client(method, **params):
        if method == "Network.getCookies":
            return {"cookies": [
                {"name": "sid", "value": "secret", "domain": ".example.com", "path": "/", "secure": True},
            ]}
        if method == "Runtime.evaluate":
            return {"result": {"value": {
                "url": "https://www.example.com/account",
                "origin": "https://www.example.com",
                "localStorage": {"token": "local-secret"},
                "sessionStorage": {"state": "session-secret"},
            }}}
        raise AssertionError(method)

    state = login_session.session_state(client, "https://www.example.com/account", site="example")

    assert state["cookies"][0]["value"] == "secret"
    assert state["origins"][0]["localStorage"]["token"] == "local-secret"
    assert state["origins"][0]["sessionStorage"]["state"] == "session-secret"


def test_cookie_param_keeps_restorable_fields_only():
    cookie = {
        "name": "sid",
        "value": "secret",
        "domain": ".example.com",
        "path": "/",
        "secure": True,
        "httpOnly": True,
        "expires": -1,
        "size": 99,
        "session": True,
    }

    assert login_session.cookie_param(cookie) == {
        "name": "sid",
        "value": "secret",
        "domain": ".example.com",
        "path": "/",
        "secure": True,
        "httpOnly": True,
    }


def test_http_get_with_login_session_captures_http_error_body():
    html = "<html>blocked</html>"
    err = urllib.error.HTTPError(
        "https://www.example.com/private",
        403,
        "Forbidden",
        {"Content-Encoding": "gzip"},
        io.BytesIO(gzip.compress(html.encode())),
    )

    def client(method, **params):
        if method == "Runtime.evaluate":
            return {"result": {"value": "Browser UA"}}
        if method == "Network.getCookies":
            return {"cookies": [{"name": "sid", "value": "abc", "domain": ".example.com", "path": "/", "secure": True}]}
        raise AssertionError(method)

    with patch("urllib.request.urlopen", side_effect=err):
        result = login_session.http_get_with_login_session(
            client,
            "https://www.example.com/private",
            block_detector=lambda html="", text="", url="": {"blocked": "blocked" in html, "kind": "test", "evidence": []},
        )

    assert result["ok"] is False
    assert result["http_ok"] is False
    assert result["status"] == 403
    assert result["block"]["blocked"] is True
    assert result["text"] == html


def test_prompt_user_login_waits_until_url_and_text_match():
    states = iter([
        {"url": "https://example.com/login", "title": "Login", "readyState": "complete", "textLength": 20},
        {"url": "https://example.com/account", "title": "Account", "readyState": "complete", "textLength": 300},
    ])
    calls = []

    def client(method, **params):
        calls.append((method, params))
        if method == "Runtime.evaluate":
            return {"result": {"value": next(states)}}
        return {}

    with patch("time.sleep"):
        result = login_session.prompt_user_login(
            client,
            "https://example.com/login",
            success_url_contains="/account",
            min_text=200,
            timeout=5,
        )

    assert result["ok"] is True
    assert result["reason"] == "login_observed"
    assert calls[0] == ("Page.enable", {})
    assert calls[1] == ("Page.navigate", {"url": "https://example.com/login"})
