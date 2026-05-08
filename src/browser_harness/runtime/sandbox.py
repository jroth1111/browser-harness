"""Real sandbox enforcement for agent runtime.

Two layers:
1. Audit hook — sys.addaudithook rejects forbidden imports/exec/compile
2. Restricted builtins — dangerous builtins removed from __builtins__

Used by agent_worker.py (subprocess). NOT honour-system — enforcement
happens at the Python runtime level.
"""
from __future__ import annotations

import sys
from typing import Any

# Modules the worker is allowed to import
WORKER_ALLOWLIST = frozenset({
    "json",
    "dataclasses",
    "typing",
    "enum",
    "time",
    "hashlib",
    "struct",
    "collections",
    "functools",
    "abc",
    "browser_harness.capabilities.models",
    "browser_harness.authority.policy",
    "browser_harness.authority.challenge",
    "browser_harness.authority.action_policy",
})

# Builtins to remove from worker namespace
RESTRICTED_BUILTINS = frozenset({
    "exec",
    "eval",
    "compile",
    "__import__",
    "breakpoint",
    "memoryview",
})

# Tool names forbidden in agent runtime
FORBIDDEN_TOOLS = frozenset({
    "cdp",
    "_send",
    "_ipc",
    "browser_cookies",
    "save_auth_profile",
    "load_auth_profile",
    "stealth_session",
    "solve_turnstile",
    "navigate_via_google",
    "http_get_browser_session_response",
    "exec",
    "eval",
    "compile",
    "__import__",
    "open",
    "globals",
    "locals",
})


def install_audit_hook() -> None:
    """Install sys.addaudithook that rejects forbidden operations.

    Must be called before any user code runs in the worker process.
    """
    # Pre-compute all parent packages of allowlisted modules so imports
    # like browser_harness.capabilities (parent of .models) aren't blocked.
    _allowed_prefixes: set[str] = set()
    for mod in WORKER_ALLOWLIST:
        parts = mod.split(".")
        for i in range(len(parts)):
            _allowed_prefixes.add(".".join(parts[: i + 1]))

    def _audit(event: str, args: tuple) -> None:
        if event == "import":
            module = args[0] if args else ""
            # Allow stdlib internals needed by allowlisted modules
            if module.startswith("_") and not module.startswith("__"):
                return
            # Check top-level module for dangerous imports
            top = module.split(".")[0]
            if top in ("urllib", "socket", "subprocess", "ctypes",
                       "multiprocessing", "threading", "signal",
                       "fcntl", "winreg"):
                if module not in _allowed_prefixes:
                    raise ImportError(f"import denied by sandbox: {module}")
            # Block browser_harness internals not in allowlist
            if top == "browser_harness" and module not in _allowed_prefixes:
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


# --- Legacy compat (agent_runtime.py imports these; deleted in Phase 3) ---

FORBIDDEN_NAMES = FORBIDDEN_TOOLS
FORBIDDEN_MODULES = frozenset({
    "urllib.request", "urllib.parse", "http.client",
    "socket", "subprocess", "ctypes",
    "multiprocessing", "threading", "signal",
})


class AgentSandbox:
    """Legacy sandbox shim — delegates to FORBIDDEN_TOOLS deny list.

    Phase 3 deletes agent_runtime.py and this class.
    """

    def __init__(self, tool_registry: dict[str, Any]) -> None:
        self._registry = tool_registry

    def call(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        if tool_name in FORBIDDEN_TOOLS:
            return {"status": "denied", "reason": f"forbidden tool: {tool_name}"}
        impl = self._registry.get(tool_name)
        if impl is None:
            return {"status": "denied", "reason": f"unknown tool: {tool_name}"}
        return impl(**params)

    def available_tools(self) -> list[str]:
        return sorted(self._registry.keys())

    def check_import(self, module: str) -> dict[str, str]:
        top = module.split(".")[0]
        if top in ("urllib", "socket", "subprocess", "ctypes"):
            return {"status": "denied", "reason": f"import denied: {module}"}
        if top == "browser_harness" and module not in WORKER_ALLOWLIST:
            return {"status": "denied", "reason": f"import denied: {module}"}
        return {"status": "allowed"}

    def eval_restricted(self, code: str) -> dict[str, str]:
        return {"status": "denied", "reason": "eval denied by sandbox"}
