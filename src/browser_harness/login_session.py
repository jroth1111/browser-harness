"""Generic user-login and browser-session primitives for CDP clients.

This module does not type credentials, solve MFA, or persist secrets. It treats
the user's browser profile as the primary authentication store and exposes small
helpers that work with any CDP client shaped as:

- callable(method, **params)
- callable(method, session_id=..., **params)
- object.send_raw(method, params, session_id=...)
- object.send(method, params)
- object.send(method, params, session_id=...)
- object.send(method, **params)
"""
import gzip
import inspect
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse


_SENSITIVE_STORAGE_LABELS = (
    "accountId",
    "bevId",
    "confirmationCode",
    "guestId",
    "hostId",
    "listingId",
    "profileId",
    "reservationId",
    "userId",
)
_STORAGE_BOUNDARY_LABELS = _SENSITIVE_STORAGE_LABELS + ("userDataFields",)
_SENSITIVE_STORAGE_SEGMENT = re.compile(
    rf"(?i)([-_/?:&=]?(?:{'|'.join(_SENSITIVE_STORAGE_LABELS)})[-_=])"
    rf"(.+?)(?=(?:[-_/?:&=](?:{'|'.join(_STORAGE_BOUNDARY_LABELS)})[-_=])|[/&?]|$)"
)
_UUIDISH = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
_LONG_NUMBER = re.compile(r"\d{5,}")
_COOKIE_PARAM_FIELDS = {
    "name",
    "value",
    "url",
    "domain",
    "path",
    "secure",
    "httpOnly",
    "sameSite",
    "expires",
    "priority",
    "sameParty",
    "sourceScheme",
    "sourcePort",
    "partitionKey",
}
_COOKIE_SET_COOKIE_FIELDS = {
    "name",
    "value",
    "url",
    "domain",
    "path",
    "secure",
    "httpOnly",
    "sameSite",
    "expires",
}


def _cdp_method_missing_error(error):
    rendered = repr(error).lower()
    return (
        "-32601" in rendered
        or "-31998" in rendered
        or "methodnotfound" in rendered
        or "method not found" in rendered
        or "notimplemented" in rendered
        or "not implemented" in rendered
        or "wasn't found" in rendered
    )


def _signature(fn):
    try:
        return inspect.signature(fn)
    except (TypeError, ValueError):
        return None


def _accepts_var_keyword(sig):
    return sig is not None and any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())


def _accepts_positional_count(sig, count):
    if sig is None:
        return True
    positional = [
        p for p in sig.parameters.values()
        if p.kind in {inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD}
    ]
    return len(positional) >= count or any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in sig.parameters.values())


def _accepts_keyword(sig, name):
    return sig is None or name in sig.parameters or _accepts_var_keyword(sig)


def send_cdp(client, method, params=None, session_id=None):
    """Send one CDP method through a generic client adapter."""
    params = params or {}
    if hasattr(client, "send_raw"):
        return client.send_raw(method, params, session_id=session_id)
    if hasattr(client, "send"):
        send = client.send
        sig = _signature(send)
        if session_id is not None and not _accepts_keyword(sig, "session_id"):
            raise TypeError("CDP client send() does not accept session_id")
        if _accepts_positional_count(sig, 2):
            if session_id is not None:
                return send(method, params, session_id=session_id)
            return send(method, params)
        if session_id is not None:
            return send(method, session_id=session_id, **params)
        return send(method, **params)
    if callable(client):
        if session_id is not None:
            return client(method, session_id=session_id, **params)
        return client(method, **params)
    raise TypeError("CDP client must be callable or expose send/send_raw")


def origin_url(url):
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return url
    return f"{parsed.scheme}://{parsed.netloc}/"


def cookie_matches_url(cookie, url):
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    domain = (cookie.get("domain") or host).lower()
    domain_base = domain.lstrip(".")
    if domain.startswith("."):
        if host != domain_base and not host.endswith(f".{domain_base}"):
            return False
    elif host != domain_base:
        return False
    if cookie.get("secure") and parsed.scheme != "https":
        return False
    path = cookie.get("path") or "/"
    request_path = parsed.path or "/"
    if path == "/":
        return True
    return request_path == path or request_path.startswith(path if path.endswith("/") else path + "/")


