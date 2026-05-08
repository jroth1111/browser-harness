import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from . import _ipc as ipc


def _process_start_time(pid):
    """Opaque process-start-time fingerprint at PID, or None if unavailable.

    Two reads returning the same non-None value mean the PID still refers to
    the same process; a different value means the PID was reused. Used by
    restart_daemon() to keep the force-kill recovery path working even when
    the daemon has already torn down its IPC socket (e.g. during a slow
    remote shutdown), without falling back to "trust the pid file" — which
    would re-introduce the PID-reuse hazard.

    Linux:   /proc/<pid>/stat field 22 (starttime in clock ticks since boot).
    macOS:   `ps -o lstart= -p <pid>` (an absolute timestamp string).
    Windows: GetProcessTimes via ctypes (FILETIME creation time, 100-ns since 1601).
    """
    if type(pid) is not int or pid <= 0:
        return None
    if sys.platform.startswith("linux"):
        try:
            with open(f"/proc/{pid}/stat", "rb") as f:
                raw = f.read().decode("ascii", errors="replace")
        except (FileNotFoundError, PermissionError, OSError):
            return None
        # Field 2 is `(comm)`; comm can contain spaces and parens, so split off
        # everything after the LAST `)` and index from there.
        try:
            tail = raw[raw.rindex(")") + 2:].split()
            return tail[19]
        except (ValueError, IndexError):
            return None
    if sys.platform == "darwin":
        try:
            out = subprocess.check_output(
                ["ps", "-o", "lstart=", "-p", str(pid)],
                stderr=subprocess.DEVNULL, timeout=2,
            )
        except (subprocess.SubprocessError, OSError):
            return None
        s = out.decode("ascii", errors="replace").strip()
        return s or None
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
        except ImportError:
            return None
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        try:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel32.OpenProcess.restype = wintypes.HANDLE
            kernel32.GetProcessTimes.argtypes = [
                wintypes.HANDLE,
                ctypes.POINTER(wintypes.FILETIME),
                ctypes.POINTER(wintypes.FILETIME),
                ctypes.POINTER(wintypes.FILETIME),
                ctypes.POINTER(wintypes.FILETIME),
            ]
            kernel32.GetProcessTimes.restype = wintypes.BOOL
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel32.CloseHandle.restype = wintypes.BOOL
        except (OSError, AttributeError):
            return None
        h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            return None
        try:
            creation = wintypes.FILETIME()
            exit_ft = wintypes.FILETIME()
            kernel_ft = wintypes.FILETIME()
            user_ft = wintypes.FILETIME()
            ok = kernel32.GetProcessTimes(
                h, ctypes.byref(creation), ctypes.byref(exit_ft),
                ctypes.byref(kernel_ft), ctypes.byref(user_ft),
            )
            if not ok:
                return None
            return (creation.dwHighDateTime << 32) | creation.dwLowDateTime
        finally:
            kernel32.CloseHandle(h)
    return None


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
GH_RELEASES = "https://api.github.com/repos/browser-use/browser-harness/releases/latest"
VERSION_CACHE = Path(tempfile.gettempdir()) / "bh-version-cache.json"
VERSION_CACHE_TTL = 24 * 3600
DOCTOR_TEXT_LIMIT = 140


def _safe_int(value, default=None):
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _log_tail(name):
    try:
        return ipc.log_path(name or NAME).read_text().strip().splitlines()[-1]
    except (FileNotFoundError, IndexError):
        return None


def _needs_chrome_remote_debugging_prompt(msg):
    """True when Chrome needs the inspect-page permission/profile flow."""
    lower = (msg or "").lower()
    return (
        "devtoolsactiveport not found" in lower
        or "enable chrome://inspect" in lower
        or "not live yet" in lower
        or (
            "ws handshake failed" in lower
            and (
                "403" in lower
                or "opening handshake" in lower
                or "timed out" in lower
                or "timeout" in lower
            )
        )
    )


def _is_local_chrome_mode(env=None):
    """True when the daemon discovers a local Chrome instead of an explicit CDP endpoint."""
    e = env or {}
    return not (
        e.get("BH_CDP_WS")
        or e.get("BH_CDP_URL")
        or os.environ.get("BH_CDP_WS")
        or os.environ.get("BH_CDP_URL")
    )


def daemon_alive(name=None):
    # Ping handshake (not a bare connect) so a stale .port file + port reuse
    # after a daemon crash doesn't make us mistake an unrelated listener for ours.
    return ipc.ping(name or NAME, timeout=1.0)


def _daemon_endpoint_names():
    # BH_TMP_DIR isolates one daemon per dir → no filename-prefix discovery,
    # just check whether our local endpoint exists. Without BH_TMP_DIR, _TMP
    # is the shared default (`/tmp` etc.) and we glob `bh-*.<suffix>` to find
    # every daemon on the machine.
    suffix = ".port" if ipc.IS_WINDOWS else ".sock"
    if ipc.BH_TMP_DIR:
        return [NAME] if (ipc._TMP / f"bh{suffix}").exists() else []
    names = []
    for p in sorted(ipc._TMP.glob(f"bh-*{suffix}")):
        raw = p.name[3:-len(suffix)]
        try:
            ipc._check(raw)
        except ValueError:
            continue
        names.append(raw)
    return names


