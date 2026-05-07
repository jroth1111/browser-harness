"""Compatibility projection — maps existing helper calls through the authority pipeline.

This module provides the bridge between the old helper interface and the new
authority system. During migration, existing code can use these projections
while new code uses AccessPlane / ActionPolicy directly.

The projections delegate to the real helpers but also route through the
authority system for policy-gated operations.
"""
from __future__ import annotations

from typing import Any

from ..authority.action_policy import ActionPolicy
from ..authority.challenge import ChallengeStateMachine
from ..authority.policy import PolicyEngine
from ..capabilities.models import (
    ChallengeStatus,
    RiskLevel,
    TransportType,
    WebAction,
    WebRequest,
)
from ..capabilities.resolver import AccessPlane
from ..scheduler.budgets import BudgetController
from ..sessions.broker import SessionBroker


class CompatibilityProjection:
    """Wraps the old helper interface behind the new authority pipeline.

    Existing code can call fetch(), click(), etc. through this projection.
    The projection routes through PolicyEngine, AccessPlane, and ActionPolicy.
    """

    def __init__(
        self,
        policy: PolicyEngine | None = None,
        access_plane: AccessPlane | None = None,
        action_policy: ActionPolicy | None = None,
        budget: BudgetController | None = None,
        broker: SessionBroker | None = None,
        legacy_helpers: dict[str, Any] | None = None,
    ):
        self.policy = policy or PolicyEngine()
        self.budget = budget or BudgetController()
        self.broker = broker or SessionBroker()
        self.action_policy = action_policy or ActionPolicy()
        self.access_plane = access_plane or AccessPlane(
            policy=self.policy,
            budget=self.budget,
            broker=self.broker,
        )
        self._legacy = legacy_helpers or {}

    def fetch(self, url: str, risk: str = "public_read", **kw: Any) -> dict[str, Any]:
        """Fetch URL through the authority pipeline."""
        request = WebRequest(
            url=url,
            risk=RiskLevel(risk) if risk in RiskLevel.__members__.values() else RiskLevel.PUBLIC_READ,
            method=kw.get("method", "GET"),
            auth_required=kw.get("auth_required", False),
        )
        result = self.access_plane.execute(request)
        return {
            "status": result.status,
            "text": result.text,
            "html": result.html,
            "url": result.url,
            "source": result.source,
            "transport": result.transport.value,
            "block_state": result.block_state.value,
            "reason": result.reason,
            "block": result.block,
        }

    def click(self, target: str, risk: str = "low_risk_write", **kw: Any) -> dict[str, Any]:
        """Click through the action policy."""
        action = WebAction(kind="click", target=target, risk=RiskLevel(risk) if risk in RiskLevel.__members__.values() else RiskLevel.LOW_RISK_WRITE)
        decision = self.action_policy.authorize(action)
        if not decision.allowed:
            return {"status": decision.status, "reason": decision.reason}

        if "click" in self._legacy:
            return self._legacy["click"](target=target, **kw)
        return {"status": "ok", "message": "authorized, delegate to legacy click"}

    def fill(self, target: str, value: str, risk: str = "low_risk_write", **kw: Any) -> dict[str, Any]:
        """Fill input through the action policy."""
        action = WebAction(kind="fill", target=target, value=value, risk=RiskLevel(risk) if risk in RiskLevel.__members__.values() else RiskLevel.LOW_RISK_WRITE)
        decision = self.action_policy.authorize(action)
        if not decision.allowed:
            return {"status": decision.status, "reason": decision.reason}

        if "fill" in self._legacy:
            return self._legacy["fill"](target=target, value=value, **kw)
        return {"status": "ok", "message": "authorized, delegate to legacy fill"}
