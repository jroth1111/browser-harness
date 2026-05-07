"""SessionBroker — owns session secrets and issues scoped capabilities.

Raw cookie/state values never leave the broker. The agent runtime gets
redacted manifests or secret refs that transports materialize internally.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..capabilities.models import LeaseSpec, RiskLevel, RouteRule


@dataclass
class SecretBundle:
    bundle_id: str
    origin: str
    account_id: str = ""
    identity_id: str = ""
    cookies: list[dict[str, Any]] = field(default_factory=list)
    local_storage: dict[str, str] = field(default_factory=dict)
    session_storage: dict[str, str] = field(default_factory=dict)
    user_agent: str = ""
    created_at: float = field(default_factory=time.time)
    expires_at: float | None = None
    consent_id: str = ""
    allowed_actions: list[str] = field(default_factory=lambda: ["read"])
    route_rules: list[RouteRule] = field(default_factory=list)


@dataclass
class SecretRef:
    ref_id: str
    scope: str
    origin: str
    account_id: str = ""
    expires_at: float | None = None


@dataclass
class RedactedManifest:
    origin: str
    account_id: str = ""
    cookie_names: list[str] = field(default_factory=list)
    has_local_storage: bool = False
    has_session_storage: bool = False
    user_agent: str = ""
    allowed_actions: list[str] = field(default_factory=list)
    route_rule_count: int = 0
    expires_at: float | None = None


class SessionBroker:
    """Broker session secrets. Agents get refs; transports materialize."""

    def __init__(self, profile_dir: Path | None = None):
        self._bundles: dict[str, SecretBundle] = {}
        self._refs: dict[str, SecretRef] = {}
        self._profile_dir = profile_dir or Path(
            os.environ.get("BH_PROFILES_DIR", os.path.expanduser("~/.bh-profiles"))
        )
        self._profile_dir.mkdir(parents=True, exist_ok=True)

    def store_secret_bundle(
        self,
        origin: str,
        cookies: list[dict[str, Any]] | None = None,
        local_storage: dict[str, str] | None = None,
        session_storage: dict[str, str] | None = None,
        user_agent: str = "",
        account_id: str = "",
        identity_id: str = "",
        allowed_actions: list[str] | None = None,
        consent_id: str = "",
        route_rules: list[RouteRule] | None = None,
        expires_at: float | None = None,
    ) -> SecretRef:
        bundle_id = self._make_id(origin, account_id)
        bundle = SecretBundle(
            bundle_id=bundle_id,
            origin=origin,
            account_id=account_id,
            identity_id=identity_id,
            cookies=cookies or [],
            local_storage=local_storage or {},
            session_storage=session_storage or {},
            user_agent=user_agent,
            allowed_actions=allowed_actions or ["read"],
            consent_id=consent_id,
            route_rules=route_rules or [],
            expires_at=expires_at,
        )
        self._bundles[bundle_id] = bundle

        ref_id = f"ref_{bundle_id}"
        ref = SecretRef(
            ref_id=ref_id,
            scope=f"{origin}:{account_id or '*'}",
            origin=origin,
            account_id=account_id,
            expires_at=expires_at,
        )
        self._refs[ref_id] = ref
        return ref

    def materialize_for_transport(
        self,
        ref: SecretRef,
        target_origin: str,
        allowed_actions: list[str] | None = None,
    ) -> SecretBundle | None:
        """Materialize secrets for a transport adapter. Only allowed if origin matches."""
        bundle = self._bundles.get(self._ref_to_bundle_id(ref.ref_id))
        if not bundle:
            return None

        if bundle.origin != target_origin:
            return None

        if bundle.expires_at and time.time() > bundle.expires_at:
            return None

        if allowed_actions and not set(allowed_actions).issubset(bundle.allowed_actions):
            return None

        return bundle

    def redacted_manifest(self, ref: SecretRef) -> RedactedManifest | None:
        """Return a manifest with no secret values — safe for agent runtime."""
        bundle = self._bundles.get(self._ref_to_bundle_id(ref.ref_id))
        if not bundle:
            return None

        return RedactedManifest(
            origin=bundle.origin,
            account_id=bundle.account_id,
            cookie_names=[c.get("name", "") for c in bundle.cookies],
            has_local_storage=bool(bundle.local_storage),
            has_session_storage=bool(bundle.session_storage),
            user_agent=bundle.user_agent,
            allowed_actions=bundle.allowed_actions,
            route_rule_count=len(bundle.route_rules),
            expires_at=bundle.expires_at,
        )

    def revoke(self, ref: SecretRef) -> bool:
        bundle_id = self._ref_to_bundle_id(ref.ref_id)
        removed = self._bundles.pop(bundle_id, None)
        self._refs.pop(ref.ref_id, None)
        return removed is not None

    def ref_for_origin(self, origin: str, account_id: str = "") -> SecretRef | None:
        ref_id = f"ref_{self._make_id(origin, account_id)}"
        return self._refs.get(ref_id)

    def _make_id(self, origin: str, account_id: str = "") -> str:
        key = f"{origin}:{account_id}"
        return hashlib.sha256(key.encode()).hexdigest()[:24]

    @staticmethod
    def _ref_to_bundle_id(ref_id: str) -> str:
        # ref_id = "ref_" + bundle_id
        return ref_id[4:] if ref_id.startswith("ref_") else ref_id