def _daemon_browser_connection(name):
    c = None
    try:
        c, token = ipc.connect(name, timeout=1.0)
        response = ipc.request(c, token, {"meta": "connection_status"})
        if not isinstance(response, dict):
            return None
        if "error" in response:
            return None
        page = response.get("page")
        if page is not None and not isinstance(page, dict):
            return None
        if page:
            page = {"title": page.get("title") or "(untitled)", "url": page.get("url") or ""}
        return {"name": name, "page": page}
    except (FileNotFoundError, ConnectionRefusedError, TimeoutError, socket.timeout, OSError, KeyError, ValueError, json.JSONDecodeError, RuntimeError):
        return None
    finally:
        if c:
            try: c.close()
            except OSError: pass


def browser_connections():
    """Live browser-harness daemons with healthy CDP browser connections and their attached page."""
    out = []
    for name in _daemon_endpoint_names():
        conn = _daemon_browser_connection(name)
        if conn:
            out.append(conn)
    return out


def active_browser_connections():
    """Count live browser-harness daemons with a healthy CDP browser connection."""
    return len(browser_connections())


def _doctor_short_text(value, limit=None):
    limit = limit or DOCTOR_TEXT_LIMIT
    value = str(value)
    return value if len(value) <= limit else value[:limit - 3] + "..."


def _doctor_text(value):
    return "" if value is None else str(value)


def ensure_daemon(wait=60.0, name=None, env=None, accept_remote_debugging_dialog=False):
    """Idempotent. Self-heals stale daemon, cold Chrome, and missing Allow on chrome://inspect."""
    if daemon_alive(name):
        # Stale daemons accept connects AND reply to meta:* (pure Python) even when the
        # CDP WS to Chrome is dead — probe with a real CDP call and require "result".
        try:
            s, token = ipc.connect(name or NAME, timeout=3.0)
            try:
                resp = ipc.request(s, token, {"method": "Target.getTargets", "params": {}})
                if isinstance(resp, dict) and "result" in resp:
                    return
            finally:
                try: s.close()
                except OSError: pass
        except Exception:
            pass
        restart_daemon(name)

    local = _is_local_chrome_mode(env)
    for attempt in (0, 1):
        e = {**os.environ, **({"BH_NAME": name} if name else {}), **(env or {})}
        root = os.path.dirname(os.path.abspath(__file__))
        p = subprocess.Popen(
            [sys.executable, os.path.join(root, "daemon.py")],
            cwd=root,
            env=e, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **ipc.spawn_kwargs(),
        )
        deadline = time.time() + wait
        while time.time() < deadline:
            if daemon_alive(name): return
            if p.poll() is not None: break
            time.sleep(0.2)
        msg = _log_tail(name) or ""
        if local and attempt == 0 and _needs_chrome_remote_debugging_prompt(msg):
            _open_chrome_inspect()
            if accept_remote_debugging_dialog:
                result = _accept_remote_debugging_dialog_keyboard()
                if result.get("ok"):
                    print("browser-harness: sent keyboard approval for chrome://inspect remote-debugging dialog", file=sys.stderr)
                else:
                    print(f"browser-harness: keyboard approval failed: {result.get('error') or result.get('reason')}", file=sys.stderr)
                    print("browser-harness: click Allow on chrome://inspect (and tick the checkbox if shown)", file=sys.stderr)
            else:
                print("browser-harness: click Allow on chrome://inspect (and tick the checkbox if shown)", file=sys.stderr)
            restart_daemon(name)
            if p.poll() is None:
                try: p.wait(timeout=3)
                except Exception: pass
            continue
        if p.poll() is None:
            try: p.wait(timeout=3)
            except Exception: pass
        raise RuntimeError(msg or f"daemon {name or NAME} didn't come up -- check {ipc.log_path(name or NAME)}")


def stop_remote_daemon(name="remote"):
    """Stop a remote daemon and its backing Browser Use cloud browser.

    Triggers the daemon's clean shutdown, which PATCHes
    /browsers/{id} {"action":"stop"} so billing ends and any profile
    state in the session is persisted."""
    restart_daemon(name)


def restart_daemon(name=None):
    """Best-effort daemon shutdown + socket/pid cleanup.

    Identity is verified via ipc.identify() before any process signal, so
    a stale pid file whose number has been reused by an unrelated process
    is never SIGTERM'd. If the daemon is unreachable, we just clean up the
    pid file and socket and return — never escalate to a kill-by-pid-file.
    """
    import signal

    name = name or NAME
    pid_path = str(ipc.pid_path(name))

    # Two pieces of information are tracked separately:
    #   - daemon_pid: the daemon's self-reported PID, or None. Only daemons
    #     running this version (or newer) include `pid` in the ping response;
    #     pre-upgrade daemons return {pong: True} only and yield None here.
    #   - daemon_alive: whether ANY daemon answers ping. Keeps the shutdown
    #     IPC path working across upgrades — without it, a still-running
    #     pre-upgrade daemon would have its socket deleted out from under it
    #     while the process stayed alive.
    daemon_pid = ipc.identify(name, timeout=5.0)
    daemon_alive = daemon_pid is not None or ipc.ping(name, timeout=1.0)
    # Snapshot the daemon's process start-time as a secondary identity check.
    # The IPC socket can disappear before the process exits (e.g. the shutdown
    # path tears down the socket and then waits on a slow remote `stop` PATCH),
    # so identify() going None partway through is not proof of process death.
    daemon_start = _process_start_time(daemon_pid)

    if daemon_alive:
        try:
            c, token = ipc.connect(name, timeout=5.0)
            ipc.request(c, token, {"meta": "shutdown"})
            try: c.close()
            except (OSError, AttributeError): pass
        except Exception:
            pass

    if daemon_pid is not None:
        for _ in range(75):
            try:
                os.kill(daemon_pid, 0)
                time.sleep(0.2)
            except (ProcessLookupError, OSError, SystemError, OverflowError):
                break
        else:
            # Re-verify identity before escalating to SIGTERM.
            verified_pid = ipc.identify(name, timeout=1.0)
            same_process = verified_pid == daemon_pid or (
                daemon_start is not None
                and _process_start_time(daemon_pid) == daemon_start
            )
            if same_process:
                try:
                    os.kill(daemon_pid, signal.SIGTERM)
                except (ProcessLookupError, OSError, SystemError, OverflowError):
                    pass

    ipc.cleanup_endpoint(name)
    try:
        os.unlink(pid_path)
    except FileNotFoundError:
        pass


