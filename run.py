import os, sys

from admin import (
    _version,
    ensure_daemon,
    restart_daemon,
    run_launch_profile,
    run_doctor,
    run_setup,
    run_update,
)
from helpers import *

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
  browser-harness --update [-y]    pull the latest version (agents: pass -y)
  browser-harness --reload         stop the daemon so next call picks up code changes
"""


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
            sys.exit("Usage: browser-harness --launch-profile PATH [--port PORT] [--url URL] [--chrome PATH] [--json]")
        profile_path = args[1]
        port = 9222
        url = "about:blank"
        chrome_path = None
        json_output = False
        i = 2
        while i < len(args):
            flag = args[i]
            if flag == "--json":
                json_output = True
                i += 1
                continue
            if flag not in {"--port", "--url", "--chrome"} or i + 1 >= len(args):
                print(f"unsupported --launch-profile flag: {flag}", file=sys.stderr)
                sys.exit(2)
            value = args[i + 1]
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
        sys.exit(run_launch_profile(profile_path, port=port, url=url, chrome_path=chrome_path, json_output=json_output))
    if args and args[0] == "--update":
        yes = any(a in {"-y", "--yes"} for a in args[1:])
        sys.exit(run_update(yes=yes))
    if args and args[0] == "--reload":
        restart_daemon()
        print("daemon stopped — will restart fresh on next call")
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
    ensure_daemon()
    exec(code, globals())


if __name__ == "__main__":
    main()
