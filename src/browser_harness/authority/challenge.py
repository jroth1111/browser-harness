"""ChallengeStateMachine — governs challenge detection and response policy.

Challenge detection is kept (detectors are adapters). Challenge solving is
removed from the production access path. The allowed outcomes are:
ok, blocked, need_handoff, auth_expired, rate_limited, unobservable.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any

from ..capabilities.models import ChallengeStatus


class ChallengeKind(enum.Enum):
    NONE = "none"
    CLOUDFLARE_TURNSTILE = "cloudflare_turnstile"
    CLOUDFLARE_CHALLENGE = "cloudflare_challenge"
    KASADA_KPSDK = "kasada_kpsdk"
    AKAMAI = "akamai"
    PERIMETERX = "perimeterx"
    DATADOME = "datadome"
    LOGIN_REDIRECT = "login_redirect"
    RATE_LIMIT = "rate_limit"
    CAPTCHA = "captcha"
    TWO_FA = "two_fa"
    UNKNOWN = "unknown"


@dataclass
class ChallengeDetection:
    found: bool = False
    kind: ChallengeKind = ChallengeKind.NONE
    evidence: list[str] = field(default_factory=list)
    challenge_type: str | None = None
    iframe_target_id: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChallengeDecision:
    status: ChallengeStatus = ChallengeStatus.OK
    kind: ChallengeKind = ChallengeKind.NONE
    reason: str = ""
    handoff_reason: str = ""


# Mapping from detection kind to production response
_KIND_RESPONSE: dict[ChallengeKind, ChallengeStatus] = {
    ChallengeKind.NONE: ChallengeStatus.OK,
    ChallengeKind.CLOUDFLARE_TURNSTILE: ChallengeStatus.NEED_HANDOFF,
    ChallengeKind.CLOUDFLARE_CHALLENGE: ChallengeStatus.NEED_HANDOFF,
    ChallengeKind.KASADA_KPSDK: ChallengeStatus.BLOCKED,
    ChallengeKind.AKAMAI: ChallengeStatus.BLOCKED,
    ChallengeKind.PERIMETERX: ChallengeStatus.BLOCKED,
    ChallengeKind.DATADOME: ChallengeStatus.BLOCKED,
    ChallengeKind.LOGIN_REDIRECT: ChallengeStatus.NEED_HANDOFF,
    ChallengeKind.RATE_LIMIT: ChallengeStatus.RATE_LIMITED,
    ChallengeKind.CAPTCHA: ChallengeStatus.NEED_HANDOFF,
    ChallengeKind.TWO_FA: ChallengeStatus.NEED_HANDOFF,
    ChallengeKind.UNKNOWN: ChallengeStatus.UNOBSERVABLE,
}


class ChallengeStateMachine:
    """Evaluate challenge detections and produce policy-compliant decisions.

    In production mode, challenges never trigger automatic solving.
    The only allowed outputs are handoff, blocked, or unobservable.
    """

    def __init__(self, dev_mode: bool = False):
        self._dev_mode = dev_mode
        self._history: list[ChallengeDecision] = []

    def evaluate(self, detection: ChallengeDetection) -> ChallengeDecision:
        if not detection.found:
            return ChallengeDecision(status=ChallengeStatus.OK, kind=ChallengeKind.NONE)

        kind = detection.kind
        status = _KIND_RESPONSE.get(kind, ChallengeStatus.UNOBSERVABLE)
        reason = f"challenge detected: {kind.value}"
        handoff_reason = ""

        if status == ChallengeStatus.NEED_HANDOFF:
            handoff_reason = f"human handoff required for {kind.value}"

        decision = ChallengeDecision(
            status=status,
            kind=kind,
            reason=reason,
            handoff_reason=handoff_reason,
        )
        self._history.append(decision)
        return decision

    def evaluate_block_detection(
        self,
        html: str = "",
        text: str = "",
        url: str = "",
        block_result: dict[str, Any] | None = None,
    ) -> ChallengeDecision:
        """Convenience: evaluate block-page detection output."""
        if block_result and block_result.get("kind"):
            kind_str = block_result["kind"]
            try:
                kind = ChallengeKind(kind_str)
            except ValueError:
                kind = ChallengeKind.UNKNOWN
            detection = ChallengeDetection(
                found=True,
                kind=kind,
                evidence=block_result.get("evidence", []),
                raw=block_result,
            )
            return self.evaluate(detection)

        return ChallengeDecision(status=ChallengeStatus.OK, kind=ChallengeKind.NONE)

    @property
    def history(self) -> list[ChallengeDecision]:
        return list(self._history)

    @property
    def last_challenge(self) -> ChallengeDecision | None:
        return self._history[-1] if self._history else None