def _browser_use(path, method, body=None):
    key = os.environ.get("BROWSER_USE_API_KEY")
    if not key:
        raise RuntimeError("BROWSER_USE_API_KEY missing -- see .env.example")
    api_base = "https://api.browser-use.com/api/v3"
    req = urllib.request.Request(
        f"{api_base}{path}",
        method=method,
        data=(json.dumps(body).encode() if body is not None else None),
        headers={"X-Browser-Use-API-Key": key, "Content-Type": "application/json"},
    )
    return json.loads(urllib.request.urlopen(req, timeout=60).read() or b"{}")


def _stop_cloud_browser(browser_id):
    if not browser_id:
        return
    try:
        _browser_use(f"/browsers/{browser_id}", "PATCH", {"action": "stop"})
    except BaseException:
        pass


def _cdp_ws_from_url(cdp_url):
    response = json.loads(urllib.request.urlopen(f"{cdp_url}/json/version", timeout=15).read())
    if not isinstance(response, dict):
        raise RuntimeError(
            "CDP /json/version returned invalid response shape: "
            f"expected object, got {type(response).__name__}"
        )
    ws = response.get("webSocketDebuggerUrl")
    if not ws:
        raise RuntimeError("CDP /json/version response missing required field: webSocketDebuggerUrl")
    return ws


def _has_local_gui():
    """True when this machine plausibly has a browser we can open. False on headless servers."""
    import platform
    system = platform.system()
    if system in ("Darwin", "Windows"):
        return True
    if system == "Linux":
        return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    return False


def _show_live_url(url):
    """Print liveUrl and auto-open it locally if there's a GUI."""
    import webbrowser
    if not url:
        return
    print(url)
    if not _has_local_gui():
        print("(no local GUI — share the liveUrl with the user)", file=sys.stderr)
        return
    try:
        webbrowser.open(url, new=2)
        print("(opened liveUrl in your default browser)", file=sys.stderr)
    except Exception as e:
        print(f"(couldn't auto-open: {e} — share the liveUrl with the user)", file=sys.stderr)


def list_cloud_profiles():
    """List cloud profiles under the current API key.

    Paginates through all pages — the API caps `pageSize` at 100."""
    out, page, seen = [], 1, 0
    while True:
        listing = _browser_use(f"/profiles?pageSize=100&pageNumber={page}", "GET")
        if isinstance(listing, dict):
            items = listing.get("items") or []
        elif isinstance(listing, list):
            items = listing
        else:
            raise RuntimeError(f"Browser Use profile list returned invalid response shape: expected object or array, got {type(listing).__name__}")
        if not isinstance(items, list):
            raise RuntimeError("Browser Use profile list response field 'items' must be an array")
        if not items:
            break
        seen += len(items)
        for p in items:
            if not isinstance(p, dict) or not p.get("id"):
                continue
            detail = _browser_use(f"/profiles/{p['id']}", "GET")
            if not isinstance(detail, dict):
                raise RuntimeError(
                    "Browser Use profile detail returned invalid response shape: "
                    f"expected object, got {type(detail).__name__}"
                )
            if not detail.get("id"):
                raise RuntimeError("Browser Use profile detail response missing required field: id")
            out.append({
                "id": detail["id"],
                "name": detail.get("name"),
                "userId": detail.get("userId"),
                "cookieDomains": detail.get("cookieDomains") or [],
                "lastUsedAt": detail.get("lastUsedAt"),
            })
        if isinstance(listing, dict):
            total_items = _safe_int(listing.get("totalItems"), None)
            if total_items is not None and seen >= total_items:
                break
        page += 1
    return out


def _resolve_profile_name(profile_name):
    """Find a single cloud profile by exact name; raise if 0 or >1 match."""
    matches = [p for p in list_cloud_profiles() if p.get("name") == profile_name]
    if not matches:
        raise RuntimeError(f"no cloud profile named {profile_name!r} -- call list_cloud_profiles() or sync_local_profile() first")
    if len(matches) > 1:
        raise RuntimeError(f"{len(matches)} cloud profiles named {profile_name!r} -- pass profileId=<uuid> instead")
    return matches[0]["id"]


def _require_cloud_browser_fields(browser):
    if not isinstance(browser, dict):
        raise RuntimeError(f"Browser Use create returned invalid response shape: expected object, got {type(browser).__name__}")
    missing = [key for key in ("id", "cdpUrl") if not browser.get(key)]
    if missing:
        detail = ", ".join(missing)
        raise RuntimeError(f"Browser Use create response missing required field(s): {detail}")
    return browser