def browser_cookies(client, urls, session_id=None):
    """Return cookies visible to the browser for `urls`.

    The returned values are sensitive. Callers should avoid printing or storing
    raw values.
    """
    urls = [urls] if isinstance(urls, str) else list(urls)
    try:
        return send_cdp(client, "Network.getCookies", {"urls": urls}, session_id=session_id).get("cookies", [])
    except Exception as error:
        if not _cdp_method_missing_error(error):
            raise

    try:
        cookies = send_cdp(client, "Storage.getCookies", {}, session_id=session_id).get("cookies", [])
    except Exception as error:
        if not _cdp_method_missing_error(error):
            raise
        cookies = send_cdp(client, "Network.getAllCookies", {}, session_id=session_id).get("cookies", [])

    return [
        cookie
        for cookie in cookies
        if any(cookie_matches_url(cookie, url) for url in urls)
    ]


def cookie_header(client, url, cookie_urls=None, cookies=None, session_id=None):
    """Build a domain/path/secure-filtered Cookie header for `url`."""
    cookie_urls = [url] if cookie_urls is None else ([cookie_urls] if isinstance(cookie_urls, str) else list(cookie_urls))
    source_cookies = browser_cookies(client, cookie_urls, session_id=session_id) if cookies is None else list(cookies)
    pairs = []
    seen = set()
    for cookie in source_cookies:
        name = cookie.get("name")
        value = cookie.get("value")
        if not name or value is None or not cookie_matches_url(cookie, url):
            continue
        if name in seen:
            continue
        seen.add(name)
        pairs.append(f"{name}={value}")
    return "; ".join(pairs)


def runtime_value(client, expression, session_id=None):
    result = send_cdp(
        client,
        "Runtime.evaluate",
        {"expression": expression, "returnByValue": True, "awaitPromise": True},
        session_id=session_id,
    )
    return result.get("result", {}).get("value")


def browser_user_agent(client, session_id=None):
    return runtime_value(client, "navigator.userAgent", session_id=session_id) or ""


def storage_key_snapshot(client, session_id=None):
    """Return local/session storage keys for the current page, never values."""
    return runtime_value(client, """(() => {
  const keys = (store) => {
    try {
      const out = [];
      for (let i = 0; store && i < store.length; i++) out.push(store.key(i));
      return out.filter(Boolean);
    } catch (e) { return []; }
  };
  return {
    url: location.href,
    origin: location.origin,
    localStorageKeys: keys(window.localStorage),
    sessionStorageKeys: keys(window.sessionStorage)
  };
})()""", session_id=session_id) or {
        "url": "",
        "origin": "",
        "localStorageKeys": [],
        "sessionStorageKeys": [],
    }


def storage_value_snapshot(client, session_id=None):
    """Return local/session storage keys and values for private auth export."""
    return runtime_value(client, """(() => {
  const dump = (store) => {
    const out = {};
    try {
      for (let i = 0; store && i < store.length; i++) {
        const key = store.key(i);
        if (key) out[key] = store.getItem(key);
      }
    } catch (e) {}
    return out;
  };
  return {
    url: location.href,
    origin: location.origin,
    localStorage: dump(window.localStorage),
    sessionStorage: dump(window.sessionStorage)
  };
})()""", session_id=session_id) or {
        "url": "",
        "origin": "",
        "localStorage": {},
        "sessionStorage": {},
    }


def redact_storage_key(key):
    """Redact private identifiers from storage key names before persistence."""
    redacted = _SENSITIVE_STORAGE_SEGMENT.sub(lambda match: f"{match.group(1)}<redacted>", str(key))
    redacted = _UUIDISH.sub("<uuid>", redacted)
    return _LONG_NUMBER.sub("<num>", redacted)


def redacted_storage_keys(keys):
    return sorted({redact_storage_key(key) for key in (keys or []) if key})


