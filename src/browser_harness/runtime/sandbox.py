"""Sandbox for agent runtime — restricts imports and exec to typed tool calls."""
from __future__ import annotations

import builtins
from typing import Any

# Modules forbidden in agent runtime
FORBIDDEN_MODULES = frozenset({
    "browser_harness._ipc",
    "browser_harness.helpers",
    "browser_harness.stealth_helpers",
    "browser_harness.login_session",
    "urllib.request",
    "urllib.error",
    "subprocess",
    "socket",
    "os",
    "sys",
    "ctypes",
    "multiprocessing",
    "threading",
    "signal",
    "fcntl",
    "winreg",
})

FORBIDDEN_NAMES = frozenset({
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


class AgentSandbox:
    """Restricts agent runtime to typed tool calls only."""

    def __init__(self, tool_registry: dict[str, Any]):
        self._tools = tool_registry
        self._namespace: dict[str, Any] = {}
        self._denied: list[str] = []

    def call(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        if tool_name not in self._tools:
            return {"status": "denied", "reason": f"unknown tool: {tool_name}"}

        if tool_name in FORBIDDEN_NAMES:
            return {"status": "denied", "reason": f"forbidden tool: {tool_name}"}

        tool = self._tools[tool_name]
        return tool(**params)

    def eval_restricted(self, expression: str) -> dict[str, Any]:
        """Agent cannot eval arbitrary Python — only tool calls."""
        return {
            "status": "denied",
            "reason": "arbitrary Python execution not available in agent runtime; use typed tool calls",
        }

    def check_import(self, module_name: str) -> dict[str, Any]:
        if module_name in FORBIDDEN_MODULES:
            return {"status": "denied", "reason": f"import forbidden in agent runtime: {module_name}"}
        return {"status": "allowed"}

    @property
    def denied_attempts(self) -> list[str]:
        return list(self._denied)

    def available_tools(self) -> list[str]:
        return [name for name in self._tools if name not in FORBIDDEN_NAMES]
