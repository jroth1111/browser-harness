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
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse


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
    return request_path.startswith(path.rstrip("/") or "/")


def browser_cookies(client, urls):
    """Return cookies visible to the browser for `urls`.

    The returned values are sensitive. Callers should avoid printing or storing
    raw values.
    """
    urls = [urls] if isinstance(urls, str) else list(urls)
    return send_cdp(client, "Network.getCookies", {"urls": urls}).get("cookies", [])


def cookie_header(client, url, cookie_urls=None, cookies=None):
    """Build a domain/path/secure-filtered Cookie header for `url`."""
    cookie_urls = [url] if cookie_urls is None else ([cookie_urls] if isinstance(cookie_urls, str) else list(cookie_urls))
    source_cookies = browser_cookies(client, cookie_urls) if cookies is None else list(cookies)
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


def session_manifest(client, urls, site=None, profile_label=None, account_label=None, backend=None, session_id=None):
    """Create a redacted login/session manifest.

    Raw cookie and storage values are intentionally omitted.
    """
    urls = [urls] if isinstance(urls, str) else list(urls)
    cookies = browser_cookies(client, urls)
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
        "local_storage_keys": sorted(storage.get("localStorageKeys") or []),
        "session_storage_keys": sorted(storage.get("sessionStorageKeys") or []),
        "current_url": storage.get("url", ""),
        "origin": storage.get("origin", ""),
        "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def browser_session_headers(client, url, headers=None, cookie_urls=None, cookies=None, session_id=None):
    """Headers for same-domain HTTP using browser UA and matching cookies."""
    out = {
        "User-Agent": browser_user_agent(client, session_id=session_id),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-AU,en;q=0.9",
        "Accept-Encoding": "gzip",
    }
    cookie = cookie_header(client, url, cookie_urls=cookie_urls, cookies=cookies)
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


def http_get_with_login_session(client, url, headers=None, cookie_urls=None, timeout=20.0, block_detector=None):
    """HTTP GET with browser user agent and matching browser cookies."""
    req = urllib.request.Request(url, headers=browser_session_headers(client, url, headers=headers, cookie_urls=cookie_urls))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            text = _read_http_text(response)
            status = getattr(response, "status", None) or (response.getcode() if hasattr(response, "getcode") else 200)
            final_url = response.geturl() if hasattr(response, "geturl") else url
            response_headers = dict(response.headers)
    except urllib.error.HTTPError as error:
        text = _read_http_text(error)
        status = error.code
        final_url = error.geturl()
        response_headers = dict(error.headers)

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
