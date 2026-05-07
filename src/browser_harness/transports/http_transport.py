"""HTTP transport — the approved adapter for domain skill HTTP requests.

Domain skills should use this transport instead of raw urllib/requests.
It routes through SessionBroker for authenticated requests and enforces
route rules, lease scoping, and origin boundaries.
"""
from __future__ import annotations

from typing import Any, Callable
from urllib.parse import urlparse

from ..authority.policy import PolicyEngine
from ..capabilities.models import (
    AuthorityDecision,
    ChallengeStatus,
    LeaseSpec,
    RiskLevel,
    RouteRule,
    TransportType,
    WebRequest,
)
from ..sessions.broker import SessionBroker
from ..scheduler.budgets import BudgetController


class HTTPTransport:
    """Approved HTTP transport for domain skills.

    Public requests: plain urllib, no session state.
    Authenticated requests: materialized from SessionBroker via lease.
    All requests: go through BudgetController.
    """

    def __init__(
        self,
        policy: PolicyEngine | None = None,
        budget: BudgetController | None = None,
        broker: SessionBroker | None = None,
        http_fn: Callable[..., str] | None = None,
    ):
        self.policy = policy or PolicyEngine()
        self.budget = budget or BudgetController()
        self.broker = broker or SessionBroker()
        self._http_fn = http_fn

    def get(self, url: str, *, risk: str = "public_read", **kw: Any) -> dict[str, Any]:
        """HTTP GET through the authority pipeline."""
        return self.execute(WebRequest(
            url=url,
            risk=RiskLevel(risk),
            method="GET",
            headers=kw.get("headers", {}),
            auth_required=kw.get("auth_required", False),
        ))

    def execute(self, request: WebRequest) -> dict[str, Any]:
        """Execute an HTTP request through the authority pipeline."""
        origin = f"{urlparse(request.url).scheme}://{urlparse(request.url).netloc}"

        # 1. Policy gate
        decision = self.policy.authorize(request)
        if not decision.allowed:
            return {"status": "denied", "reason": decision.reason}

        # 2. Budget gate
        ok, budget_reason = self.budget.ok(origin)
        if not ok:
            return {"status": "rate_limited", "reason": budget_reason}

        # 3. Execute
        try:
            if request.auth_required:
                return self._authenticated_request(request, origin)
            return self._public_request(request, origin)
        except Exception as e:
            self.budget.record(origin, status=500, block=True)
            return {"status": "error", "reason": str(e)}

    def _public_request(self, request: WebRequest, origin: str) -> dict[str, Any]:
        if not self._http_fn:
            return {"status": "error", "reason": "no HTTP adapter registered"}
        text = self._http_fn(request.url, headers=request.headers)
        self.budget.record(origin, status=200)
        return {"status": "ok", "text": text, "source": "http"}

    def _authenticated_request(self, request: WebRequest, origin: str) -> dict[str, Any]:
        ref = self.broker.ref_for_origin(origin)
        if not ref:
            return {"status": "denied", "reason": f"no session for {origin}"}

        bundle = self.broker.materialize_for_transport(ref, target_origin=origin)
        if not bundle:
            return {"status": "denied", "reason": "session expired or scope mismatch"}

        # The actual HTTP call with session cookies is done inside the transport
        # — the domain skill never sees raw cookie values
        if not self._http_fn:
            return {"status": "error", "reason": "no HTTP adapter registered"}

        # In a real implementation, we'd attach cookies from the bundle here
        text = self._http_fn(request.url, headers=request.headers)
        self.budget.record(origin, status=200)
        return {"status": "ok", "text": text, "source": "session_http"}
