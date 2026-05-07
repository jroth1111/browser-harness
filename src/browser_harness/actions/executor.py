"""Action executor — browser actions (click, fill, press) behind ActionPolicy.

In agent mode, all actions go through ActionPolicy classification and gating.
R3+ actions require approval or handoff. In dev mode, delegates to legacy helpers.
"""
from __future__ import annotations

from typing import Any, Callable

from ..authority.action_policy import ActionPolicy
from ..capabilities.models import AuthorityDecision, RiskLevel, WebAction


class ActionExecutor:
    """Execute browser actions through the action policy.

    Actions are classified by risk:
    R0: read-only (snapshot, screenshot) → allowed
    R2: low-risk write (fill, type, press non-submit) → allowed
    R3: external side effect (submit, send) → need approval
    R4: payment/delete/security → need handoff
    """

    def __init__(
        self,
        action_policy: ActionPolicy | None = None,
        click_fn: Callable[..., Any] | None = None,
        fill_fn: Callable[..., Any] | None = None,
        press_fn: Callable[..., Any] | None = None,
        type_fn: Callable[..., Any] | None = None,
    ):
        self.action_policy = action_policy or ActionPolicy()
        self._click_fn = click_fn
        self._fill_fn = fill_fn
        self._press_fn = press_fn
        self._type_fn = type_fn

    def execute(self, action: WebAction) -> dict[str, Any]:
        """Execute a browser action through policy."""
        decision = self.action_policy.authorize(action)
        if not decision.allowed:
            return {
                "status": decision.status,
                "reason": decision.reason,
                "risk": action.risk.value,
            }

        # Dispatch to legacy helper
        if action.kind == "click":
            return self._do_click(action)
        elif action.kind == "fill":
            return self._do_fill(action)
        elif action.kind == "press":
            return self._do_press(action)
        elif action.kind == "type":
            return self._do_type(action)
        else:
            return {"status": "ok", "message": f"no executor for {action.kind}"}

    def _do_click(self, action: WebAction) -> dict[str, Any]:
        if not self._click_fn:
            return {"status": "ok", "message": "authorized but no click adapter"}
        result = self._click_fn(action.target, **({"coordinates": action.coordinates} if action.coordinates else {}))
        return {"status": "ok", "result": result}

    def _do_fill(self, action: WebAction) -> dict[str, Any]:
        if not self._fill_fn:
            return {"status": "ok", "message": "authorized but no fill adapter"}
        result = self._fill_fn(action.target, action.value)
        return {"status": "ok", "result": result}

    def _do_press(self, action: WebAction) -> dict[str, Any]:
        if not self._press_fn:
            return {"status": "ok", "message": "authorized but no press adapter"}
        result = self._press_fn(action.value)
        return {"status": "ok", "result": result}

    def _do_type(self, action: WebAction) -> dict[str, Any]:
        if not self._type_fn:
            return {"status": "ok", "message": "authorized but no type adapter"}
        result = self._type_fn(action.target, action.value)
        return {"status": "ok", "result": result}