def start_remote_daemon(name="remote", profileName=None, **create_kwargs):
    """Provision a Browser Use cloud browser and start a daemon attached to it.

    Returns the full browser dict including `liveUrl`. Prints the liveUrl and
    auto-opens it locally when a GUI is detected, so the user can watch along.

    Requires PolicyEngine authorization for the provision_browser action.
    BH_AUTOSPAWN env var is treated as a standing permission seed.
    """
    # Authority gate: provision_browser is an external side effect
    from .authority.policy import PolicyEngine
    from .capabilities.models import WebAction, RiskLevel
    standing = {RiskLevel.PUBLIC_READ}
    if os.environ.get("BH_AUTOSPAWN"):
        standing.add(RiskLevel.EXTERNAL_SIDE_EFFECT)
    policy = PolicyEngine(standing_permissions=standing)
    action = WebAction(kind="provision_browser", risk=RiskLevel.EXTERNAL_SIDE_EFFECT)
    decision = policy.authorize_action(action)
    if not decision.allowed:
        raise RuntimeError(
            f"provision_browser denied: {decision.reason}. "
            "Set BH_AUTOSPAWN=1 for standing permission or call from dev_runtime."
        )

    if daemon_alive(name):
        raise RuntimeError(f"daemon {name!r} already alive -- restart_daemon({name!r}) first")
    if profileName:
        if "profileId" in create_kwargs:
            raise RuntimeError("pass profileName OR profileId, not both")
        create_kwargs["profileId"] = _resolve_profile_name(profileName)
    browser = _require_cloud_browser_fields(_browser_use("/browsers", "POST", create_kwargs))
    ws = _cdp_ws_from_url(browser["cdpUrl"])
    try:
        ensure_daemon(
            name=name,
            env={
                "BH_CDP_WS": ws,
                "BH_BROWSER_ID": browser["id"],
            },
        )
    except BaseException:
        _stop_cloud_browser(browser.get("id"))
        raise
    _show_live_url(browser.get("liveUrl"))
    return browser


def sync_local_profile(profile_name, browser=None, cloud_profile_id=None,
                        include_domains=None, exclude_domains=None):
    """Sync a local profile's cookies to a cloud profile. Returns the cloud UUID.

    Shells out to `profile-use sync` (v1.0.5+). Requires BROWSER_USE_API_KEY."""
    import re, shutil
    if not shutil.which("profile-use"):
        raise RuntimeError("profile-use not installed -- curl -fsSL https://browser-use.com/profile.sh | sh")
    if not os.environ.get("BROWSER_USE_API_KEY"):
        raise RuntimeError("BROWSER_USE_API_KEY missing")
    cmd = ["profile-use", "sync", "--profile", profile_name]
    if browser:
        cmd += ["--browser", browser]
    if cloud_profile_id:
        cmd += ["--cloud-profile-id", cloud_profile_id]
    for d in include_domains or []:
        cmd += ["--domain", d]
    for d in exclude_domains or []:
        cmd += ["--exclude-domain", d]
    r = subprocess.run(cmd, text=True, capture_output=True)
    sys.stdout.write(r.stdout)
    sys.stderr.write(r.stderr)
    if r.returncode != 0:
        raise RuntimeError(f"profile-use sync failed (exit {r.returncode})")
    if cloud_profile_id:
        return cloud_profile_id
    m = re.search(r"Profile created:\s+([0-9a-f-]{36})", r.stdout)
    if not m:
        raise RuntimeError(f"profile-use did not report a profile UUID (exit {r.returncode})")
    return m.group(1)


def list_local_profiles():
    """Detected local browser profiles on this machine. Shells out to `profile-use list --json`.
    Returns [{BrowserName, BrowserPath, ProfileName, ProfilePath, DisplayName}, ...]."""
    import shutil
    if not shutil.which("profile-use"):
        raise RuntimeError("profile-use not installed; use `browser-harness --setup` or configure local Chrome remote debugging")
    return json.loads(subprocess.check_output(["profile-use", "list", "--json"], text=True))


def _version():
    """Installed version of the browser-harness package. Empty string if unknown."""
    try:
        from importlib.metadata import PackageNotFoundError, version
        try:
            return version("browser-harness")
        except PackageNotFoundError:
            return ""
    except Exception:
        return ""


def _repo_dir():
    """Return the repo root if this install is an editable git clone, else None."""
    for p in Path(__file__).resolve().parents:
        if (p / ".git").is_dir():
            return p
    return None


def _install_mode():
    """"git" for editable clone, "pypi" for an installed wheel, "unknown" otherwise."""
    if _repo_dir():
        return "git"
    return "pypi" if _version() else "unknown"


def _cache_read():
    try:
        cache = json.loads(VERSION_CACHE.read_text())
    except (FileNotFoundError, ValueError):
        return {}
    return cache if isinstance(cache, dict) else {}


def _cache_write(data):
    try:
        VERSION_CACHE.write_text(json.dumps(data))
    except OSError:
        pass


def _latest_release_tag(force=False):
    """Return latest release tag from GitHub, or None. Cached for 24h to avoid hammering the API."""
    cache = _cache_read()
    now = time.time()
    if not force and cache.get("tag") and now - cache.get("fetched_at", 0) < VERSION_CACHE_TTL:
        return cache["tag"]
    try:
        req = urllib.request.Request(GH_RELEASES, headers={"Accept": "application/vnd.github+json"})
        tag = json.loads(urllib.request.urlopen(req, timeout=5).read()).get("tag_name") or ""
    except Exception:
        return cache.get("tag")  # fall back to last known
    tag = tag.lstrip("v")
    _cache_write({**cache, "tag": tag, "fetched_at": now})
    return tag or None


