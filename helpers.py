"""Browser control via CDP. Read, edit, extend -- this file is yours."""
import atexit, base64, functools, json, os, re, socket, time, urllib.error, urllib.request
from collections import deque
from importlib.resources import files
from pathlib import Path
from urllib.parse import urljoin, urlparse
import login_session


def _load_env():
    p = Path(__file__).parent / ".env"
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()

NAME = os.environ.get("BH_NAME", "default")
SOCK = f"/tmp/bh-{NAME}.sock"
INTERNAL = ("chrome://", "chrome-untrusted://", "devtools://", "chrome-extension://", "about:")

_sock = None


def _asset_dir(local_name, package_name):
    local = Path(__file__).parent / local_name
    if local.is_dir():
        return local
    try:
        return Path(str(files(package_name)))
    except Exception:
        return local


def _reconnect():
    global _sock, _BROWSER_UA
    if _sock is not None:
        try:
            _sock.close()
        except OSError:
            pass
    _sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    _sock.settimeout(30)
    try:
        _sock.connect(SOCK)
    except Exception:
        _sock.close()
        _sock = None
        raise
    _BROWSER_UA = None  # invalidate cached UA on reconnect


def _recv(timeout=30):
    deadline = time.time() + timeout
    data = b""
    while not data.endswith(b"\n"):
        if time.time() > deadline:
            raise RuntimeError(f"_recv() timeout — no newline within {timeout}s")
        if len(data) > 10 << 20:
            raise RuntimeError(f"_recv() oversized response: {len(data)} bytes")
        chunk = _sock.recv(1 << 20)
        if not chunk:
            break
        data += chunk
    return data


# CDP methods that mutate browser state — don't auto-retry on socket errors.
_MUTATING_CDP = frozenset((
    "Page.navigate", "Input.dispatchMouseEvent", "Input.dispatchKeyEvent",
    "Input.insertText", "DOM.setFileInputFiles", "Page.captureScreenshot",
    "Network.setBlockedURLs", "Target.closeTarget", "Target.createTarget",
))


def _send(req, timeout=30):
    global _sock
    if _sock is None:
        _reconnect()
    payload = (json.dumps(req) + "\n").encode()
    method = req.get("method", "")
    try:
        _sock.sendall(payload)
        data = _recv(timeout)
    except (OSError, ConnectionResetError) as e:
        if method in _MUTATING_CDP:
            raise RuntimeError(f"socket error during {method}: {e}") from e
        _reconnect()
        _sock.sendall(payload)
        data = _recv(timeout)
    except (RuntimeError, ValueError):
        # _recv() timeout/oversize — socket state is corrupt
        try: _sock.close()
        except OSError: pass
        _sock = None
        raise
    try:
        r = json.loads(data)
    except (ValueError, json.JSONDecodeError) as e:
        # Malformed response — socket stream is misaligned, force reconnect
        try: _sock.close()
        except OSError: pass
        _sock = None
        raise RuntimeError(f"invalid CDP response ({len(data)} bytes): {e}") from e
    if "error" in r:
        err = r["error"]
        msg = err["message"] if isinstance(err, dict) and "message" in err else err
        raise RuntimeError(msg)
    return r


def _require_key(mapping, key, context):
    if not isinstance(mapping, dict) or key not in mapping:
        raise RuntimeError(f"{context} missing {key!r}: {mapping!r}")
    return mapping[key]


_RECOVERABLE_PATTERNS = (
    "Session with given id not found",
    "Not attached to target",
    "Connection closed",
    "Target closed",
    "No session with given id",
)


def _is_recoverable(error):
    msg = str(error).lower()
    return any(p.lower() in msg for p in _RECOVERABLE_PATTERNS)


def with_session_recovery(fn, *args, retries=1, **kwargs):
    """Run fn(), retry once on recoverable CDP errors after reconnecting."""
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        if not _is_recoverable(e) or retries <= 0:
            raise
        _reconnect()
        return fn(*args, **kwargs)


