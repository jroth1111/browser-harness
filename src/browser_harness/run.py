import importlib.util
import os
import sys
import urllib.request
from pathlib import Path

# Windows default stdout encoding is cp1252, which can't encode the 🟢 marker
# helpers prepend to tab titles (or anything else outside Latin-1). Force UTF-8
# so `print(page_info())` doesn't UnicodeEncodeError on Windows.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from .admin import (
    _version,
    NAME,
    daemon_alive,
    ensure_daemon,
    list_cloud_profiles,
    print_update_banner,
    restart_daemon,
    run_launch_profile,
    run_doctor,
    run_setup,
    run_update,
    start_remote_daemon,
    stop_remote_daemon,
    sync_local_profile,
)
from .helpers import *
from .agent_helpers import *  # noqa: F401,F403  agent-editable namespace
from .response import Response
from .runtime.dev_runtime import run_dev  # noqa: F401

HELP = """Browser Harness

Read SKILL.md for the default workflow and examples.

Typical usage:
  browser-harness <<'PY'
  ensure_real_tab()
  print(page_info())
  PY

Helpers are pre-imported. The daemon auto-starts and connects to the running browser.

Commands:
  browser-harness --version        print the installed version
  browser-harness --doctor [--json] [--network]
                                   diagnose local daemon, endpoint, and CDP state
  browser-harness --setup [--accept-remote-debugging-dialog]
                                   interactively attach to your running browser
  browser-harness --launch-profile PATH [--port PORT] [--url URL] [--chrome PATH] [--json]
                                   launch visible Chrome with loopback CDP
  browser-harness --skill-learning-gate CANDIDATE.json [...]
                                   validate empirical skill-learning candidates
  browser-harness --update [-y]    pull the latest version (agents: pass -y)
  browser-harness --reload         stop the daemon so next call picks up code changes
  browser-harness --handoff ID     complete a human-in-the-loop challenge handoff
"""


def _skill_learning_gate_main():
    try:
        from .skill_learning_gate import main

        return main
    except ModuleNotFoundError:
        path = Path(__file__).resolve().with_name("skill_learning_gate.py")
        spec = importlib.util.spec_from_file_location("skill_learning_gate", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.main


# Probe /json/version (not a bare TCP connect) so a non-Chrome process bound to
# 9222/9223 doesn't masquerade as Chrome and skip the cloud bootstrap. Mirrors
# daemon.py's fallback probe.
def _local_chrome_listening():
    for port in (9222, 9223):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=0.3).close()
            return True
        except OSError:
            pass
    return False


# BU_CDP_URL / BU_CDP_WS (and BH_* aliases) are documented to override local
# Chrome discovery, so they must also block cloud auto-bootstrap. Without this
# guard, start_remote_daemon() in admin.py overwrites the WS in the daemon env
# with a cloud WebSocket URL, silently replacing the user's explicit endpoint
# and billing them for a cloud browser they never asked for.
def _explicit_cdp_configured():
    return bool(
        os.environ.get("BU_CDP_URL")
        or os.environ.get("BU_CDP_WS")
        or os.environ.get("BH_CDP_URL")
        or os.environ.get("BH_CDP_WS")
    )


def _capture_session_after_handoff(request, session_broker=None):
    """Capture cookies + storage from the daemon-controlled tab after the
    user finishes a challenge.  Returns a SecretRef on success, None on
    failure.  The caller decides how to surface the failure.
    """
    from . import helpers
    from .sessions import login_adapter
    from .sessions.broker import SessionBroker

    broker = session_broker or SessionBroker()
    try:
        cookies = login_adapter.browser_cookies(helpers.cdp, [request.url])
    except Exception as e:
        print(f"warning: cookie capture failed: {e}", file=sys.stderr)
        cookies = []
    try:
        storage = login_adapter.storage_value_snapshot(helpers.cdp)
    except Exception as e:
        print(f"warning: storage capture failed: {e}", file=sys.stderr)
        storage = {"localStorage": {}, "sessionStorage": {}}

    if not cookies and not storage.get("localStorage") and not storage.get("sessionStorage"):
        return None

    ref = broker.store_secret_bundle(
        origin=request.origin,
        cookies=cookies,
        local_storage=storage.get("localStorage", {}) or {},
        session_storage=storage.get("sessionStorage", {}) or {},
        allowed_actions=["read"],
    )
    cookie_names = sorted({c.get("name", "") for c in cookies if c.get("name")})
    has_local = bool(storage.get("localStorage"))
    has_session = bool(storage.get("sessionStorage"))
    print(f"Captured session: {len(cookie_names)} cookies "
          f"(local_storage={has_local}, session_storage={has_session}).")
    if cookie_names:
        print(f"  cookie names: {', '.join(cookie_names)}")
    return ref


def _run_handoff(handoff_id: str, session_broker=None) -> None:
    from . import helpers
    from .authority.handoff import HandoffBroker

    broker = HandoffBroker()
    request = broker.get(handoff_id)
    if not request:
        print(f"handoff {handoff_id} not found or expired", file=sys.stderr)
        sys.exit(1)

    print(f"Challenge: {request.challenge_kind}")
    print(f"URL: {request.url}")
    print(f"Origin: {request.origin}")
    print()

    daemon_available = True
    try:
        helpers.new_tab(request.url)
    except Exception as e:
        daemon_available = False
        print(f"daemon unavailable ({e}); falling back to system browser", file=sys.stderr)
        import webbrowser
        webbrowser.open(request.url)

    print("Browser opened. Complete the challenge, then press Enter to continue...")
    input()

    ref = None
    if daemon_available:
        ref = _capture_session_after_handoff(request, session_broker=session_broker)
    session_ref_id = ref.ref_id if ref else ""

    token = broker.complete(handoff_id, session_ref_id=session_ref_id)
    print(f"Handoff complete. Resume token signed (nonce={token.nonce}).")
    if session_ref_id:
        print(f"Session ref: {session_ref_id}")
    print("The agent can now retry the original request.")


