"""AccessPlane — the authority-preserving request pipeline.

Orchestrates: PolicyGate → Cache → Official API → Public HTTP →
Authenticated HTTP → Browser bootstrap → Browser-derived lease →
Full browser → Human handoff / stop.

Does NOT call challenge-solving directly. Challenges become authority
boundaries returning need_handoff/blocked/unobservable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import urlparse

from ..authority.challenge import (
    ChallengeDetection,
    ChallengeKind,
    ChallengeStateMachine,
)
from ..authority.policy import PolicyEngine
from ..capabilities.models import (
    AuthorityDecision,
    Capability,
    ChallengeStatus,
    LeaseSpec,
    RiskLevel,
    TransportDecision,
    TransportType,
    WebRequest,
)
from ..sessions.broker import SessionBroker
from ..scheduler.budgets import BudgetController


@dataclass
class AccessResult:
    url: str
    status: int = 0
    text: str = ""
    html: str = ""
    source: str = ""
    transport: TransportType = TransportType.PUBLIC_HTTP
    block_state: ChallengeStatus = ChallengeStatus.OK
    reason: str = ""
    block: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    capability_id: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


_MAX_CACHE_ENTRIES = 256


class AccessPlane:
    """The authority-preserving access pipeline.

    Each request goes through:
    1. PolicyEngine.authorize() → AuthorityDecision
    2. BudgetController.ok() → rate/budget check
    3. Transport selection via CapabilityResolver
    4. Challenge evaluation via ChallengeStateMachine
    5. BudgetController.record() → record result
    """

    def __init__(
        self,
        policy: PolicyEngine | None = None,
        budget: BudgetController | None = None,
        broker: SessionBroker | None = None,
        challenge_sm: ChallengeStateMachine | None = None,
        http_fn: Callable[..., str] | None = None,
        session_http_fn: Callable[..., dict] | None = None,
        browser_fn: Callable[..., dict] | None = None,
        block_detect_fn: Callable[..., dict] | None = None,
        handoff_broker: Any | None = None,
    ):
        self.policy = policy or PolicyEngine()
        self.budget = budget or BudgetController()
        self.broker = broker or SessionBroker()
        self.challenge_sm = challenge_sm or ChallengeStateMachine()
        self._http_fn = http_fn
        self._session_http_fn = session_http_fn
        self._browser_fn = browser_fn
        self._block_detect_fn = block_detect_fn
        self._handoff_broker = handoff_broker
        self._cache: dict[str, AccessResult] = {}

    def execute(self, request: WebRequest) -> AccessResult:
        """Execute a web request through the full authority pipeline."""
        origin = self._origin(request.url)

        # 1. Policy gate
        decision = self.policy.authorize(request)
        if not decision.allowed:
            return AccessResult(
                url=request.url,
                status=403,
                reason=decision.reason,
                block_state=ChallengeStatus.BLOCKED,
            )

        # 2. Budget gate
        ok, budget_reason = self.budget.ok(origin)
        if not ok:
            return AccessResult(
                url=request.url,
                status=429,
                reason=budget_reason,
                block_state=ChallengeStatus.RATE_LIMITED,
            )

        # 3. Cache check (only PUBLIC_READ results are cached; don't serve
        #    them to higher-risk or auth_required requests — that would
        #    bypass the transport selection enforcement.)
        cache_key = f"{request.method}:{request.url}"
        if cache_key in self._cache and request.risk == RiskLevel.PUBLIC_READ and not request.auth_required:
            return self._cache[cache_key]

        # 4. Transport selection and execution
        result = self._resolve_and_execute(request, decision)
        # 5. Record budget
        self.budget.record(origin, status=result.status, block=result.block.get("blocked", False))

        # 6. Cache successful results (bounded — evict oldest when full)
        if result.status == 200 and request.risk == RiskLevel.PUBLIC_READ:
            if len(self._cache) >= _MAX_CACHE_ENTRIES:
                self._cache.pop(next(iter(self._cache)))
            self._cache[cache_key] = result

        return result

    def _resolve_and_execute(self, request: WebRequest, decision: AuthorityDecision) -> AccessResult:
        """Try transports in preference order per the decision.

        If a SessionBroker ref exists for the origin, promote
        AUTHENTICATED_HTTP ahead of PUBLIC_HTTP — captured sessions exist
        because the public path was previously blocked, so retrying it
        first would just rediscover the block.

        If request.auth_required is True, PUBLIC_HTTP is removed from the
        order and AUTHENTICATED_HTTP is promoted to first position. The
        caller explicitly said the public path is not acceptable.
        """
        order = list(decision.allowed_capability_types)
        origin = self._origin(request.url)

        if request.auth_required:
            # Caller requires authentication — remove public path entirely
            order = [t for t in order if t != TransportType.PUBLIC_HTTP]
            # Ensure AUTHENTICATED_HTTP is available even if the risk level's
            # default transport order doesn't include it (e.g. PUBLIC_READ).
            if TransportType.AUTHENTICATED_HTTP not in order:
                order.insert(0, TransportType.AUTHENTICATED_HTTP)
            else:
                order = (
                    [TransportType.AUTHENTICATED_HTTP]
                    + [t for t in order if t != TransportType.AUTHENTICATED_HTTP]
                )
        elif (
            self.broker.ref_for_origin(origin) is not None
            and TransportType.AUTHENTICATED_HTTP in order
        ):
            order = (
                [TransportType.AUTHENTICATED_HTTP]
                + [t for t in order if t != TransportType.AUTHENTICATED_HTTP]
            )

        for transport in order:
            if transport == TransportType.PUBLIC_HTTP:
                result = self._try_public_http(request)
                if result:
                    return result

            elif transport == TransportType.AUTHENTICATED_HTTP:
                result = self._try_authenticated_http(request)
                if result:
                    return result

            elif transport in (TransportType.FULL_BROWSER, TransportType.BROWSER_BOOTSTRAP):
                result = self._try_browser(request)
                if result:
                    return result

            elif transport == TransportType.HUMAN_HANDOFF:
                return AccessResult(
                    url=request.url,
                    status=403,
                    reason="human handoff required",
                    block_state=ChallengeStatus.NEED_HANDOFF,
                    transport=TransportType.HUMAN_HANDOFF,
                )

        return AccessResult(
            url=request.url,
            status=502,
            reason="no transport available",
            block_state=ChallengeStatus.UNOBSERVABLE,
        )

    def _try_public_http(self, request: WebRequest) -> AccessResult | None:
        if not self._http_fn:
            return None
        try:
            text = self._http_fn(request.url, headers=request.headers)
            if not isinstance(text, str):
                return None
            block = self._detect_block(text, text, request.url)
            if block.get("blocked"):
                kind = self._block_kind_to_challenge_kind(block)
                challenge = self.challenge_sm.evaluate(
                    ChallengeDetection(found=True, kind=kind, evidence=block.get("evidence", []))
                )
                return AccessResult(
                    url=request.url,
                    status=403,
                    text=text,
                    html=text,
                    source="http",
                    transport=TransportType.PUBLIC_HTTP,
                    block_state=challenge.status,
                    block=block,
                    reason="blocked",
                    extra=self._handoff_extra(request, challenge.status, kind.value),
                )
            return AccessResult(
                url=request.url,
                status=200,
                text=text,
                html=text,
                source="http",
                transport=TransportType.PUBLIC_HTTP,
                block_state=ChallengeStatus.OK,
            )
        except Exception:
            return None

    def _try_authenticated_http(self, request: WebRequest) -> AccessResult | None:
        if not self._session_http_fn:
            return None
        origin = self._origin(request.url)
        ref = self.broker.ref_for_origin(origin)
        if not ref:
            return None
        bundle = self.broker.materialize_for_transport(ref, target_origin=origin)
        if not bundle:
            return None
        try:
            result = self._session_http_fn(request.url, headers=request.headers)
            if not isinstance(result, dict):
                return None
            text = str(result.get("text", ""))
            block = result.get("block") or self._detect_block(text, text, request.url)
            if block.get("blocked"):
                kind = self._block_kind_to_challenge_kind(block)
                challenge = self.challenge_sm.evaluate(
                    ChallengeDetection(found=True, kind=kind, evidence=block.get("evidence", []))
                )
                return AccessResult(
                    url=request.url,
                    status=result.get("status", 403),
                    text=text,
                    html=text,
                    source="session",
                    transport=TransportType.AUTHENTICATED_HTTP,
                    block_state=challenge.status,
                    block=block,
                    reason="blocked",
                    extra=self._handoff_extra(request, challenge.status, kind.value),
                )
            return AccessResult(
                url=request.url,
                status=result.get("status", 200),
                text=text,
                html=text,
                source="session",
                transport=TransportType.AUTHENTICATED_HTTP,
                headers=result.get("headers", {}),
                block_state=ChallengeStatus.OK,
            )
        except Exception:
            return None

    def _try_browser(self, request: WebRequest) -> AccessResult | None:
        if not self._browser_fn:
            return None
        try:
            result = self._browser_fn(url=request.url)
            if not isinstance(result, dict):
                return None
            ok = result.get("ok", False)
            block = result.get("block") or {}
            status = 200 if ok else 502
            challenge_status = ChallengeStatus.OK

            kind = ChallengeKind.UNKNOWN
            if not ok:
                kind = self._block_kind_to_challenge_kind(block) if block.get("blocked") else ChallengeKind.UNKNOWN
                detection = ChallengeDetection(
                    found=block.get("blocked", False),
                    kind=kind,
                    evidence=block.get("evidence", []),
                )
                challenge = self.challenge_sm.evaluate(detection)
                challenge_status = challenge.status
                # Transport failed without a detected block — the page is
                # unobservable.  Leaving this as OK causes agent_host to
                # report status="ok" for a 502 response.
                if not block.get("blocked"):
                    challenge_status = ChallengeStatus.UNOBSERVABLE

            extra: dict[str, Any] = {}
            if not ok and block.get("blocked"):
                extra = self._handoff_extra(request, challenge_status, kind.value)

            return AccessResult(
                url=result.get("url", request.url),
                status=status,
                text=result.get("text", ""),
                html=result.get("html", ""),
                source="browser",
                transport=TransportType.FULL_BROWSER,
                block_state=challenge_status,
                block=block,
                reason=result.get("reason", ""),
                extra=extra,
            )
        except Exception:
            return None

    def _detect_block(self, html: str, text: str, url: str) -> dict:
        if self._block_detect_fn:
            return self._block_detect_fn(html=html, text=text, url=url)
        return {}

    @staticmethod
    def _block_kind_to_challenge_kind(block: dict) -> ChallengeKind:
        kind_str = (block.get("kind") or "").lower()
        mapping = {
            "cloudflare": ChallengeKind.CLOUDFLARE_CHALLENGE,
            "turnstile": ChallengeKind.CLOUDFLARE_TURNSTILE,
            "kasada": ChallengeKind.KASADA_KPSDK,
            "kpsdk": ChallengeKind.KASADA_KPSDK,
            "akamai": ChallengeKind.AKAMAI,
            "perimeterx": ChallengeKind.PERIMETERX,
            "datadome": ChallengeKind.DATADOME,
            "login": ChallengeKind.LOGIN_REDIRECT,
            "rate_limit": ChallengeKind.RATE_LIMIT,
            "captcha": ChallengeKind.CAPTCHA,
        }
        for key, kind in mapping.items():
            if key in kind_str:
                return kind
        return ChallengeKind.BLOCKED if block.get("blocked") else ChallengeKind.UNKNOWN

    def _handoff_extra(self, request: WebRequest, status: ChallengeStatus, challenge_kind: str = "unknown") -> dict[str, Any]:
        if status != ChallengeStatus.NEED_HANDOFF or not self._handoff_broker:
            return {}
        origin = self._origin(request.url)
        handoff = self._handoff_broker.create(
            url=request.url,
            origin=origin,
            challenge_kind=challenge_kind,
        )
        return {"handoff_id": handoff.handoff_id}

    @staticmethod
    def _origin(url: str) -> str:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"
