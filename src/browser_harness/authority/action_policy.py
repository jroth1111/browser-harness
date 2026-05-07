"""ActionPolicy — classifies and gates browser actions by risk.

R0: public read         → allowed
R1: authenticated read   → requires session scope
R2: low-risk write       → standing permission or approval
R3: external side effect → explicit approval
R4: payment/delete/sec   → human handoff
"""
from __future__ import annotations

from ..capabilities.models import AuthorityDecision, RiskLevel, TransportType, WebAction


class ActionPolicy:
    """Classify and gate browser actions by risk level."""

    # Actions that are always R2 or below
    LOW_RISK_ACTIONS = frozenset({
        "snapshot",
        "screenshot",
        "scroll",
        "select",
        "hover",
        "read_text",
        "get_attribute",
    })

    # Actions that imply external side effects
    EXTERNAL_SIDE_EFFECT_HINTS = frozenset({
        "submit",
        "send",
        "post",
        "confirm",
        "accept",
        "agree",
        "place_order",
        "book",
        "purchase",
    })

    # Actions that require human handoff
    HIGH_RISK_HINTS = frozenset({
        "payment",
        "pay",
        "delete",
        "remove_account",
        "change_password",
        "change_email",
        "2fa",
        "two_factor",
        "security",
    })

    def classify(self, action: WebAction) -> RiskLevel:
        """Classify an action into a risk level based on its properties."""
        if action.risk != RiskLevel.LOW_RISK_WRITE:
            return action.risk  # caller already classified

        kind = action.kind.lower()
        target = action.target.lower()
        value = action.value.lower()

        # Check for high-risk keywords in target/value
        text = f"{kind} {target} {value}"
        for hint in self.HIGH_RISK_HINTS:
            if hint in text:
                return RiskLevel.PAYMENT_DELETE_SECURITY

        for hint in self.EXTERNAL_SIDE_EFFECT_HINTS:
            if hint in text:
                return RiskLevel.EXTERNAL_SIDE_EFFECT

        if kind in self.LOW_RISK_ACTIONS:
            return RiskLevel.PUBLIC_READ

        return RiskLevel.LOW_RISK_WRITE

    def authorize(self, action: WebAction) -> AuthorityDecision:
        """Authorize an action after classification."""
        classified_risk = self.classify(action)
        classified_action = WebAction(
            kind=action.kind,
            target=action.target,
            value=action.value,
            risk=classified_risk,
            coordinates=action.coordinates,
        )

        if classified_risk == RiskLevel.PUBLIC_READ:
            return AuthorityDecision(
                allowed=True,
                status="allowed",
                risk_max=classified_risk,
                reason="R0: read-only action",
            )

        if classified_risk == RiskLevel.LOW_RISK_WRITE:
            return AuthorityDecision(
                allowed=True,
                status="allowed",
                risk_max=classified_risk,
                reason="R2: low-risk write",
            )

        if classified_risk == RiskLevel.EXTERNAL_SIDE_EFFECT:
            return AuthorityDecision(
                allowed=False,
                status="need_user_approval",
                risk_max=classified_risk,
                allowed_capability_types=[TransportType.FULL_BROWSER, TransportType.HUMAN_HANDOFF],
                reason="R3: external side effect requires approval",
            )

        if classified_risk in (RiskLevel.PAYMENT_DELETE_SECURITY, RiskLevel.LOGIN_CHALLENGE_2FA):
            return AuthorityDecision(
                allowed=False,
                status="need_handoff",
                risk_max=classified_risk,
                allowed_capability_types=[TransportType.HUMAN_HANDOFF],
                reason=f"{'R4' if classified_risk == RiskLevel.PAYMENT_DELETE_SECURITY else 'R5'}: requires human handoff",
            )

        return AuthorityDecision(
            allowed=False,
            status="denied",
            reason=f"unclassifiable action: {action.kind}",
        )