def _recovered(fn):
    """Decorator: retry once on recoverable CDP errors after reconnecting."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            if not _is_recoverable(e):
                raise
            _reconnect()
            return fn(*args, **kwargs)
    return wrapper


def cdp(method, session_id=None, timeout=30, **params):
    """Raw CDP. cdp('Page.navigate', url='...'), cdp('DOM.getDocument', depth=-1)."""
    return _send({"method": method, "params": params, "session_id": session_id}, timeout=timeout).get("result", {})


def drain_events():  return _send({"meta": "drain_events"}).get("events", [])
def endpoint_info(): return _send({"meta": "endpoint_info"}).get("endpoint_info", {})


def launch_browser(**kwargs):
    """Launch Chrome with CDP and connect the daemon. Returns {pid, port, ws_url}."""
    from admin import launch_browser as _launch
    return _launch(**kwargs)


def close_browser(launch_info):
    """Close a browser launched by launch_browser()."""
    from admin import close_browser as _close
    return _close(launch_info)


# --- navigation / page ---
def _wait_until_load(strategy, timeout=15.0):
    """Wait for a specific load event strategy. Returns {ok, reason}."""
    if strategy == "load":
        target_event = "Page.loadEventFired"
    elif strategy == "domcontentloaded":
        target_event = "Page.domContentLoadedEventFired"
    elif strategy == "networkidle":
        return _wait_until_network_idle(timeout)
    else:
        raise ValueError(f"unknown wait_until strategy: {strategy!r}")
    cdp("Page.enable")
    drain_events()
    deadline = time.time() + timeout
    while time.time() < deadline:
        for ev in drain_events():
            if ev.get("method") == target_event:
                return {"ok": True, "reason": strategy}
        time.sleep(0.3)
    return {"ok": False, "reason": "timeout"}


def _wait_until_network_idle(timeout=15.0):
    """Wait until no network requests are in flight for 500ms."""
    pending = set()
    deadline = time.time() + timeout
    idle_since = None
    result = {"ok": False, "reason": "timeout"}
    try:
        cdp("Network.enable")
        drain_events()
        while time.time() < deadline:
            for ev in drain_events():
                m = ev.get("method", "")
                rid = (ev.get("params") or {}).get("requestId")
                if m == "Network.requestWillBeSent" and rid:
                    pending.add(rid)
                    idle_since = None
                elif m in ("Network.loadingFinished", "Network.loadingFailed") and rid:
                    pending.discard(rid)
            if not pending:
                if idle_since is None:
                    idle_since = time.time()
                elif time.time() - idle_since >= 0.5:
                    result = {"ok": True, "reason": "networkidle"}
                    break
            else:
                idle_since = None
            time.sleep(0.1)
    finally:
        try:
            cdp("Network.disable")
        except Exception:
            pass
    if not result["ok"]:
        result["pending_requests"] = len(pending)
    return result


def smart_wait(timeout=20.0, min_text=200, waf_timeout=15.0):
    """Multi-phase page-ready check: settle, WAF detect, load, network idle, content.

    Each phase draws from the total *timeout* budget. Returns a dict with
    {phase, ok, reason, elapsed_ms} describing which phase resolved first.
    """
    start = time.time()

    def remaining():
        return max(0, timeout - (time.time() - start))

    # Phase 1: settle — give the page a moment to start rendering
    time.sleep(min(1.0, remaining()))

    # Phase 2: WAF / block-page detection
    if remaining() > 0:
        try:
            status = page_content_status()
            if status.get("block", {}).get("blocked"):
                waf_deadline = time.time() + min(waf_timeout, remaining())
                while time.time() < waf_deadline:
                    time.sleep(0.5)
                    status = page_content_status()
                    if not status.get("block", {}).get("blocked"):
                        return {"phase": "waf_cleared", "ok": True, "reason": "waf_cleared",
                                "elapsed_ms": int((time.time() - start) * 1000)}
                return {"phase": "waf_blocked", "ok": False, "reason": "blocked",
                        "elapsed_ms": int((time.time() - start) * 1000)}
        except Exception:
            pass

    # Phase 3: load event
    if remaining() > 0:
        load_result = _wait_until_load("load", timeout=min(5.0, remaining()))
        if load_result.get("ok"):
            return {"phase": "load", "ok": True, "reason": "load",
                    "elapsed_ms": int((time.time() - start) * 1000)}

    # Phase 4: network idle
    if remaining() > 0:
        idle_result = _wait_until_network_idle(timeout=min(5.0, remaining()))
        if idle_result.get("ok"):
            return {"phase": "networkidle", "ok": True, "reason": "networkidle",
                    "elapsed_ms": int((time.time() - start) * 1000)}

    # Phase 5: content check
    if remaining() > 0:
        content_result = wait_for_content(min_text=min_text, timeout=remaining())
        if content_result.get("ok"):
            return {"phase": "content", "ok": True, "reason": content_result.get("reason"),
                    "elapsed_ms": int((time.time() - start) * 1000)}

    return {"phase": "timeout", "ok": False, "reason": "all_phases_exhausted",
            "elapsed_ms": int((time.time() - start) * 1000)}


@_recovered
def goto_url(url, wait_until=None):
    """Navigate the current tab to *url*.

    wait_until: "load" | "domcontentloaded" | "networkidle" | "content" | None.
    When None (default), returns raw CDP result (backward compatible).
    When set, returns structured {ok, reason, url, title, frameId, domain_skills}.
    """
    cdp("Page.enable")
    drain_events()
    r = cdp("Page.navigate", url=url)
    d = (_asset_dir("domain-skills", "browser_harness_domain_skills") / (urlparse(url).hostname or "").removeprefix("www.").split(".")[0])
    ds = sorted(p.name for p in d.rglob("*.md"))[:10] if d.is_dir() else []

    if wait_until is None:
        return {**r, "domain_skills": ds} if ds else r

    if wait_until == "content":
        status = wait_for_content(timeout=15.0)
        info = page_info()
        return {
            "ok": status.get("ok", False),
            "reason": status.get("reason"),
            "url": info.get("url", url),
            "title": info.get("title", ""),
            "frameId": r.get("frameId"),
            "domain_skills": ds,
        }

    wait_result = _wait_until_load(wait_until)
    info = page_info()
    return {
        "ok": wait_result.get("ok", False),
        "reason": wait_result.get("reason"),
        "url": info.get("url", url),
        "title": info.get("title", ""),
        "frameId": r.get("frameId"),
        "domain_skills": ds,
    }

def goto_with_auth(url, wait_until=None):
    """Navigate to *url*, restoring a saved auth profile for the domain first.

    Calls load_auth_profile before goto_url. If no profile exists or it's
    expired, navigates without restored auth. Returns the goto_url result.
    """
    login_session.load_auth_profile(cdp, urlparse(url).hostname or "")
    return goto_url(url, wait_until=wait_until)


def navigate_via_google(url, google_base="https://www.google.com"):
    """Navigate to URL with Google as the HTTP Referer.

    Opens Google first, then redirects to the target URL. Some WAF systems
    (Cloudflare, Akamai) treat search-engine referrals as organic traffic and
    apply lighter challenge requirements.

    Returns a dict with content health status (ok, reason, block, textLength)
    plus viewport metrics (url, title, w, h). Check ``ok`` before extracting.
    """
    goto_url(google_base)
    wait_for_load(timeout=10.0)
    # Use JS navigation so the browser sends Google as the referrer
    js(f"location.href = {json.dumps(url)}")
    status = wait_for_content(min_text=200, timeout=15.0)
    info = page_info()
    return {**status, "w": info.get("w", 0), "h": info.get("h", 0)}

@_recovered
def page_info():
    """{url, title, w, h, sx, sy, pw, ph} - viewport + scroll + page size.

    If a native dialog (alert/confirm/prompt/beforeunload) is open, returns
    {dialog: {type, message, ...}} instead - the page's JS thread is frozen
    until the dialog is handled (see interaction-skills/dialogs.md)."""
    dialog = _send({"meta": "pending_dialog"}).get("dialog")
    if dialog:
        return {"dialog": dialog}
    target = cdp("Target.getTargetInfo").get("targetInfo", {})
    metrics = cdp("Page.getLayoutMetrics")
    viewport = metrics.get("cssLayoutViewport") or metrics.get("layoutViewport") or {}
    content = metrics.get("cssContentSize") or metrics.get("contentSize") or {}
    return {
        "url": target.get("url", ""),
        "title": target.get("title", ""),
        "w": int(viewport.get("clientWidth") or 0),
        "h": int(viewport.get("clientHeight") or 0),
        "sx": int(viewport.get("pageX") or 0),
        "sy": int(viewport.get("pageY") or 0),
        "pw": int(content.get("width") or 0),
        "ph": int(content.get("height") or 0),
    }

def page_info_js():
    """JS-based page info fallback. This explicitly executes page JavaScript."""
    r = cdp("Runtime.evaluate",
            expression="JSON.stringify({url:location.href,title:document.title,w:innerWidth,h:innerHeight,sx:scrollX,sy:scrollY,pw:document.documentElement.scrollWidth,ph:document.documentElement.scrollHeight})",
            returnByValue=True)
    result = _require_key(r, "result", "Runtime.evaluate response")
    value = _require_key(result, "value", "Runtime.evaluate result")
    return json.loads(value)

def detect_block_page(html="", text="", url=""):
    """Detect known bot/WAF challenge shells from page source/text.

    This is intentionally detection-only. It does not attempt to solve challenges
    or hide automation; callers use it to avoid mistaking an empty challenge page
    for real content.
    """
    html = html or ""
    text = text or ""
    url = url or ""
    # Single lowercased copy for substring matching — avoids per-needle regex.
    haystack = (html + "\n" + text + "\n" + url).lower()
    html_len = len(html)
    stripped_text = text.strip()
    evidence = []
    kind = None

    def _has(needle):
        return needle in haystack

    def _matches(needles):
        return [n for n in needles if n in haystack]

    # Kasada/KPSDK
    kpsdk_hits = _matches(("window.kpsdk", "x-kpsdk", "kp_uidz", "/ips.js"))
    if len(kpsdk_hits) >= 2 and (not stripped_text or html_len < 8000):
        kind = "kasada_kpsdk"
        evidence.extend(kpsdk_hits)

    # Akamai — expanded with Crawl4AI's Reference # patterns
    if not kind:
        akamai_hits = _matches((
            "reference #", "pardon our interruption", "errors.edgesuite.net",
            "failover-waf", "access denied", "akamai",
            "_abck", "akamai_sw",
        ))
        if len(akamai_hits) >= 2 or (_has("reference #") and html_len < 10000):
            kind = "akamai"
            evidence.extend(akamai_hits[:3])

    # PerimeterX
    if not kind:
        px_hits = _matches((
            "_pxappid", "window._px", "collector.perimeterx.net",
            "captcha.px-cdn.net", "human security challenge",
            "px-cdn.net", "_pxmvid",
        ))
        if len(px_hits) >= 2 or (_has("_pxappid") and html_len < 10000):
            kind = "perimeterx"
            evidence.extend(px_hits[:3])

    # Imperva/Incapsula
    if not kind:
        imperva_hits = _matches((
            "_incapsula_resource", "incident id", "x-iinfo",
            "imperva", "incapsula",
        ))
        if len(imperva_hits) >= 2:
            kind = "imperva"
            evidence.extend(imperva_hits[:3])

    # DataDome
    if not kind:
        dd_hits = _matches((
            "window.dd", "dd.key", "datadome.co",
            "dd_tracker", "_dd_l", "ddjskey",
        ))
        if len(dd_hits) >= 2 or (_has("datadome.co") and html_len < 10000):
            kind = "datadome"
            evidence.extend(dd_hits[:3])

    # Generic WAF shell — small page with block indicators (Crawl4AI tier 2/3)
    if not kind and html_len < 10000:
        generic_hits = _matches((
            "checking your browser", "just a moment",
            "please verify you are human", "are you a robot",
            "blocked by security", "request blocked",
        ))
        if generic_hits:
            kind = "waf_generic"
            evidence.extend(generic_hits[:2])

    # Auth gate / login redirect — page is an auth wall, not the requested content
    if not kind:
        url_lower = url.lower()
        # Path-segment matching to avoid false positives like "/products/login-guide"
        auth_url_hits = [p for p in (
            "/login", "/signin", "/sign-in", "/auth/login", "/authenticate",
            "/accounts/login", "/account/login", "/sso/login",
        ) if url_lower.rstrip("/").endswith(p) or f"{p}?" in url_lower or f"{p}&" in url_lower]
        auth_text_hits = _matches((
            "sign in to continue", "log in to continue",
            "please sign in", "please log in",
            "login to access", "authentication required",
            "you need to sign in", "you must be logged in",
            "create an account to continue", "register to continue",
        ))
        if auth_url_hits or (auth_text_hits and html_len < 30000):
            kind = "auth_gate"
            evidence.extend(auth_url_hits[:2])
            evidence.extend(auth_text_hits[:2])

    if not kind:
        return {"blocked": False, "kind": None, "evidence": []}
    return {"blocked": True, "kind": kind, "evidence": evidence}

@_recovered
def page_content_status(html_limit=12000, text_limit=12000):
    """Return JS-derived page content health plus block/challenge detection.

    Use after navigation when a page can be "loaded" but still contain no useful
    app content, for example a WAF challenge shell. This explicitly executes page
    JavaScript.
    """
    expr = f"""
