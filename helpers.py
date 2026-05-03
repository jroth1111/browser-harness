"""Browser control via CDP. Read, edit, extend -- this file is yours."""
import atexit, base64, json, os, socket, time, urllib.request
from importlib.resources import files
from pathlib import Path
from urllib.parse import urlparse
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
    global _sock
    if _sock is not None:
        try:
            _sock.close()
        except OSError:
            pass
    _sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    _sock.connect(SOCK)


def _send(req):
    global _sock
    if _sock is None:
        _reconnect()
    payload = (json.dumps(req) + "\n").encode()
    try:
        _sock.sendall(payload)
        data = b""
        while not data.endswith(b"\n"):
            chunk = _sock.recv(1 << 20)
            if not chunk:
                break
            data += chunk
    except OSError:
        _reconnect()
        _sock.sendall(payload)
        data = b""
        while not data.endswith(b"\n"):
            chunk = _sock.recv(1 << 20)
            if not chunk:
                break
            data += chunk
    r = json.loads(data)
    if "error" in r: raise RuntimeError(r["error"])
    return r


def _require_key(mapping, key, context):
    if not isinstance(mapping, dict) or key not in mapping:
        raise RuntimeError(f"{context} missing {key!r}: {mapping!r}")
    return mapping[key]


def cdp(method, session_id=None, **params):
    """Raw CDP. cdp('Page.navigate', url='...'), cdp('DOM.getDocument', depth=-1)."""
    return _send({"method": method, "params": params, "session_id": session_id}).get("result", {})


def drain_events():  return _send({"meta": "drain_events"})["events"]
def endpoint_info(): return _send({"meta": "endpoint_info"}).get("endpoint_info", {})


# --- navigation / page ---
def goto_url(url):
    cdp("Page.enable")
    drain_events()
    r = cdp("Page.navigate", url=url)
    d = (_asset_dir("domain-skills", "browser_harness_domain_skills") / (urlparse(url).hostname or "").removeprefix("www.").split(".")[0])
    return {**r, "domain_skills": sorted(p.name for p in d.rglob("*.md"))[:10]} if d.is_dir() else r

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
    haystack = "\n".join((html, text, url)).lower()
    stripped_text = text.strip()
    evidence = []
    kind = None

    kpsdk_hits = [s for s in ("window.kpsdk", "x-kpsdk", "kp_uidz", "/ips.js") if s in haystack]
    if len(kpsdk_hits) >= 2 and (not stripped_text or len(html) < 8000):
        kind = "kasada_kpsdk"
        evidence.extend(kpsdk_hits)

    akamai_hits = [s for s in ("access denied", "errors.edgesuite.net", "failover-waf") if s in haystack]
    if not kind and len(akamai_hits) >= 2:
        kind = "akamai_access_denied"
        evidence.extend(akamai_hits)

    if not kind:
        return {"blocked": False, "kind": None, "evidence": []}
    return {"blocked": True, "kind": kind, "evidence": evidence}

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
            close_tab(tid)

def fetch_with_browser_session(url, seed_url=None, retries=1, min_text=500, timeout=20.0, headers=None):
    """Fetch `url` with browser cookies, optionally re-seeding and retrying.

    Use this when a persistent headful profile can satisfy a site challenge but
    direct HTTP may have stale/missing cookies. The returned dict includes the
    final response text plus compact attempt evidence.
    """
    attempts = []
    cookie_urls = [url]
    if seed_url and _origin_url(seed_url) != _origin_url(url):
        cookie_urls.append(seed_url)
    for attempt in range(max(0, retries) + 1):
        response = http_get_browser_session_response(url, headers=headers, cookie_urls=cookie_urls, timeout=timeout)
        attempts.append({
            "stage": "fetch",
            "attempt": attempt + 1,
            "status": response.get("status"),
            "url": response.get("url"),
            "ok": response.get("ok"),
            "http_ok": response.get("http_ok"),
            "block": response.get("block"),
            "textLength": len(response.get("text") or ""),
        })
        if response.get("ok"):
            return {**response, "attempts": attempts, "reason": "content"}
        if not seed_url or attempt >= max(0, retries):
            reason = "blocked" if response.get("block", {}).get("blocked") else "http_error"
            return {**response, "attempts": attempts, "reason": reason}
        seed = seed_browser_session(seed_url, min_text=min_text, timeout=timeout, close=True)
        attempts.append({
            "stage": "seed",
            "attempt": attempt + 1,
            "ok": seed.get("ok"),
            "reason": seed.get("reason"),
            "block": seed.get("block"),
            "cookieNames": seed.get("cookieNames", []),
            "textLength": seed.get("textLength"),
        })
        if not seed.get("ok"):
            return {
                **response,
                "ok": False,
                "attempts": attempts,
                "reason": f"seed_{seed.get('reason', 'failed')}",
                "seed": seed,
            }

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
            close_tab(tid)

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
        if ch in {"'", '"'}:
            quote = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return html[i:pos + 1]
    return None