def _version_tuple(v):
    """Best-effort semver parse. Non-numeric components sort as 0, so pre-releases may not rank perfectly."""
    parts = []
    for s in (v or "").split("."):
        m = ""
        for ch in s:
            if ch.isdigit():
                m += ch
            else:
                break
        parts.append(int(m) if m else 0)
    return tuple(parts)


def check_for_update():
    """(current, latest, newer_available). latest may be None if the API was unreachable and no cache exists."""
    cur = _version()
    latest = _latest_release_tag()
    newer = bool(cur and latest and _version_tuple(latest) > _version_tuple(cur))
    return cur, latest, newer


def print_update_banner(out=None):
    """Print the update banner to stderr once per day. Silent when up-to-date or offline."""
    out = out or sys.stderr
    cache = _cache_read()
    today = time.strftime("%Y-%m-%d")
    if cache.get("banner_shown_on") == today:
        return
    cur, latest, newer = check_for_update()
    if not newer:
        return
    print(f"[browser-harness] update available: {cur} -> {latest}", file=out)
    print(f"[browser-harness] agents: run `browser-harness --update -y` to upgrade and restart the daemon", file=out)
    _cache_write({**cache, "banner_shown_on": today})


def _chrome_running():
    """Cross-platform best-effort check for a running Chrome/Edge process."""
    import platform
    system = platform.system()
    try:
        if system == "Windows":
            out = subprocess.check_output(["tasklist"], text=True, timeout=5)
            names = ("chrome.exe", "msedge.exe")
        else:
            out = subprocess.check_output(["ps", "-A", "-o", "comm="], text=True, timeout=5)
            names = ("Google Chrome", "chrome", "chromium", "Microsoft Edge", "msedge")
        return any(n.lower() in out.lower() for n in names)
    except Exception:
        return False


def _daemon_meta(meta, name=None, timeout=2.0):
    c = None
    try:
        c, token = ipc.connect(name or NAME, timeout=timeout)
        return ipc.request(c, token, {"meta": meta})
    except (FileNotFoundError, ConnectionRefusedError, TimeoutError, socket.timeout, OSError, ValueError, json.JSONDecodeError, RuntimeError):
        return {}
    finally:
        if c:
            try: c.close()
            except OSError: pass


def _open_chrome_inspect():
    """Open chrome://inspect/#remote-debugging so the user can tick the checkbox."""
    import platform, webbrowser
    url = "chrome://inspect/#remote-debugging"
    if platform.system() == "Darwin":
        try:
            subprocess.run([
                "osascript",
                "-e", 'tell application "Google Chrome" to activate',
                "-e", f'tell application "Google Chrome" to open location "{url}"',
            ], timeout=5, check=False)
            return
        except Exception:
            pass
    try:
        webbrowser.open(url, new=2)
    except Exception:
        pass


def _remote_debugging_keyboard_applescript(wait=1.0, app_name="Google Chrome"):
    return [
        f'tell application "{app_name}" to activate',
        f"delay {float(wait):.2f}",
        'tell application "System Events"',
        "keystroke tab",
        "delay 0.10",
        "keystroke space",
        "delay 0.10",
        "keystroke tab",
        "delay 0.10",
        "keystroke return",
        "end tell",
    ]


def _accept_remote_debugging_dialog_keyboard(wait=1.0, app_name="Google Chrome"):
    """Opt-in keyboard-only consent for Chrome's native remote-debugging dialog."""
    import platform
    if platform.system() != "Darwin":
        return {"ok": False, "reason": "keyboard consent automation is implemented for macOS only"}
    args = ["osascript"]
    for line in _remote_debugging_keyboard_applescript(wait=wait, app_name=app_name):
        args.extend(["-e", line])
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=10, check=False)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stderr": result.stderr.strip(),
        "error": result.stderr.strip() if result.returncode else "",
    }


def _default_chrome_executable():
    import platform, shutil
    if platform.system() == "Darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            str(Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        ]
        for candidate in candidates:
            if Path(candidate).exists():
                return candidate
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _validate_port(port):
    port = int(port)
    if port < 1 or port > 65535:
        raise ValueError("port must be in 1..65535")
    return port


_HEADLESS_STEALTH_ARGS = (
    "--disable-blink-features=AutomationControlled",
    "--test-type",
    "--lang=en-US",
    "--mute-audio",
    "--disable-sync",
    "--hide-scrollbars",
    "--disable-logging",
    "--enable-async-dns",
    "--accept-lang=en-US",
    "--use-mock-keychain",
    "--disable-translate",
    "--disable-voice-input",
    "--window-position=0,0",
    "--ignore-gpu-blocklist",
    "--disable-dev-shm-usage",
    "--metrics-recording-only",
    "--disable-crash-reporter",
    "--force-color-profile=srgb",
    "--font-render-hinting=none",
    "--aggressive-cache-discard",
    "--disable-domain-reliability",
    "--disable-threaded-animation",
    "--disable-threaded-scrolling",
    "--enable-simple-cache-backend",
    "--disable-background-networking",
    "--enable-surface-synchronization",
    "--disable-renderer-backgrounding",
    "--disable-ipc-flooding-protection",
    "--safebrowsing-disable-auto-update",
    "--disable-background-timer-throttling",
    "--run-all-compositor-stages-before-draw",
    "--disable-client-side-phishing-detection",
    "--disable-backgrounding-occluded-windows",
    "--autoplay-policy=user-gesture-required",
    "--disable-features=AudioServiceOutOfProcess,TranslateUI,BlinkGenPropertyTrees",
)

