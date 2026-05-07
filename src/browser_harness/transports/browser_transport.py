"""Navigation controller — browser navigation behind authority.

Wraps goto_url, new_tab, switch_tab behind PolicyEngine and BudgetController.
In dev mode, delegates directly to legacy helpers. In agent mode, routes
through the authority pipeline.
"""
from __future__ import annotations

from typing import Any, Callable

from ..authority.challenge import ChallengeStateMachine, ChallengeDetection, ChallengeKind
from ..authority.policy import PolicyEngine
from ..capabilities.models import (
    AuthorityDecision,
    Capability,
    ChallengeStatus,
    RiskLevel,
    TransportType,
    WebRequest,
)
from ..scheduler.budgets import BudgetController


class NavigationController:
    """Navigate the browser through the authority pipeline.

    In agent mode:
    1. PolicyEngine.authorize(url, risk)
    2. BudgetController.ok(origin)
    3. Execute navigation via legacy helper
    4. BudgetController.record(result)
    5. ChallengeStateMachine.evaluate(block_status)
    """

    def __init__(
        self,
        policy: PolicyEngine | None = None,
        budget: BudgetController | None = None,
        challenge_sm: ChallengeStateMachine | None = None,
        goto_fn: Callable[..., Any] | None = None,
        new_tab_fn: Callable[..., Any] | None = None,
        switch_tab_fn: Callable[..., Any] | None = None,
    ):
        self.policy = policy or PolicyEngine()
        self.budget = budget or BudgetController()
        self.challenge_sm = challenge_sm or ChallengeStateMachine()
        self._goto_fn = goto_fn
        self._new_tab_fn = new_tab_fn
        self._switch_tab_fn = switch_tab_fn

    def goto(self, url: str, risk: str = "public_read", **kw: Any) -> dict[str, Any]:
        """Navigate to URL through authority pipeline."""
        request = WebRequest(url=url, risk=RiskLevel(risk))
        decision = self.policy.authorize(request)
        if not decision.allowed:
            return {"ok": False, "reason": decision.reason, "status": "denied"}

        from urllib.parse import urlparse
        origin = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        ok, budget_reason = self.budget.ok(origin)
        if not ok:
            return {"ok": False, "reason": budget_reason, "status": "rate_limited"}

        if not self._goto_fn:
            return {"ok": False, "reason": "no navigation adapter registered"}

        try:
            result = self._goto_fn(url, **kw)
            status_code = 200 if result.get("ok", True) else 502
            self.budget.record(origin, status=status_code)

            # Check for challenge/block
            block = result.get("block") or {}
            if block.get("blocked"):
                detection = ChallengeDetection(found=True, kind=ChallengeKind.UNKNOWN)
                challenge = self.challenge_sm.evaluate(detection)
                result["challenge_state"] = challenge.status.value

            return result
        except Exception as e:
            self.budget.record(origin, status=500, block=True)
            return {"ok": False, "reason": str(e)}

    def new_tab(self, url: str = "about:blank", **kw: Any) -> dict[str, Any]:
        """Open a new tab through authority pipeline."""
        if url != "about:blank":
            request = WebRequest(url=url, risk=RiskLevel.PUBLIC_READ)
            decision = self.policy.authorize(request)
            if not decision.allowed:
                return {"ok": False, "reason": decision.reason}

        if not self._new_tab_fn:
            return {"ok": False, "reason": "no tab adapter registered"}

        return self._new_tab_fn(url, **kw)

    def switch_tab(self, **kw: Any) -> dict[str, Any]:
        """Switch tab — no URL involved, no authority gate needed."""
        if not self._switch_tab_fn:
            return {"ok": False, "reason": "no tab adapter registered"}
        return self._switch_tab_fn(**kw)