(() => {{
  const body = document.body;
  const root = document.documentElement;
  const text = body ? body.innerText : "";
  const html = root ? root.outerHTML : "";
  return {{
    url: location.href,
    title: document.title,
    readyState: document.readyState,
    textLength: text.length,
    htmlLength: html.length,
    text: text.slice(0, {int(text_limit)}),
    html: html.slice(0, {int(html_limit)})
  }};
}})()
"""
    state = js(expr) or {}
    block = detect_block_page(
        html=state.get("html", ""),
        text=state.get("text", ""),
        url=state.get("url", ""),
    )
    return {**state, "block": block}

def wait_for_content(min_text=200, timeout=15.0, poll=0.5):
    """Wait until body text is useful, a known block page appears, or timeout hits.

    Returns a structured status dict. This explicitly executes page JavaScript.
    """
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        last = page_content_status()
        # Tab detached or JS error — stop polling immediately
        if last.get("_js_undefined") or last.get("_js_error"):
            return {**last, "ok": False, "reason": "js_error"}
        if last.get("block", {}).get("blocked"):
            return {**last, "ok": False, "reason": "blocked"}
        if int(last.get("textLength") or 0) >= min_text:
            return {**last, "ok": True, "reason": "content"}
        time.sleep(poll)
    return {**last, "ok": False, "reason": "timeout"}

def _cookie_matches_url(cookie, url):
    return login_session.cookie_matches_url(cookie, url)

def browser_cookies(urls):
    """Return cookies visible to the attached browser for `urls`.

    This explicitly queries browser session state through CDP. Do not print or
    commit the returned values.
    """
    return login_session.browser_cookies(cdp, urls)

def browser_cookie_header(url, cookie_urls=None):
    """Cookie header for `url` from attached-browser cookies, domain-filtered."""
    return login_session.cookie_header(cdp, url, cookie_urls=cookie_urls)

def _origin_url(url):
    return login_session.origin_url(url)

def _browser_session_headers(url, headers=None, cookie_urls=None):
    return login_session.browser_session_headers(cdp, url, headers=headers, cookie_urls=cookie_urls)

def http_get_browser_session_response(url, headers=None, cookie_urls=None, timeout=20.0):
    """HTTP GET result using the attached browser's UA and matching cookies.

    Returns `{ok, http_ok, status, url, text, block, headers}` and captures HTTP
    error bodies so callers can detect WAF/challenge pages instead of losing the
    response to an exception.
    """
    return login_session.http_get_with_login_session(
        cdp,
        url,
        headers=headers,
        cookie_urls=cookie_urls,
        timeout=timeout,
        block_detector=detect_block_page,
    )

def login_session_manifest(urls, site=None, profile_label=None, account_label=None, backend=None):
    """Redacted login/session manifest for the attached browser.

    Contains cookie names/domains and storage keys, never raw cookie or storage
    values. Use this to create local session continuity receipts.
    """
    return login_session.session_manifest(
        cdp,
        urls,
        site=site,
        profile_label=profile_label,
        account_label=account_label,
        backend=backend,
    )

def prompt_user_login(login_url, success_url_contains=None, min_text=200, timeout=180.0, poll=2.0):
    """Open a login page and wait for the user to complete login manually."""
    return login_session.prompt_user_login(
        cdp,
        login_url,
        success_url_contains=success_url_contains,
        min_text=min_text,
        timeout=timeout,
        poll=poll,
    )

def http_get_browser_session(url, headers=None, cookie_urls=None, timeout=20.0):
    """HTTP GET using the attached browser's user agent and matching cookies.

    This is useful after a real browser profile has passed a site challenge and
    you want to fetch additional same-domain HTML/API pages without rendering
    each one. It does not solve challenges; without valid browser cookies it will
    receive the same block page as ordinary HTTP.
    """
    result = http_get_browser_session_response(url, headers=headers, cookie_urls=cookie_urls, timeout=timeout)
    if not result["http_ok"]:
        raise RuntimeError(f"browser-session HTTP failed: {result['status']} {result['url']}")
    return result["text"]

def seed_browser_session(url, min_text=500, timeout=20.0, close=True):
    """Navigate a real browser tab to `url` and verify useful content appears.

    Returns a structured status with `ok`, `reason`, `block`, `cookieNames`, and
    `targetId`. This is the explicit "solve/refresh the browser session first"
    primitive for domains whose direct HTTP requests depend on browser cookies.
    """
    tid = None
    try:
        tid = new_tab(url)
        wait_for_load(timeout=timeout)
        status = wait_for_content(min_text=min_text, timeout=timeout)
        cookie_names = sorted({
            c.get("name", "")
            for c in browser_cookies([_origin_url(url), url])
            if c.get("name") and _cookie_matches_url(c, url)
        })
        return {**status, "targetId": tid, "seedUrl": url, "cookieNames": cookie_names}
    finally:
        if close and tid:
            try: close_tab(tid)
            except Exception: pass

def browser_backend_info():
    """Diagnose the attached CDP backend. Explicitly runs JS for page-level facts."""
    version = {}
    version_error = None
    try:
        version = cdp("Browser.getVersion")
    except Exception as e:
        version_error = str(e)
    js_probe = {}
    js_error = None
    try:
        js_probe = js("""({
            userAgent: navigator.userAgent,
            webdriver: navigator.webdriver,
            platform: navigator.platform,
            languages: navigator.languages,
            plugins: navigator.plugins ? navigator.plugins.length : null,
            hardwareConcurrency: navigator.hardwareConcurrency,
            deviceMemory: navigator.deviceMemory || null
        })""") or {}
    except Exception as e:
        js_error = str(e)

    endpoint = endpoint_info()
    blob = " ".join(str(x or "") for x in (
        endpoint.get("browser"),
        version.get("product"),
        version.get("userAgent"),
        js_probe.get("userAgent"),
    )).lower()
    if "lightpanda" in blob:
        kind = "lightpanda"
    elif "headless" in blob:
        kind = "headless_chrome"
    elif "chrome" in blob or "chromium" in blob or "edge" in blob:
        kind = "chromium"
    else:
        kind = "unknown"

    risks = []
    if kind in {"lightpanda", "headless_chrome"}:
        risks.append(f"{kind} may not satisfy full browser fingerprint challenges")
    if js_probe.get("webdriver") is True:
        risks.append("navigator.webdriver is true")
    if js_probe.get("plugins") == 0:
        risks.append("navigator.plugins is empty")
    return {
        "kind": kind,
        "endpoint": endpoint,
        "version": version,
        "versionError": version_error,
        "js": js_probe,
        "jsError": js_error,
        "risks": risks,
    }

def _backend_recommendation(status, backend):
    block = status.get("block") or {}
    if block.get("kind") == "kasada_kpsdk":
        if backend.get("kind") in {"lightpanda", "headless_chrome"}:
            return "Seed or fetch this domain with a persistent headful Chrome profile; this backend received a Kasada/KPSDK shell."
        return "Use a persistent browser profile that can pass the Kasada/KPSDK challenge, then reuse browser-session HTTP."
    if status.get("ok"):
        return "Backend served useful content."
    return "Inspect the page status and consider a persistent headful profile if the target serves challenge pages."

def diagnose_url_capability(url, min_text=500, timeout=20.0, close=True):
    """Navigate to `url` and report backend capability/content status."""
    tid = None
    try:
        tid = new_tab(url)
        wait_for_load(timeout=timeout)
        status = wait_for_content(min_text=min_text, timeout=timeout)
        backend = browser_backend_info()
        return {
            "ok": status.get("ok", False),
            "reason": status.get("reason"),
            "url": status.get("url"),
            "title": status.get("title"),
            "textLength": status.get("textLength"),
            "htmlLength": status.get("htmlLength"),
            "block": status.get("block"),
            "backend": backend,
            "recommendation": _backend_recommendation(status, backend),
        }
    finally:
        if close and tid:
            try: close_tab(tid)
            except Exception: pass

def _extract_json_assignment(html, name):
    marker = f"window.{name}="
    start = html.find(marker)
    if start < 0:
        return None
    i = html.find("{", start + len(marker))
    if i < 0:
        return None
    depth = 0
    quote = None
    escape = False
    for pos in range(i, len(html)):
        ch = html[pos]
        if quote:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                quote = None
            continue
        if ch in {"'", '"', '`'}:
            quote = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return html[i:pos + 1]
    return None

def _decode_nested_json_strings(value, _depth=0):
    if _depth > 10:
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith(("{", "[")):
            try:
                return _decode_nested_json_strings(json.loads(stripped), _depth + 1)
            except (TypeError, ValueError):
                return value
        return value
    if isinstance(value, list):
        return [_decode_nested_json_strings(item, _depth + 1) for item in value]
    if isinstance(value, dict):
        return {k: _decode_nested_json_strings(v, _depth + 1) for k, v in value.items()}
    return value

def extract_argonaut_exchange(html=None, decode_json_strings=True):
    """Extract `window.ArgonautExchange` from current page HTML or supplied HTML.

    REA Argonaut pages embed route data as a JSON assignment where values may be
    JSON-encoded strings. By default those nested strings are decoded too.
    """
    if html is None:
        html = js("document.documentElement.outerHTML")
    raw = _extract_json_assignment(html or "", "ArgonautExchange")
    if not raw:
        return {}
    data = json.loads(raw)
    return _decode_nested_json_strings(data) if decode_json_strings else data

# --- input ---
_debug_click_counter = 0

def _debug_click_dpr(image_width):
    """Infer screenshot pixel scale from CDP layout metrics without page JS."""
    try:
        info = page_info()
    except Exception:
        return 1
    viewport_width = int(info.get("w") or 0)
    if viewport_width <= 0:
        return 1
    return image_width / viewport_width

@_recovered
def click_at_xy(x, y, button="left", clicks=1, humanize=False, steps=12):
    if os.environ.get("BH_DEBUG_CLICKS"):
        global _debug_click_counter
        try:
            from PIL import Image, ImageDraw
            path = capture_screenshot(f"/tmp/debug_click_{_debug_click_counter}.png")
            img = Image.open(path)
            dpr = _debug_click_dpr(img.width)
            draw = ImageDraw.Draw(img)
            px, py = int(x * dpr), int(y * dpr)
            r = int(15 * dpr)
            draw.ellipse([px - r, py - r, px + r, py + r], outline="red", width=int(3 * dpr))
            draw.line([px - r - int(5 * dpr), py, px + r + int(5 * dpr), py], fill="red", width=int(2 * dpr))
            draw.line([px, py - r - int(5 * dpr), px, py + r + int(5 * dpr)], fill="red", width=int(2 * dpr))
            img.save(path)
            print(f"[debug_click] saved {path} (x={x}, y={y}, dpr={dpr})")
        except Exception as e:
            print(f"[debug_click] overlay failed: {e}")
        _debug_click_counter += 1
    if humanize:
        import random
        # Randomize final click position within ±5px to avoid pixel-exact repetition
        jitter_x = random.uniform(-5, 5)
        jitter_y = random.uniform(-5, 5)
        target_x, target_y = x + jitter_x, y + jitter_y
        # Move from a random starting position with eased interpolation
        start_x = max(0, x - random.randint(30, 60))
        start_y = y + random.randint(-20, 20)
        total_ms = random.uniform(80, 160)
        step_sleep = total_ms / (max(2, steps) * 1000)
        for i in range(1, max(2, steps) + 1):
            t = i / max(2, steps)
            eased = t * t * (3 - 2 * t)
            cdp("Input.dispatchMouseEvent", type="mouseMoved",
                x=start_x + (target_x - start_x) * eased,
                y=start_y + (target_y - start_y) * eased)
            if i < max(2, steps):
                time.sleep(step_sleep)
        x, y = target_x, target_y
    cdp("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button=button, clickCount=clicks)
    cdp("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button=button, clickCount=clicks)

def type_text(text, delay=0):
    if delay <= 0:
        cdp("Input.insertText", text=text)
        return
    for ch in text:
        vk = ord(ch) if len(ch) == 1 else 0
        base = {"key": ch, "code": ch, "windowsVirtualKeyCode": vk, "nativeVirtualKeyCode": vk}
        cdp("Input.dispatchKeyEvent", type="keyDown", **base)
        cdp("Input.dispatchKeyEvent", type="char", text=ch, **base)
        cdp("Input.dispatchKeyEvent", type="keyUp", **base)
        time.sleep(delay)

_KEYS = {  # key → (windowsVirtualKeyCode, code, text)
    "Enter": (13, "Enter", "\r"), "Tab": (9, "Tab", "\t"), "Backspace": (8, "Backspace", ""),
    "Escape": (27, "Escape", ""), "Delete": (46, "Delete", ""), " ": (32, "Space", " "),
    "ArrowLeft": (37, "ArrowLeft", ""), "ArrowUp": (38, "ArrowUp", ""),
    "ArrowRight": (39, "ArrowRight", ""), "ArrowDown": (40, "ArrowDown", ""),
    "Home": (36, "Home", ""), "End": (35, "End", ""),
    "PageUp": (33, "PageUp", ""), "PageDown": (34, "PageDown", ""),
}
def press_key(key, modifiers=0):
    """Modifiers bitfield: 1=Alt, 2=Ctrl, 4=Meta(Cmd), 8=Shift.
    Special keys (Enter, Tab, Arrow*, Backspace, etc.) carry their virtual key codes
    so listeners checking e.keyCode / e.key all fire."""
    vk, code, text = _KEYS.get(key, (ord(key[0]) if len(key) == 1 else 0, key, key if len(key) == 1 else ""))
    base = {"key": key, "code": code, "modifiers": modifiers, "windowsVirtualKeyCode": vk, "nativeVirtualKeyCode": vk}
    cdp("Input.dispatchKeyEvent", type="keyDown", **base, **({"text": text} if text else {}))
    if text and len(text) == 1:
        cdp("Input.dispatchKeyEvent", type="char", text=text, **{k: v for k, v in base.items() if k != "text"})
    cdp("Input.dispatchKeyEvent", type="keyUp", **base)

def scroll(x, y, dy=-300, dx=0):
    cdp("Input.dispatchMouseEvent", type="mouseWheel", x=x, y=y, deltaX=dx, deltaY=dy)


# --- visual ---
@_recovered
def capture_screenshot(path="/tmp/shot.png", full=False):
    r = cdp("Page.captureScreenshot", format="png", captureBeyondViewport=full)
    data = base64.b64decode(_require_key(r, "data", "Page.captureScreenshot response"))
    with open(path, "wb") as f:
        f.write(data)
    return path


# --- tabs ---
def list_tabs(include_chrome=True):
    out = []
    for t in cdp("Target.getTargets")["targetInfos"]:
        if t["type"] != "page": continue
        url = t.get("url", "")
        if not include_chrome and url.startswith(INTERNAL): continue
        out.append({"targetId": t["targetId"], "title": t.get("title", ""), "url": url})
    return out

def current_tab():
    t = cdp("Target.getTargetInfo").get("targetInfo", {})
    return {"targetId": t.get("targetId"), "url": t.get("url", ""), "title": t.get("title", "")}

def switch_tab(target):
    # Accept either a raw targetId string or the dict returned by current_tab() / list_tabs(),
    # so `switch_tab(current_tab())` works without a manual ["targetId"] dance.
    target_id = target.get("targetId") if isinstance(target, dict) else target
    cdp("Target.activateTarget", targetId=target_id)
    sid = _require_key(cdp("Target.attachToTarget", targetId=target_id, flatten=True), "sessionId", "Target.attachToTarget response")
    _send({"meta": "set_session", "session_id": sid, "target_id": target_id})
    return sid

def close_tab(target=None):
    """Close a tab by targetId/dict, or the current tab when omitted.

    When closing the attached tab, re-attach to the first remaining real tab so
    the next helper call does not pay a stale-session recovery round-trip.
    """
    cur = current_tab()
    target_id = cur.get("targetId") if target is None else (target.get("targetId") if isinstance(target, dict) else target)
    if not target_id:
        raise RuntimeError(f"close_tab missing targetId: {target!r}")
    was_current = cur.get("targetId") == target_id
    result = cdp("Target.closeTarget", targetId=target_id)
    if was_current:
        tabs = list_tabs(include_chrome=False) or list_tabs(include_chrome=True)
        if tabs:
            switch_tab(tabs[0])
            cur = current_tab()
            if cur.get("url", "").startswith(INTERNAL):
                raise RuntimeError("no real browser tabs remaining — all tabs are internal chrome:// pages")
    return result.get("success", True)

def close_tabs(targets):
    """Close many tabs by targetId/dict and re-attach if the current tab closes."""
    cur = current_tab()
    cur_id = cur.get("targetId")
    target_ids = []
    for target in targets:
        target_id = target.get("targetId") if isinstance(target, dict) else target
        if target_id:
            target_ids.append(target_id)
    closed_current = cur_id in target_ids
    out = {}
    for target_id in target_ids:
        out[target_id] = cdp("Target.closeTarget", targetId=target_id).get("success", True)
    if closed_current:
        tabs = list_tabs(include_chrome=False) or list_tabs(include_chrome=True)
        if tabs:
            switch_tab(tabs[0])
    return out

_MAX_TABS = int(os.environ.get("BH_MAX_TABS", "5"))


def _enforce_tab_limit():
    tab_count = len(list_tabs(include_chrome=False))
    if tab_count >= _MAX_TABS:
        raise RuntimeError(
            f"tab limit reached ({tab_count}/{_MAX_TABS}). "
            f"Close a tab first or set BH_MAX_TABS to raise the limit."
        )


def new_tab(url="about:blank"):
    # Always create blank, then goto: passing url to createTarget races with
    # attach, so the brief about:blank is "complete" by the time the caller
    # polls and wait_for_load() returns before navigation actually starts.
    _enforce_tab_limit()
    tid = _require_key(cdp("Target.createTarget", url="about:blank"), "targetId", "Target.createTarget response")
    try:
        switch_tab(tid)
        if url != "about:blank":
            goto_url(url)
    except Exception:
        try: cdp("Target.closeTarget", targetId=tid)
        except Exception: pass
        raise
    return tid

def ensure_real_tab():
    """Switch to a real user tab if current is chrome:// / internal / stale."""
    tabs = list_tabs(include_chrome=False)
    if not tabs:
        return None
    try:
        cur = current_tab()
        if cur["url"] and not cur["url"].startswith(INTERNAL):
            return cur
    except Exception:
        pass
    switch_tab(tabs[0]["targetId"])
    return tabs[0]

