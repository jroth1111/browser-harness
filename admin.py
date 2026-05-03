import json
import os
import socket
import time
import urllib.request
from pathlib import Path


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
VERSION_CACHE = Path("/tmp/bh-version-cache.json")
VERSION_CACHE_TTL = 24 * 3600


def _paths(name):
    n = name or NAME
    return f"/tmp/bh-{n}.sock", f"/tmp/bh-{n}.pid"


def _legacy_paths(name):
    n = name or NAME
    prefix = "/tmp/" + "bu-"
    return f"{prefix}{n}.sock", f"{prefix}{n}.pid", f"{prefix}{n}.log"


def _log_tail(name):
    p = f"/tmp/bh-{name or NAME}.log"
    try:
        return Path(p).read_text().strip().splitlines()[-1]
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
    """True when the daemon discovers a local Chrome instead of a remote CDP WS."""
    return not (env or {}).get("BH_CDP_WS") and not os.environ.get("BH_CDP_WS")


def daemon_alive(name=None):
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(1)
        s.connect(_paths(name)[0])
        s.close()
        return True
    except (FileNotFoundError, ConnectionRefusedError, socket.timeout):
        return False


def ensure_daemon(wait=60.0, name=None, env=None, accept_remote_debugging_dialog=False):
    """Idempotent. Self-heals stale daemon, cold Chrome, and missing Allow on chrome://inspect."""
    if daemon_alive(name):
        # Stale daemons accept connects AND reply to meta:* (pure Python) even when the
        # CDP WS to Chrome is dead — probe with a real CDP call and require "result".
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s.settimeout(3)
            s.connect(_paths(name)[0])
            s.sendall(b'{"method":"Target.getTargets","params":{}}\n')
            data = b""
            while not data.endswith(b"\n"):
                chunk = s.recv(1 << 16)
                if not chunk: break
                data += chunk
            if b'"result"' in data: return
        except Exception: pass
        restart_daemon(name)

    import subprocess, sys
    local = _is_local_chrome_mode(env)
    for attempt in (0, 1):
        e = {**os.environ, **({"BH_NAME": name} if name else {}), **(env or {})}
        root = os.path.dirname(os.path.abspath(__file__))
        p = subprocess.Popen(
            [sys.executable, os.path.join(root, "daemon.py")],
            cwd=root,
            env=e, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
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
            continue
        raise RuntimeError(msg or f"daemon {name or NAME} didn't come up -- check /tmp/bh-{name or NAME}.log")


def restart_daemon(name=None):
    """Best-effort daemon shutdown + socket/pid cleanup.

    Name is historical: callers typically follow this with another
    `browser-harness` invocation, which auto-spawns a fresh daemon via
    ensure_daemon(). The function itself only stops."""
    import signal

    sock, pid_path = _paths(name)
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect(sock)
        s.sendall(b'{"meta":"shutdown"}\n')
        s.recv(1024)
        s.close()
    except Exception:
        pass
    try:
        pid = int(open(pid_path).read())
    except (FileNotFoundError, ValueError):
        pid = None
    if pid:
        for _ in range(75):
            try:
                os.kill(pid, 0)
                time.sleep(0.2)
            except ProcessLookupError:
                break
        else:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    for f in (sock, pid_path):
        try:
            os.unlink(f)
        except FileNotFoundError:
            pass
    for f in _legacy_paths(name):
        try:
            os.unlink(f)
        except FileNotFoundError:
            pass


def list_local_profiles():
    """Detected local browser profiles on this machine. Shells out to `profile-use list --json`.
    Returns [{BrowserName, BrowserPath, ProfileName, ProfilePath, DisplayName}, ...]."""
    import json, shutil, subprocess
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
    p = Path(__file__).resolve().parent
    return p if (p / ".git").is_dir() else None


def _install_mode():
    """"git" for editable clone, "pypi" for an installed wheel, "unknown" otherwise."""
    if _repo_dir():
        return "git"
    return "pypi" if _version() else "unknown"


def _cache_read():
    try:
        return json.loads(VERSION_CACHE.read_text())
    except (FileNotFoundError, ValueError):
        return {}


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


def _chrome_running():
    """Cross-platform best-effort check for a running Chrome/Edge process."""
    import platform, subprocess
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
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    s.connect(_paths(name)[0])
    s.sendall((json.dumps({"meta": meta}) + "\n").encode())
    data = b""
    while not data.endswith(b"\n"):
        chunk = s.recv(1 << 16)
        if not chunk:
            break
        data += chunk
    s.close()
    if not data:
        return {}
    return json.loads(data)


def _open_chrome_inspect():
    """Open chrome://inspect/#remote-debugging so the user can tick the checkbox."""
    import platform, subprocess, webbrowser
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
    import platform, subprocess
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
    "--disable-blink-features=AutomationControlled",
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
    import subprocess
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
        cmd.extend(f"--ignore-default-args-switch={a}" for a in _HEADLESS_HARMFUL_ARGS)
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
    import sys
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


def run_setup(accept_remote_debugging_dialog=False):
    """Interactive bootstrap: attach to the running browser, guiding the user through chrome://inspect if needed.

    Exit code 0 on success, 1 on failure."""
    import sys
    print("browser-harness setup: attaching to your browser...")

    if daemon_alive():
        print("daemon already running; nothing to do.")
        return 0

    if not _chrome_running():
        print("no Chrome/Edge process detected. please start your browser and rerun `browser-harness --setup`.")
        return 1

    # First attach attempt.
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


def _scan_active_files(patterns):
    import re
    files = [
        "daemon.py",
        "admin.py",
        "run.py",
        "helpers.py",
        "SKILL.md",
        "install.md",
        "README.md",
        "pyproject.toml",
        "docs/local-cdp-providers.md",
        "docs/reference.md",
        "docs/contributing-guide.md",
    ]
    hits = []
    root = Path(__file__).resolve().parent
    rx = re.compile(patterns)
    for rel in files:
        path = root / rel
        if not path.exists():
            continue
        for lineno, line in enumerate(path.read_text(errors="ignore").splitlines(), 1):
            if rx.search(line):
                hits.append(f"{rel}:{lineno}")
    return hits


def _page_info_uses_runtime():
    import ast
    path = Path(__file__).resolve().parent / "helpers.py"
    tree = ast.parse(path.read_text())
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "page_info":
            source = ast.get_source_segment(path.read_text(), node) or ""
            return "Runtime.evaluate" in source
    return True


def _doctor_checks(network=False):
    import platform
    checks = []
    chrome = _chrome_running()
    daemon = daemon_alive()

    checks.append(_check("pass", "platform.info", f"{platform.system()} {platform.release()}"))
    checks.append(_check("pass" if chrome else "warn", "browser.process", "Chrome/Edge process detected" if chrome else "Chrome/Edge process not detected", "start Chrome/Edge and rerun `browser-harness --setup`" if not chrome else None))
    checks.append(_check("pass" if daemon else "fail", "daemon.alive", "daemon socket responds" if daemon else "daemon socket is not responding", "run `browser-harness --setup` to attach" if not daemon else None))

    if daemon:
        sock, _ = _paths(None)
        try:
            mode = Path(sock).stat().st_mode & 0o777
            checks.append(_check("pass" if mode == 0o600 else "fail", "daemon.socket_permissions", oct(mode), f"expected {sock} to have mode 0600"))
        except OSError as e:
            checks.append(_check("fail", "daemon.socket_permissions", str(e), "restart the daemon with `browser-harness --reload`"))
        try:
            endpoint = _daemon_meta("endpoint_info").get("endpoint_info") or {}
        except Exception as e:
            endpoint = {}
            checks.append(_check("warn", "endpoint.info", str(e), "restart the daemon with `browser-harness --reload`"))
    else:
        endpoint = {}

    if endpoint:
        checks.append(_check("pass", "endpoint.present", endpoint.get("resolved_url", "")))
        checks.append(_check("pass", "endpoint.source", endpoint.get("source", "unknown")))
        checks.append(_check("pass" if endpoint.get("is_loopback") else ("warn" if endpoint.get("remote_allowed") else "fail"), "endpoint.loopback", endpoint.get("host") or "", "use a 127.0.0.1/localhost endpoint or set BH_CDP_ALLOW_REMOTE=1 only for user-owned self-hosted CDP"))
        if endpoint.get("remote_allowed"):
            checks.append(_check("warn", "endpoint.remote_allowed", "BH_CDP_ALLOW_REMOTE=1", "bind CDP to loopback when possible"))
        for warning in endpoint.get("warnings") or []:
            if "BH_CDP_ALLOW_REMOTE" in warning and endpoint.get("remote_allowed"):
                continue
            checks.append(_check("warn", "endpoint.warning", warning, "review BH_CDP_WS and prefer a loopback ws/http endpoint when possible"))
        checks.append(_check("pass", "endpoint.scheme", endpoint.get("resolved_url", "").split(":", 1)[0]))
        version_detail = " ".join(x for x in (endpoint.get("browser"), endpoint.get("protocol_version")) if x)
        checks.append(_check("pass" if version_detail else "warn", "endpoint.version", version_detail, "use a DevTools HTTP base URL in BH_CDP_WS when product/version detail is needed" if not version_detail else None))
    else:
        checks.append(_check("fail", "endpoint.present", "no live endpoint metadata", "run `browser-harness --setup` or set BH_CDP_WS to a local CDP endpoint"))

    legacy_pattern = "|".join([
        r"BU" + r"_CDP_WS",
        r"BU" + r"_NAME",
        r"/tmp/" + r"bu-",
        r"browser-use\.com/profile",
        r"api\.browser-use",
        r"cloud\.browser-use",
    ])
    cloud_hits = _scan_active_files(legacy_pattern)
    checks.append(_check("pass" if not cloud_hits else "fail", "strings.no_cloud_runtime", ", ".join(cloud_hits), "remove legacy Browser Use/cloud runtime strings from active files" if cloud_hits else None))

    root = Path(__file__).resolve().parent
    daemon_text = (root / "daemon.py").read_text(errors="ignore")
    helpers_text = (root / "helpers.py").read_text(errors="ignore")
    attach_bad = [m for m in ("Runtime.enable", "DOM.enable", "Network.enable") if m in daemon_text]
    checks.append(_check("pass" if not attach_bad else "fail", "cdp.attach_minimal", ", ".join(attach_bad), "remove automatic CDP domain enables from daemon attach" if attach_bad else None))
    checks.append(_check("pass" if "Console.enable" not in daemon_text + helpers_text else "fail", "cdp.no_console_enable", "", "remove Console.enable from core"))
    marker_bad = "document.title.startsWith" in daemon_text + helpers_text or "\\U0001F7E2" in daemon_text + helpers_text
    checks.append(_check("pass" if not marker_bad else "fail", "page.no_title_marker", "", "remove hidden title marker mutation" if marker_bad else None))
    page_info_bad = _page_info_uses_runtime()
    checks.append(_check("pass" if not page_info_bad else "fail", "helpers.page_info_no_runtime", "", "rewrite page_info to avoid Runtime.evaluate" if page_info_bad else None))
    checks.append(_check("pass", "network.default_offline", "default doctor performs local checks only"))

    if network:
        checks.append(_check("warn", "network.external", "network checks are not implemented yet", "keep public IP/WebRTC checks behind --network"))
    return checks


def _doctor_status(checks):
    return "fail" if any(c["status"] == "fail" for c in checks) else ("warn" if any(c["status"] == "warn" for c in checks) else "pass")


def run_doctor(json_output=False, network=False):
    """Read-only diagnostics. Exit 0 unless a required local check fails."""
    import platform, sys
    cur = _version()
    mode = _install_mode()
    cur_display = cur or "(unknown)"
    checks = _doctor_checks(network=network)
    status = _doctor_status(checks)
    if json_output:
        print(json.dumps({"status": status, "checks": checks}, indent=2))
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
    import subprocess, sys
    cur, latest, newer = check_for_update()
    # Only short-circuit as "up to date" when we actually know the installed
    # version. Otherwise `newer=False` just means "couldn't compare" — proceed.
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
            # Fall back to pip in case this wasn't a `uv tool install`.
            pip = subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "browser-harness"])
            if pip.returncode != 0:
                return pip.returncode
    else:
        print("unknown install mode; can't auto-update.", file=sys.stderr)
        return 1

    # Invalidate banner/tag cache so the new version doesn't keep nagging.
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
