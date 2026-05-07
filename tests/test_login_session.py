import gzip
import io
import json
import os
import stat
import tempfile
import urllib.error
from pathlib import Path
from unittest.mock import patch

import pytest

from browser_harness import login_session


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
        "not a cookie",
        {"name": "sid", "value": "abc", "domain": ".example.com", "path": "/", "secure": True},
        {"name": "other", "value": "bad", "domain": ".other.test", "path": "/", "secure": True},
        {"name": "path", "value": "bad", "domain": ".example.com", "path": "/admin", "secure": True},
    ]

    assert login_session.cookie_header(None, "https://www.example.com/page", cookies=cookies) == "sid=abc"


def test_browser_cookies_uses_page_session_when_provided():
    calls = []

    def client(method, session_id=None, **params):
        calls.append((method, params, session_id))
        if method == "Network.getCookies":
            return {"cookies": []}
        raise AssertionError(method)

    assert login_session.browser_cookies(client, "https://www.example.com/", session_id="page-session") == []
    assert calls == [("Network.getCookies", {"urls": ["https://www.example.com/"]}, "page-session")]


def test_browser_cookies_skips_malformed_network_cookie_rows():
    def client(method, session_id=None, **params):
        if method == "Network.getCookies":
            return {"cookies": [
                "not-a-cookie",
                {"name": "sid", "value": "abc"},
            ]}
        raise AssertionError(method)

    cookies = login_session.browser_cookies(client, "https://www.example.com/")

    assert [cookie["name"] for cookie in cookies] == ["sid"]


def test_browser_cookies_falls_back_to_browser_level_storage_cookies():
    calls = []

    def client(method, session_id=None, **params):
        calls.append((method, params, session_id))
        if method == "Network.getCookies":
            raise RuntimeError("{'code': -32601, 'message': \"'Network.getCookies' wasn't found\"}")
        if method == "Storage.getCookies":
            return {"cookies": [
                {"name": "sid", "value": "abc", "domain": ".example.com", "path": "/", "secure": True},
                {"name": "other", "value": "bad", "domain": ".other.test", "path": "/", "secure": True},
            ]}
        raise AssertionError(method)

    cookies = login_session.browser_cookies(client, "https://www.example.com/account")

    assert [cookie["name"] for cookie in cookies] == ["sid"]
    assert calls == [
        ("Network.getCookies", {"urls": ["https://www.example.com/account"]}, None),
        ("Storage.getCookies", {}, None),
    ]


def test_browser_cookies_skips_malformed_browser_level_cookie_rows():
    def client(method, session_id=None, **params):
        if method == "Network.getCookies":
            raise RuntimeError("{'code': -32601, 'message': \"'Network.getCookies' wasn't found\"}")
        if method == "Storage.getCookies":
            return {"cookies": [
                "not-a-cookie",
                {"name": "sid", "value": "abc", "domain": ".example.com", "path": "/", "secure": True},
            ]}
        raise AssertionError(method)

    cookies = login_session.browser_cookies(client, "https://www.example.com/account")

    assert [cookie["name"] for cookie in cookies] == ["sid"]


def test_restore_cookies_falls_back_to_browser_level_storage_set_cookies():
    calls = []

    def client(method, session_id=None, **params):
        calls.append((method, params, session_id))
        if method == "Network.setCookies":
            raise RuntimeError("{'code': -31998, 'message': 'NotImplemented'}")
        if method == "Storage.setCookies":
            return {}
        raise AssertionError(method)

    result = login_session.restore_cookies(
        client,
        [{"name": "sid", "value": "secret", "domain": ".example.com", "path": "/", "secure": True}],
    )

    assert result == {"restored": 1}
    assert calls == [
        ("Network.setCookies", {"cookies": [{"name": "sid", "value": "secret", "domain": ".example.com", "path": "/", "secure": True}]}, None),
        ("Storage.setCookies", {"cookies": [{"name": "sid", "value": "secret", "domain": ".example.com", "path": "/", "secure": True}]}, None),
    ]


