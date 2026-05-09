"""ActionPolicy — classifies and gates browser actions by risk.

R0: public read         → allowed
R1: authenticated read   → requires session scope
R2: low-risk write       → standing permission or approval
R3: external side effect → explicit approval
R4: payment/delete/sec   → human handoff
"""
from __future__ import annotations

import re

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

    @classmethod
    def _compile_patterns(cls, hints: frozenset[str]) -> list[re.Pattern]:
        patterns = []
        for hint in hints:
            phrase = hint.replace("_", " ")
            # Word boundary around each word in the phrase
            pat = r'\b' + r'\s+'.join(re.escape(w) for w in phrase.split()) + r'\b'
            patterns.append(re.compile(pat, re.IGNORECASE))
        return patterns

    _HIGH_RISK_PATTERNS: list[re.Pattern] | None = None
    _EXTERNAL_SIDE_EFFECT_PATTERNS: list[re.Pattern] | None = None

    @classmethod
    def _get_high_risk_patterns(cls) -> list[re.Pattern]:
        if cls._HIGH_RISK_PATTERNS is None:
            cls._HIGH_RISK_PATTERNS = cls._compile_patterns(cls.HIGH_RISK_HINTS)
        return cls._HIGH_RISK_PATTERNS

    @classmethod
    def _get_external_side_effect_patterns(cls) -> list[re.Pattern]:
        if cls._EXTERNAL_SIDE_EFFECT_PATTERNS is None:
            cls._EXTERNAL_SIDE_EFFECT_PATTERNS = cls._compile_patterns(cls.EXTERNAL_SIDE_EFFECT_HINTS)
        return cls._EXTERNAL_SIDE_EFFECT_PATTERNS

    _RISK_RANK = {
        RiskLevel.PUBLIC_READ: 0,
        RiskLevel.AUTHENTICATED_READ: 1,
        RiskLevel.LOW_RISK_WRITE: 2,
        RiskLevel.EXTERNAL_SIDE_EFFECT: 3,
        RiskLevel.PAYMENT_DELETE_SECURITY: 4,
        RiskLevel.LOGIN_CHALLENGE_2FA: 5,
    }

    def classify(self, action: WebAction) -> RiskLevel:
        """Classify an action into a risk level based on its properties.

        Always runs keyword analysis for defense in depth. Keyword
        escalation takes the max of caller-declared risk and keyword
        risk, preventing callers from bypassing HIGH_RISK_HINTS /
        EXTERNAL_SIDE_EFFECT_HINTS by setting a lower risk level.
        """
        keyword_risk = self._classify_by_keywords(action)
        caller_risk = action.risk

        # Keyword escalation: never allow de-escalation below what
        # keyword analysis determines.
        if self._RISK_RANK[keyword_risk] > self._RISK_RANK[caller_risk]:
            return keyword_risk

        # Read-only action downgrade: only from LOW_RISK_WRITE to
        # PUBLIC_READ.  The caller used the default/unclassified risk,
        # and the action kind is inherently non-mutating.
        if caller_risk == RiskLevel.LOW_RISK_WRITE and keyword_risk == RiskLevel.PUBLIC_READ:
            return RiskLevel.PUBLIC_READ

        return caller_risk

    def _classify_by_keywords(self, action: WebAction) -> RiskLevel:
        """Keyword-based risk classification independent of caller's risk."""
        kind = action.kind.lower()
        target = action.target.lower()
        value = action.value.lower()
        # Normalize underscores to spaces so that action kinds and targets
        # like "change_password" match hint patterns compiled from
        # HIGH_RISK_HINTS / EXTERNAL_SIDE_EFFECT_HINTS which convert
        # underscores to word-boundary-separated regex alternatives.
        text = f"{kind} {target} {value}".replace("_", " ")

        for pattern in self._get_high_risk_patterns():
            if pattern.search(text):
                return RiskLevel.PAYMENT_DELETE_SECURITY

        for pattern in self._get_external_side_effect_patterns():
            if pattern.search(text):
                return RiskLevel.EXTERNAL_SIDE_EFFECT

        if kind in self.LOW_RISK_ACTIONS:
            return RiskLevel.PUBLIC_READ

        return RiskLevel.LOW_RISK_WRITE

    def authorize(self, action: WebAction) -> AuthorityDecision:
        """Authorize an action after classification."""
        classified_risk = self.classify(action)

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
