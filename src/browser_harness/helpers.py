"""Browser control via CDP. Read, edit, extend -- this file is yours."""
import atexit, base64, functools, json, math, os, re, socket, sys, time, urllib.error, urllib.request
import hashlib
from collections import deque
from importlib.resources import files
from pathlib import Path
from urllib.parse import urljoin, urlparse
from . import _ipc as ipc
from . import login_session


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
ipc._check(NAME)
INTERNAL = ("chrome://", "chrome-untrusted://", "devtools://", "chrome-extension://", "about:")

BLOCKER_JS = """(()=>{
if(window.__bh_blockers_installed__)return;window.__bh_blockers_installed__=true;
window.__bh_blockers__=window.__bh_blockers__||[];
const log=k=>{const a=window.__bh_blockers__;a.push({kind:k,t:Date.now()});if(a.length>200)a.splice(0,a.length-200);};
const w=(o,n,k)=>{if(!o)return;const f=o[n];if(typeof f!=='function')return;o[n]=function(){log(k);return f.apply(this,arguments);};};
try{w(navigator.geolocation,'getCurrentPosition','geolocation');}catch(_){}
try{w(navigator.geolocation,'watchPosition','geolocation');}catch(_){}
try{w(Notification,'requestPermission','notifications');}catch(_){}
try{w(navigator.mediaDevices,'getUserMedia','media');}catch(_){}
try{w(navigator.mediaDevices,'getDisplayMedia','display');}catch(_){}
try{w(navigator.clipboard,'read','clipboard-read');}catch(_){}
try{w(navigator.clipboard,'readText','clipboard-read');}catch(_){}
try{w(navigator.bluetooth,'requestDevice','bluetooth');}catch(_){}
try{w(navigator.usb,'requestDevice','usb');}catch(_){}
try{w(navigator.serial,'requestPort','serial');}catch(_){}
try{w(navigator.hid,'requestDevice','hid');}catch(_){}
try{w(window,'showOpenFilePicker','file-picker');}catch(_){}
try{w(window,'showSaveFilePicker','file-picker');}catch(_){}
try{w(window,'showDirectoryPicker','file-picker');}catch(_){}
try{w(window,'print','print');}catch(_){}
try{w(document,'requestStorageAccess','storage-access');}catch(_){}
addEventListener('click',e=>{const t=e.target;if(t&&t.tagName==='INPUT'&&t.type==='file')log('file-input');},true);
})();"""

_sock = None
_sock_token = None


def _asset_dir(local_name, package_name):
    local = Path(__file__).parent / local_name
    if local.is_dir():
        return local
    try:
        return Path(str(files(package_name)))
    except Exception:
        return local


def _reconnect():
    global _sock, _sock_token, _BROWSER_UA
    if _sock is not None:
        try:
            _sock.close()
        except OSError:
            pass
    try:
        _sock, _sock_token = ipc.connect(NAME, timeout=30)
    except Exception:
        try:
            _sock.close()
        except Exception:
            pass
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


# CDP methods whose replay after a lost response is safe enough to auto-retry.
_IDEMPOTENT_CDP = frozenset((
    "Browser.getVersion", "DOM.getDocument", "DOM.getOuterHTML",
    "Network.getCookies", "Page.getLayoutMetrics", "Target.getTargets",
))


def _send(req, timeout=30):
    global _sock
    if _sock is None:
        _reconnect()
    token = _sock_token
    payload_req = {**req, "token": token} if token else req
    payload = (json.dumps(payload_req) + "\n").encode()
    method = req.get("method", "")
    try:
        _sock.sendall(payload)
        data = _recv(timeout)
    except (OSError, ConnectionResetError) as e:
        if method not in _IDEMPOTENT_CDP:
            raise RuntimeError(f"socket error during {method}: {e}") from e
        _reconnect()
        token = _sock_token
        payload_req = {**req, "token": token} if token else req
        payload = (json.dumps(payload_req) + "\n").encode()
        try:
            _sock.sendall(payload)
            data = _recv(timeout)
        except (OSError, RuntimeError, ValueError):
            try: _sock.close()
            except OSError: pass
            _sock = None
            raise
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
    if not isinstance(r, dict):
        try: _sock.close()
        except OSError: pass
        _sock = None
        raise RuntimeError(f"invalid CDP response shape: expected object, got {type(r).__name__}")
    if "error" in r:
        err = r["error"]
        msg = err["message"] if isinstance(err, dict) and "message" in err else err
        raise RuntimeError(msg)
    return r


def _require_key(mapping, key, context):
    if not isinstance(mapping, dict) or key not in mapping:
        raise RuntimeError(f"{context} missing {key!r}: {mapping!r}")
    return mapping[key]


def _target_infos(response, context="Target.getTargets response"):
    targets = _require_key(response, "targetInfos", context)
    if not isinstance(targets, list):
        raise RuntimeError(f"{context} field 'targetInfos' must be a list: {response!r}")
    return [target for target in targets if isinstance(target, dict)]


