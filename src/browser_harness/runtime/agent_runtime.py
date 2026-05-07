"""Agent runtime — typed tool calls into an authority-preserving access plane.

No arbitrary Python. No raw imports. All actions go through PolicyEngine.
Fetch/extract go through AccessPlane. Actions go through ActionPolicy.
"""
from __future__ import annotations

import json
import sys
from typing import Any

from ..authority.action_policy import ActionPolicy
from ..authority.policy import PolicyEngine
from ..capabilities.models import (
    AuthorityDecision,
    ChallengeStatus,
    ExtractionResult,
    LeaseSpec,
    RiskLevel,
    TransportType,
    WebAction,
    WebRequest,
)
from ..capabilities.resolver import AccessPlane
from .sandbox import AgentSandbox, FORBIDDEN_NAMES


def _risk_from_str(risk: str) -> RiskLevel:
    try:
        return RiskLevel(risk)
    except ValueError:
        return RiskLevel.PUBLIC_READ


class AgentRuntime:
    """Typed tool-call runtime for AI agents.

    Tools:
        fetch     — request a URL through the AccessPlane
        click     — click an element through ActionPolicy
        extract   — extract fields from a URL with provenance
        navigate  — navigate the browser to a URL
        fill      — fill an input with a value
        press     — press a key
        snapshot  — take an accessibility tree snapshot
        screenshot — take a screenshot

    Each tool call goes through PolicyEngine authorization.
    """

    def __init__(
        self,
        policy: PolicyEngine | None = None,
        access_plane: AccessPlane | None = None,
        action_policy: ActionPolicy | None = None,
        tools: dict[str, Any] | None = None,
    ):
        self.policy = policy or PolicyEngine()
        self.access_plane = access_plane or AccessPlane(policy=self.policy)
        self.action_policy = action_policy or ActionPolicy()
        self._tool_impls = tools or {}
        self._sandbox = AgentSandbox(self._build_tool_registry())

    def _build_tool_registry(self) -> dict[str, Any]:
        registry: dict[str, Any] = {
            "fetch": self._tool_fetch,
            "click": self._tool_click,
            "extract": self._tool_extract,
            "navigate": self._tool_navigate,
            "fill": self._tool_fill,
            "press": self._tool_press,
            "snapshot": self._tool_snapshot,
            "screenshot": self._tool_screenshot,
        }
        registry.update(self._tool_impls)
        return registry

    def call(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        result = self._sandbox.call(tool_name, params)
        if result.get("status") == "denied":
            return result
        return result

    def run_cli(self, args: list[str] | None = None) -> int:
        """CLI entry point: browser-harness-agent call <tool> '<json params>'"""
        argv = args or sys.argv[1:]
        if not argv or argv[0] in ("-h", "--help"):
            print("Usage: browser-harness-agent call <tool> '<json params>'")
            print("\nAvailable tools:", ", ".join(sorted(self._sandbox.available_tools())))
            return 0

        if argv[0] == "call" and len(argv) >= 3:
            tool_name = argv[1]
            try:
                params = json.loads(argv[2])
            except json.JSONDecodeError as e:
                print(json.dumps({"status": "error", "reason": f"invalid JSON: {e}"}))
                return 1

            if not isinstance(params, dict):
                print(json.dumps({"status": "error", "reason": "params must be a JSON object"}))
                return 1

            result = self.call(tool_name, params)
            print(json.dumps(result, default=str))
            return 0 if result.get("status") != "denied" else 1

        if argv[0] == "list-tools":
            print(json.dumps(self._sandbox.available_tools()))
            return 0

        print(f"Usage: browser-harness-agent call <tool> '<json params>'", file=sys.stderr)
        return 1

    # --- Tool implementations ---

    def _tool_fetch(self, url: str = "", risk: str = "public_read", **kw: Any) -> dict[str, Any]:
        request = WebRequest(
            url=url,
            risk=_risk_from_str(risk),
            method=kw.get("method", "GET"),
            expected_type=kw.get("expected_type", "html"),
            auth_required=kw.get("auth_required", False),
        )

        # Use AccessPlane for full pipeline: policy → budget → transport → challenge
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

        if "click" in self._tool_impls:
            return self._tool_impls["click"](action=action, decision=decision, **kw)

        return {"status": "ok", "message": "authorized but no action executor registered"}

    def _tool_extract(self, url: str = "", fields: list[str] | None = None, **kw: Any) -> dict[str, Any]:
        risk = kw.get("risk", "public_read")
        request = WebRequest(url=url, risk=_risk_from_str(risk))
        decision = self.policy.authorize(request)
        if not decision.allowed:
            return {"status": decision.status, "reason": decision.reason}

        if "extract" in self._tool_impls:
            return self._tool_impls["extract"](request=request, decision=decision, fields=fields, **kw)

        return {
            "status": "ok",
            "fields": fields or [],
            "message": "authorized but no extractor registered",
        }

    def _tool_navigate(self, url: str = "", risk: str = "public_read", **kw: Any) -> dict[str, Any]:
        request = WebRequest(url=url, risk=_risk_from_str(risk))
        decision = self.policy.authorize(request)
        if not decision.allowed:
            return {"status": decision.status, "reason": decision.reason}

        if "navigate" in self._tool_impls:
            return self._tool_impls["navigate"](request=request, decision=decision, **kw)

        return {"status": "ok", "message": "authorized but no navigation controller registered"}

    def _tool_fill(self, target: str = "", value: str = "", risk: str = "low_risk_write", **kw: Any) -> dict[str, Any]:
        action = WebAction(kind="fill", target=target, value=value, risk=_risk_from_str(risk))
        decision = self.action_policy.authorize(action)
        if not decision.allowed:
            return {"status": decision.status, "reason": decision.reason}

        if "fill" in self._tool_impls:
            return self._tool_impls["fill"](action=action, decision=decision, **kw)

        return {"status": "ok", "message": "authorized but no action executor registered"}

    def _tool_press(self, key: str = "", risk: str = "low_risk_write", **kw: Any) -> dict[str, Any]:
        action = WebAction(kind="press", value=key, risk=_risk_from_str(risk))
        decision = self.action_policy.authorize(action)
        if not decision.allowed:
            return {"status": decision.status, "reason": decision.reason}

        if "press" in self._tool_impls:
            return self._tool_impls["press"](action=action, decision=decision, **kw)

        return {"status": "ok", "message": "authorized but no action executor registered"}

    def _tool_snapshot(self, **kw: Any) -> dict[str, Any]:
        if "snapshot" in self._tool_impls:
            return self._tool_impls["snapshot"](**kw)
        return {"status": "ok", "message": "no snapshot adapter registered"}

    def _tool_screenshot(self, **kw: Any) -> dict[str, Any]:
        if "screenshot" in self._tool_impls:
            return self._tool_impls["screenshot"](**kw)
        return {"status": "ok", "message": "no screenshot adapter registered"}


def main() -> int:
    runtime = AgentRuntime()
    return runtime.run_cli()


if __name__ == "__main__":
    sys.exit(main())