def iframe_target(url_substr):
    """First iframe target whose URL contains `url_substr`. Use with js(..., target_id=...)."""
    for t in cdp("Target.getTargets")["targetInfos"]:
        if t["type"] == "iframe" and url_substr in t.get("url", ""):
            return t["targetId"]
    return None


def poll_for_new_tab(timeout=5.0, poll=0.3):
    """Wait for a new page target to appear. Returns target dict or None."""
    known = {t["targetId"] for t in list_tabs(include_chrome=False)}
    deadline = time.time() + timeout
    while time.time() < deadline:
        for _ in drain_events():
            pass
        current = {t["targetId"] for t in list_tabs(include_chrome=False)}
        new = current - known
        if new:
            tid = new.pop()
            return next(t for t in list_tabs() if t["targetId"] == tid)
        time.sleep(poll)
    return None


# --- utility ---
def wait(seconds=1.0):
    time.sleep(seconds)

def wait_for_load(timeout=15.0):
    """Wait for Page.loadEventFired without executing page JavaScript."""
    result = _wait_until_load("load", timeout)
    return result.get("ok", False)

def wait_for_load_js(timeout=15.0):
    """JS-based load wait fallback. This explicitly executes page JavaScript."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if js("document.readyState") == "complete": return True
        time.sleep(0.3)
    return False

def js(expression, target_id=None):
    """Explicitly run JavaScript in the attached tab or an iframe target.

    Expressions with top-level `return` are automatically wrapped in an IIFE, so both
    `document.title` and `const x = 1; return x` are valid inputs.

    Returns the JS value on success. Returns structured dicts on failure:
    - {"_js_error": message} — expression threw an exception
    - {"_js_undefined": True} — expression returned undefined (tab may be detached)
    """
    sid = _require_key(cdp("Target.attachToTarget", targetId=target_id, flatten=True), "sessionId", "Target.attachToTarget response") if target_id else None
    # Wrap in IIFE when expression contains a return keyword at statement level.
    # Strip quoted strings first to avoid matching "return" inside selectors like '.return-to-top'.
    stripped = re.sub(r'''('(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*"|`(?:[^`\\]|\\.)*`)''', '', expression)
    if re.search(r'\breturn\b', stripped) and not expression.strip().startswith("("):
        expression = f"(function(){{{expression}}})()"
    r = cdp("Runtime.evaluate", session_id=sid, expression=expression, returnByValue=True, awaitPromise=True)
    result = r.get("result") or {}
    if not r.get("result"):
        return {"_js_error": f"Runtime.evaluate returned no result: {r!r}"}
    # Check for JS exception — return structured error instead of undefined
    if result.get("type") == "undefined" and "exceptionDetails" in r:
        exc = r["exceptionDetails"]
        msg = ""
        exc_text = exc.get("exception", {})
        if isinstance(exc_text, dict):
            msg = exc_text.get("description", "")
        if not msg:
            msg = exc.get("text", "unknown JS error")
        return {"_js_error": msg}
    # Distinguish "JS returned undefined" from error states
    if result.get("type") == "undefined":
        return {"_js_undefined": True}
    return result.get("value")


_KC = {"Enter": 13, "Tab": 9, "Escape": 27, "Backspace": 8, " ": 32, "ArrowLeft": 37, "ArrowUp": 38, "ArrowRight": 39, "ArrowDown": 40}


def dispatch_key(selector, key="Enter", event="keypress"):
    """Dispatch a DOM KeyboardEvent on the matched element.

    Use this when a site reacts to synthetic DOM key events on an element more reliably
    than to raw CDP input events. This explicitly executes page JavaScript.
    """
    kc = _KC.get(key, ord(key) if len(key) == 1 else 0)
    js(
        f"(()=>{{const e=document.querySelector({json.dumps(selector)});if(e){{e.focus();e.dispatchEvent(new KeyboardEvent({json.dumps(event)},{{key:{json.dumps(key)},code:{json.dumps(key)},keyCode:{kc},which:{kc},bubbles:true}}));}}}})()"
    )

def upload_file(selector, path):
    """Set files on a file input via CDP DOM.setFileInputFiles. `path` is an absolute filepath (use tempfile.mkstemp if needed)."""
    doc = cdp("DOM.getDocument", depth=-1)
    nid = _require_key(cdp("DOM.querySelector", nodeId=doc["root"]["nodeId"], selector=selector), "nodeId", "DOM.querySelector response")
    if not nid: raise RuntimeError(f"no element for {selector}")
    cdp("DOM.setFileInputFiles", files=[path] if isinstance(path, str) else list(path), nodeId=nid)

INTERACTIVE_ROLES = frozenset((
    "button", "link", "textbox", "checkbox", "radio", "combobox",
    "listbox", "menuitem", "menuitemcheckbox", "menuitemradio",
    "option", "searchbox", "slider", "spinbutton", "switch",
    "tab", "treeitem", "Iframe",
))

CONTENT_ROLES = frozenset((
    "heading", "cell", "gridcell", "columnheader", "rowheader",
    "listitem", "article", "region", "main", "navigation",
))

STRUCTURAL_ROLES = frozenset((
    "generic", "group", "list", "table", "row", "rowgroup",
    "grid", "treegrid", "menu", "menubar", "toolbar", "tablist",
    "tree", "directory", "document", "application", "presentation",
    "none", "WebArea", "RootWebArea",
))

_PROPS_OF_INTEREST = frozenset(("checked", "expanded", "selected", "disabled", "required", "level"))

_ref_map = {}
_ref_seq = 0


def _ax_value(field):
    if isinstance(field, dict):
        return field.get("value", "")
    return field or ""


def _ax_props(node):
    props = node.get("properties") or []
    out = {}
    for p in props:
        name = p.get("name")
        if name in _PROPS_OF_INTEREST:
            val = p.get("value", {})
            out[name] = val.get("value") if isinstance(val, dict) else val
    return out


def ax_snapshot(max_nodes=120, compact=False):
    """Accessibility-tree snapshot.

    compact=True returns only interactive + named content nodes as compact
    strings with stable eN refs (e.g. ``button "Login" [ref=e0]``). The ref
    map is populated for use with click_ref(). Default mode returns the
    original list-of-dicts format.
    """
    global _ref_map, _ref_seq
    nodes = cdp("Accessibility.getFullAXTree").get("nodes", [])
    if not compact:
        out = []
        for node in nodes[:max_nodes]:
            role = _ax_value(node.get("role"))
            name = _ax_value(node.get("name"))
            value = _ax_value(node.get("value"))
            if not role and not name and not value:
                continue
            out.append({
                "ref": node.get("backendDOMNodeId") or node.get("nodeId"),
                "role": role,
                "name": name,
                "value": value,
            })
        return out
    # Compact mode: filtered, token-efficient output with stable refs
    _ref_map = {}
    _ref_seq = 0
    out = []
    for node in nodes:
        role = _ax_value(node.get("role"))
        name = _ax_value(node.get("name"))
        value = _ax_value(node.get("value"))
        if role in STRUCTURAL_ROLES:
            continue
        if role == "StaticText" and not name:
            continue
        is_interactive = role in INTERACTIVE_ROLES
        is_content = role in CONTENT_ROLES and name
        if not is_interactive and not is_content:
            continue
        ref = f"e{_ref_seq}"
        _ref_map[ref] = {
            "backend_node_id": node.get("backendDOMNodeId"),
            "role": role,
            "name": name,
            "nth": _ref_seq,
        }
        _ref_seq += 1
        parts = [role]
        if name:
            parts.append(f'"{name}"')
        attrs = [f"ref={ref}"]
        for k, v in _ax_props(node).items():
            if v is None:
                continue
            if v is False and k != "disabled":
                continue
            attrs.append(f"{k}={v}")
        parts.append(f"[{', '.join(attrs)}]")
        if value and value != name:
            parts.append(f": {value}")
        out.append(" ".join(parts))
        if len(out) >= max_nodes:
            break
    return out


def clear_refs():
    """Clear the element ref map. Call after navigation to invalidate stale refs."""
    global _ref_map, _ref_seq
    _ref_map = {}
    _ref_seq = 0


def _resolve_ref_center(ref):
    """Resolve an eN ref to page (x, y) coordinates via DOM.getBoxModel."""
    entry = _ref_map.get(ref)
    if not entry:
        raise RuntimeError(f"unknown ref {ref!r}; take a snapshot first")
    bid = entry["backend_node_id"]
    if bid is None:
        raise RuntimeError(f"ref {ref} has no backend_node_id; re-snapshot")
    try:
        model = cdp("DOM.getBoxModel", backendNodeId=bid)
    except RuntimeError:
        return _resolve_ref_fallback(entry)
    content = model.get("model", {}).get("content", [])
    if len(content) >= 8:
        x = (content[0] + content[2] + content[4] + content[6]) / 4
        y = (content[1] + content[3] + content[5] + content[7]) / 4
        return x, y
    raise RuntimeError(f"ref {ref}: DOM.getBoxModel returned no content quad")


def _resolve_ref_fallback(entry):
    """Fallback: re-query AX tree to find fresh backend_node_id by role/name."""
    nodes = cdp("Accessibility.getFullAXTree").get("nodes", [])
    role, name, nth = entry["role"], entry["name"], entry["nth"]
    match_count = 0
    for node in nodes:
        n_role = _ax_value(node.get("role"))
        n_name = _ax_value(node.get("name"))
        # Apply same filter as compact mode so nth index matches
        if n_role in STRUCTURAL_ROLES:
            continue
        if n_role == "StaticText" and not n_name:
            continue
        is_interactive = n_role in INTERACTIVE_ROLES
        is_content = n_role in CONTENT_ROLES and n_name
        if not is_interactive and not is_content:
            continue
        if n_role == role and n_name == name:
            if match_count == nth:
                bid = node.get("backendDOMNodeId")
                if bid is None:
                    break
                entry["backend_node_id"] = bid
                model = cdp("DOM.getBoxModel", backendNodeId=bid)
                content = model.get("model", {}).get("content", [])
                if len(content) >= 8:
                    x = (content[0] + content[2] + content[4] + content[6]) / 4
                    y = (content[1] + content[3] + content[5] + content[7]) / 4
                    return x, y
                break
            match_count += 1
    raise RuntimeError(f"could not resolve ref for {role} {name!r}")


def click_ref(ref, **kwargs):
    """Click element by eN ref from last ax_snapshot(compact=True)."""
    x, y = _resolve_ref_center(ref)
    return click_at_xy(x, y, **kwargs)


# --- crawl state ---
class CrawlState:
    """In-memory dedup/accumulator for browser crawls. Opt-in, no persistence."""

    def __init__(self, key_field, marginal_window=5):
        self.key_field = key_field
        self._occurrences = {}  # key -> encounter count
        self._records = []
        self._dup_attempts = 0
        self._missing_key = 0
        self._blocked = []
        self._scope_totals = {}
        self._marginal = deque(maxlen=marginal_window)

    def add(self, record):
        """Add record if key_field value is new. Returns True if added."""
        key = record.get(self.key_field)
        if key is None:
            self._missing_key += 1
            return False
        if key in self._occurrences:
            self._occurrences[key] += 1
            self._dup_attempts += 1
            return False
        self._occurrences[key] = 1
        self._records.append(record)
        return True

    def record_blocked(self, url, reason=""):
        self._blocked.append({"url": url, "reason": reason})

    def record_scope_total(self, scope, expected):
        self._scope_totals[scope] = self._scope_totals.get(scope, 0) + expected

    def page_done(self, new_count):
        """Record new items found on this page (call after each page)."""
        self._marginal.append(new_count)

    def saturation_reached(self, k=3):
        """True when last k page-new-item counts are all 0."""
        if len(self._marginal) < k:
            return False
        return all(c == 0 for c in list(self._marginal)[-k:])

    def estimated_unseen(self):
        """Chao1 lower-bound estimate of unseen items from occurrence counts."""
        f1 = sum(1 for c in self._occurrences.values() if c == 1)
        f2 = sum(1 for c in self._occurrences.values() if c == 2)
        if f1 == 0:
            return 0
        if f2 == 0:
            return f1 * (f1 - 1) // 2
        return f1 * f1 // (2 * f2)

    def summary(self):
        return {
            "records": len(self._records),
            "deduped": self._dup_attempts,
            "missing_key": self._missing_key,
            "blocked": len(self._blocked),
            "scope_totals": dict(self._scope_totals),
            "saturated": self.saturation_reached(),
            "estimated_unseen": self.estimated_unseen(),
        }

    def receipt(self, source_context=None, safety=None):
        """Compact crawl evidence suitable for a redacted capability receipt."""
        safety_summary = safety.summary() if safety is not None else None
        return {
            "key_field": self.key_field,
            "source_context": dict(source_context or {}),
            "summary": self.summary(),
            "marginal": list(self._marginal),
            "blocked_sample": self._blocked[:5],
            "safety": safety_summary,
        }

    def save(self, path):
        """Serialize crawl state to JSON. Returns *path* for chaining."""
        data = {
            "key_field": self.key_field,
            "marginal_window": self._marginal.maxlen,
            "occurrences": self._occurrences,
            "records": self._records,
            "dup_attempts": self._dup_attempts,
            "missing_key": self._missing_key,
            "blocked": self._blocked,
            "scope_totals": self._scope_totals,
            "marginal": list(self._marginal),
        }
        Path(path).write_text(json.dumps(data, default=str))
        return path

    @staticmethod
    def load(path):
        """Deserialize crawl state from JSON. Returns a new CrawlState."""
        data = json.loads(Path(path).read_text())
        cs = CrawlState(data["key_field"], marginal_window=data.get("marginal_window", 5))
        cs._occurrences = data.get("occurrences", {})
        cs._records = data.get("records", [])
        cs._dup_attempts = data.get("dup_attempts", 0)
        cs._missing_key = data.get("missing_key", 0)
        cs._blocked = data.get("blocked", [])
        cs._scope_totals = data.get("scope_totals", {})
        cs._marginal = deque(data.get("marginal", []), maxlen=cs._marginal.maxlen)
        return cs


class SafetyGate:
    """Configurable safety limits for crawl sessions.

    Call ``gate.ok()`` before each request, ``gate.record(status)`` after.
    When limits are hit, ``ok()`` returns False (or raises RuntimeError if
    *raise_on_fail* was set).
    """

    def __init__(self, max_requests=None, max_seconds=None,
                 consecutive_block_threshold=None, backoff_on_429=True,
                 raise_on_fail=False):
        self._max_requests = max_requests
        self._max_seconds = max_seconds
        self._block_threshold = consecutive_block_threshold
        self._backoff_on_429 = backoff_on_429
        self._raise = raise_on_fail
        self._count = 0
        self._start = time.time()
        self._consecutive_blocks = 0
        self._count_429 = 0
        self._backoff_until = 0.0
        self._backoff_dur = 1.0

    def ok(self):
        """Return True if another request is within budget."""
        if self._max_requests is not None and self._count >= self._max_requests:
            return self._fail("max_requests")
        if self._max_seconds is not None and time.time() - self._start >= self._max_seconds:
            return self._fail("max_seconds")
        if self._block_threshold is not None and self._consecutive_blocks >= self._block_threshold:
            return self._fail("consecutive_blocks")
        if time.time() < self._backoff_until:
            return self._fail("backoff")
        self._count += 1
        return True

    def record(self, status_code, blocked=False):
        if blocked:
            self._consecutive_blocks += 1
        else:
            self._consecutive_blocks = 0
        if status_code == 429 and self._backoff_on_429:
            self._count_429 += 1
            self._backoff_until = time.time() + self._backoff_dur
            self._backoff_dur = min(self._backoff_dur * 2, 60.0)

    def summary(self):
        return {
            "requests": self._count,
            "elapsed_seconds": round(time.time() - self._start, 1),
            "consecutive_blocks": self._consecutive_blocks,
            "429_count": self._count_429,
            "limits_reached": self._limits_reached(),
            "backoff_until": self._backoff_until if self._backoff_until > time.time() else None,
        }

    def reset(self):
        self._count = 0
        self._start = time.time()
        self._consecutive_blocks = 0
        self._count_429 = 0
        self._backoff_until = 0.0
        self._backoff_dur = 1.0

    def _fail(self, reason):
        if self._raise:
            raise RuntimeError(f"SafetyGate limit: {reason}")
        return False

    def _limits_reached(self):
        hit = []
        if self._max_requests is not None and self._count >= self._max_requests:
            hit.append("max_requests")
        if self._max_seconds is not None and time.time() - self._start >= self._max_seconds:
            hit.append("max_seconds")
        if self._block_threshold is not None and self._consecutive_blocks >= self._block_threshold:
            hit.append("consecutive_blocks")
        return hit


def fill_rate_triage(records):
    """Compute fill-rate triage for extracted records.

    Returns dict mapping field_name -> {present, null, unobservable, omitted,
    total, fill_rate, status} with status one of OK/LOW/BROKEN/BLOCKED.
    """
    if not records:
        return {}
    all_keys = set()
    for r in records:
        all_keys.update(r.keys())
    triage = {}
    for field in sorted(all_keys):
        present = null = unobservable = omitted = 0
        for r in records:
            if field not in r:
                omitted += 1
            elif r[field] is None:
                null += 1
            elif r[field] == "__UNOBSERVABLE__":
                unobservable += 1
            else:
                present += 1
        n = len(records)
        checked = n - omitted
        fill = present / checked if checked > 0 else 0
        if unobservable > 0:
            status = "BLOCKED"
        elif checked > 0 and present == 0 and null == checked:
            status = "OK"
        elif fill >= 1.0:
            status = "OK"
        elif fill >= 0.5:
            status = "LOW"
        else:
            status = "BROKEN"
        triage[field] = {
            "present": present, "null": null,
            "unobservable": unobservable, "omitted": omitted,
            "total": n, "fill_rate": round(fill, 3), "status": status,
        }
    return triage


def field_triage(records):
    """Backward-compatible name for fill-rate triage in skill docs/tests."""
    return fill_rate_triage(records)


def capture_screenshot_trace(directory="/tmp/bh-trace", frames=3, interval=0.5, full=False):
    """Opt-in screenshot timeline. Writes artifacts only when called."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(frames):
        path = directory / f"frame-{i:03d}.png"
        paths.append(capture_screenshot(str(path), full=full))
        if i != frames - 1:
            time.sleep(interval)
    return paths

