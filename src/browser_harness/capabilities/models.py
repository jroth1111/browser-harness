"""Typed capability models for the authority-preserving access plane."""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


class RiskLevel(enum.Enum):
    PUBLIC_READ = "public_read"
    AUTHENTICATED_READ = "authenticated_read"
    LOW_RISK_WRITE = "low_risk_write"
    EXTERNAL_SIDE_EFFECT = "external_side_effect"
    PAYMENT_DELETE_SECURITY = "payment_delete_security"
    LOGIN_CHALLENGE_2FA = "login_challenge_2fa"


class TransportType(enum.Enum):
    CACHE = "cache"
    EXISTING_CAPABILITY = "existing_capability"
    OFFICIAL_API = "official_api"
    PUBLIC_HTTP = "public_http"
    AUTHENTICATED_HTTP = "authenticated_http"
    BROWSER_BOOTSTRAP = "browser_bootstrap"
    BROWSER_DERIVED_LEASE = "browser_derived_lease"
    FULL_BROWSER = "full_browser"
    HUMAN_HANDOFF = "human_handoff"


class ChallengeStatus(enum.Enum):
    OK = "ok"
    BLOCKED = "blocked"
    NEED_HANDOFF = "need_handoff"
    AUTH_EXPIRED = "auth_expired"
    RATE_LIMITED = "rate_limited"
    UNOBSERVABLE = "unobservable"


class ExtractionState(enum.Enum):
    VALUE = "value"
    ABSENT = "absent"
    UNOBSERVABLE = "unobservable"
    NOT_CHECKED = "not_checked"


@dataclass(frozen=True)
class WebRequest:
    method: str = "GET"
    url: str = ""
    risk: RiskLevel = RiskLevel.PUBLIC_READ
    expected_type: str = "html"
    auth_required: bool = False
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes | None = None


@dataclass(frozen=True)
class RouteRule:
    origin: str
    path_pattern: str
    allowed_methods: list[str] = field(default_factory=lambda: ["GET"])
    risk_max: RiskLevel = RiskLevel.PUBLIC_READ
    transport_preference: TransportType = TransportType.PUBLIC_HTTP
    auth_required: bool = False
    source: str = ""  # "learned", "manifest", "static"


@dataclass(frozen=True)
class Capability:
    cap_id: str
    transport: TransportType
    scope: str  # e.g. origin or origin+path
    risk_max: RiskLevel
    secret_bundle_ref: str | None = None
    expires_at: float | None = None
    allowed_methods: list[str] = field(default_factory=lambda: ["GET"])
    max_requests: int | None = None
    manifest_version: str | None = None


@dataclass
class TransportDecision:
    transport: TransportType
    capability: Capability | None = None
    route_rule: RouteRule | None = None
    reason: str = ""


@dataclass
class AuthorityDecision:
    allowed: bool = False
    status: str = "denied"  # allowed, denied, need_user_approval, need_handoff
    risk_max: RiskLevel = RiskLevel.PUBLIC_READ
    allowed_capability_types: list[TransportType] = field(default_factory=list)
    reason: str = ""

    @property
    def need_approval(self) -> bool:
        return self.status == "need_user_approval"

    @property
    def need_handoff(self) -> bool:
        return self.status == "need_handoff"


@dataclass
class WebAction:
    kind: str  # click, type, fill, press, submit, navigate
    target: str = ""
    value: str = ""
    risk: RiskLevel = RiskLevel.LOW_RISK_WRITE
    coordinates: tuple[int, int] | None = None

    @property
    def is_external_side_effect(self) -> bool:
        return self.risk in (
            RiskLevel.EXTERNAL_SIDE_EFFECT,
            RiskLevel.PAYMENT_DELETE_SECURITY,
        )


@dataclass
class ElementTarget:
    evidence_type: str  # "ax_ref", "selector", "coordinates", "ocr"
    evidence_id: str | None = None
    selector: str | None = None
    coordinates: tuple[int, int] | None = None
    screenshot_ref: str | None = None
    confidence: float = 1.0


@dataclass
class ExtractionFieldResult:
    name: str
    state: ExtractionState = ExtractionState.NOT_CHECKED
    value: Any = None
    source: str = ""


@dataclass
class ExtractionResult:
    url: str
    fields: list[ExtractionFieldResult] = field(default_factory=list)
    source_receipt: str = ""
    capability_id: str = ""
    transport: TransportType = TransportType.PUBLIC_HTTP
    block_state: ChallengeStatus = ChallengeStatus.OK
    manifest_version: str = ""

    @property
    def canonical(self) -> bool:
        return bool(self.source_receipt)


@dataclass
class LeaseSpec:
    origin: str
    account_id: str = ""
    identity_id: str = ""
    allowed_methods: list[str] = field(default_factory=lambda: ["GET"])
    risk_max: RiskLevel = RiskLevel.PUBLIC_READ
    route_rules: list[RouteRule] = field(default_factory=list)
    secret_bundle_ref: str = ""
    expires_at: float | None = None
    max_requests: int | None = None
    max_parallel: int = 1
    manifest_version: str = ""

    def allows(self, request: WebRequest) -> bool:
        from urllib.parse import urlparse

        parsed = urlparse(request.url)
        if parsed.scheme + "://" + parsed.netloc != self.origin:
            return False
        if request.method.upper() not in [m.upper() for m in self.allowed_methods]:
            return False
        if not self._route_allows(parsed.path, request.method):
            return False
        risk_order = list(RiskLevel)
        if risk_order.index(request.risk) > risk_order.index(self.risk_max):
            return False
        return True

    def _route_allows(self, path: str, method: str) -> bool:
        if not self.route_rules:
            return True
        import re

        for rule in self.route_rules:
            if re.match(rule.path_pattern, path):
                return method.upper() in [m.upper() for m in rule.allowed_methods]
        return False