def main():
    args = sys.argv[1:]
    if args and args[0] in {"-h", "--help"}:
        print(HELP)
        return
    if args and args[0] == "--version":
        print(_version() or "unknown")
        return
    if args and args[0] == "--doctor":
        allowed = {"--json", "--network"}
        unknown = [a for a in args[1:] if a not in allowed]
        if unknown:
            print(f"unsupported --doctor flag: {unknown[0]}", file=sys.stderr)
            sys.exit(2)
        sys.exit(run_doctor(json_output="--json" in args[1:], network="--network" in args[1:]))
    if args and args[0] == "--setup":
        allowed = {"--accept-remote-debugging-dialog"}
        unknown = [a for a in args[1:] if a not in allowed]
        if unknown:
            print(f"unsupported --setup flag: {unknown[0]}", file=sys.stderr)
            sys.exit(2)
        sys.exit(run_setup(accept_remote_debugging_dialog="--accept-remote-debugging-dialog" in args[1:]))
    if args and args[0] == "--launch-profile":
        if len(args) < 2 or args[1].startswith("-"):
            sys.exit("Usage: browser-harness --launch-profile PATH [--port PORT] [--url URL] [--chrome PATH] [--headless] [--window-size WxH] [--json]")
        profile_path = args[1]
        port = 9222
        url = "about:blank"
        chrome_path = None
        json_output = False
        headless = False
        window_size = None
        i = 2
        def require_value(flag):
            if i + 1 >= len(args) or args[i + 1].startswith("-"):
                print(f"{flag} requires a value", file=sys.stderr)
                sys.exit(2)
            return args[i + 1]
        while i < len(args):
            flag = args[i]
            if flag == "--json":
                json_output = True
                i += 1
                continue
            if flag == "--headless":
                headless = True
                i += 1
                continue
            if flag == "--window-size":
                value = require_value(flag)
                parts = value.split("x")
                if len(parts) != 2 or not all(p.isdigit() for p in parts):
                    print(f"invalid --window-size value: {value} (expected WxH)", file=sys.stderr)
                    sys.exit(2)
                window_size = (int(parts[0]), int(parts[1]))
                i += 2
                continue
            if flag not in {"--port", "--url", "--chrome"} or i + 1 >= len(args):
                print(f"unsupported --launch-profile flag: {flag}", file=sys.stderr)
                sys.exit(2)
            value = require_value(flag)
            if flag == "--port":
                try:
                    port = int(value)
                except ValueError:
                    print(f"invalid --port value: {value}", file=sys.stderr)
                    sys.exit(2)
            elif flag == "--url":
                url = value
            elif flag == "--chrome":
                chrome_path = value
            i += 2
        sys.exit(run_launch_profile(profile_path, port=port, url=url, chrome_path=chrome_path,
                                    headless=headless, window_size=window_size, json_output=json_output))
    if args and args[0] == "--skill-learning-gate":
        _skill_learning_gate_main()(args[1:])
        return
    if args and args[0] == "--update":
        allowed = {"-y", "--yes"}
        unknown = [a for a in args[1:] if a not in allowed]
        if unknown:
            print(f"unsupported --update flag: {unknown[0]}", file=sys.stderr)
            sys.exit(2)
        yes = any(a in {"-y", "--yes"} for a in args[1:])
        sys.exit(run_update(yes=yes))
    if args and args[0] == "--reload":
        restart_daemon()
        print("daemon stopped — will restart fresh on next call")
        return
    if args and args[0] == "--handoff":
        if len(args) < 2 or args[1].startswith("-"):
            sys.exit("Usage: browser-harness --handoff <handoff_id>")
        _run_handoff(args[1])
        return
    if args and args[0] == "--debug-clicks":
        os.environ["BH_DEBUG_CLICKS"] = "1"
        args = args[1:]
    if args and args[0] == "-c":
        if len(args) < 2:
            sys.exit("Usage: browser-harness -c \"print(page_info())\"")
        code = args[1]
    elif not args and not sys.stdin.isatty():
        code = sys.stdin.read()
        if not code.strip():
            sys.exit("Usage: browser-harness -c \"print(page_info())\"")
    else:
        sys.exit("Usage: browser-harness -c \"print(page_info())\"")
    print_update_banner()
    # Auto-bootstrap a cloud browser is opt-in via BU_AUTOSPAWN — BROWSER_USE_API_KEY alone
    # is not enough, since the key is commonly set for unrelated reasons (profile sync,
    # cloud API calls, parent agents managing their own session). An explicit BU_CDP_URL
    # / BU_CDP_WS (or BH_* alias) also blocks the spawn so we honour the precedence
    # install.md promises.
    if (
        not daemon_alive()
        and not _local_chrome_listening()
        and not _explicit_cdp_configured()
        and os.environ.get("BROWSER_USE_API_KEY")
        and os.environ.get("BU_AUTOSPAWN")
    ):
        start_remote_daemon(NAME)
    ensure_daemon()
    run_dev(code)


if __name__ == "__main__":
    main()