def discover_local_cdp_endpoints(ports=(9222, 3000, 5050), host="127.0.0.1", timeout=0.25):
    """Probe loopback DevTools HTTP endpoints. Does not scan public networks."""
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("local CDP discovery only supports loopback hosts")
    netloc_host = f"[{host}]" if ":" in host else host
    found = []
    for port in ports:
        base = f"http://{netloc_host}:{int(port)}"
        try:
            with urllib.request.urlopen(f"{base}/json/version", timeout=timeout) as r:
                data = json.loads(r.read().decode())
        except Exception:
            continue
        found.append({
            "http_base": base,
            "webSocketDebuggerUrl": data.get("webSocketDebuggerUrl"),
            "browser": data.get("Browser"),
            "protocol_version": data.get("Protocol-Version"),
        })
    return found

_BROWSER_UA = None


def _real_user_agent():
    """Lazily read the attached browser's User-Agent. Falls back to a realistic full string."""
    global _BROWSER_UA
    if _BROWSER_UA is not None:
        return _BROWSER_UA
    try:
        version = cdp("Browser.getVersion")
        ua = version.get("userAgent", "")
        if ua:
            _BROWSER_UA = ua
            return ua
    except Exception:
        pass
    _BROWSER_UA = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )
    return _BROWSER_UA


