"""PolicyEngine — central authority broker for all web actions."""
from __future__ import annotations

from ..capabilities.models import (
    AuthorityDecision,
    RiskLevel,
    TransportType,
    WebAction,
    WebRequest,
)


# Risk ordering: lower index = lower risk
_RISK_ORDER = [
    RiskLevel.PUBLIC_READ,
    RiskLevel.AUTHENTICATED_READ,
    RiskLevel.LOW_RISK_WRITE,
    RiskLevel.EXTERNAL_SIDE_EFFECT,
    RiskLevel.PAYMENT_DELETE_SECURITY,
    RiskLevel.LOGIN_CHALLENGE_2FA,
]


class PolicyEngine:
    """Authorize web requests and actions against risk rules.

    Rules:
        R0: public_read          → allowed if domain allowed
        R1: authenticated_read   → requires user/account/session scope
        R2: low_risk_write       → standing permission or approval
        R3: external_side_effect → explicit approval
        R4: payment/delete/sec   → human handoff
        R5: login/CAPTCHA/2FA    → human handoff
    """

    def __init__(
        self,
        allowed_domains: set[str] | None = None,
        blocked_domains: set[str] | None = None,
        standing_permissions: set[RiskLevel] | None = None,
    ):
        self.allowed_domains = allowed_domains
        self.blocked_domains = blocked_domains or set()
        self.standing_permissions = standing_permissions or {RiskLevel.PUBLIC_READ}

    def authorize(self, request: WebRequest) -> AuthorityDecision:
        from urllib.parse import urlparse

        parsed = urlparse(request.url)
        origin = f"{parsed.scheme}://{parsed.netloc}"

        if origin in self.blocked_domains:
            return AuthorityDecision(
                allowed=False,
                status="denied",
                reason=f"domain blocked: {origin}",
            )

        if self.allowed_domains is not None and origin not in self.allowed_domains:
            return AuthorityDecision(
                allowed=False,
                status="denied",
                reason=f"domain not in allowlist: {origin}",
            )

        return self._check_risk(request)

    def authorize_action(self, action: WebAction) -> AuthorityDecision:
        risk = action.risk

        if risk == RiskLevel.PUBLIC_READ:
            return AuthorityDecision(
                allowed=True,
                status="allowed",
                risk_max=risk,
                allowed_capability_types=self._transport_order(risk),
                reason="R0: public read",
            )

        if risk == RiskLevel.AUTHENTICATED_READ:
            return AuthorityDecision(
                allowed=True,
                status="allowed",
                risk_max=risk,
                allowed_capability_types=self._transport_order(risk),
                reason="R1: authenticated read",
            )

        if risk == RiskLevel.LOW_RISK_WRITE:
            if risk in self.standing_permissions:
                return AuthorityDecision(
                    allowed=True,
                    status="allowed",
                    risk_max=risk,
                    allowed_capability_types=self._transport_order(risk),
                    reason="R2: low-risk write with standing permission",
                )
            return AuthorityDecision(
                allowed=False,
                status="need_user_approval",
                risk_max=risk,
                allowed_capability_types=self._transport_order(risk),
                reason="R2: low-risk write requires approval",
            )

        if risk == RiskLevel.EXTERNAL_SIDE_EFFECT:
            if risk in self.standing_permissions:
                return AuthorityDecision(
                    allowed=True,
                    status="allowed",
                    risk_max=risk,
                    allowed_capability_types=self._transport_order(risk),
                    reason="R3: external side effect with standing permission",
                )
            return AuthorityDecision(
                allowed=False,
                status="need_user_approval",
                risk_max=risk,
                allowed_capability_types=self._transport_order(risk),
                reason="R3: external side effect requires explicit approval",
            )

        if risk in (RiskLevel.PAYMENT_DELETE_SECURITY, RiskLevel.LOGIN_CHALLENGE_2FA):
            return AuthorityDecision(
                allowed=False,
                status="need_handoff",
                risk_max=risk,
                allowed_capability_types=[TransportType.HUMAN_HANDOFF],
                reason=f"{'R4' if risk == RiskLevel.PAYMENT_DELETE_SECURITY else 'R5'}: requires human handoff",
            )

        return AuthorityDecision(
            allowed=False,
            status="denied",
            reason=f"unknown risk level: {risk}",
        )

    def _check_risk(self, request: WebRequest) -> AuthorityDecision:
        risk = request.risk
        action = WebAction(kind="request", risk=risk)
        return self.authorize_action(action)

    @staticmethod
    def _transport_order(risk: RiskLevel) -> list[TransportType]:
        """Return allowed transport types in preference order for a risk level."""
        cache_up = [
            TransportType.PUBLIC_HTTP,
        ]
        authed = [
            TransportType.AUTHENTICATED_HTTP,
            TransportType.BROWSER_BOOTSTRAP,
            TransportType.FULL_BROWSER,
        ]

        if risk == RiskLevel.PUBLIC_READ:
            return cache_up
        return cache_up + authed
