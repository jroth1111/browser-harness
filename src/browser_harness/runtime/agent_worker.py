"""Agent worker — subprocess with real sandbox enforcement.

Spawned by agent_host.py. Installs audit hook before any tool code runs.
Receives JSON-over-stdio tool calls, dispatches to tool implementations,
calls back to host for transport operations.
"""
from __future__ import annotations

import json
import struct
import sys

from .sandbox import install_audit_hook, restrict_builtins, FORBIDDEN_TOOLS

# Only these tools may be dispatched; everything else is denied.
ALLOWED_TOOLS = frozenset({
    "fetch",
    "click",
    "extract",
    "navigate",
    "fill",
    "press",
    "scroll",
    "snapshot",
    "wait",
})

# Install enforcement BEFORE any other imports
install_audit_hook()

# Restrict builtins
_safe_builtins = restrict_builtins()
__builtins__ = _safe_builtins  # type: ignore[assignment]

# Now import allowed modules
from ..capabilities.models import (  # noqa: E402
    RiskLevel,
    WebRequest,
    WebAction,
)


def _read_frame() -> dict:
    """Read a length-prefixed JSON frame from stdin."""
    raw_len = sys.stdin.buffer.read(4)
    if not raw_len or len(raw_len) < 4:
        sys.exit(0)
    length = struct.unpack(">I", raw_len)[0]
    if length > 10 * 1024 * 1024:  # 10MB limit
        _write_frame({"type": "error", "error": "frame too large"})
        sys.exit(3)
    data = sys.stdin.buffer.read(length)
    return json.loads(data)


def _write_frame(msg: dict) -> None:
    """Write a length-prefixed JSON frame to stdout."""
    data = json.dumps(msg, default=str).encode()
    sys.stdout.buffer.write(struct.pack(">I", len(data)))
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()


def _validate_params(params: dict) -> dict | None:
    """Validate tool params. Returns error dict or None if valid."""
    if not isinstance(params, dict):
        return {"type": "error", "error": "params must be a dict"}
    return None


def _dispatch(msg: dict) -> dict:
    """Dispatch a tool call message."""
    msg_id = msg.get("id", 0)
    tool = msg.get("tool", "")
    params = msg.get("params", {})

    if tool in FORBIDDEN_TOOLS:
        return {"type": "result", "id": msg_id, "status": "denied",
                "reason": f"forbidden tool: {tool}"}

    if tool not in ALLOWED_TOOLS:
        return {"type": "result", "id": msg_id, "status": "denied",
                "reason": f"unknown tool: {tool}"}

    validation = _validate_params(params)
    if validation:
        validation["id"] = msg_id
        return validation

    return {"type": "callback", "id": msg_id, "tool": tool, "params": params}


def worker_main() -> int:
    """Main loop for the worker process."""
    try:
        while True:
            msg = _read_frame()
            if msg.get("type") == "shutdown":
                return 0
            result = _dispatch(msg)
            _write_frame(result)
    except (KeyboardInterrupt, SystemExit):
        return 0
    except Exception as e:
        _write_frame({"type": "error", "error": str(e)})
        return 1


if __name__ == "__main__":
    sys.exit(worker_main())