def http_get(url, headers=None, timeout=20.0):
    """Pure local HTTP -- no browser. Use for static pages / APIs. Wrap in ThreadPoolExecutor for bulk."""
    import gzip
    h = {"User-Agent": _real_user_agent(), "Accept-Encoding": "gzip"}
    if headers: h.update(headers)
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout) as r:
        data = r.read()
        ct = r.headers.get("Content-Type", "")
        if r.headers.get("Content-Encoding") == "gzip":
            try:
                data = gzip.decompress(data)
            except (OSError, EOFError):
                # Corrupt gzip — retry without Accept-Encoding: gzip
                with urllib.request.urlopen(urllib.request.Request(url, headers={**h, "Accept-Encoding": "identity"}), timeout=timeout) as r2:
                    data = r2.read()
                    ct = r2.headers.get("Content-Type", "")
        # Binary content — decode with replace so callers (detect_block_page, Response)
        # always get str, never bytes (bytes + str concatenation raises TypeError)
        if ct and not ct.startswith(("text/", "application/json", "application/javascript", "application/xml")):
            return data.decode("utf-8", errors="replace")
        charset = "utf-8"
        if "charset=" in ct:
            charset = ct.split("charset=")[1].split(";")[0].strip().strip('"')
        try:
            return data.decode(charset)
        except (UnicodeDecodeError, LookupError):
            return data.decode("utf-8", errors="replace")


def _detect_cloudflare_type(html):
    """Detect Cloudflare challenge type from page content. Returns type string or None."""
    for ctype in ("non-interactive", "managed", "interactive"):
        if f"cType: '{ctype}'" in html:
            return ctype
    if 'script[src*="challenges.cloudflare.com/turnstile"]' in html:
        return "embedded"
    return None