_HEADLESS_HARMFUL_ARGS = (
    "--enable-automation",
    "--disable-component-update",
    "--disable-default-apps",
    "--disable-extensions",
)


def launch_headful_profile(profile_path, port=9222, url="about:blank", chrome_path=None,
                           headless=False, window_size=None):
    """Launch Chrome with a loopback CDP endpoint and explicit profile."""
    profile = Path(profile_path).expanduser()
    profile.mkdir(parents=True, exist_ok=True)
    port = _validate_port(port)
    chrome = chrome_path or _default_chrome_executable()
    if not chrome:
        raise RuntimeError("could not find a Chrome/Chromium executable")
    cmd = [
        chrome,
        f"--user-data-dir={profile}",
        "--remote-debugging-address=127.0.0.1",
        f"--remote-debugging-port={port}",
        "--no-first-run",
        "--no-default-browser-check",
        "--new-window",
    ]
    if headless:
        cmd.append("--headless=new")
        cmd.extend(_HEADLESS_STEALTH_ARGS)
        cmd.append(f"--ignore-default-args={','.join(_HEADLESS_HARMFUL_ARGS)}")
    if window_size:
        cmd.append(f"--window-size={window_size[0]},{window_size[1]}")
    cmd.append(url)
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    return {
        "pid": proc.pid,
        "profile_path": str(profile),
        "http_endpoint": f"http://127.0.0.1:{port}",
        "env": f"BH_CDP_WS=http://127.0.0.1:{port}",
        "command": cmd,
    }


def run_launch_profile(profile_path, port=9222, url="about:blank", chrome_path=None,
                       headless=False, window_size=None, json_output=False):
    """CLI wrapper for launching an agent-owned Chrome profile."""
    try:
        result = launch_headful_profile(profile_path, port=port, url=url, chrome_path=chrome_path,
                                        headless=headless, window_size=window_size)
    except Exception as e:
        print(f"launch failed: {e}", file=sys.stderr)
        return 1
    if json_output:
        print(json.dumps(result, indent=2))
    else:
        print(f"launched Chrome pid {result['pid']}")
        print(f"profile: {result['profile_path']}")
        print(f"endpoint: {result['http_endpoint']}")
        print(f"export {result['env']}")
    return 0


def launch_browser(headless=False, profile=None, proxy=None, extensions=None,
                   port=0, chrome_path=None):
    """Launch Chrome with CDP and connect the daemon.

    Returns dict with pid, port, ws_url, profile_path, temp_profile.
    """
    import shutil
    chrome = chrome_path or os.environ.get("BH_CHROME_PATH") or _default_chrome_executable()
    if not chrome:
        raise RuntimeError("Chrome not found; set BH_CHROME_PATH or install Chrome")
    port = port or 0
    is_temp = False
    if profile:
        user_data_dir = str(Path(profile).expanduser())
        dap = Path(user_data_dir) / "DevToolsActivePort"
        try: dap.unlink()
        except FileNotFoundError: pass
    else:
        user_data_dir = tempfile.mkdtemp(prefix="bh-chrome-")
        is_temp = True
    cmd = [chrome]
    cmd.append(f"--remote-debugging-port={port}")
    cmd.append(f"--user-data-dir={user_data_dir}")
    cmd.extend(["--no-first-run", "--no-default-browser-check",
                "--disable-background-networking", "--disable-sync",
                "--disable-features=Translate", "--metrics-recording-only"])
    if headless:
        cmd.append("--headless=new")
        cmd.extend(_HEADLESS_STEALTH_ARGS)
    if proxy:
        cmd.append(f"--proxy-server={proxy}")
    if extensions:
        ext_list = ",".join(str(e) for e in extensions)
        cmd.append(f"--load-extension={ext_list}")
        cmd.append(f"--disable-extensions-except={ext_list}")
    cmd.append("about:blank")
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE, start_new_session=True)
    deadline = time.time() + 15
    dap_path = Path(user_data_dir) / "DevToolsActivePort"
    while time.time() < deadline:
        if proc.poll() is not None:
            stderr = (proc.stderr.read().decode(errors="replace")[:500]) if proc.stderr else ""
            if is_temp:
                shutil.rmtree(user_data_dir, ignore_errors=True)
            raise RuntimeError(f"Chrome exited immediately (pid {proc.pid}): {stderr}")
        if dap_path.exists():
            break
        time.sleep(0.3)
    else:
        _kill_and_wait(proc)
        if is_temp:
            shutil.rmtree(user_data_dir, ignore_errors=True)
        raise RuntimeError("Chrome did not write DevToolsActivePort within 15s")
    dap_lines = dap_path.read_text().strip().split("\n")
    try:
        actual_port = int(dap_lines[0].strip())
    except (ValueError, IndexError) as e:
        _kill_and_wait(proc)
        if is_temp:
            shutil.rmtree(user_data_dir, ignore_errors=True)
        raise RuntimeError(f"unexpected DevToolsActivePort format: {dap_lines!r}") from e
    ws_path = dap_lines[1].strip() if len(dap_lines) > 1 else ""
    env_ws = f"ws://127.0.0.1:{actual_port}{ws_path}"
    previous_ws = os.environ.get("BH_CDP_WS")
    os.environ["BH_CDP_WS"] = env_ws
    try:
        restart_daemon()
        ensure_daemon()
    except BaseException:
        if previous_ws is None:
            os.environ.pop("BH_CDP_WS", None)
        else:
            os.environ["BH_CDP_WS"] = previous_ws
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        if proc.stderr:
            proc.stderr.close()
        if is_temp:
            shutil.rmtree(user_data_dir, ignore_errors=True)
        raise
    if proc.stderr:
        proc.stderr.close()
    return {
        "pid": proc.pid,
        "port": actual_port,
        "ws_url": env_ws,
        "profile_path": user_data_dir,
        "temp_profile": is_temp,
        "_proc": proc,
    }