def session_manifest(client, urls, site=None, profile_label=None, account_label=None, backend=None, session_id=None):
    """Create a redacted login/session manifest.

    Raw cookie and storage values are intentionally omitted.
    """
    urls = [urls] if isinstance(urls, str) else list(urls)
    cookies = browser_cookies(client, urls, session_id=session_id)
    storage = storage_key_snapshot(client, session_id=session_id)
    cookie_names = sorted({c.get("name", "") for c in cookies if c.get("name")})
    cookie_domains = sorted({c.get("domain", "") for c in cookies if c.get("domain")})
    return {
        "site": site,
        "profile_label": profile_label,
        "account_label": account_label,
        "browser_backend": backend,
        "urls": urls,
        "logged_in_observed": bool(cookie_names),
        "cookie_names": cookie_names,
        "cookie_domains": cookie_domains,
        "local_storage_keys": redacted_storage_keys(storage.get("localStorageKeys")),
        "session_storage_keys": redacted_storage_keys(storage.get("sessionStorageKeys")),
        "current_url": storage.get("url", ""),
        "origin": storage.get("origin", ""),
        "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def session_state(client, urls, site=None, profile_label=None, account_label=None, backend=None, session_id=None):
    """Create a private restorable auth state.

    This includes cookie and storage values. Store only in an ignored/private
    local path with restrictive file permissions.
    """
    urls = [urls] if isinstance(urls, str) else list(urls)
    storage = storage_value_snapshot(client, session_id=session_id)
    return {
        "state_format": "browser-harness.login_session.v1",
        "site": site,
        "profile_label": profile_label,
        "account_label": account_label,
        "browser_backend": backend,
        "urls": urls,
        "cookies": browser_cookies(client, urls, session_id=session_id),
        "origins": [{
            "origin": storage.get("origin", ""),
            "url": storage.get("url", ""),
            "localStorage": storage.get("localStorage") or {},
            "sessionStorage": storage.get("sessionStorage") or {},
        }],
        "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def cookie_param(cookie):
    out = {key: cookie[key] for key in _COOKIE_PARAM_FIELDS if key in cookie and cookie[key] is not None}
    if out.get("expires", 0) < 0:
        out.pop("expires", None)
    return out


def set_cookie_param(cookie):
    out = {key: cookie[key] for key in _COOKIE_SET_COOKIE_FIELDS if key in cookie and cookie[key] is not None}
    if out.get("expires", 0) < 0:
        out.pop("expires", None)
    domain = out.get("domain")
    if "url" not in out and domain:
        host = str(domain).lstrip(".")
        path = out.get("path") or "/"
        scheme = "https" if out.get("secure", False) else "http"
        out["url"] = f"{scheme}://{host}{path}"
    return out


def _dict_items(value):
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _state_dict(state):
    return state if isinstance(state, dict) else {}


def _restore_cookies_individually(client, cookies, session_id=None):
    restored = 0
    failures = []
    for cookie in _dict_items(cookies):
        params = set_cookie_param(cookie)
        if not params.get("name") or params.get("value") is None:
            continue
        try:
            result = send_cdp(client, "Network.setCookie", params, session_id=session_id)
            if result.get("success", True):
                restored += 1
                continue
            failures.append({"name": params.get("name"), "domain": params.get("domain"), "reason": "success_false"})
        except Exception as error:
            failures.append({"name": params.get("name"), "domain": params.get("domain"), "reason": repr(error)})
    out = {"restored": restored}
    if failures:
        out["failed"] = len(failures)
        out["failures"] = failures
    return out


def restore_cookies(client, cookies, session_id=None):
    cookie_items = _dict_items(cookies)
    params = [cookie_param(cookie) for cookie in cookie_items if cookie.get("name") and cookie.get("value") is not None]
    if not params:
        return {"restored": 0}
    try:
        send_cdp(client, "Network.setCookies", {"cookies": params}, session_id=session_id)
        return {"restored": len(params)}
    except Exception as error:
        if not _cdp_method_missing_error(error):
            raise
    try:
        send_cdp(client, "Storage.setCookies", {"cookies": params}, session_id=session_id)
        return {"restored": len(params)}
    except Exception as error:
        if not _cdp_method_missing_error(error):
            raise
    return _restore_cookies_individually(client, cookie_items, session_id=session_id)


def restore_origin_storage(client, origin_state, include_session_storage=False, session_id=None):
    origin_state = origin_state if isinstance(origin_state, dict) else {}
    payload = {
        "localStorage": origin_state.get("localStorage") or {},
        "sessionStorage": origin_state.get("sessionStorage") or {},
        "includeSessionStorage": bool(include_session_storage),
    }
    return runtime_value(client, f"""(() => {{
  const state = {json.dumps(payload)};
  const restore = (store, values) => {{
    let count = 0;
    for (const [key, value] of Object.entries(values || {{}})) {{
      store.setItem(key, value == null ? "" : String(value));
      count++;
    }}
    return count;
  }};
  return {{
    origin: location.origin,
    localStorageRestored: restore(window.localStorage, state.localStorage),
    sessionStorageRestored: state.includeSessionStorage ? restore(window.sessionStorage, state.sessionStorage) : 0
  }};
}})()""", session_id=session_id)


def restore_session_state(client, state, include_session_storage=False, session_id=None):
    state = _state_dict(state)
    cookie_result = restore_cookies(client, state.get("cookies") or [], session_id=session_id)
    storage_results = []
    current_origin = runtime_value(client, "location.origin", session_id=session_id)
    for origin_state in _dict_items(state.get("origins") or []):
        if origin_state.get("origin") == current_origin:
            storage_results.append(restore_origin_storage(
                client,
                origin_state,
                include_session_storage=include_session_storage,
                session_id=session_id,
            ))
    return {"cookies": cookie_result, "storage": storage_results}


def wait_for_page_status(client, min_text=250, timeout=30.0, poll=0.5, session_id=None):
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        last = page_status(client, session_id=session_id)
        if int(last.get("textLength") or 0) >= min_text:
            return {**last, "ok": True, "reason": "content"}
        time.sleep(poll)
    return {**last, "ok": False, "reason": "timeout"}


def navigate_and_wait(client, url, min_text=250, timeout=30.0, poll=0.5, session_id=None):
    pre_url = runtime_value(client, "location.href", session_id=session_id)
    send_cdp(client, "Page.enable", session_id=session_id)
    send_cdp(client, "Page.navigate", {"url": url}, session_id=session_id)
    deadline = time.time() + timeout
    while time.time() < deadline:
        last = page_status(client, session_id=session_id)
        url_changed = last.get("url") != pre_url
        text_ok = int(last.get("textLength") or 0) >= min_text
        if url_changed and text_ok:
            return {**last, "ok": True, "reason": "content"}
        # Same URL but content loaded — page refresh or canonical redirect.
        if not url_changed and text_ok and last.get("readyState") == "complete":
            return {**last, "ok": True, "reason": "content"}
        time.sleep(poll)
    last = page_status(client, session_id=session_id)
    return {**last, "ok": False, "reason": "timeout"}


def _same_origin(url, origin):
    got = urlparse(url or "")
    want = urlparse(origin or "")
    if not (got.scheme and got.netloc and got.scheme == want.scheme):
        return False
    if (got.hostname or "").lower() != (want.hostname or "").lower():
        return False
    got_port = got.port or (443 if got.scheme == "https" else 80)
    want_port = want.port or (443 if want.scheme == "https" else 80)
    return got_port == want_port


def wait_for_origin(client, origin, timeout=30.0, poll=0.5, session_id=None):
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        last = page_status(client, session_id=session_id)
        if _same_origin(last.get("url"), origin):
            return {**last, "ok": True, "reason": "origin"}
        time.sleep(poll)
    return {**last, "ok": False, "reason": "origin_timeout"}


def login_redirect_observed(status, login_path_markers=("/login",), login_title_markers=("login", "sign in", "sign up")):
    parsed = urlparse(status.get("url") or "")
    path = parsed.path.lower()
    title = (status.get("title") or "").lower()
    return any(marker in path for marker in login_path_markers) or any(marker in title for marker in login_title_markers)


def verify_authenticated_urls(
    client,
    urls,
    min_text=250,
    timeout=30.0,
    poll=0.5,
    session_id=None,
    login_path_markers=("/login",),
    login_title_markers=("login", "sign in", "sign up"),
):
    results = []
    for url in urls:
        status = navigate_and_wait(client, url, min_text=min_text, timeout=timeout, poll=poll, session_id=session_id)
        login_redirect = login_redirect_observed(
            status,
            login_path_markers=login_path_markers,
            login_title_markers=login_title_markers,
        )
        results.append({
            "requested_url": url,
            "final_url": status.get("url", ""),
            "title": status.get("title", ""),
            "ok": bool(status.get("ok") and not login_redirect),
            "reason": "login_redirect" if login_redirect else status.get("reason"),
            "text_length": status.get("textLength"),
        })
    return {"ok": all(item["ok"] for item in results), "resources_checked": results}


def restore_session_state_and_verify(
    client,
    state,
    urls,
    include_session_storage=True,
    min_text=250,
    timeout=30.0,
    poll=0.5,
    session_id=None,
):
    """Restore private auth state into the current browser context and verify URLs.

    The caller is responsible for providing a fresh browser profile/process when
    they need proof that the state is restorable without an existing login.
    """
    state = _state_dict(state)
    send_cdp(client, "Page.enable", session_id=session_id)
    send_cdp(client, "Network.enable", session_id=session_id)
    origin_items = _dict_items(state.get("origins") or [])
    origin_state = origin_items[0] if origin_items else {}
    state_urls = state.get("urls") if isinstance(state.get("urls"), list) else []
    origin = origin_state.get("origin") or origin_url((state_urls or ["about:blank"])[0]).rstrip("/")
    if origin and origin != "about:blank":
        send_cdp(client, "Page.navigate", {"url": origin + "/"}, session_id=session_id)
        wait_for_origin(client, origin, timeout=timeout, poll=poll, session_id=session_id)
    restore = restore_session_state(
        client,
        state,
        include_session_storage=include_session_storage,
        session_id=session_id,
    )
    verification = verify_authenticated_urls(
        client,
        urls,
        min_text=min_text,
        timeout=timeout,
        poll=poll,
        session_id=session_id,
    )
    return {"ok": verification["ok"], "restore": restore, **verification}


def browser_session_headers(client, url, headers=None, cookie_urls=None, cookies=None, session_id=None):
    """Headers for same-domain HTTP using browser UA and matching cookies."""
    out = {
        "User-Agent": browser_user_agent(client, session_id=session_id),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-AU,en;q=0.9",
        "Accept-Encoding": "gzip",
    }
    cookie = cookie_header(client, url, cookie_urls=cookie_urls, cookies=cookies, session_id=session_id)
    if cookie:
        out["Cookie"] = cookie
    if headers:
        out.update(headers)
    return out


def _read_http_text(response):
    data = response.read()
    if response.headers.get("Content-Encoding") == "gzip":
        try:
            data = gzip.decompress(data)
        except (OSError, EOFError):
            pass
    return data.decode("utf-8", "replace")


class _CrossDomainRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Strip cookies when a redirect crosses origin boundaries."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None:
            orig_url = req.full_url if hasattr(req, "full_url") else ""
            if orig_url and newurl and not _same_origin(orig_url, newurl):
                new.headers.pop("Cookie", None)
                new.unredirected_hdrs.pop("Cookie", None)
        return new


def http_get_with_login_session(client, url, headers=None, cookie_urls=None, timeout=20.0, block_detector=None):
    """HTTP GET with browser user agent and matching browser cookies."""
    req_headers = browser_session_headers(client, url, headers=headers, cookie_urls=cookie_urls)
    req = urllib.request.Request(url, headers=req_headers)
    opener = urllib.request.build_opener(_CrossDomainRedirectHandler)
    try:
        with opener.open(req, timeout=timeout) as response:
            text = _read_http_text(response)
            status = getattr(response, "status", None) or (response.getcode() if hasattr(response, "getcode") else 200)
            final_url = response.geturl() if hasattr(response, "geturl") else url
            response_headers = dict(response.headers)
    except urllib.error.HTTPError as error:
        text = _read_http_text(error)
        status = error.code
        final_url = error.geturl()
        response_headers = dict(error.headers)
    except (urllib.error.URLError, OSError, TimeoutError) as error:
        text = ""
        status = None
        final_url = url
        response_headers = {}
        block = {"blocked": False, "kind": None, "evidence": []}
        return {
            "ok": False, "http_ok": False, "status": status, "url": final_url,
            "text": text, "block": block, "headers": response_headers,
            "error": str(error),
        }

    block = block_detector(html=text, text=text, url=final_url) if block_detector else {"blocked": False, "kind": None, "evidence": []}
    http_ok = 200 <= int(status or 0) < 400
    return {
        "ok": http_ok and not block.get("blocked"),
        "http_ok": http_ok,
        "status": status,
        "url": final_url,
        "text": text,
        "block": block,
        "headers": response_headers,
    }


def page_status(client, session_id=None):
    """Return current page status using only generic CDP Runtime evaluation."""
    return runtime_value(client, """(() => {
  const body = document.body;
  return {
    url: location.href,
    title: document.title,
    readyState: document.readyState,
    textLength: body && body.innerText ? body.innerText.length : 0
  };
})()""", session_id=session_id) or {}


def prompt_user_login(
    client,
    login_url,
    success_url_contains=None,
    min_text=200,
    timeout=180.0,
    poll=2.0,
    session_id=None,
):
    """Navigate to `login_url` and wait for the user to complete login.

    This helper never enters credentials. It simply opens the login page and
    polls for a useful page or URL change. For MFA/account selection, the user
    completes the flow in the visible browser.
    """
    send_cdp(client, "Page.enable", session_id=session_id)
    send_cdp(client, "Page.navigate", {"url": login_url}, session_id=session_id)
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        last = page_status(client, session_id=session_id)
        url_ok = not success_url_contains or success_url_contains in (last.get("url") or "")
        text_ok = int(last.get("textLength") or 0) >= min_text
        if url_ok and text_ok:
            return {**last, "ok": True, "reason": "login_observed"}
        time.sleep(poll)
    return {**last, "ok": False, "reason": "timeout"}


# --- auth profile persistence ---

_PROFILES_DIR = Path.home() / ".bh-profiles"
_PROFILE_TTL = 24 * 60 * 60  # 24 hours


def _registrable_domain(hostname):
    """Extract eTLD+1 from hostname. Simple heuristic without tldextract."""
    hostname = _normalize_hostname(hostname)
    if not hostname:
        return hostname
    stripped = hostname.removeprefix("www.")
    parts = stripped.split(".")
    if len(parts) <= 2:
        return stripped
    multi_tlds = {"co.uk", "co.jp", "com.au", "co.nz", "com.br", "com.cn",
                  "com.hk", "com.sg", "co.kr", "co.in", "org.uk", "net.au"}
    if ".".join(parts[-2:]) in multi_tlds and len(parts) >= 3:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def _normalize_hostname(value):
    raw = str(value or "").strip().lower()
    if not raw:
        return raw
    parsed = urlparse(raw if "://" in raw else f"//{raw}")
    host = parsed.hostname or raw
    if host in {".", ".."}:
        raise ValueError(f"unsafe auth profile domain: {value!r}")
    host = host.strip(".")
    if not host:
        return host
    if "/" in host or "\\" in host:
        raise ValueError(f"unsafe auth profile domain: {value!r}")
    if not re.fullmatch(r"[a-z0-9.-]+", host):
        raise ValueError(f"unsafe auth profile domain: {value!r}")
    return host


def auth_profile_path(domain):
    return _PROFILES_DIR / _registrable_domain(domain)


def save_auth_profile(client, domain, urls=None, session_id=None):
    """Save cookies and storage for *domain* to ~/.bh-profiles.

    Returns the profile directory path. Creates manifest.json (redacted) and
    state.json (full values, 0600 permissions).
    """
    domain = _registrable_domain(domain)
    profile_dir = _PROFILES_DIR / domain
    profile_dir.mkdir(parents=True, exist_ok=True)
    try:
        _PROFILES_DIR.chmod(0o700)
        profile_dir.chmod(0o700)
    except OSError:
        pass
    urls = urls or [f"https://{domain}"]

    manifest = session_manifest(client, urls, site=domain, session_id=session_id)
    manifest_path = profile_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    manifest_path.chmod(0o600)

    state = session_state(client, urls, site=domain, session_id=session_id)
    state_path = profile_dir / "state.json"
    state_path.write_text(json.dumps(state, indent=2))
    state_path.chmod(0o600)

    return str(profile_dir)


def _restore_profile_state_on_saved_origins(client, state, include_session_storage=False, session_id=None):
    state = _state_dict(state)
    send_cdp(client, "Page.enable", session_id=session_id)
    send_cdp(client, "Network.enable", session_id=session_id)
    cookie_result = restore_cookies(client, state.get("cookies") or [], session_id=session_id)
    storage_results = []
    for origin_state in _dict_items(state.get("origins") or []):
        origin = origin_state.get("origin")
        if not origin or origin == "about:blank":
            continue
        send_cdp(client, "Page.navigate", {"url": origin.rstrip("/") + "/"}, session_id=session_id)
        origin_status = wait_for_origin(client, origin, timeout=10.0, poll=0.25, session_id=session_id)
        if not origin_status.get("ok"):
            storage_results.append({"origin": origin, "ok": False, "reason": origin_status.get("reason")})
            continue
        restored = restore_origin_storage(
            client,
            origin_state,
            include_session_storage=include_session_storage,
            session_id=session_id,
        )
        storage_results.append({**restored, "ok": True})
    return {"cookies": cookie_result, "storage": storage_results}


def auth_restore_ok(restore, state=None):
    state = _state_dict(state)
    restore = _state_dict(restore)
    cookies = restore.get("cookies") or {}
    cookie_count = int(cookies.get("restored") or 0)
    expected_cookies = len([c for c in _dict_items(state.get("cookies") or []) if c.get("name") and c.get("value") is not None])
    expected_storage = 0
    for origin_state in _dict_items(state.get("origins") or []):
        expected_storage += len(origin_state.get("localStorage") or {})
        expected_storage += len(origin_state.get("sessionStorage") or {})
    storage_count = 0
    storage_failures = 0
    for item in _dict_items(restore.get("storage") or []):
        if item.get("ok") is False:
            storage_failures += 1
        storage_count += int(item.get("localStorageRestored") or 0)
        storage_count += int(item.get("sessionStorageRestored") or 0)
    cookies_ok = cookie_count >= expected_cookies
    storage_ok = storage_count >= expected_storage
    return cookies_ok and storage_ok and storage_failures == 0 and (expected_cookies > 0 or expected_storage > 0)


def load_auth_profile_result(client, domain, ttl=_PROFILE_TTL, session_id=None):
    """Load and restore auth profile for *domain* if fresh enough.

    Returns a structured restore result with ok=False for missing, expired,
    unreadable, or partially unrestored profiles.
    """
    domain = _registrable_domain(domain)
    state_path = _PROFILES_DIR / domain / "state.json"
    if not state_path.exists():
        return {"ok": False, "reason": "missing_profile"}

    try:
        age = time.time() - os.path.getmtime(state_path)
        if age > ttl:
            return {"ok": False, "reason": "expired_profile", "age_seconds": age}
    except OSError:
        return {"ok": False, "reason": "stat_failed"}

    try:
        state = json.loads(state_path.read_text())
    except (OSError, json.JSONDecodeError):
        return {"ok": False, "reason": "read_failed"}
    restore = _restore_profile_state_on_saved_origins(client, state, include_session_storage=True, session_id=session_id)
    return {"ok": auth_restore_ok(restore, state), "reason": "restored", "restore": restore}


def load_auth_profile(client, domain, ttl=_PROFILE_TTL, session_id=None):
    """Load and restore auth profile for *domain* if fresh enough.

    Returns True only when the saved profile was restored on its saved origins.
    """
    try:
        return bool(load_auth_profile_result(client, domain, ttl=ttl, session_id=session_id).get("ok"))
    except Exception:
        return False
