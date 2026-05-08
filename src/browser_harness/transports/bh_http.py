"""bh_http — authority-routed HTTP adapter for domain skills.

Domain skills should use this instead of urllib.request.urlopen.
Routes every request through AccessPlane with policy/budget/challenge gates.

Usage:
    from browser_harness.transports.bh_http import get, execute

    resp = get("https://example.com/api/data")
    resp = execute(WebRequest(url="...", risk="authenticated_read", auth_required=True))
"""
from __future__ import annotations

from typing import Any

from ..authority.challenge import ChallengeStateMachine
from ..authority.policy import PolicyEngine
from ..capabilities.models import (
    Capability,
    ChallengeStatus,
    RiskLevel,
    TransportType,
    WebRequest,
)
from ..capabilities.resolver import AccessPlane, AccessResult
from ..scheduler.budgets import BudgetController
from ..sessions.broker import SessionBroker
from ..response import Response


def _default_plane() -> AccessPlane:
    return AccessPlane(
        policy=PolicyEngine(),
        budget=BudgetController(),
        broker=SessionBroker(),
        challenge_sm=ChallengeStateMachine(),
    )


def execute(
    request: WebRequest,
    capability: Capability | None = None,
    plane: AccessPlane | None = None,
) -> Response:
    """Execute a WebRequest through the authority pipeline.

    Returns a Response object with the same interface as helpers.fetch().
    """
    p = plane or _default_plane()
    result = p.execute(request)
    return _result_to_response(result)


def get(
    url: str,
    *,
    risk: str = "public_read",
    headers: dict[str, str] | None = None,
    plane: AccessPlane | None = None,
) -> Response:
    """HTTP GET through the authority pipeline.

    Drop-in replacement for urllib.request.urlopen(url).read().
    """
    request = WebRequest(
        url=url,
        risk=_risk(risk),
        method="GET",
        headers=headers or {},
        auth_required=False,
    )
    return execute(request, plane=plane)


def post(
    url: str,
    *,
    risk: str = "low_risk_write",
    body: Any = None,
    headers: dict[str, str] | None = None,
    plane: AccessPlane | None = None,
) -> Response:
    """HTTP POST through the authority pipeline."""
    request = WebRequest(
        url=url,
        risk=_risk(risk),
        method="POST",
        headers=headers or {},
        auth_required=False,
        extra={"body": body},
    )
    return execute(request, plane=plane)


def _risk(risk: str) -> RiskLevel:
    try:
        return RiskLevel(risk)
    except ValueError:
        return RiskLevel.PUBLIC_READ


def _result_to_response(result: AccessResult) -> Response:
    return Response(
        html=result.html,
        text=result.text,
        url=result.url,
        status=result.status,
        source="authority",
        headers=result.headers,
        reason=result.reason,
        block=result.block,
    )