def _kill_and_wait(proc, timeout=3):
    proc.kill()
    try:
        proc.wait(timeout=timeout)
    except Exception:
        pass


def close_browser(launch_info):
    """Close a browser launched by launch_browser()."""
    import signal, shutil
    restart_daemon()
    pid = launch_info.get("pid")
    proc = launch_info.get("_proc")
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        else:
            if proc is not None:
                try:
                    proc.wait(timeout=10)
                except Exception:
                    _kill_and_wait(proc)
    if launch_info.get("temp_profile"):
        shutil.rmtree(launch_info["profile_path"], ignore_errors=True)


def run_setup(accept_remote_debugging_dialog=False):
    """Interactive bootstrap: attach to the running browser, guiding the user through chrome://inspect if needed.

    Exit code 0 on success, 1 on failure."""
    print("browser-harness setup: attaching to your browser...")

    if daemon_alive():
        print("daemon already running; nothing to do.")
        return 0

    if not _chrome_running():
        print("no Chrome/Edge process detected. please start your browser and rerun `browser-harness --setup`.")
        return 1

    try:
        ensure_daemon(wait=20.0, accept_remote_debugging_dialog=accept_remote_debugging_dialog)
        print("daemon is up.")
        return 0
    except RuntimeError as e:
        first_err = str(e)

    needs_inspect = _is_local_chrome_mode() and _needs_chrome_remote_debugging_prompt(first_err)
    if needs_inspect:
        print("chrome remote-debugging is not enabled on the current profile.")
        print("opening chrome://inspect/#remote-debugging -- in the tab that opens:")
        print("  1. if chrome shows the profile picker, pick your normal profile;")
        print("  2. tick 'Discover network targets' and click Allow if prompted.")
        _open_chrome_inspect()
        if accept_remote_debugging_dialog:
            result = _accept_remote_debugging_dialog_keyboard()
            if result.get("ok"):
                print("sent keyboard approval for the remote-debugging dialog.")
            else:
                print(f"keyboard approval failed: {result.get('error') or result.get('reason')}")
    else:
        print(f"attach failed: {first_err}")
        print("retrying for up to 60s (chrome may still be starting up)...")

    deadline = time.time() + 60
    last = first_err
    while time.time() < deadline:
        try:
            ensure_daemon(wait=5.0, accept_remote_debugging_dialog=accept_remote_debugging_dialog)
            print("daemon is up.")
            return 0
        except RuntimeError as e:
            last = str(e)
            time.sleep(2)

    print(f"setup failed: {last}", file=sys.stderr)
    print("run `browser-harness --doctor` for diagnostics.", file=sys.stderr)
    return 1


def _check(status, check_id, detail="", fix=None):
    return {"id": check_id, "status": status, "detail": detail, "fix": fix}


def _doctor_checks(network=False):
    import platform
    checks = []
    chrome = _chrome_running()
    daemon = daemon_alive()

    checks.append(_check("pass", "platform.info", f"{platform.system()} {platform.release()}"))
    checks.append(_check("pass" if chrome else "warn", "browser.process",
                         "Chrome/Edge process detected" if chrome else "Chrome/Edge process not detected",
                         "start Chrome/Edge and rerun `browser-harness --setup`" if not chrome else None))
    checks.append(_check("pass" if daemon else "fail", "daemon.alive",
                         "daemon socket responds" if daemon else "daemon socket is not responding",
                         "run `browser-harness --setup` to attach" if not daemon else None))

    if daemon:
        try:
            mode = ipc._sock_path(NAME).stat().st_mode & 0o777
            checks.append(_check("pass" if mode == 0o600 else "fail", "daemon.socket_permissions", oct(mode),
                                 f"expected {ipc._sock_path(NAME)} to have mode 0600"))
        except OSError as e:
            checks.append(_check("warn", "daemon.socket_permissions", str(e),
                                 "restart the daemon with `browser-harness --reload`"))
        try:
            endpoint = _daemon_meta("endpoint_info").get("endpoint_info") or {}
        except Exception as e:
            endpoint = {}
            checks.append(_check("warn", "endpoint.info", str(e),
                                 "restart the daemon with `browser-harness --reload`"))
    else:
        endpoint = {}

    if endpoint:
        resolved_url = _doctor_text(endpoint.get("resolved_url"))
        checks.append(_check("pass", "endpoint.present", resolved_url))
        checks.append(_check("pass", "endpoint.source", _doctor_text(endpoint.get("source") or "unknown")))
        checks.append(_check(
            "pass" if endpoint.get("is_loopback") else ("warn" if endpoint.get("remote_allowed") else "fail"),
            "endpoint.loopback", _doctor_text(endpoint.get("host")),
            "use a 127.0.0.1/localhost endpoint or set BH_CDP_ALLOW_REMOTE=1 only for user-owned self-hosted CDP"))
        if endpoint.get("remote_allowed"):
            checks.append(_check("warn", "endpoint.remote_allowed", "BH_CDP_ALLOW_REMOTE=1",
                                 "bind CDP to loopback when possible"))
        for warning in endpoint.get("warnings") or []:
            warning = _doctor_text(warning)
            if "BH_CDP_ALLOW_REMOTE" in warning and endpoint.get("remote_allowed"):
                continue
            checks.append(_check("warn", "endpoint.warning", warning,
                                 "review BH_CDP_WS and prefer a loopback ws/http endpoint when possible"))
        checks.append(_check("pass", "endpoint.scheme", resolved_url.split(":", 1)[0]))
        version_detail = " ".join(_doctor_text(x) for x in (endpoint.get("browser"), endpoint.get("protocol_version")) if x)
        checks.append(_check("pass" if version_detail else "warn", "endpoint.version", version_detail,
                             "use a DevTools HTTP base URL in BH_CDP_WS when product/version detail is needed" if not version_detail else None))
    elif daemon:
        # Daemon up but endpoint metadata not yet available: warn (transient), don't fail.
        checks.append(_check("warn", "endpoint.present", "no live endpoint metadata",
                             "restart the daemon with `browser-harness --reload`"))
    else:
        checks.append(_check("fail", "endpoint.present", "no live endpoint metadata",
                             "run `browser-harness --setup` or set BH_CDP_WS to a local CDP endpoint"))

    checks.append(_check("pass", "network.default_offline", "default doctor performs local checks only"))

    if network:
        checks.append(_check("warn", "network.external", "network checks are not implemented yet",
                             "keep public IP/WebRTC checks behind --network"))
    return checks