def _dict_rows(value):
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _dict_value(value):
    return value if isinstance(value, dict) else {}


def _text_value(value):
    return "" if value is None else str(value)


def _string_field(value, default=""):
    return value if isinstance(value, str) else default


def _int_count(value):
    if isinstance(value, bool):
        return 0
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _status_code(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else 0


def _env_int(name, default):
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


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
    import os as _os
    if _os.environ.get("BH_AGENT_WORKER") == "1":
        raise RuntimeError("cdp() not available in agent worker; use authority-routed tools")
    return _send({"method": method, "params": params, "session_id": session_id}, timeout=timeout).get("result", {})


def drain_events():  return _dict_rows(_send({"meta": "drain_events"}).get("events", []))
def endpoint_info(): return _send({"meta": "endpoint_info"}).get("endpoint_info", {})


def launch_browser(**kwargs):
    """Launch Chrome with CDP and connect the daemon. Returns {pid, port, ws_url}."""
    from .admin import launch_browser as _launch
    return _launch(**kwargs)


def close_browser(launch_info):
    """Close a browser launched by launch_browser()."""
    from .admin import close_browser as _close
    return _close(launch_info)


# --- navigation / page ---
def _wait_until_load(strategy, timeout=15.0, *, pre_drain=True):
    """Wait for a specific load event strategy. Returns {ok, reason}.

    pre_drain=True drains stale events before polling (safe default for
    standalone callers like wait_for_load).  Callers that already drained
    before triggering navigation (e.g. goto_url) pass pre_drain=False to
    avoid discarding the load event that just fired.
    """
    if strategy == "load":
        target_event = "Page.loadEventFired"
    elif strategy == "domcontentloaded":
        target_event = "Page.domContentLoadedEventFired"
    elif strategy == "networkidle":
        return _wait_until_network_idle(timeout)
    else:
        raise ValueError(f"unknown wait_until strategy: {strategy!r}")
    cdp("Page.enable")
    if pre_drain:
        drain_events()
    deadline = time.time() + timeout
    while time.time() < deadline:
        for ev in drain_events():
            if not isinstance(ev, dict):
                continue
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
                if not isinstance(ev, dict):
                    continue
                m = ev.get("method", "")
                params = ev.get("params") if isinstance(ev.get("params"), dict) else {}
                rid = params.get("requestId")
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
            if _dict_value(status.get("block")).get("blocked"):
                waf_deadline = time.time() + min(waf_timeout, remaining())
                while time.time() < waf_deadline:
                    time.sleep(0.5)
                    status = page_content_status()
                    if not _dict_value(status.get("block")).get("blocked"):
                        return {"phase": "waf_cleared", "ok": True, "reason": "waf_cleared",
                                "elapsed_ms": int((time.time() - start) * 1000)}
                return {"phase": "waf_blocked", "ok": False, "reason": "blocked",
                        "elapsed_ms": int((time.time() - start) * 1000)}
        except Exception:
            pass

    # Phase 3: load event
    if remaining() > 0:
        load_result = _wait_until_load("load", timeout=min(5.0, remaining()), pre_drain=False)
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
    d = _domain_skill_dir(url)
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

    wait_result = _wait_until_load(wait_until, pre_drain=False)
    info = page_info()
    return {
        "ok": wait_result.get("ok", False),
        "reason": wait_result.get("reason"),
        "url": info.get("url", url),
        "title": info.get("title", ""),
        "frameId": r.get("frameId"),
        "domain_skills": ds,
    }

def _domain_skill_dir(url):
    root = _asset_dir("domain-skills", "browser_harness_domain_skills")
    hostname = (urlparse(url).hostname or "").lower().removeprefix("www.")
    if not hostname:
        return root / ""
    aliases = {
        "realestate.com.au": "realestate-com-au",
        "www.realestate.com.au": "realestate-com-au",
    }
    candidates = []
    if hostname in aliases:
        candidates.append(aliases[hostname])
    candidates.append(hostname.replace(".", "-"))
    candidates.append(hostname.split(".")[0])
    for name in candidates:
        d = root / name
        if d.is_dir():
            return d
    return root / candidates[0]


@_recovered
def page_info():
    """{url, title, w, h, sx, sy, pw, ph} - viewport + scroll + page size.

    If a native dialog (alert/confirm/prompt/beforeunload) is open, returns
    {dialog: {type, message, ...}} instead - the page's JS thread is frozen
    until the dialog is handled (see interaction-skills/dialogs.md)."""
    dialog = _send({"meta": "pending_dialog"}).get("dialog")
    if dialog:
        return {"dialog": dialog}
    target_resp = cdp("Target.getTargetInfo")
    _raise_if_cdp_exception(target_resp, "page_info")
    target = _dict_value(target_resp.get("targetInfo"))
    metrics = cdp("Page.getLayoutMetrics")
    _raise_if_cdp_exception(metrics, "page_info")
    viewport = _dict_value(metrics.get("cssLayoutViewport")) or _dict_value(metrics.get("layoutViewport"))
    content = _dict_value(metrics.get("cssContentSize")) or _dict_value(metrics.get("contentSize"))
    return {
        "url": target.get("url", ""),
        "title": target.get("title", ""),
        "w": _int_count(viewport.get("clientWidth")),
        "h": _int_count(viewport.get("clientHeight")),
        "sx": _int_count(viewport.get("pageX")),
        "sy": _int_count(viewport.get("pageY")),
        "pw": _int_count(content.get("width")),
        "ph": _int_count(content.get("height")),
    }


def _raise_if_cdp_exception(resp, ctx):
    if not isinstance(resp, dict) or "exceptionDetails" not in resp:
        return
    result = _dict_value(resp.get("result"))
    details = _dict_value(resp.get("exceptionDetails"))
    desc = result.get("description") or details.get("text") or "JS exception"
    raise RuntimeError(f"{ctx}: {desc}")

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
    html = str(html or "")
    text = str(text or "")
    url = str(url or "")
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
        if (len(akamai_hits) >= 2 and (not stripped_text or html_len < 10000)) or (_has("reference #") and html_len < 10000):
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
    state = _dict_value(js(expr))
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
        try:
            last = page_content_status()
        except RuntimeError as e:
            # Tab detached or JS exception — stop polling immediately
            return {"ok": False, "reason": "js_error", "error": str(e)}
        if _dict_value(last.get("block")).get("blocked"):
            return {**last, "ok": False, "reason": "blocked"}
        if _int_count(last.get("textLength")) >= min_text:
            return {**last, "ok": True, "reason": "content"}
        time.sleep(poll)
    return {**last, "ok": False, "reason": "timeout"}

def _cookie_matches_url(cookie, url):
    return login_session.cookie_matches_url(cookie, url)

def browser_cookies(urls):
    """Return redacted cookie manifest for `urls`.

    Returns cookie names, domains, and flags — never raw values.
    For internal transport use, login_session.browser_cookies provides
    the full dict including values.
    """
    raw = login_session.browser_cookies(cdp, urls)
    return [
        {
            "name": c.get("name", ""),
            "domain": c.get("domain", ""),
            "path": c.get("path", "/"),
            "secure": c.get("secure", False),
            "httpOnly": c.get("httpOnly", False),
            "sameSite": c.get("sameSite", ""),
            "expires": c.get("expires", -1),
        }
        for c in raw
        if isinstance(c, dict)
    ]

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
        wait_for_load(timeout=timeout, pre_drain=False)
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
    pattern = re.compile(
        rf"(?:\b(?:window|globalThis|self)\s*\.\s*)?{re.escape(name)}\s*=\s*",
        re.MULTILINE,
    )
    match = pattern.search(html)
    if not match:
        return None
    obj_start = html.find("{", match.end())
    arr_start = html.find("[", match.end())
    starts = [pos for pos in (obj_start, arr_start) if pos >= 0]
    if not starts:
        return None
    i = min(starts)
    opener = html[i]
    closer = "}" if opener == "{" else "]"
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
        elif ch == opener:
            depth += 1
        elif ch == closer:
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
    viewport_width = _int_count(info.get("w"))
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


def fill_input(selector, text, clear_first=True, timeout=0.0):
    """Fill a framework-managed input (React controlled, Vue v-model, Ember tracked).

    type_text() uses Input.insertText which bypasses framework event listeners
    and leaves submit buttons disabled. This focuses the element, optionally
    clears it via select-all+Backspace, types via real key events, then fires
    synthetic input+change events so the framework sees the update.

    Pass ``timeout > 0`` to wait for late-rendered elements (route changes,
    data fetches) before typing. Raises RuntimeError if not found.
    """
    if timeout > 0:
        if not wait_for_element(selector, timeout=timeout):
            raise RuntimeError(f"fill_input: element not found: {selector!r}")
    focused = js(
        f"(()=>{{const e=document.querySelector({json.dumps(selector)});"
        f"if(!e)return false;e.focus();return true;}})()"
    )
    if not focused:
        raise RuntimeError(f"fill_input: element not found: {selector!r}")
    if clear_first:
        # Dispatch select-all directly. press_key would emit a `char` event
        # for "a", and with Cmd/Ctrl held Chrome treats that as a printable
        # letter instead of a shortcut, leaving the field uncleared.
        mods = 4 if sys.platform == "darwin" else 2  # Cmd on macOS, Ctrl elsewhere
        select_all = {"key": "a", "code": "KeyA", "modifiers": mods,
                      "windowsVirtualKeyCode": 65, "nativeVirtualKeyCode": 65}
        cdp("Input.dispatchKeyEvent", type="rawKeyDown", **select_all)
        cdp("Input.dispatchKeyEvent", type="keyUp", **select_all)
        press_key("Backspace")
    for ch in text:
        press_key(ch)
    js(
        f"(()=>{{const e=document.querySelector({json.dumps(selector)});"
        f"if(!e)return;"
        f"e.dispatchEvent(new Event('input',{{bubbles:true}}));"
        f"e.dispatchEvent(new Event('change',{{bubbles:true}}));}})();"
    )


def wait_for_element(selector, timeout=10.0, visible=False):
    """Poll until ``document.querySelector(selector)`` exists, or timeout.

    wait_for_load() returns 'complete' before SPAs finish rendering. Use this
    after route changes, data fetches, or any async render path. With
    ``visible=True``, also requires the element to be non-hidden and in-layout
    (uses checkVisibility with a getComputedStyle fallback for older Chrome —
    NOT offsetParent, which fails for ``position: fixed`` elements).
    """
    if visible:
        check = (
            f"(()=>{{const e=document.querySelector({json.dumps(selector)});"
            f"if(!e)return false;"
            f"if(typeof e.checkVisibility==='function')"
            f"return e.checkVisibility({{checkOpacity:true,checkVisibilityCSS:true}});"
            f"const s=getComputedStyle(e);"
            f"return s.display!=='none'&&s.visibility!=='hidden'&&s.opacity!=='0'}})()"
        )
    else:
        check = f"!!document.querySelector({json.dumps(selector)})"
    deadline = time.time() + timeout
    while time.time() < deadline:
        if js(check): return True
        time.sleep(0.3)
    return False


def wait_for_network_idle(timeout=10.0, idle_ms=500):
    """Wait until inflight requests finish and Network.* events go quiet for ``idle_ms``.

    Useful after form submits, SPA route transitions, and any action triggering
    XHR/fetch without a visible DOM change. Builds on drain_events() — no
    daemon changes. Returns True if idle window reached, False on timeout.

    Events are filtered to the active session — a previously-attached
    background tab keeps emitting Network events into the daemon's global
    buffer; without this filter they would poison the idle check on the
    current tab.
    """
    deadline = time.time() + timeout
    last_activity = time.time()
    inflight = set()
    active_session = _send({"meta": "session"}).get("session_id")
    while time.time() < deadline:
        for e in drain_events():
            if not isinstance(e, dict):
                continue
            if e.get("session_id") != active_session:
                continue
            method = e.get("method", "")
            params = e.get("params") if isinstance(e.get("params"), dict) else {}
            if method == "Network.requestWillBeSent":
                inflight.add(params.get("requestId"))
                last_activity = time.time()
            elif method in ("Network.loadingFinished", "Network.loadingFailed"):
                inflight.discard(params.get("requestId"))
                last_activity = time.time()
            elif method.startswith("Network."):
                last_activity = time.time()
        if not inflight and (time.time() - last_activity) * 1000 >= idle_ms:
            return True
        time.sleep(0.1)
    return False


# --- visual ---
@_recovered
def capture_screenshot(path="/tmp/shot.png", full=False, max_dim=None):
    """Save a PNG of the current viewport (or full page if full=True).

    Set ``max_dim`` (e.g. 1800) to downsize the image so its longer side
    fits — useful on 2× HiDPI displays where the raw screenshot exceeds
    the per-side pixel limit some image-aware LLMs enforce."""
    r = cdp("Page.captureScreenshot", format="png", captureBeyondViewport=full)
    data = base64.b64decode(_require_key(r, "data", "Page.captureScreenshot response"))
    with open(path, "wb") as f:
        f.write(data)
    if max_dim:
        from PIL import Image
        img = Image.open(path)
        if max(img.size) > max_dim:
            img.thumbnail((max_dim, max_dim))
            img.save(path)
    return path


# --- tabs ---
def list_tabs(include_chrome=True):
    out = []
    for t in _target_infos(cdp("Target.getTargets")):
        if t.get("type") != "page": continue
        target_id = t.get("targetId")
        if not target_id: continue
        url = _text_value(t.get("url"))
        if not include_chrome and url.startswith(INTERNAL): continue
        out.append({"targetId": target_id, "title": _text_value(t.get("title")), "url": url})
    return out

def current_tab():
    t = _dict_value(cdp("Target.getTargetInfo").get("targetInfo"))
    return {"targetId": t.get("targetId"), "url": _text_value(t.get("url")), "title": _text_value(t.get("title"))}

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

_MAX_TABS = _env_int("BH_MAX_TABS", 5)


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
    for t in _target_infos(cdp("Target.getTargets")):
        if t.get("type") == "iframe" and t.get("targetId") and url_substr in t.get("url", ""):
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

def wait_for_load(timeout=15.0, *, pre_drain=True):
    """Wait for Page.loadEventFired without executing page JavaScript.

    pre_drain=True (default) clears stale events first — safe for
    standalone use.  Pass pre_drain=False after new_tab()/goto_url()
    which already drained before navigation, to avoid discarding the
    load event that just fired.
    """
    result = _wait_until_load("load", timeout, pre_drain=pre_drain)
    return result.get("ok", False)

def wait_for_load_js(timeout=15.0):
    """JS-based load wait fallback. This explicitly executes page JavaScript."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if js("document.readyState") == "complete": return True
        time.sleep(0.3)
    return False

def _js_snippet(expression, limit=160):
    snippet = expression.strip().replace("\n", "\\n")
    return snippet[:limit - 3] + "..." if len(snippet) > limit else snippet


def _js_exception_description(result, details):
    desc = result.get("description")
    details = _dict_value(details)
    exc = details.get("exception") if details else None
    if not desc and isinstance(exc, dict):
        desc = exc.get("description")
        if desc is None and "value" in exc:
            desc = str(exc["value"])
        if desc is None:
            desc = exc.get("className")
    if not desc and details:
        desc = details.get("text")
    return desc or "JavaScript evaluation failed"


def _decode_unserializable_js_value(value):
    if not isinstance(value, str):
        return value
    if value == "NaN":
        return math.nan
    if value == "Infinity":
        return math.inf
    if value == "-Infinity":
        return -math.inf
    if value == "-0":
        return -0.0
    if value.endswith("n"):
        return int(value[:-1])
    return value


def _runtime_value(response, expression):
    result = response.get("result", {})
    details = response.get("exceptionDetails")
    if details or result.get("subtype") == "error":
        desc = _js_exception_description(result, details)
        details = _dict_value(details)
        if details:
            line = details.get("lineNumber")
            col = details.get("columnNumber")
            loc = f" at line {line}, column {col}" if line is not None and col is not None else ""
        else:
            loc = ""
        raise RuntimeError(f"JavaScript evaluation failed{loc}: {desc}; expression: {_js_snippet(expression)}")
    if "value" in result:
        return result["value"]
    if "unserializableValue" in result:
        return _decode_unserializable_js_value(result["unserializableValue"])
    return None


def _runtime_evaluate(expression, session_id=None, await_promise=False):
    try:
        r = cdp("Runtime.evaluate", session_id=session_id, expression=expression, returnByValue=True, awaitPromise=await_promise)
    except TimeoutError as e:
        raise RuntimeError(f"Runtime.evaluate timed out; expression: {_js_snippet(expression)}") from e
    return _runtime_value(r, expression)


def _has_return_statement(expression):
    i = 0
    n = len(expression)
    state = "code"
    quote = ""
    while i < n:
        ch = expression[i]
        nxt = expression[i + 1] if i + 1 < n else ""
        if state == "code":
            if ch in ("'", '"', "`"):
                state = "string"; quote = ch; i += 1; continue
            if ch == "/" and nxt == "/":
                state = "line_comment"; i += 2; continue
            if ch == "/" and nxt == "*":
                state = "block_comment"; i += 2; continue
            if expression.startswith("return", i):
                before = expression[i - 1] if i > 0 else ""
                after = expression[i + 6] if i + 6 < n else ""
                if not (before == "_" or before.isalnum()) and not (after == "_" or after.isalnum()):
                    return True
            i += 1; continue
        if state == "line_comment":
            if ch == "\n":
                state = "code"
            i += 1; continue
        if state == "block_comment":
            if ch == "*" and nxt == "/":
                state = "code"; i += 2; continue
            i += 1; continue
        if state == "string":
            if ch == "\\":
                i += 2; continue
            if ch == quote:
                state = "code"; quote = ""
            i += 1; continue
    return False


def js(expression, target_id=None):
    """Explicitly run JavaScript in the attached tab or an iframe target.

    Expressions with top-level `return` are automatically wrapped in an IIFE, so both
    `document.title` and `const x = 1; return x` are valid inputs.

    Returns the JS value on success (None for `undefined`). Decodes
    Runtime.evaluate `unserializableValue` payloads (NaN, ±Infinity, -0, BigInt).
    Raises RuntimeError when the expression throws or evaluation fails, and when
    the underlying CDP call times out (the message includes a snippet of the
    offending expression for debugging).
    """
    sid = _require_key(cdp("Target.attachToTarget", targetId=target_id, flatten=True), "sessionId", "Target.attachToTarget response") if target_id else None
    try:
        if _has_return_statement(expression) and not expression.strip().startswith("("):
            expression = f"(function(){{{expression}}})()"
        return _runtime_evaluate(expression, session_id=sid, await_promise=True)
    finally:
        if sid:
            cdp("Target.detachFromTarget", sessionId=sid)


def install_blocker_probe():
    """Inject a diagnostic wrapper around permission-gated Web APIs.

    Wraps geolocation, notifications, mediaDevices, clipboard, bluetooth/usb/serial/hid,
    file pickers, print, storage-access, and file-input clicks so they log to
    window.__bh_blockers__ when triggered. Idempotent per page.
    Returns the result of Page.addScriptToEvaluateOnNewDocument.
    """
    cdp("Page.enable")
    return cdp("Page.addScriptToEvaluateOnNewDocument", source=BLOCKER_JS)


def pending_blockers(clear_js=False):
    """Return records of OS-native popups from JS probe and CDP events.

    JS-side: permission-gated API calls logged by install_blocker_probe().
    CDP-side: Page.javascriptDialogOpening, Page.fileChooserOpened, Page.downloadWillBegin.
    Returns {"cdp": [...], "js": [...]}. Falls back to CDP-only if JS is frozen.
    """
    cdp_side = _dict_rows(_send({"meta": "pending_blockers"}).get("blockers") or [])
    js_expr = "(function(){const a=window.__bh_blockers__||[];" + \
              ("window.__bh_blockers__=[];" if clear_js else "") + \
              "return a;})()"
    try:
        raw = js(js_expr)
    except Exception:
        raw = None
    js_side = _dict_rows(raw)
    return {"cdp": cdp_side, "js": js_side}


def dismiss_dialog(accept=True):
    """Dismiss a native browser dialog via CDP. Undetectable by antibot.

    Works even when the JS thread is frozen. Peeks at buffered CDP events first
    to extract dialog info. Returns {type, message, url} or None if no dialog.
    """
    events = _dict_rows(drain_events())
    info = None
    for e in events:
        if e.get("method") == "Page.javascriptDialogOpening":
            p = e.get("params") if isinstance(e.get("params"), dict) else {}
            info = {"type": p.get("type", ""), "message": p.get("message", ""), "url": p.get("url", "")}
    try:
        cdp("Page.handleJavaScriptDialog", accept=accept)
        if not info:
            info = {"type": "unknown", "message": "", "url": ""}
    except Exception:
        pass
    return info


def capture_dialogs():
    """Stub window.alert/confirm/prompt so they never block. Detectable by antibot.

    Call BEFORE the action that triggers the dialog; read with dialogs().
    For beforeunload or frozen pages, use dismiss_dialog() instead.
    """
    js("window.__bh_dialogs__=[];window.alert=m=>window.__bh_dialogs__.push(String(m));"
       "window.confirm=m=>{window.__bh_dialogs__.push(String(m));return true;};"
       "window.prompt=(m,d)=>{window.__bh_dialogs__.push(String(m));return d||'';}")


def dialogs():
    """Return list of captured dialog messages since last capture_dialogs()."""
    return js("window.__bh_dialogs__||[]") or []


def grant_permissions(origin, permissions):
    """Pre-grant browser permissions for an origin. Prevents popups.

    Common permissions: geolocation, notifications, microphone, camera,
    clipboard-read, clipboard-write. Must be called before the page requests.
    """
    return cdp("Browser.grantPermissions", origin=origin, permissions=permissions)


def set_geolocation(lat, lon, accuracy=100):
    """Override browser geolocation. Prevents geolocation permission popups."""
    return cdp("Emulation.setGeolocationOverride",
               latitude=lat, longitude=lon, accuracy=accuracy)


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
    props = _dict_rows(node.get("properties") or [])
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
    nodes = _dict_rows(cdp("Accessibility.getFullAXTree").get("nodes", []))
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
    content = _dict_value(model.get("model")).get("content", [])
    if len(content) >= 8:
        x = (content[0] + content[2] + content[4] + content[6]) / 4
        y = (content[1] + content[3] + content[5] + content[7]) / 4
        return x, y
    raise RuntimeError(f"ref {ref}: DOM.getBoxModel returned no content quad")


def _resolve_ref_fallback(entry):
    """Fallback: re-query AX tree to find fresh backend_node_id by role/name."""
    nodes = _dict_rows(cdp("Accessibility.getFullAXTree").get("nodes", []))
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
                content = _dict_value(model.get("model")).get("content", [])
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
        CrawlState._validate_checkpoint(data, path)
        cs = CrawlState(data["key_field"], marginal_window=data.get("marginal_window", 5))
        cs._occurrences = data.get("occurrences", {})
        cs._records = data.get("records", [])
        cs._dup_attempts = data.get("dup_attempts", 0)
        cs._missing_key = data.get("missing_key", 0)
        cs._blocked = data.get("blocked", [])
        cs._scope_totals = data.get("scope_totals", {})
        cs._marginal = deque(data.get("marginal", []), maxlen=cs._marginal.maxlen)
        return cs

    @staticmethod
    def _validate_checkpoint(data, path):
        if not isinstance(data, dict):
            raise ValueError(f"{path}: crawl checkpoint must be a JSON object")
        if not isinstance(data.get("key_field"), str) or not data["key_field"]:
            raise ValueError(f"{path}: crawl checkpoint field 'key_field' must be a non-empty string")
        expected_shapes = {
            "occurrences": dict,
            "records": list,
            "blocked": list,
            "scope_totals": dict,
            "marginal": list,
        }
        for field, expected_type in expected_shapes.items():
            if field in data and not isinstance(data[field], expected_type):
                raise ValueError(f"{path}: crawl checkpoint field '{field}' must be {expected_type.__name__}")
        for field in ("dup_attempts", "missing_key", "marginal_window"):
            if field in data and (isinstance(data[field], bool) or not isinstance(data[field], int)):
                raise ValueError(f"{path}: crawl checkpoint field '{field}' must be int")


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
        if not isinstance(data, dict):
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
                params = ev.get("params") if isinstance(ev.get("params"), dict) else {}
                rid = params.get("requestId")
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
            if not isinstance(ev, dict):
                continue
            m = ev.get("method", "")
            p = ev.get("params") if isinstance(ev.get("params"), dict) else {}
            rid = p.get("requestId")
            if not rid:
                continue
            if m == "Network.requestWillBeSent":
                redir = p.get("redirectResponse") if isinstance(p.get("redirectResponse"), dict) else None
                if redir and rid in self._requests:
                    self._finalize(rid, redir.get("status"),
                                   redir.get("headers") if isinstance(redir.get("headers"), dict) else {},
                                   redir.get("mimeType", ""))
                request = p.get("request") if isinstance(p.get("request"), dict) else {}
                self._requests[rid] = {
                    "url": _text_value(request.get("url", "")),
                    "method": _string_field(request.get("method"), "GET"),
                    "headers": request.get("headers") if isinstance(request.get("headers"), dict) else {},
                    "resource_type": _string_field(p.get("type")),
                }
                n += 1
            elif m == "Network.responseReceived":
                resp = p.get("response") if isinstance(p.get("response"), dict) else {}
                self._responses[rid] = {
                    "status": _status_code(resp.get("status")),
                    "headers": resp.get("headers") if isinstance(resp.get("headers"), dict) else {},
                    "content_type": resp.get("mimeType", ""),
                }
                if self._capture_bodies:
                    try:
                        body = cdp("Network.getResponseBody", requestId=rid)
                        raw_body = body.get("body", "")
                        if body.get("base64Encoded"):
                            raw_body = base64.b64decode(raw_body).decode("utf-8", "replace")
                        self._responses[rid]["body"] = raw_body[:self._max_body_chars]
                        self._responses[rid]["body_truncated"] = len(raw_body) > self._max_body_chars
                    except Exception:
                        pass
                if rid in self._requests:
                    self._finalize(rid,
                                   _status_code(resp.get("status")),
                                   resp.get("headers") if isinstance(resp.get("headers"), dict) else {},
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
            if not isinstance(e, dict):
                continue
            url = _text_value(e.get("url", ""))
            if not url:
                continue
            key = normalize_fn(url) if normalize_fn else url
            if key not in agg:
                agg[key] = {"url": url, "method": _string_field(e.get("method")),
                            "resource_type": e.get("resource_type", ""),
                            "status": e.get("status") or 0,
                            "content_type": e.get("content_type", ""),
                            "count": 0}
            agg[key]["count"] += 1
        return sorted(agg.values(), key=lambda x: -x["count"])

    def responses_for(self, pattern):
        """Full request/response pairs where URL matches *pattern* regex."""
        matches = []
        for e in self._entries:
            if not isinstance(e, dict):
                continue
            url = _text_value(e.get("url", ""))
            if not re.search(pattern, url):
                continue
            if url == e.get("url"):
                matches.append(e)
            else:
                matches.append({**e, "url": url})
        return matches

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
            s = e.get("status") or 0
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
        if not isinstance(headers, dict):
            return {}
        redacted = {}
        for key, value in headers.items():
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
        if "body" in safe:
            body = safe.pop("body") or ""
            if not isinstance(body, str):
                body = str(body)
            safe["body_omitted"] = True
            safe["body_length"] = len(body)
            safe["body_sha256"] = hashlib.sha256(body.encode("utf-8", "replace")).hexdigest()
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
        if not isinstance(u, str) or not u:
            continue
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
        if not isinstance(ep, dict):
            continue
        url = ep.get("url", "")
        method = _string_field(ep.get("method", "GET"))
        if not url:
            results.append({"url": "", "skipped": True, "reason": "missing-url"})
            continue
        if method.upper() != "GET":
            results.append({"url": url, "skipped": True, "reason": "non-GET"})
            continue
        try:
            if use_session:
                resp = http_get_browser_session_response(url, timeout=timeout)
                replay_status = resp.get("status") or 0
                replay_ct = _dict_value(resp.get("headers")).get("content-type", "")
            else:
                req = urllib.request.Request(url, headers={"User-Agent": _real_user_agent()})
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    replay_status, replay_ct = r.status, r.headers.get("Content-Type", "")
            orig_status = ep.get("status") or 0
            orig_ct = ep.get("content_type", "")
            replay_ct = replay_ct if isinstance(replay_ct, str) else ""
            orig_ct = orig_ct if isinstance(orig_ct, str) else ""
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
                "original_status": ep.get("status") or 0,
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


def _authority_fetch(url, headers=None, timeout=20.0, min_text=500):
    """Fetch through the authority pipeline — no challenge-solving.

    The AccessPlane orchestrates policy, budget, transport selection, and
    challenge evaluation. Challenges produce handoff IDs instead of bypass.
    """
    from .capabilities.models import ChallengeStatus, RiskLevel, WebRequest
    from .capabilities.resolver import AccessPlane
    from .authority.policy import PolicyEngine
    from .authority.challenge import ChallengeStateMachine
    from .authority.handoff import HandoffBroker
    from .sessions.broker import SessionBroker
    from .scheduler.budgets import BudgetController
    from .response import Response

    def _public_http(url, headers=None, **kw):
        try:
            return http_get(url, headers=headers, timeout=timeout)
        except urllib.error.HTTPError as e:
            # 4xx/5xx responses often contain challenge/block pages —
            # return the body and status so _detect_block can analyze it.
            try:
                return {"text": e.read().decode("utf-8", errors="replace"), "status": e.code}
            except Exception:
                return None
        except (urllib.error.URLError, OSError):
            return None

    def _session_http(url, headers=None, **kw):
        try:
            return http_get_browser_session_response(url, headers=headers, timeout=timeout)
        except (urllib.error.URLError, OSError):
            return None

    def _browser(url, **kw):
        tid = None
        try:
            tid = new_tab(url)
            wait_for_load(timeout=timeout, pre_drain=False)
            status = wait_for_content(min_text=min_text, timeout=timeout)
            html = js("document.documentElement.outerHTML") or ""
            return {
                "ok": status.get("ok", False),
                "text": status.get("text", ""),
                "html": html,
                "url": status.get("url", url),
                "status": 200 if status.get("ok") else 502,
                "reason": status.get("reason", ""),
                "block": status.get("block") or {},
            }
        except Exception:
            return None
        finally:
            if tid:
                try:
                    close_tab(tid)
                except Exception:
                    pass

    plane = AccessPlane(
        policy=PolicyEngine(),
        budget=BudgetController(),
        broker=SessionBroker(),
        challenge_sm=ChallengeStateMachine(),
        http_fn=_public_http,
        session_http_fn=_session_http,
        browser_fn=_browser,
        block_detect_fn=detect_block_page,
        handoff_broker=HandoffBroker(),
    )
    request = WebRequest(
        url=url,
        risk=RiskLevel.PUBLIC_READ,
        method="GET",
        headers=headers or {},
    )
    result = plane.execute(request)
    return Response(
        html=result.html,
        text=result.text,
        url=result.url,
        status=result.status,
        source="authority",
        headers=result.headers,
        reason=result.reason,
        block=result.block,
    )


def fetch(url, source="auto", headers=None, timeout=20.0, min_text=500):
    """Fetch URL and return a ``Response`` with CSS/XPath query support.

    *source* selects the fetch strategy:

    - ``"auto"`` (default): routes through the authority pipeline (AccessPlane).
      Policy gate, budget check, transport selection, challenge evaluation.
      Never calls solve_turnstile — challenges produce handoff IDs instead.
    - ``"http"``: plain HTTP via ``http_get()`` — fastest, no browser state.
    - ``"session"``: HTTP with browser cookies via ``http_get_browser_session_response()``.
    - ``"browser"``: real browser navigation via ``new_tab()`` + ``wait_for_content()``.
    """
    if source in ("auto", "authority"):
        return _authority_fetch(url, headers=headers, timeout=timeout, min_text=min_text)
    from .response import Response

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
        except (urllib.error.URLError, OSError):
            return Response(
                html="", text="", url=url, status=502, source="http",
                reason="connection_error", block={},
            )

    if source == "session":
        try:
            result = http_get_browser_session_response(url, headers=headers, timeout=timeout)
        except Exception:
            return Response(
                html="", text="", url=url, status=502, source="session",
                reason="session_error", block={},
            )
        block = result.get("block") or detect_block_page(
            html=result.get("text", ""),
            text=result.get("text", ""),
            url=result.get("url", url),
        )
        reason = "blocked" if block.get("blocked") else ("content" if result.get("ok") else "http_error")
        return Response(
            html=result.get("text", ""), text=result.get("text", ""),
            url=result.get("url", url), status=result.get("status") or 502,
            source="session", headers=result.get("headers", {}),
            reason=reason, block=block,
        )

    if source == "browser":
        tid = None
        try:
            tid = new_tab(url)
            wait_for_load(timeout=timeout, pre_drain=False)
            status = wait_for_content(min_text=min_text, timeout=timeout)
            html = js("document.documentElement.outerHTML") or ""
            block = status.get("block") or detect_block_page(
                html=html, text=status.get("text", ""), url=status.get("url", url),
            )
            if status.get("ok") and not block.get("blocked"):
                return Response(
                    html=html, text=status.get("text", ""),
                    url=status.get("url", url), status=200,
                    source="browser", reason=status.get("reason"),
                    block=block,
                )
            return Response(
                html=html, text=status.get("text", ""),
                url=status.get("url", url),
                status=403 if block.get("blocked") else (
                    200 if status.get("ok") else (
                        504 if status.get("reason") == "timeout" else 502)),
                source="browser", reason=status.get("reason"), block=block,
            )
        finally:
            if tid:
                try: close_tab(tid)
                except Exception: pass

    return Response(html="", text="", url=url, status=400, source="unknown",
                    reason=f"unknown source: {source}")


def _close_sock():
    global _sock
    if _sock is not None:
        try:
            _sock.close()
        except OSError:
            pass
        _sock = None


atexit.register(_close_sock)