def detect_turnstile(timeout=5.0):
    """Check if a Cloudflare Turnstile challenge is present on the current page.

    Returns ``{"found": bool, "challenge_type": str|None, "iframe_target_id": str|None}``.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        for t in cdp("Target.getTargets").get("targetInfos", []):
            if t.get("type") == "iframe" and "challenges.cloudflare.com" in t.get("url", ""):
                return {"found": True, "challenge_type": "turnstile_iframe", "iframe_target_id": t["targetId"]}
        # Check for Turnstile script or widget in DOM
        found = js("""!!(
            document.querySelector('script[src*="challenges.cloudflare.com/turnstile"]') ||
            document.querySelector('.cf-turnstile') ||
            document.querySelector('#cf-turnstile') ||
            document.querySelector('#cf_turnstile')
        )""")
        if found:
            return {"found": True, "challenge_type": "turnstile_widget", "iframe_target_id": None}
        # Check page title for "Just a moment..." (CF challenge page)
        title = js("document.title")
        if title and "just a moment" in title.lower():
            return {"found": True, "challenge_type": "cf_challenge_page", "iframe_target_id": None}
        time.sleep(0.5)
    return {"found": False, "challenge_type": None, "iframe_target_id": None}


def solve_turnstile(timeout=30.0, poll=1.0, max_attempts=3):
    """Click the Cloudflare Turnstile checkbox and wait for challenge completion.

    Requires a visible browser (headful or headless with virtual display).
    Uses Scrapling's offset coordinates (+26-28/+25-27px from widget top-left)
    and humanized click timing. Retries recursively if the challenge persists.
    Returns ``{"solved": bool, "reason": str, "attempts": int}``.
    """
    import random

    for attempt in range(1, max_attempts + 1):
        detection = detect_turnstile(timeout=5.0)
        if not detection["found"]:
            return {"solved": False, "reason": "no_turnstile_found", "attempts": attempt}

        # Non-interactive challenges just need waiting
        html = js("document.documentElement.outerHTML") or ""
        challenge_type = _detect_cloudflare_type(html)

        if challenge_type == "non-interactive":
            deadline = time.time() + timeout
            while time.time() < deadline:
                title = js("document.title") or ""
                if "just a moment" not in title.lower():
                    return {"solved": True, "reason": "non_interactive_passed", "attempts": attempt}
                time.sleep(1.0)
            return {"solved": False, "reason": "timeout", "attempts": attempt}

        # Embedded Turnstile — widget is inside the page, no CF challenge page.
        # Wait for the hidden input to receive a token (indicates completion).
        if challenge_type == "embedded":
            deadline = time.time() + timeout
            while time.time() < deadline:
                token = js("""(() => {
                    const inp = document.querySelector('input[name="cf-turnstile-response"]');
                    if (inp && inp.value && inp.value.length > 10) return inp.value;
                    return null;
                })()""")
                if token:
                    return {"solved": True, "reason": "embedded_token_received", "attempts": attempt}
                # Some sites use a data-callback instead
                callback_done = js("""!!(
                    window.turnstile && window.turnstile.getResponse &&
                    window.turnstile.getResponse()
                )""")
                if callback_done:
                    return {"solved": True, "reason": "embedded_callback_fired", "attempts": attempt}
                time.sleep(1.0)
            return {"solved": False, "reason": "embedded_timeout", "attempts": attempt}

        # Find the Turnstile widget bounding box. Try iframe first, then CSS selectors.
        box = js("""(() => {
            // Method 1: CF iframe bounding box
            const iframe = document.querySelector('iframe[src*="challenges.cloudflare.com"]');
            if (iframe) {
                const r = iframe.getBoundingClientRect();
                if (r.width > 0 && r.height > 0) return {x: r.x, y: r.y, w: r.width, h: r.height};
            }
            // Method 2: Turnstile widget container selectors (Scrapling fallback)
            for (const sel of ['#cf-turnstile div', '#cf_turnstile div', '.turnstile>div>div',
                               '.main-content p+div>div>div']) {
                const el = document.querySelector(sel);
                if (el) {
                    const r = el.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0) return {x: r.x, y: r.y, w: r.width, h: r.height};
                }
            }
            return null;
        })()""")

        if not box:
            # No widget found — check if challenge already solved
            title = js("document.title") or ""
            if "just a moment" not in title.lower():
                return {"solved": True, "reason": "already_solved", "attempts": attempt}
            return {"solved": False, "reason": "widget_not_found", "attempts": attempt}

        # Scrapling's exact offset: checkbox is +26-28px right and +25-27px down from top-left
        x = box["x"] + random.randint(26, 28)
        y = box["y"] + random.randint(25, 27)

        # Humanized click: move to position first, then click with delay
        click_at_xy(x, y, humanize=True)

        # Wait for CF page to disappear
        wait(0.5)  # Brief pause for click to register
        deadline = time.time() + timeout
        while time.time() < deadline:
            title = js("document.title") or ""
            if "just a moment" not in title.lower():
                # Verify actual content appeared (not still a WAF shell)
                status = page_content_status()
                if int(status.get("textLength") or 0) >= 500:
                    if not status.get("block", {}).get("blocked"):
                        return {"solved": True, "reason": "content_appeared", "attempts": attempt}
            time.sleep(poll)

        # Challenge still present — retry if attempts remain
        if attempt >= max_attempts:
            return {"solved": False, "reason": "timeout_after_retries", "attempts": attempt}

    return {"solved": False, "reason": "max_attempts_exceeded", "attempts": max_attempts}


def block_resources(ad_domains=True, extra_domains=None, resource_types=None):
    """Block ad domains and/or resource types on the current page.

    Call after navigating. Domain blocking uses ``Network.setBlockedURLs`` and
    persists until navigation. Resource-type blocking uses ``Fetch.enable`` and
    flushes already-paused requests in a bounded loop — catches in-flight
    requests but not future ones. Returns the total number of blocking rules.
    """
    count = 0
    domains = set()
    if ad_domains:
        domains.update(_AD_DOMAINS)
    if extra_domains:
        domains.update(extra_domains)

    if domains:
        url_patterns = []
        for d in domains:
            url_patterns.append(f"*.{d}/*")
            url_patterns.append(f"*://{d}/*")
        cdp("Network.setBlockedURLs", urls=url_patterns)
        cdp("Network.enable")
        count += len(domains)

    if resource_types:
        cdp("Fetch.enable", patterns=[
            {"resourceType": rt, "requestStage": "Request"} for rt in resource_types
        ])
        for _ in range(20):
            paused = [e for e in drain_events()
                      if e.get("method") == "Fetch.requestPaused"]
            if not paused:
                break
            for ev in paused:
                rid = ev.get("params", {}).get("requestId")
                if rid:
                    try:
                        cdp("Fetch.failRequest", requestId=rid,
                            errorReason="BlockedByClient")
                    except Exception:
                        pass
            time.sleep(0.05)
        try:
            cdp("Fetch.disable")
        except Exception:
            pass
        count += len(resource_types)

    return count


# --- network capture ---

class NetworkCapture:
    """In-memory request/response log built from CDP Network events.

    Call ``start()`` before navigation, ``poll()`` after to drain buffered CDP
    events and populate the log.  Response body capture is opt-in via
    *capture_bodies=True* (calls ``Network.getResponseBody`` per response).

    **Do not** call ``smart_wait()`` or ``_wait_until_network_idle()`` while
    NetworkCapture is active — they call ``drain_events()`` (stealing events)
    and ``Network.disable`` (killing the event stream).
    """

    _SENSITIVE_HEADERS = {
        "authorization",
        "cookie",
        "set-cookie",
        "proxy-authorization",
        "x-api-key",
        "x-csrf-token",
        "x-xsrf-token",
    }

    def __init__(self, capture_bodies=False, max_entries=1000, max_body_chars=200000):
        self._capture_bodies = capture_bodies
        self._max = max_entries
        self._max_body_chars = max_body_chars
        self._active = False
        self.clear()

    def start(self):
        cdp("Network.enable")
        self.clear()
        self._active = True

    def stop(self):
        try:
            cdp("Network.disable")
        except Exception:
            pass
        self._active = False

    def poll(self):
        """Drain CDP events and process network events. Returns new entry count."""
        n = 0
        for ev in drain_events():
            m = ev.get("method", "")
            p = ev.get("params", {})
            rid = p.get("requestId")
            if not rid:
                continue
            if m == "Network.requestWillBeSent":
                redir = p.get("redirectResponse")
                if redir and rid in self._requests:
                    self._finalize(rid, redir.get("status"),
                                   redir.get("headers", {}),
                                   redir.get("mimeType", ""))
                self._requests[rid] = {
                    "url": p.get("request", {}).get("url", ""),
                    "method": p.get("request", {}).get("method", "GET"),
                    "headers": p.get("request", {}).get("headers", {}),
                    "resource_type": p.get("type", ""),
                }
                n += 1
            elif m == "Network.responseReceived":
                resp = p.get("response", {})
                self._responses[rid] = {
                    "status": resp.get("status", 0),
                    "headers": resp.get("headers", {}),
                    "content_type": resp.get("mimeType", ""),
                }
                if self._capture_bodies:
                    try:
                        body = cdp("Network.getResponseBody", requestId=rid)
                        raw_body = body.get("body", "")
                        self._responses[rid]["body"] = raw_body[:self._max_body_chars]
                        self._responses[rid]["body_truncated"] = len(raw_body) > self._max_body_chars
                    except Exception:
                        pass
                if rid in self._requests:
                    self._finalize(rid,
                                   resp.get("status", 0),
                                   resp.get("headers", {}),
                                   resp.get("mimeType", ""))
                    n += 1
            elif m == "Network.loadingFailed":
                if rid in self._requests:
                    self._requests[rid]["failed"] = True
        return n

    def endpoints(self, normalize_fn=None):
        """Deduplicated list of URLs seen.  Returns [{url, method, resource_type, status, content_type, count}]."""
        agg = {}
        for e in self._entries:
            key = normalize_fn(e["url"]) if normalize_fn else e["url"]
            if key not in agg:
                agg[key] = {"url": e["url"], "method": e["method"],
                            "resource_type": e.get("resource_type", ""),
                            "status": e.get("status", 0),
                            "content_type": e.get("content_type", ""),
                            "count": 0}
            agg[key]["count"] += 1
        return sorted(agg.values(), key=lambda x: -x["count"])

    def responses_for(self, pattern):
        """Full request/response pairs where URL matches *pattern* regex."""
        return [e for e in self._entries if re.search(pattern, e["url"])]

    def redacted_entries(self):
        """Captured entries with sensitive headers removed for receipts/logs."""
        return [self._redact_entry(e) for e in self._entries]

    def redacted_responses_for(self, pattern):
        """Redacted request/response pairs where URL matches *pattern* regex."""
        return [self._redact_entry(e) for e in self.responses_for(pattern)]

    def summary(self):
        by_rt, by_status = {}, {}
        for e in self._entries:
            rt = e.get("resource_type", "?")
            by_rt[rt] = by_rt.get(rt, 0) + 1
            s = e.get("status", 0)
            by_status[s] = by_status.get(s, 0) + 1
        return {
            "total_requests": len(self._requests) + len(self._entries),
            "total_responses": len(self._entries),
            "by_resource_type": by_rt,
            "by_status": by_status,
            "pending_requests": len(self._requests),
        }

    def clear(self):
        self._requests = {}
        self._responses = {}
        self._entries = deque(maxlen=self._max)

    def _finalize(self, rid, status, resp_headers, content_type):
        req = self._requests.pop(rid, None)
        if not req:
            return
        entry = {**req, "status": status, "response_headers": resp_headers,
                 "content_type": content_type}
        resp = self._responses.pop(rid, {})
        if "body" in resp:
            entry["body"] = resp["body"]
            entry["body_truncated"] = resp.get("body_truncated", False)
        self._entries.append(entry)

    @classmethod
    def _redact_headers(cls, headers):
        redacted = {}
        for key, value in (headers or {}).items():
            if str(key).lower() in cls._SENSITIVE_HEADERS:
                redacted[key] = "REDACTED"
            else:
                redacted[key] = value
        return redacted

    @classmethod
    def _redact_entry(cls, entry):
        safe = dict(entry)
        safe["headers"] = cls._redact_headers(safe.get("headers"))
        safe["response_headers"] = cls._redact_headers(safe.get("response_headers"))
        return safe


_URL_NUM = re.compile(r"^\d{2,}$")
_URL_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
_URL_HEX = re.compile(r"^[0-9a-f]{16,}$", re.I)
_URL_SLUG = re.compile(r"^(.*[-_])\d{2,}$")


def url_cluster(urls):
    """Normalize URL path segments and group by pattern.

    Numbers → ``{id}``, UUIDs → ``{uuid}``, hex hashes → ``{hash}``.
    Returns ``[{pattern, urls, count}]`` sorted by count descending.
    """

    def _norm(url):
        p = urlparse(url)
        segs = []
        for s in p.path.split("/"):
            if _URL_NUM.match(s):
                s = "{id}"
            elif _URL_UUID.match(s):
                s = "{uuid}"
            elif _URL_HEX.match(s):
                s = "{hash}"
            else:
                m = _URL_SLUG.match(s)
                if m:
                    s = m.group(1) + "{id}"
            segs.append(s)
        return p._replace(path="/".join(segs)).geturl()

    groups = {}
    for u in urls:
        key = _norm(u)
        groups.setdefault(key, []).append(u)
    return sorted(
        [{"pattern": k, "urls": v, "count": len(v)} for k, v in groups.items()],
        key=lambda x: -x["count"],
    )


_API_PATTERNS = [
    (re.compile(r'''fetch\(\s*["'`]([^"'`]+)["'`]'''), None, "fetch"),
    (re.compile(r'''axios\.\w+\(\s*["'`]([^"'`]+)["'`]'''), None, "axios"),
    (re.compile(r'''\.open\(\s*["']\w+["']\s*,\s*["'`]([^"'`]+)["'`]'''), None, "xhr"),
    (re.compile(r'''["'`](/api/[^"'`]+)["'`]'''), None, "api_path"),
]


def discover_api_endpoints(url, timeout=20.0):
    """Fetch page HTML, extract API URL patterns from JS assets.

    Returns ``{endpoints: [{url, source}], script_count, errors}``.
    """
    from concurrent.futures import ThreadPoolExecutor

    errors = []
    html = ""
    try:
        html = http_get(url, timeout=timeout)
    except Exception:
        try:
            r = http_get_browser_session_response(url, timeout=timeout)
            html = r.get("text", "")
        except Exception as exc:
            errors.append(f"fetch failed: {exc}")
            return {"endpoints": [], "script_count": 0, "errors": errors}

    src_urls = re.findall(r'<script[^>]*src=["\']([^"\']+)["\']', html, re.I)
    src_urls = [urljoin(url, s) for s in src_urls][:20]
    inline = re.findall(r'<script[^>]*>(.*?)</script>', html, re.I | re.DOTALL)

    js_sources = list(inline)
    fetched = 0

    def _fetch_js(js_url):
        try:
            return http_get(js_url, timeout=timeout)
        except Exception:
            return ""

    with ThreadPoolExecutor(max_workers=6) as pool:
        for text in pool.map(_fetch_js, src_urls):
            if text:
                js_sources.append(text)
                fetched += 1
    seen = set()
    endpoints = []
    for src in js_sources:
        for regex, group, source in _API_PATTERNS:
            for m in regex.finditer(src):
                raw = m.group(group) if group else m.group(1)
                if not raw or raw.startswith(("${", "javascript:", "data:")) or "${" in raw:
                    continue
                resolved = urljoin(url, raw)
                norm = resolved.split("?")[0]
                if norm in seen:
                    continue
                seen.add(norm)
                endpoints.append({"url": resolved, "source": source})

    return {
        "endpoints": sorted(endpoints, key=lambda e: e["url"]),
        "script_count": fetched + len(inline),
        "errors": errors,
    }


def replay_endpoints(capture, use_session=False, timeout=20.0):
    """Re-issue captured GET requests as plain HTTP and compare responses.

    Returns ``{results: [{...}], summary: {total, matched, mismatched, errors}}``.
    """
    results = []
    for ep in capture.endpoints():
        url, method = ep["url"], ep.get("method", "GET")
        if method.upper() != "GET":
            results.append({"url": url, "skipped": True, "reason": "non-GET"})
            continue
        try:
            if use_session:
                resp = http_get_browser_session_response(url, timeout=timeout)
                replay_status, replay_ct = resp.get("status", 0), resp.get("headers", {}).get("content-type", "")
            else:
                req = urllib.request.Request(url, headers={"User-Agent": _real_user_agent()})
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    replay_status, replay_ct = r.status, r.headers.get("Content-Type", "")
            orig_status = ep.get("status", 0)
            orig_ct = ep.get("content_type", "")
            ct_match = (replay_ct.split(";")[0].strip().lower()
                        == orig_ct.split(";")[0].strip().lower())
            results.append({
                "url": url,
                "original_status": orig_status,
                "replay_status": replay_status,
                "status_match": orig_status == replay_status,
                "content_type_match": ct_match,
            })
        except urllib.error.HTTPError as e:
            results.append({
                "url": url,
                "original_status": ep.get("status", 0),
                "replay_status": e.code,
                "status_match": False,
            })
        except Exception as exc:
            results.append({"url": url, "error": str(exc)})
        time.sleep(0.1)

    replayed = [r for r in results if not r.get("skipped")]
    matched = sum(1 for r in replayed if r.get("status_match"))
    errors = sum(1 for r in replayed if "error" in r)
    return {
        "results": results,
        "summary": {"total": len(results), "matched": matched,
                    "mismatched": len(replayed) - matched - errors, "errors": errors},
    }


_AD_DOMAINS = (
    "ad.doubleclick.net", "ads.google.com", "adservice.google.com",
    "adservice.google.dk", "pagead2.googlesyndication.com",
    "ads.pubmatic.com", "ad.360yield.com", "ad.turn.com",
    "adadvisor.net", "adnxs.com", "adsrvr.org", "advertising.com",
    "ads.yahoo.com", "adcolony.com", "adform.net", "adition.com",
    "adk2.com", "adn.com", "adocean.pl", "adroll.com", "adscale.de",
    "adsdk.yandex.ru", "adsymptotic.com", "adtech.de", "adtechus.com",
    "adtng.com", "adux.com", "advombat.ru", "adxpansion.com",
    "adzerk.net", "amazon-adsystem.com", "analytics.google.com",
    "assets.bounceexchange.com", "bat.bing.com", "bid.g.doubleclick.net",
    "bing.com/th?", "braze.com", "bounceexchange.com", "branch.io",
    "btloader.com", "casalemedia.com", "cdn.mxpnl.com", "chartbeat.net",
    "clicks.hurra.com", "cloudflare.com/cdn-cgi/scripts/", "criteo.com",
    "criteo.net", "cs.ecn.atomicmpc.com.au", "doubleclick.net",
    "e-merchant.com", "e2.enemygem.com", "eyeota.net", "facebook.com/tr",
    "facebook.net/signals",
    "google-analytics.com", "google.com/pagead", "googleadservices.com",
    "googlesyndication.com", "googletagmanager.com",
    "hotjar.com", "impact-ad.jp", "js.driftt.com", "liadm.com",
    "linkedin.com/li/", "lixbaseline.com", "log.outbrain.com",
    "metrics.brightcove.com", "mixpanel.com", "moatads.com",
    "mxpnl.com", "netdice.hurra.com", "newegg.com/html", "newrelic.com",
    "nr-data.net", "optimizely.com", "outbrain.com", "owneriq.net",
    "pagead.googlesyndication.com", "panels.tv", "pixel.facebook.com",
    "pixel.quantserve.com", "pixel.wp.com", "pubmatic.com",
    "quantserve.com", "rfihub.com", "rubiconproject.com",
    "scorecardresearch.com", "segment.io", "segment.com", "semasio.net",
    "serving-sys.com", "sharethis.com", "simplicitymarketingltd.ck.io",
    "snap.licdn.com", "ssl.google-analytics.com", "stats.g.doubleclick.net",
    "taboola.com", "tapad.com", "tapstream.com", "tdn.daftcode.com",
    "theadex.com", "thetradedesk.com", "track.hubspot.com",
    "tracker.affirm.com", "trc.taboola.com", "tremorhub.com",
    "trustarc.com", "turn.com", "twitter.com/i/", "urbanairship.com",
    "visualrevenue.com", "vk.com/rtrg", "world.taobao.com",
    "x.bidswitch.net", "yandex.ru/clck", "yandex.ru/cycounter",
    "zeotap.com",
)


def fetch(url, source="auto", headers=None, timeout=20.0, min_text=500):
    """Fetch URL and return a ``Response`` with CSS/XPath query support.

    *source* selects the fetch strategy:

    - ``"http"``: plain HTTP via ``http_get()`` — fastest, no browser state.
    - ``"session"``: HTTP with browser cookies via ``http_get_browser_session_response()``.
    - ``"browser"``: real browser navigation via ``new_tab()`` + ``wait_for_content()``.
    - ``"auto"`` (default): tries HTTP, then session, then browser (with Turnstile fallback).

    The returned Response may include a ``turnstile_solved`` key set to True when
    Cloudflare Turnstile was detected and solved during the browser fallback.
    """
    from response import Response

    def _readiness_status_code(status):
        if status.get("ok"):
            return 200
        block = status.get("block") or {}
        if block.get("blocked"):
            return 403
        if status.get("reason") == "timeout":
            return 504
        return 502

    if source == "http":
        try:
            text = http_get(url, headers=headers, timeout=timeout)
            block = detect_block_page(html=text, text=text, url=url)
            return Response(
                html=text, text=text, url=url, status=200, source="http",
                reason="blocked" if block.get("blocked") else "content",
                block=block,
            )
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            block = detect_block_page(html=body, text=body, url=url)
            return Response(
                html=body, text=body, url=url, status=e.code, source="http",
                reason="blocked" if block.get("blocked") else "http_error",
                block=block,
            )

    if source == "session":
        result = http_get_browser_session_response(url, headers=headers, timeout=timeout)
        block = result.get("block") or detect_block_page(
            html=result.get("text", ""),
            text=result.get("text", ""),
            url=result.get("url", url),
        )
        reason = "blocked" if block.get("blocked") else ("content" if result.get("ok") else "http_error")
        return Response(
            html=result.get("text", ""), text=result.get("text", ""),
            url=result.get("url", url), status=result.get("status", 0),
            source="session", headers=result.get("headers", {}),
            reason=reason, block=block,
        )

    if source == "browser":
        tid = None
        try:
            tid = new_tab(url)
            wait_for_load(timeout=timeout)
            status = wait_for_content(min_text=min_text, timeout=timeout)
            html = js("document.documentElement.outerHTML") or ""
            block = status.get("block") or {}
            if status.get("ok"):
                return Response(
                    html=html, text=status.get("text", ""),
                    url=status.get("url", url), status=200,
                    source="browser", reason=status.get("reason"),
                    block=status.get("block"),
                )
            return Response(
                html=html, text=status.get("text", ""),
                url=status.get("url", url), status=_readiness_status_code(status),
                source="browser", reason=status.get("reason"), block=block,
            )
        finally:
            if tid:
                try: close_tab(tid)
                except Exception: pass
    try:
        text = http_get(url, headers=headers, timeout=timeout)
        block = detect_block_page(html=text, text=text, url=url)
        if not block.get("blocked") and len(text.strip()) >= min_text:
            return Response(html=text, text=text, url=url, status=200, source="http")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        block = detect_block_page(html=body, text=body, url=url)
        if block.get("blocked") or len(body.strip()) < min_text:
            pass  # fall through to session/browser
        else:
            return Response(html=body, text=body, url=url, status=e.code, source="http")
    except (urllib.error.URLError, OSError, ConnectionError, RuntimeError):
        pass

    try:
        result = http_get_browser_session_response(url, headers=headers, timeout=timeout)
        block = detect_block_page(html=result.get("text", ""), text=result.get("text", ""), url=url)
        if result.get("ok") and not block.get("blocked") and len((result.get("text") or "").strip()) >= min_text:
            return Response(
                html=result.get("text", ""), text=result.get("text", ""),
                url=result.get("url", url), status=result.get("status", 0),
                source="session", headers=result.get("headers", {}),
            )
    except (urllib.error.URLError, OSError, ConnectionError, RuntimeError):
        pass
    tid = None
    try:
        tid = new_tab(url)
        wait_for_load(timeout=timeout)
        status = wait_for_content(min_text=min_text, timeout=timeout)
        html = js("document.documentElement.outerHTML") or ""
        if status.get("ok"):
            return Response(
                html=html, text=status.get("text", ""),
                url=status.get("url", url), status=200,
                source="browser", reason=status.get("reason"),
                block=status.get("block"),
            )
        # Blocked — try Turnstile if Cloudflare challenge detected
        if not status.get("ok"):
            detection = detect_turnstile(timeout=3.0)
            if detection["found"]:
                result = solve_turnstile(timeout=timeout)
                if result.get("solved"):
                    status2 = wait_for_content(min_text=min_text, timeout=timeout)
                    html = js("document.documentElement.outerHTML") or html
                    return Response(
                        html=html, text=status2.get("text", ""),
                        url=status2.get("url", url),
                        status=_readiness_status_code(status2),
                        source="browser",
                        turnstile_solved=True,
                        reason=status2.get("reason"),
                        block=status2.get("block"),
                    )
        block = status.get("block") or {}
        return Response(
            html=html, text=status.get("text", ""),
            url=status.get("url", url), status=_readiness_status_code(status),
            source="browser", reason=status.get("reason"), block=block,
        )
    finally:
        if tid:
            try: close_tab(tid)
            except Exception: pass


def fetch_with_browser_session(url, headers=None, timeout=20.0, min_text=500):
    """Fetch with browser-established cookies and return a Response object."""
    return fetch(url, source="session", headers=headers, timeout=timeout, min_text=min_text)


def _close_sock():
    global _sock
    if _sock is not None:
        try:
            _sock.close()
        except OSError:
            pass
        _sock = None


atexit.register(_close_sock)
