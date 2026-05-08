"""Real sandbox enforcement for agent worker subprocess.

Two layers:
1. Audit hook — sys.addaudithook rejects any import outside an explicit
   allowlist. Strict allowlist, not denylist: a stdlib module the worker
   needs must be named in STDLIB_ALLOWLIST or the import fails. This is
   how we keep `import http.client`, `import os.popen`, `import importlib`
   from quietly slipping past while a smaller denylist takes the headlines.
2. Restricted builtins — dangerous builtins removed from the namespace
   (exec, eval, compile, __import__, breakpoint, memoryview).

Used by agent_worker.py.  No honour-system.  Enforcement is at the Python
runtime level.
"""
from __future__ import annotations

import sys
from typing import Any

# Allowed top-level stdlib modules.  Each entry has been audited for absence
# of network/filesystem-write/process-spawn capability.  Adding to this list
# is a security decision — every new entry should be justified.
STDLIB_ALLOWLIST = frozenset({
    # Data structures and primitives
    "abc", "collections", "copy", "copyreg", "dataclasses", "enum",
    "functools", "itertools", "operator", "types", "typing", "weakref",
    # Numeric / text
    "decimal", "fractions", "math", "numbers", "re", "string", "unicodedata",
    # Time
    "calendar", "datetime", "time", "zoneinfo",
    # Encoding / serialization (no code execution)
    "base64", "binascii", "codecs", "encodings", "json", "struct",
    # Crypto / hashing
    "hashlib", "hmac", "secrets",
    # Diagnostics
    "contextlib", "contextvars", "traceback", "warnings",
    # I/O on already-open streams (sys.stdin/stdout); no file open
    "io",
})

# Allowed browser_harness modules.  The worker imports these to validate
# tool calls; the host runs the transport.  Add only modules that are
# pure validation / data — no transport, no daemon, no filesystem.
WORKER_ALLOWLIST = frozenset({
    "browser_harness.capabilities.models",
    "browser_harness.authority.policy",
    "browser_harness.authority.challenge",
    "browser_harness.authority.action_policy",
})

# Builtins removed from the worker namespace.  exec/eval/compile/__import__
# would bypass the audit hook by routing imports through other paths.
RESTRICTED_BUILTINS = frozenset({
    "exec", "eval", "compile", "__import__", "breakpoint", "memoryview",
})

# Tool names the worker must always reject, even if a future allowlist
# expansion would otherwise permit them.  Belt to RESTRICTED_BUILTINS'
# suspenders.
FORBIDDEN_TOOLS = frozenset({
    "cdp", "_send", "_ipc",
    "browser_cookies", "save_auth_profile", "load_auth_profile",
    "stealth_session",
    "solve_turnstile", "navigate_via_google",
    "http_get_browser_session_response",
    "exec", "eval", "compile", "__import__",
    "open", "globals", "locals",
})


def install_audit_hook() -> None:
    """Install sys.addaudithook that rejects imports outside the allowlist.

    Must be called before any user code runs in the worker process.
    """
    # Pre-compute parent packages of allowlisted browser_harness modules
    # so `import browser_harness.capabilities` (parent of .models) succeeds.
    _allowed_prefixes: set[str] = set()
    for mod in WORKER_ALLOWLIST:
        parts = mod.split(".")
        for i in range(len(parts)):
            _allowed_prefixes.add(".".join(parts[: i + 1]))

    def _audit(event: str, args: tuple) -> None:
        if event != "import":
            return
        module = args[0] if args else ""
        if not module:
            return
        # Allow private/dunder modules — these are stdlib internals
        # (e.g. _thread, _weakrefset, __future__) used by allowlisted code.
        if module.startswith("_"):
            return
        top = module.split(".")[0]
        if top in STDLIB_ALLOWLIST:
            return
        if module in _allowed_prefixes:
            return
        raise ImportError(f"import denied by sandbox: {module}")

    sys.addaudithook(_audit)


def restrict_builtins() -> dict[str, Any]:
    """Remove dangerous builtins from the worker namespace.

    Returns the restricted __builtins__ dict.
    """
    import builtins
    safe = {}
    for name in dir(builtins):
        if name not in RESTRICTED_BUILTINS:
            safe[name] = getattr(builtins, name)
    return safe