def test_restore_cookies_falls_back_to_individual_network_set_cookie():
    calls = []

    def client(method, session_id=None, **params):
        calls.append((method, params, session_id))
        if method in {"Network.setCookies", "Storage.setCookies"}:
            raise RuntimeError("{'code': -31998, 'message': 'NotImplemented'}")
        if method == "Network.setCookie":
            return {"success": True}
        raise AssertionError(method)

    result = login_session.restore_cookies(
        client,
        [{"name": "sid", "value": "secret", "domain": ".example.com", "path": "/", "secure": True}],
    )

    assert result == {"restored": 1}
    assert calls == [
        ("Network.setCookies", {"cookies": [{"name": "sid", "value": "secret", "domain": ".example.com", "path": "/", "secure": True}]}, None),
        ("Storage.setCookies", {"cookies": [{"name": "sid", "value": "secret", "domain": ".example.com", "path": "/", "secure": True}]}, None),
        ("Network.setCookie", {
            "name": "sid",
            "value": "secret",
            "domain": ".example.com",
            "path": "/",
            "secure": True,
            "url": "https://example.com/",
        }, None),
    ]


def test_restore_cookies_ignores_malformed_cookie_entries():
    calls = []

    def client(method, session_id=None, **params):
        calls.append((method, params, session_id))
        return {}

    result = login_session.restore_cookies(
        client,
        ["bad-cookie", ["also", "bad"], {"name": "sid", "value": "secret", "domain": ".example.com"}],
    )

    assert result == {"restored": 1}
    assert calls == [
        ("Network.setCookies", {"cookies": [{"name": "sid", "value": "secret", "domain": ".example.com"}]}, None),
    ]


def test_set_cookie_param_strips_nonportable_bulk_fields():
    cookie = {
        "name": "sid",
        "value": "secret",
        "domain": ".example.com",
        "path": "/",
        "secure": True,
        "httpOnly": True,
        "expires": -1,
        "priority": "Medium",
        "sourceScheme": "Secure",
        "sourcePort": 443,
    }

    assert login_session.set_cookie_param(cookie) == {
        "name": "sid",
        "value": "secret",
        "domain": ".example.com",
        "path": "/",
        "secure": True,
        "httpOnly": True,
        "url": "https://example.com/",
    }


def test_cookie_params_drop_non_numeric_expires_values():
    cookie = {
        "name": "sid",
        "value": "secret",
        "domain": ".example.com",
        "expires": "not-a-number",
    }

    assert login_session.cookie_param(cookie) == {
        "name": "sid",
        "value": "secret",
        "domain": ".example.com",
    }
    assert login_session.set_cookie_param(cookie) == {
        "name": "sid",
        "value": "secret",
        "domain": ".example.com",
        "url": "http://example.com/",
    }


def test_runtime_value_tolerates_malformed_result_envelope():
    def client(method, **params):
        assert method == "Runtime.evaluate"
        return {"result": "not-an-object"}

    assert login_session.runtime_value(client, "navigator.userAgent") is None


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


def test_restore_session_state_and_verify_passes_authenticated_urls():
    class Client:
        def __init__(self):
            self.calls = []
            self.page_statuses = iter([
                # wait_for_origin polls
                {"url": "about:blank", "title": "", "readyState": "complete", "textLength": 0},
                {"url": "https://www.example.com/", "title": "Home", "readyState": "complete", "textLength": 0},
                # navigate_and_wait pre_url + polls
                {"url": "https://www.example.com/", "title": "Home", "readyState": "complete", "textLength": 0},
                {"url": "https://www.example.com/private", "title": "Private", "readyState": "complete", "textLength": 500},
            ])

        def __call__(self, method, session_id=None, **params):
            self.calls.append((method, params, session_id))
            if method == "Runtime.evaluate":
                expression = params["expression"]
                if expression == "location.origin":
                    return {"result": {"value": "https://www.example.com"}}
                if "localStorageRestored" in expression:
                    return {"result": {"value": {"origin": "https://www.example.com", "localStorageRestored": 1, "sessionStorageRestored": 1}}}
                return {"result": {"value": next(self.page_statuses)}}
            return {}

    state = {
        "cookies": [{"name": "sid", "value": "secret", "domain": ".example.com", "path": "/", "secure": True}],
        "origins": [{
            "origin": "https://www.example.com",
            "localStorage": {"token": "local-secret"},
            "sessionStorage": {"state": "session-secret"},
        }],
    }
    with patch("time.sleep"):
        result = login_session.restore_session_state_and_verify(
            Client(),
            state,
            ["https://www.example.com/private"],
            min_text=250,
            timeout=2,
        )

    assert result["ok"] is True
    assert result["restore"]["cookies"] == {"restored": 1}
    assert result["restore"]["storage"][0]["localStorageRestored"] == 1
    assert result["resources_checked"][0]["title"] == "Private"


