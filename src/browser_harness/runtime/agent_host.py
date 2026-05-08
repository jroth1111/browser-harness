"""Agent host — parent process that spawns sandboxed worker.

Owns transports, PolicyEngine, SessionBroker, AccessPlane. Spawns
agent_worker.py as a subprocess with audit hook enforcement. Communicates
via length-prefixed JSON-over-stdio.
"""
from __future__ import annotations

import json
import struct
import subprocess
import sys
from pathlib import Path
from typing import Any

from ..authority.action_policy import ActionPolicy
from ..authority.policy import PolicyEngine
from ..capabilities.models import RiskLevel, WebRequest, WebAction
from ..capabilities.resolver import AccessPlane


def _risk_from_str(risk: str) -> RiskLevel:
    try:
        return RiskLevel(risk)
    except ValueError:
        return RiskLevel.PUBLIC_READ


class AgentHost:
    """Parent process for the agent runtime.

    Spawns a sandboxed worker subprocess. Routes tool calls through
    PolicyEngine and AccessPlane.
    """

    def __init__(
        self,
        policy: PolicyEngine | None = None,
        access_plane: AccessPlane | None = None,
        action_policy: ActionPolicy | None = None,
    ):
        self.policy = policy or PolicyEngine()
        self.access_plane = access_plane or AccessPlane(policy=self.policy)
        self.action_policy = action_policy or ActionPolicy()
        self._worker: subprocess.Popen | None = None

    def _spawn_worker(self) -> subprocess.Popen:
        # -S skips usercustomize.  We pass the parent's sys.path via
        # PYTHONPATH so the editable install of browser_harness is
        # importable inside the child without full site-packages.
        worker_script = (
            "from browser_harness.runtime.agent_worker import worker_main; "
            "import sys; sys.exit(worker_main())"
        )
        import os
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(sys.path)
        env["BH_AGENT_WORKER"] = "1"
        proc = subprocess.Popen(
            [sys.executable, "-S", "-c", worker_script],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        self._worker = proc
        return proc

    def _send_frame(self, msg: dict) -> None:
        if not self._worker or not self._worker.stdin:
            raise RuntimeError("worker not running")
        data = json.dumps(msg, default=str).encode()
        self._worker.stdin.write(struct.pack(">I", len(data)))
        self._worker.stdin.write(data)
        self._worker.stdin.flush()

    def _recv_frame(self) -> dict:
        if not self._worker or not self._worker.stdout:
            raise RuntimeError("worker not running")
        raw_len = self._worker.stdout.read(4)
        if not raw_len or len(raw_len) < 4:
            raise RuntimeError("worker closed")
        length = struct.unpack(">I", raw_len)[0]
        data = self._worker.stdout.read(length)
        return json.loads(data)

    def call(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send a tool call to the worker and return the result."""
        if not self._worker:
            self._spawn_worker()

        self._send_frame({
            "type": "call",
            "id": 1,
            "tool": tool_name,
            "params": params,
        })

        response = self._recv_frame()

        if response.get("type") == "callback":
            # Worker validated the call; host executes the tool
            return self._execute_tool(response["tool"], response["params"])
        if response.get("type") == "result":
            return response
        if response.get("type") == "error":
            return {"status": "error", "reason": response.get("error", "unknown")}

        return {"status": "error", "reason": f"unexpected response: {response}"}

    def _execute_tool(self, tool: str, params: dict) -> dict[str, Any]:
        """Execute a tool call in the host process."""
        if tool == "fetch":
            return self._tool_fetch(**params)
        if tool == "click":
            return self._tool_click(**params)
        if tool == "extract":
            return self._tool_extract(**params)
        if tool == "navigate":
            return self._tool_navigate(**params)
        if tool == "fill":
            return self._tool_fill(**params)
        if tool == "press":
            return self._tool_press(**params)
        return {"status": "error", "reason": f"unknown tool: {tool}"}

    def shutdown(self) -> None:
        if self._worker:
            try:
                self._send_frame({"type": "shutdown"})
                self._worker.wait(timeout=5)
            except Exception:
                self._worker.kill()
            self._worker = None

    # --- Tool implementations (run in host, not worker) ---

    def _tool_fetch(self, url: str = "", risk: str = "public_read", **kw: Any) -> dict[str, Any]:
        request = WebRequest(
            url=url,
            risk=_risk_from_str(risk),
            method=kw.get("method", "GET"),
            auth_required=kw.get("auth_required", False),
        )
        result = self.access_plane.execute(request)
        return {
            "status": "ok" if result.status == 200 else result.block_state.value,
            "url": result.url,
            "source": result.source,
            "transport": result.transport.value,
            "block_state": result.block_state.value,
            "reason": result.reason,
        }

    def _tool_click(self, target: str = "", risk: str = "low_risk_write", **kw: Any) -> dict[str, Any]:
        action = WebAction(kind="click", target=target, risk=_risk_from_str(risk))
        decision = self.action_policy.authorize(action)
        if not decision.allowed:
            return {"status": decision.status, "reason": decision.reason}
        return {"status": "ok", "message": "authorized"}

    def _tool_extract(self, url: str = "", fields: list | None = None, **kw: Any) -> dict[str, Any]:
        risk = kw.get("risk", "public_read")
        request = WebRequest(url=url, risk=_risk_from_str(risk))
        decision = self.policy.authorize(request)
        if not decision.allowed:
            return {"status": decision.status, "reason": decision.reason}
        return {"status": "ok", "fields": fields or []}

    def _tool_navigate(self, url: str = "", risk: str = "public_read", **kw: Any) -> dict[str, Any]:
        request = WebRequest(url=url, risk=_risk_from_str(risk))
        decision = self.policy.authorize(request)
        if not decision.allowed:
            return {"status": decision.status, "reason": decision.reason}
        return {"status": "ok", "message": "authorized"}

    def _tool_fill(self, target: str = "", value: str = "", risk: str = "low_risk_write", **kw: Any) -> dict[str, Any]:
        action = WebAction(kind="fill", target=target, value=value, risk=_risk_from_str(risk))
        decision = self.action_policy.authorize(action)
        if not decision.allowed:
            return {"status": decision.status, "reason": decision.reason}
        return {"status": "ok", "message": "authorized"}

    def _tool_press(self, key: str = "", risk: str = "low_risk_write", **kw: Any) -> dict[str, Any]:
        action = WebAction(kind="press", value=key, risk=_risk_from_str(risk))
        decision = self.action_policy.authorize(action)
        if not decision.allowed:
            return {"status": decision.status, "reason": decision.reason}
        return {"status": "ok", "message": "authorized"}

    def run_cli(self, args: list[str] | None = None) -> int:
        """CLI entry point: browser-harness-agent call <tool> '<json params>'"""
        argv = args or sys.argv[1:]
        if not argv or argv[0] in ("-h", "--help"):
            print("Usage: browser-harness-agent call <tool> '<json params>'")
            return 0

        if argv[0] == "call" and len(argv) >= 3:
            tool_name = argv[1]
            try:
                params = json.loads(argv[2])
            except json.JSONDecodeError as e:
                print(json.dumps({"status": "error", "reason": f"invalid JSON: {e}"}))
                return 1

            try:
                result = self.call(tool_name, params)
                print(json.dumps(result, default=str))
                return 0 if result.get("status") != "denied" else 1
            finally:
                self.shutdown()

        print(f"Usage: browser-harness-agent call <tool> '<json params>'", file=sys.stderr)
        return 1


def main() -> int:
    host = AgentHost()
    try:
        return host.run_cli()
    finally:
        host.shutdown()


if __name__ == "__main__":
    sys.exit(main())
