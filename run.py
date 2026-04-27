import os, sys

from admin import (
    _version,
    ensure_daemon,
    restart_daemon,
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
  browser-harness --setup          interactively attach to your running browser
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
        sys.exit(run_setup())
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