def test_verify_authenticated_urls_tolerates_malformed_page_status_shapes():
    statuses = [
        "bad-status",
        {"url": "https://www.example.com/private", "title": "Private", "readyState": "complete", "textLength": "not-a-count"},
    ]

    def client(method, session_id=None, **params):
        if method == "Runtime.evaluate":
            expression = params["expression"]
            if expression == "location.href":
                return {"result": {"value": "about:blank"}}
            status = statuses.pop(0) if len(statuses) > 1 else statuses[0]
            return {"result": {"value": status}}
        return {}

    with patch("time.sleep"):
        result = login_session.verify_authenticated_urls(
            client,
            ["https://www.example.com/private"],
            min_text=250,
            timeout=0.01,
            poll=0,
        )

    assert result == {
        "ok": False,
        "resources_checked": [{
            "requested_url": "https://www.example.com/private",
            "final_url": "https://www.example.com/private",
            "title": "Private",
            "ok": False,
            "reason": "timeout",
            "text_length": "not-a-count",
        }],
    }


def test_restore_session_state_and_verify_handles_malformed_state_shapes():
    calls = []
    statuses = iter([
        {"url": "about:blank", "title": "", "readyState": "complete", "textLength": 0},
        {"url": "https://www.example.com/private", "title": "Private", "readyState": "complete", "textLength": 500},
    ])

    def client(method, session_id=None, **params):
        calls.append((method, params, session_id))
        if method == "Runtime.evaluate":
            expression = params["expression"]
            if expression == "location.origin":
                return {"result": {"value": "about:blank"}}
            return {"result": {"value": next(statuses)}}
        return {}

    with patch("time.sleep"):
        result = login_session.restore_session_state_and_verify(
            client,
            {"cookies": ["bad-cookie"], "origins": ["bad-origin"], "urls": "not-a-list"},
            ["https://www.example.com/private"],
            min_text=250,
            timeout=1,
        )

    assert result["ok"] is True
    assert result["restore"] == {"cookies": {"restored": 0}, "storage": []}
    navigated_urls = [call[1]["url"] for call in calls if call[0] == "Page.navigate"]
    assert navigated_urls == ["https://www.example.com/private"]


def test_verify_authenticated_urls_fails_login_redirect():
    states = iter([
        # navigate_and_wait pre_url
        {"url": "about:blank", "title": "", "readyState": "complete", "textLength": 0},
        # navigate_and_wait first poll — redirected to login
        {"url": "https://www.example.com/login?redirect=private", "title": "Log in", "readyState": "complete", "textLength": 500},
    ])

    def client(method, **params):
        if method == "Runtime.evaluate":
            return {"result": {"value": next(states)}}
        return {}

    with patch("time.sleep"):
        result = login_session.verify_authenticated_urls(client, ["https://www.example.com/private"], timeout=1)

    assert result["ok"] is False
    assert result["resources_checked"][0]["reason"] == "login_redirect"


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

    with patch("urllib.request.OpenerDirector.open", side_effect=err):
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


def test_cross_domain_redirect_strips_cookies():
    import urllib.request

    handler = login_session._CrossDomainRedirectHandler()
    req = urllib.request.Request("https://example.com/path", headers={"Cookie": "sid=abc"})
    # Simulate a redirect to a different origin
    new = handler.redirect_request(
        req, None, 302, "Found", {"Location": "https://other.com/path"}, "https://other.com/path",
    )
    assert new is not None
    # The new request should NOT carry the Cookie header
    assert "Cookie" not in new.headers
    assert "Cookie" not in new.unredirected_hdrs