def _doctor_status(checks):
    return "fail" if any(c["status"] == "fail" for c in checks) else ("warn" if any(c["status"] == "warn" for c in checks) else "pass")


def run_doctor(json_output=False, network=False):
    """Read-only diagnostics. Exit 0 unless a required local check fails."""
    import platform
    cur = _version()
    mode = _install_mode()
    cur_display = cur or "(unknown)"
    checks = _doctor_checks(network=network)
    status = _doctor_status(checks)
    connections = browser_connections()
    if json_output:
        payload = {
            "status": status,
            "checks": checks,
            "browser_connections": connections,
        }
        print(json.dumps(payload, indent=2))
        return 1 if status == "fail" else 0

    print("browser-harness doctor")
    print(f"  platform          {platform.system()} {platform.release()}")
    print(f"  python            {sys.version.split()[0]}")
    print(f"  version           {cur_display} ({mode})")
    for check in checks:
        mark = {"pass": "ok  ", "warn": "WARN", "fail": "FAIL"}[check["status"]]
        detail = f" - {check['detail']}" if check.get("detail") else ""
        fix = f" ({check['fix']})" if check.get("fix") else ""
        print(f"  [{mark}] {check['id']}{detail}{fix}")

    # Modern row-style summary so agents can grep "active browser connections".
    conn_mark = "ok  " if connections else "WARN"
    print(f"  [{conn_mark}] active browser connections — {len(connections)}")
    for conn in connections:
        page = conn.get("page")
        if page:
            title = _doctor_short_text(page["title"])
            url = _doctor_short_text(page["url"])
            print(f"        {conn['name']} — active page: {title} — {url}")
        else:
            print(f"        {conn['name']} — active page: (no real page)")
    return 1 if status == "fail" else 0


def _prompt_yes(question, default_yes=True, yes=False):
    if yes:
        return True
    suffix = "[Y/n]" if default_yes else "[y/N]"
    try:
        ans = input(f"{question} {suffix} ").strip().lower()
    except EOFError:
        return default_yes
    if not ans:
        return default_yes
    return ans.startswith("y")


def run_update(yes=False):
    """Pull the latest version and (after prompt) restart the daemon so it picks up changed code.

    Exit 0 on success, non-zero on failure."""
    cur, latest, newer = check_for_update()
    if cur and latest and not newer:
        print(f"browser-harness is up to date ({cur}).")
        return 0
    if cur and latest:
        print(f"updating browser-harness: {cur} -> {latest}")
    elif latest:
        print(f"installed version unknown; will try to update to {latest}.")
    else:
        print("could not reach github; will try to update anyway.")

    mode = _install_mode()
    if mode == "git":
        repo = _repo_dir()
        status = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"], capture_output=True, text=True)
        if status.returncode != 0:
            print(f"git status failed: {status.stderr.strip()}", file=sys.stderr)
            return 1
        if status.stdout.strip():
            print(f"refusing to update: uncommitted changes in {repo}", file=sys.stderr)
            print("commit or stash them first, or run `git -C %s pull` yourself." % repo, file=sys.stderr)
            return 1
        r = subprocess.run(["git", "-C", str(repo), "pull", "--ff-only"])
        if r.returncode != 0:
            return r.returncode
    elif mode == "pypi":
        tool_upgrade = subprocess.run(["uv", "tool", "upgrade", "browser-harness"])
        if tool_upgrade.returncode != 0:
            pip = subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "browser-harness"])
            if pip.returncode != 0:
                return pip.returncode
    else:
        print("unknown install mode; can't auto-update.", file=sys.stderr)
        return 1

    cache = _cache_read()
    cache.pop("banner_shown_on", None)
    _cache_write(cache)

    if daemon_alive():
        if _prompt_yes("restart the running daemon so it picks up the new code?", default_yes=True, yes=yes):
            restart_daemon()
            print("daemon stopped; it will auto-restart on next `browser-harness` call.")
        else:
            print("daemon left running on old code. run `browser-harness` and it'll use the new code after the daemon recycles.")
    print("update complete.")
    return 0