def _decode_nested_json_strings(value):
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith(("{", "[")):
            try:
                return _decode_nested_json_strings(json.loads(stripped))
            except (TypeError, ValueError):
                return value
        return value
    if isinstance(value, list):
        return [_decode_nested_json_strings(item) for item in value]
    if isinstance(value, dict):
        return {k: _decode_nested_json_strings(v) for k, v in value.items()}
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
        start_x = max(0, x - 40)
        start_y = y
        for i in range(1, max(2, steps) + 1):
            t = i / max(2, steps)
            eased = t * t * (3 - 2 * t)
            cdp("Input.dispatchMouseEvent", type="mouseMoved", x=start_x + (x - start_x) * eased, y=start_y + (y - start_y) * eased)
    cdp("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button=button, clickCount=clicks)
    cdp("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button=button, clickCount=clicks)

def type_text(text, delay=0):
    if delay <= 0:
        cdp("Input.insertText", text=text)
        return
    for ch in text:
        cdp("Input.insertText", text=ch)
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
    _send({"meta": "set_session", "session_id": sid})
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

def new_tab(url="about:blank"):
    # Always create blank, then goto: passing url to createTarget races with
    # attach, so the brief about:blank is "complete" by the time the caller
    # polls and wait_for_load() returns before navigation actually starts.
    tid = _require_key(cdp("Target.createTarget", url="about:blank"), "targetId", "Target.createTarget response")
    switch_tab(tid)
    if url != "about:blank":
        goto_url(url)
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


# --- utility ---
def wait(seconds=1.0):
    time.sleep(seconds)

def wait_for_load(timeout=15.0):
    """Wait for Page.loadEventFired without executing page JavaScript."""
    cdp("Page.enable")
    deadline = time.time() + timeout
    while time.time() < deadline:
        for event in drain_events():
            if event.get("method") == "Page.loadEventFired":
                return True
        time.sleep(0.3)
    return False

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
    """
    sid = _require_key(cdp("Target.attachToTarget", targetId=target_id, flatten=True), "sessionId", "Target.attachToTarget response") if target_id else None
    if "return " in expression and not expression.strip().startswith("("):
        expression = f"(function(){{{expression}}})()"
    r = cdp("Runtime.evaluate", session_id=sid, expression=expression, returnByValue=True, awaitPromise=True)
    return r.get("result", {}).get("value")


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

def _ax_value(field):
    if isinstance(field, dict):
        return field.get("value", "")
    return field or ""

def ax_snapshot(max_nodes=120):
    """Explicit accessibility-tree snapshot. Not enabled or collected on attach."""
    nodes = cdp("Accessibility.getFullAXTree").get("nodes", [])
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

def http_get(url, headers=None, timeout=20.0):
    """Pure local HTTP -- no browser. Use for static pages / APIs. Wrap in ThreadPoolExecutor for bulk."""
    import gzip
    h = {"User-Agent": "Mozilla/5.0", "Accept-Encoding": "gzip"}
    if headers: h.update(headers)
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout) as r:
        data = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            try:
                data = gzip.decompress(data)
            except (OSError, EOFError):
                pass
        return data.decode()


def _close_sock():
    global _sock
    if _sock is not None:
        try:
            _sock.close()
        except OSError:
            pass
        _sock = None


atexit.register(_close_sock)