def test_same_domain_redirect_keeps_cookies():
    import urllib.request

    handler = login_session._CrossDomainRedirectHandler()
    req = urllib.request.Request("https://example.com/path", headers={"Cookie": "sid=abc"})
    # Same-origin redirect — cookie should be preserved
    new = handler.redirect_request(
        req, None, 302, "Found", {"Location": "https://example.com/other"}, "https://example.com/other",
    )
    assert new is not None
    assert new.headers.get("Cookie") == "sid=abc"


def test_registrable_domain_extracts_etld1():
    assert login_session._registrable_domain("www.airbnb.com") == "airbnb.com"
    assert login_session._registrable_domain("https://www.airbnb.com/hosting/inbox") == "airbnb.com"
    assert login_session._registrable_domain("example.com:8443") == "example.com"
    assert login_session._registrable_domain("sub.example.co.uk") == "example.co.uk"
    assert login_session._registrable_domain("example.com") == "example.com"
    assert login_session._registrable_domain("") == ""
    assert login_session._registrable_domain("localhost") == "localhost"


def test_auth_profile_domain_rejects_unsafe_path_segments(tmp_path):
    with patch.object(login_session, "_PROFILES_DIR", tmp_path):
        with pytest.raises(ValueError, match="unsafe auth profile domain"):
            login_session.auth_profile_path("../evil.com")

        path = login_session.auth_profile_path("https://www.example.com/path")
        assert path == tmp_path / "example.com"


def test_save_and_load_auth_profile_roundtrip(tmp_path):
    profiles_dir = tmp_path / "profiles"
    fake_state = {
        "state_format": "browser-harness.login_session.v1",
        "cookies": [{"name": "sid", "value": "abc123", "domain": ".example.com", "path": "/"}],
        "origins": [{"origin": "https://example.com", "localStorage": {"key": "val"}, "sessionStorage": {}}],
    }

    calls = []

    def fake_client(method, **kwargs):
        calls.append((method, kwargs))
        if "getCookies" in method or "Cookies" in method:
            return {"cookies": fake_state["cookies"]}
        if "Storage" in method or "storage" in method:
            return {"localStorage": [{"name": "key", "value": "val"}], "sessionStorage": []}
        if method == "Runtime.evaluate":
            expression = kwargs.get("expression", "")
            if "location.origin" in expression and "localStorageRestored" not in expression:
                return {"result": {"value": "https://example.com"}}
            if "localStorageRestored" in expression:
                return {"result": {"value": {
                    "origin": "https://example.com",
                    "localStorageRestored": 1,
                    "sessionStorageRestored": 1,
                }}}
            return {"result": {"value": {
                "url": "https://example.com/",
                "title": "Example",
                "readyState": "complete",
                "textLength": 100,
            }}}
        return {}

    with patch.object(login_session, "_PROFILES_DIR", profiles_dir), \
         patch("browser_harness.login_session.session_manifest", return_value={"site": "example.com"}), \
         patch("browser_harness.login_session.session_state", return_value=fake_state):
        path = login_session.save_auth_profile(fake_client, "www.example.com")
        assert (profiles_dir / "example.com" / "manifest.json").exists()
        assert (profiles_dir / "example.com" / "state.json").exists()

        state_file = profiles_dir / "example.com" / "state.json"
        perms = stat.S_IMODE(os.stat(state_file).st_mode)
        assert perms & 0o077 == 0  # no group/other read
        assert stat.S_IMODE(os.stat(profiles_dir).st_mode) & 0o077 == 0
        assert stat.S_IMODE(os.stat(profiles_dir / "example.com").st_mode) & 0o077 == 0

        result = login_session.load_auth_profile(fake_client, "example.com")
        assert result is True
        assert ("Page.navigate", {"url": "https://example.com/"}) in calls


def test_load_auth_profile_returns_false_when_missing(tmp_path):
    with patch.object(login_session, "_PROFILES_DIR", tmp_path / "nonexistent"):
        assert login_session.load_auth_profile(lambda **kw: {}, "missing.com") is False


def test_load_auth_profile_returns_false_when_expired(tmp_path):
    domain_dir = tmp_path / "expired.com"
    domain_dir.mkdir()
    old_state = {"cookies": [], "origins": [], "observed_at": "2020-01-01T00:00:00Z"}
    state_file = domain_dir / "state.json"
    state_file.write_text(json.dumps(old_state))
    # Set mtime to 2 days ago
    import time as _time
    old_mtime = _time.time() - 48 * 3600
    os.utime(state_file, (old_mtime, old_mtime))

    with patch.object(login_session, "_PROFILES_DIR", tmp_path):
        assert login_session.load_auth_profile(lambda **kw: {}, "expired.com", ttl=86400) is False


def test_load_auth_profile_returns_false_when_state_is_corrupt(tmp_path):
    domain_dir = tmp_path / "example.com"
    domain_dir.mkdir()
    (domain_dir / "state.json").write_text("{not-json", encoding="utf-8")

    with patch.object(login_session, "_PROFILES_DIR", tmp_path), \
         patch("browser_harness.login_session.restore_session_state") as mock_restore:
        assert login_session.load_auth_profile(lambda **kw: {}, "example.com") is False

    mock_restore.assert_not_called()


def test_load_auth_profile_returns_false_for_malformed_state_shapes(tmp_path):
    domain_dir = tmp_path / "example.com"
    domain_dir.mkdir()
    (domain_dir / "state.json").write_text(
        json.dumps({"cookies": ["bad-cookie"], "origins": ["bad-origin"]}),
        encoding="utf-8",
    )

    def client(method, **kwargs):
        if method in {"Page.enable", "Network.enable"}:
            return {}
        if method == "Runtime.evaluate":
            return {"result": {"value": "about:blank"}}
        raise AssertionError(method)

    with patch.object(login_session, "_PROFILES_DIR", tmp_path):
        result = login_session.load_auth_profile_result(client, "example.com")

    assert result["ok"] is False
    assert result["reason"] == "restored"
    assert result["restore"] == {"cookies": {"restored": 0}, "storage": []}


def test_auth_restore_ok_ignores_malformed_restore_and_state_entries():
    assert login_session.auth_restore_ok(
        {"cookies": {"restored": 1}, "storage": ["bad-storage"]},
        {"cookies": ["bad-cookie", {"name": "sid", "value": "secret"}], "origins": ["bad-origin"]},
    ) is True


def test_auth_restore_ok_ignores_malformed_storage_maps_and_counts():
    assert login_session.auth_restore_ok(
        {
            "cookies": {"restored": 1},
            "storage": [
                {
                    "ok": True,
                    "localStorageRestored": "not-a-count",
                    "sessionStorageRestored": None,
                }
            ],
        },
        {
            "cookies": [{"name": "sid", "value": "secret"}],
            "origins": [
                {
                    "origin": "https://example.com",
                    "localStorage": "not-a-map",
                    "sessionStorage": ["not", "a", "map"],
                }
            ],
        },
    ) is True


def test_load_auth_profile_restores_storage_on_saved_origin_from_blank_page(tmp_path):
    domain_dir = tmp_path / "example.com"
    domain_dir.mkdir()
    state = {
        "cookies": [],
        "origins": [{"origin": "https://example.com", "localStorage": {"token": "secret"}, "sessionStorage": {}}],
    }
    (domain_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")
    calls = []

    def client(method, **kwargs):
        calls.append((method, kwargs))
        if method in {"Page.enable", "Network.enable"}:
            return {}
        if method == "Page.navigate":
            return {}
        if method == "Runtime.evaluate":
            expression = kwargs.get("expression", "")
            if "localStorageRestored" in expression:
                return {"result": {"value": {
                    "origin": "https://example.com",
                    "localStorageRestored": 1,
                    "sessionStorageRestored": 0,
                }}}
            if "location.origin" in expression:
                return {"result": {"value": "https://example.com"}}
            return {"result": {"value": {
                "url": "https://example.com/",
                "title": "Example",
                "readyState": "complete",
                "textLength": 0,
            }}}
        if method == "Network.setCookies":
            return {}
        raise AssertionError(method)

    with patch.object(login_session, "_PROFILES_DIR", tmp_path):
        result = login_session.load_auth_profile_result(client, "example.com")

    assert result["ok"] is True
    assert ("Page.navigate", {"url": "https://example.com/"}) in calls
    assert result["restore"]["storage"][0]["localStorageRestored"] == 1
