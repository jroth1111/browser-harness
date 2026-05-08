"""Authority proof tests — prove the new authority model is real.

These tests verify that:
1. Agent runtime cannot execute arbitrary Python
2. Raw CDP is not agent-facing
3. Session secrets never leave the broker
4. Challenges become authority boundaries (no silent solver)
5. Actions are gated by risk level
6. Budgets are enforced
7. Domain skills cannot own transport authority
"""
import json
import pytest
from pathlib import Path

from browser_harness.runtime.agent_host import AgentHost
from browser_harness.runtime.agent_worker import ALLOWED_TOOLS
from browser_harness.runtime.sandbox import (
    FORBIDDEN_TOOLS,
    RESTRICTED_BUILTINS,
    STDLIB_ALLOWLIST,
    WORKER_ALLOWLIST,
)
from browser_harness.authority.policy import PolicyEngine
from browser_harness.capabilities.resolver import AccessPlane
from browser_harness.authority.challenge import (
    ChallengeStateMachine,
    ChallengeDetection,
    ChallengeKind,
    ChallengeDecision,
)
from browser_harness.authority.action_policy import ActionPolicy
from browser_harness.capabilities.models import (
    AuthorityDecision,
    ChallengeStatus,
    Capability,
    ExtractionResult,
    ExtractionState,
    LeaseSpec,
    RiskLevel,
    RouteRule,
    TransportType,
    WebAction,
    WebRequest,
)
from browser_harness.sessions.broker import SessionBroker, SecretRef
from browser_harness.scheduler.budgets import BudgetController, BudgetConfig
from browser_harness.transports.cdp_adapter import CDPAdapter, PolicyDeniedError
from browser_harness.transports.provider_registry import (
    ProviderRegistry,
    ProviderInfo,
    ProviderCapability,
    default_registry,
)


# --- 1. Sandbox structural invariants ---

class TestSandboxInvariants:
    """Structural facts the worker subprocess relies on.

    Behavioral end-to-end checks (audit hook actually rejects imports,
    worker actually denies forbidden tools, host actually routes valid
    calls) live in tests/test_agent_worker_isolation.py — they spawn a
    real subprocess.  These are static guarantees the build can verify
    without a worker.
    """
    def test_allowed_and_forbidden_tools_disjoint(self):
        assert ALLOWED_TOOLS.isdisjoint(FORBIDDEN_TOOLS)

    def test_forbidden_tools_cover_known_authority_leaks(self):
        for leak in ["cdp", "_send", "_ipc", "browser_cookies",
                     "stealth_session", "solve_turnstile",
                     "navigate_via_google"]:
            assert leak in FORBIDDEN_TOOLS

    def test_dangerous_builtins_restricted(self):
        for name in ("exec", "eval", "compile", "__import__"):
            assert name in RESTRICTED_BUILTINS

    def test_stdlib_allowlist_excludes_network_and_spawn(self):
        for forbidden in ("urllib", "http", "socket", "subprocess",
                          "ctypes", "multiprocessing", "threading",
                          "signal", "os", "sys", "pathlib", "tempfile",
                          "importlib", "pickle"):
            assert forbidden not in STDLIB_ALLOWLIST

    def test_worker_allowlist_only_validation_modules(self):
        for mod in WORKER_ALLOWLIST:
            assert mod.startswith("browser_harness.")
            assert "transport" not in mod
            assert "helpers" not in mod
            assert "daemon" not in mod
            assert "_ipc" not in mod


# --- 2. Raw CDP bypass test ---

class TestCDPAdapterPolicy:
    def test_cdp_adapter_requires_capability(self):
        adapter = CDPAdapter(cdp_fn=lambda method, **kw: {})
        with pytest.raises(PolicyDeniedError):
            adapter.send("Network.getCookies")

    def test_cdp_adapter_requires_capability_for_runtime_evaluate(self):
        adapter = CDPAdapter(cdp_fn=lambda method, **kw: {})
        with pytest.raises(PolicyDeniedError):
            adapter.send("Runtime.evaluate", expression="document.cookie")

    def test_cdp_adapter_allows_with_capability(self):
        adapter = CDPAdapter(cdp_fn=lambda method, **kw: {"result": {}})
        cap = Capability(
            cap_id="test",
            transport=TransportType.FULL_BROWSER,
            scope="https://example.com",
            risk_max=RiskLevel.PUBLIC_READ,
        )
        result = adapter.send("Runtime.evaluate", capability=cap, expression="1+1")
        assert result["result"] == {}

    def test_cdp_adapter_rejects_wrong_capability_type(self):
        adapter = CDPAdapter(cdp_fn=lambda method, **kw: {})
        cap = Capability(
            cap_id="test",
            transport=TransportType.PUBLIC_HTTP,
            scope="https://example.com",
            risk_max=RiskLevel.PUBLIC_READ,
        )
        with pytest.raises(PolicyDeniedError):
            adapter.send("Runtime.evaluate", capability=cap, expression="1+1")

    def test_restricted_methods(self):
        adapter = CDPAdapter()
        assert adapter.is_restricted("Network.getCookies")
        assert adapter.is_restricted("Runtime.evaluate")
        assert adapter.is_restricted("Page.navigate")
        assert not adapter.is_restricted("Page.getFrameTree")


# --- 3. Challenge no-solver test ---

class TestChallengeStateMachine:
    def test_turnstile_returns_handoff_not_solver(self):
        sm = ChallengeStateMachine()
        detection = ChallengeDetection(
            found=True,
            kind=ChallengeKind.CLOUDFLARE_TURNSTILE,
            challenge_type="turnstile_widget",
        )
        decision = sm.evaluate(detection)
        assert decision.status == ChallengeStatus.NEED_HANDOFF
        assert "handoff" in decision.reason.lower() or "turnstile" in decision.reason.lower()

    def test_login_redirect_returns_handoff(self):
        sm = ChallengeStateMachine()
        detection = ChallengeDetection(
            found=True,
            kind=ChallengeKind.LOGIN_REDIRECT,
        )
        decision = sm.evaluate(detection)
        assert decision.status == ChallengeStatus.NEED_HANDOFF

    def test_rate_limit_returns_rate_limited(self):
        sm = ChallengeStateMachine()
        detection = ChallengeDetection(
            found=True,
            kind=ChallengeKind.RATE_LIMIT,
        )
        decision = sm.evaluate(detection)
        assert decision.status == ChallengeStatus.RATE_LIMITED

    def test_no_challenge_returns_ok(self):
        sm = ChallengeStateMachine()
        detection = ChallengeDetection(found=False)
        decision = sm.evaluate(detection)
        assert decision.status == ChallengeStatus.OK

    def test_kasada_returns_blocked(self):
        sm = ChallengeStateMachine()
        detection = ChallengeDetection(found=True, kind=ChallengeKind.KASADA_KPSDK)
        decision = sm.evaluate(detection)
        assert decision.status == ChallengeStatus.BLOCKED

    def test_2fa_returns_handoff(self):
        sm = ChallengeStateMachine()
        detection = ChallengeDetection(found=True, kind=ChallengeKind.TWO_FA)
        decision = sm.evaluate(detection)
        assert decision.status == ChallengeStatus.NEED_HANDOFF


# --- 4. Auth state cannot be read raw ---

class TestSessionBroker:
    def test_agent_gets_redacted_manifest_only(self):
        broker = SessionBroker()
        ref = broker.store_secret_bundle(
            origin="https://example.com",
            cookies=[
                {"name": "session", "value": "secret123", "domain": ".example.com"},
                {"name": "csrf", "value": "tok456", "domain": ".example.com"},
            ],
            local_storage={"user_prefs": "dark_mode"},
            user_agent="Mozilla/5.0",
            account_id="user1",
        )
        manifest = broker.redacted_manifest(ref)
        assert manifest is not None
        assert "cookie_names" in manifest.__dataclass_fields__
        assert manifest.cookie_names == ["session", "csrf"]
        # Ensure no secret values in serialized form
        manifest_json = json.dumps(manifest.__dict__, default=str)
        assert "secret123" not in manifest_json
        assert "tok456" not in manifest_json
        assert "dark_mode" not in manifest_json

    def test_materialize_rejects_wrong_origin(self):
        broker = SessionBroker()
        ref = broker.store_secret_bundle(
            origin="https://example.com",
            cookies=[{"name": "s", "value": "v"}],
        )
        result = broker.materialize_for_transport(ref, target_origin="https://evil.example")
        assert result is None

    def test_materialize_accepts_matching_origin(self):
        broker = SessionBroker()
        ref = broker.store_secret_bundle(
            origin="https://example.com",
            cookies=[{"name": "s", "value": "v"}],
        )
        result = broker.materialize_for_transport(ref, target_origin="https://example.com")
        assert result is not None
        assert len(result.cookies) == 1

    def test_revoke_removes_bundle(self):
        broker = SessionBroker()
        ref = broker.store_secret_bundle(
            origin="https://example.com",
            cookies=[{"name": "s", "value": "v"}],
        )
        assert broker.revoke(ref) is True
        assert broker.redacted_manifest(ref) is None

    def test_expired_bundle_not_materialized(self):
        import time
        broker = SessionBroker()
        ref = broker.store_secret_bundle(
            origin="https://example.com",
            cookies=[{"name": "s", "value": "v"}],
            expires_at=time.time() - 100,  # expired
        )
        result = broker.materialize_for_transport(ref, target_origin="https://example.com")
        assert result is None


# --- 5. Lease scope test ---

class TestLeaseScope:
    def _make_lease(self, **overrides):
        defaults = dict(
            origin="https://app.example.com",
            allowed_methods=["GET"],
            risk_max=RiskLevel.PUBLIC_READ,
            secret_bundle_ref="ref_test",
            route_rules=[
                RouteRule(
                    origin="https://app.example.com",
                    path_pattern=r"/api/.*",
                    allowed_methods=["GET"],
                ),
            ],
        )
        defaults.update(overrides)
        return LeaseSpec(**defaults)

    def test_lease_denies_wrong_origin(self):
        lease = self._make_lease()
        req = WebRequest(url="https://evil.example/api/x", risk=RiskLevel.PUBLIC_READ)
        assert not lease.allows(req)

    def test_lease_denies_wrong_method(self):
        lease = self._make_lease()
        req = WebRequest(method="POST", url="https://app.example.com/api/data", risk=RiskLevel.PUBLIC_READ)
        assert not lease.allows(req)

    def test_lease_denies_unruled_path(self):
        lease = self._make_lease()
        req = WebRequest(url="https://app.example.com/admin", risk=RiskLevel.PUBLIC_READ)
        assert not lease.allows(req)

    def test_lease_allows_matching_request(self):
        lease = self._make_lease()
        req = WebRequest(url="https://app.example.com/api/data", risk=RiskLevel.PUBLIC_READ)
        assert lease.allows(req)

    def test_lease_denies_excess_risk(self):
        lease = self._make_lease(risk_max=RiskLevel.PUBLIC_READ)
        req = WebRequest(url="https://app.example.com/api/data", risk=RiskLevel.EXTERNAL_SIDE_EFFECT)
        assert not lease.allows(req)


# --- 6. Policy engine risk rules ---

class TestPolicyEngine:
    def test_r0_public_read_allowed(self):
        engine = PolicyEngine()
        req = WebRequest(url="https://example.com/page", risk=RiskLevel.PUBLIC_READ)
        decision = engine.authorize(req)
        assert decision.allowed

    def test_r3_external_side_effect_needs_approval(self):
        engine = PolicyEngine()
        action = WebAction(kind="click", target="submit", risk=RiskLevel.EXTERNAL_SIDE_EFFECT)
        decision = engine.authorize_action(action)
        assert decision.status == "need_user_approval"
        assert not decision.allowed

    def test_r4_payment_needs_handoff(self):
        engine = PolicyEngine()
        action = WebAction(kind="click", target="pay", risk=RiskLevel.PAYMENT_DELETE_SECURITY)
        decision = engine.authorize_action(action)
        assert decision.status == "need_handoff"
        assert not decision.allowed

    def test_blocked_domain_denied(self):
        engine = PolicyEngine(blocked_domains={"https://evil.example"})
        req = WebRequest(url="https://evil.example/page", risk=RiskLevel.PUBLIC_READ)
        decision = engine.authorize(req)
        assert not decision.allowed
        assert "blocked" in decision.reason

    def test_allowlist_enforced(self):
        engine = PolicyEngine(allowed_domains={"https://example.com"})
        req = WebRequest(url="https://other.example/page", risk=RiskLevel.PUBLIC_READ)
        decision = engine.authorize(req)
        assert not decision.allowed


# --- 7. Action policy classification ---

class TestActionPolicy:
    def test_screenshot_is_read_only(self):
        policy = ActionPolicy()
        action = WebAction(kind="screenshot", risk=RiskLevel.LOW_RISK_WRITE)
        risk = policy.classify(action)
        assert risk == RiskLevel.PUBLIC_READ

    def test_submit_button_is_external_side_effect(self):
        policy = ActionPolicy()
        action = WebAction(kind="click", target="submit", risk=RiskLevel.LOW_RISK_WRITE)
        risk = policy.classify(action)
        assert risk == RiskLevel.EXTERNAL_SIDE_EFFECT

    def test_payment_button_is_high_risk(self):
        policy = ActionPolicy()
        action = WebAction(kind="click", target="pay now", risk=RiskLevel.LOW_RISK_WRITE)
        risk = policy.classify(action)
        assert risk == RiskLevel.PAYMENT_DELETE_SECURITY

    @pytest.mark.parametrize("risk", [
        RiskLevel.EXTERNAL_SIDE_EFFECT,
        RiskLevel.PAYMENT_DELETE_SECURITY,
    ])
    def test_sensitive_action_requires_approval_or_handoff(self, risk):
        policy = ActionPolicy()
        action = WebAction(kind="click", target="submit", risk=risk)
        decision = policy.authorize(action)
        assert not decision.allowed
        assert decision.status in ("need_user_approval", "need_handoff")


# --- 8. Budget and circuit breaker ---

class TestBudgetController:
    def test_repeated_403_opens_circuit_breaker(self):
        ctrl = BudgetController(BudgetConfig(
            circuit_breaker_threshold=3,
            request_interval_seconds=0,
        ))
        origin = "https://example.com"

        for _ in range(3):
            ok, _ = ctrl.ok(origin)
            assert ok
            ctrl.record(origin, status=403, block=True)

        ok, reason = ctrl.ok(origin)
        assert not ok
        assert "circuit" in reason.lower()

    def test_origin_budget_exhaustion(self):
        ctrl = BudgetController(BudgetConfig(max_requests_per_origin=2, request_interval_seconds=0))
        origin = "https://example.com"
        ctrl.record(origin, status=200)
        ctrl.record(origin, status=200)
        ok, reason = ctrl.ok(origin)
        assert not ok

    def test_writer_lock_prevents_concurrent_mutation(self):
        ctrl = BudgetController()
        assert ctrl.claim_writer("profile1", "worker_a")
        assert not ctrl.claim_writer("profile1", "worker_b")
        ctrl.release_writer("profile1", "worker_a")
        assert ctrl.claim_writer("profile1", "worker_b")

    def test_one_bootstrap_writer_per_profile(self):
        ctrl = BudgetController()
        assert ctrl.claim_writer("p1", "a")
        assert not ctrl.claim_writer("p1", "b")
        assert ctrl.writer_holder("p1") == "a"


# --- 9. Source receipt required for canonical extraction ---

class TestExtractionProof:
    def test_canonical_extraction_requires_receipt(self):
        result = ExtractionResult(
            url="https://example.com",
            fields=[],
            source_receipt="receipt_abc",
        )
        assert result.canonical

    def test_extraction_without_receipt_is_not_canonical(self):
        result = ExtractionResult(
            url="https://example.com",
            fields=[],
            source_receipt="",
        )
        assert not result.canonical

    def test_extraction_field_states(self):
        result = ExtractionResult(
            url="https://example.com",
            fields=[
                {"name": "price", "state": "value", "value": "$10"},
                {"name": "stock", "state": "absent"},
                {"name": "reviews", "state": "unobservable"},
            ],
            source_receipt="r1",
        )
        assert result.canonical


# --- 10. Domain skills transport authority gate ---

FORBIDDEN_DOMAIN_TOKENS = [
    "urllib.request.urlopen",
    "requests.get",
    "requests.post",
    "browser_cookies",
    "cdp(",
    "stealth_session",
    "solve_turnstile",
    "navigate_via_google",
    "Network.getCookies",
    "Runtime.evaluate",
]


def _load_approved_adapters(domain_dir: Path) -> set[str]:
    """Load approved adapter paths from .approved-adapters files.

    Each domain skill can contain a .approved-adapters file listing Python
    file paths (relative to the domain skill directory, one per line) that
    are intentionally using low-level transport APIs as adapter code.
    Lines starting with # are comments; blank lines are ignored.
    """
    approved = set()
    for adapters_file in domain_dir.rglob(".approved-adapters"):
        skill_dir = adapters_file.parent
        skill_rel = skill_dir.relative_to(domain_dir)
        for line in adapters_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Normalize: skill_dir/file.py relative to domain_dir
            full_rel = str(skill_rel / line)
            approved.add(full_rel)
    return approved


class TestDomainSkillAuthority:
    def test_domain_skills_do_not_import_transport_authority(self):
        """Domain skills should not contain raw transport authority.

        This test currently documents known violations (Leak 6 in the authority
        refactor plan). Once domain skills are migrated to use AccessPlane and
        approved adapters, this test will pass fully.
        """
        domain_dir = Path(__file__).parent.parent / "domain-skills"
        if not domain_dir.exists():
            pytest.skip("domain-skills directory not found")

        approved = _load_approved_adapters(domain_dir)

        violations = []
        for path in domain_dir.rglob("*.py"):
            rel = str(path.relative_to(domain_dir))
            if rel in approved:
                continue
            text = path.read_text()
            for token in FORBIDDEN_DOMAIN_TOKENS:
                if token in text:
                    violations.append(f"{path.relative_to(domain_dir.parent)}: {token}")

        assert not violations, (
            f"Domain skills contain forbidden transport authority ({len(violations)} violations):\n"
            + "\n".join(violations[:10])
            + (f"\n... and {len(violations) - 10} more" if len(violations) > 10 else "")
        )


# --- 11. Provider registry ---

class TestProviderRegistry:
    def test_agent_cannot_launch_provider_directly(self):
        """Subprocess agent does not expose provider launch as a tool."""
        host = AgentHost()
        try:
            result = host.call("stealth_session", {})
            assert result["status"] == "denied"
        finally:
            host.shutdown()

    def test_default_registry_has_providers(self):
        registry = default_registry()
        providers = registry.list_providers()
        ids = {p.provider_id for p in providers}
        assert "local_chrome" in ids
        assert "patchright" in ids

    def test_find_by_capability(self):
        registry = default_registry()
        stealth = registry.find_by_capability(ProviderCapability.STEALTH)
        assert len(stealth) > 0
        ids = {p.provider_id for p in stealth}
        assert "local_chrome" not in ids


# --- 12. Subprocess agent host CLI ---

class TestAgentHostCLI:
    def test_high_risk_action_requires_handoff(self):
        """Click on a payment target is gated to need_handoff, not allowed."""
        host = AgentHost()
        try:
            result = host.call(
                "click",
                {"target": "pay", "risk": "payment_delete_security"},
            )
            assert result["status"] == "need_handoff"
        finally:
            host.shutdown()

    def test_allowed_tools_set_includes_authority_tools(self):
        for tool in ("fetch", "click", "extract", "navigate", "fill", "press"):
            assert tool in ALLOWED_TOOLS

    def test_allowed_tools_excludes_authority_leaks(self):
        for tool in ("cdp", "browser_cookies", "_send", "stealth_session"):
            assert tool not in ALLOWED_TOOLS


# --- 13. Daemon lazy domain enabling ---

class TestDaemonLazyDomains:
    def test_lazy_daemon_only_enables_page_on_attach(self):
        """In lazy mode, attach should not eagerly enable Runtime, DOM, or Network."""
        import asyncio
        from browser_harness.daemon import Daemon

        class _FakeCDP:
            def __init__(self):
                self.calls = []
            async def send_raw(self, method, params=None, session_id=None):
                self.calls.append((method, params, session_id))
                if method == "Target.getTargets":
                    return {"targetInfos": [{"targetId": "t1", "type": "page", "url": "https://example.com"}]}
                if method == "Target.attachToTarget":
                    return {"sessionId": "session-X"}
                return {}

        d = Daemon(lazy_domains=True)
        d.cdp = _FakeCDP()
        asyncio.run(d.attach_first_page())

        enabled = {call[0] for call in d.cdp.calls if call[0].endswith(".enable")}
        forbidden = {"Runtime.enable", "DOM.enable", "Network.enable", "Console.enable"}
        violations = forbidden & enabled
        assert not violations, f"lazy attach should not enable: {violations}"
        assert "Page.enable" in enabled, "lazy attach should enable Page"

    def test_eager_daemon_enables_all_four(self):
        """Legacy mode preserves the existing 4-domain behavior."""
        import asyncio
        from browser_harness.daemon import Daemon

        class _FakeCDP:
            def __init__(self):
                self.calls = []
            async def send_raw(self, method, params=None, session_id=None):
                self.calls.append((method, params, session_id))
                if method == "Target.getTargets":
                    return {"targetInfos": [{"targetId": "t1", "type": "page", "url": "https://example.com"}]}
                if method == "Target.attachToTarget":
                    return {"sessionId": "session-X"}
                return {}

        d = Daemon(lazy_domains=False)
        d.cdp = _FakeCDP()
        asyncio.run(d.attach_first_page())

        enabled = {call[0] for call in d.cdp.calls if call[0].endswith(".enable")}
        assert enabled == {"Page.enable", "DOM.enable", "Runtime.enable", "Network.enable"}

    def test_ensure_domains_enables_on_demand(self):
        """Controllers can explicitly enable domains they need."""
        import asyncio
        from browser_harness.daemon import Daemon

        class _FakeCDP:
            def __init__(self):
                self.calls = []
            async def send_raw(self, method, params=None, session_id=None):
                self.calls.append((method, params, session_id))
                return {}

        d = Daemon(lazy_domains=True)
        d.cdp = _FakeCDP()
        asyncio.run(d.ensure_domains("session-X", "Runtime", "DOM"))

        enabled = {call[0] for call in d.cdp.calls if call[0].endswith(".enable")}
        assert "Runtime.enable" in enabled
        assert "DOM.enable" in enabled
        assert "Network.enable" not in enabled


# --- 14. Extraction enforcement ---

class TestExtractionEnforcement:
    def test_canonical_extraction_includes_receipt(self):
        from browser_harness.extraction.source_selection import enforce_canonical_extraction

        result = enforce_canonical_extraction(
            url="https://example.com/product",
            fields={"price": "$10", "name": "Widget", "stock": "5"},
            source_type="browser_ui",
            source_context={"page": "product"},
            backend="cdp",
        )
        assert result.canonical
        assert result.source_receipt  # non-empty

    def test_canonical_extraction_classifies_fields(self):
        from browser_harness.extraction.source_selection import enforce_canonical_extraction

        result = enforce_canonical_extraction(
            url="https://example.com",
            fields={"price": "$10", "stock": None},
            source_type="http",
            source_context={"source": "api"},
            backend="urllib",
            expected_fields=["price", "stock", "reviews"],
        )
        states = {f.name: f.state for f in result.fields}
        assert states["price"] == ExtractionState.VALUE
        assert states["stock"] == ExtractionState.ABSENT
        assert states["reviews"] == ExtractionState.NOT_CHECKED

    def test_canonical_extraction_rejects_empty_string_as_missing(self):
        """The extraction contract rejects empty strings — callers must use None or omit."""
        from browser_harness.extraction.source_selection import enforce_canonical_extraction

        with pytest.raises(ValueError, match="empty string is ambiguous"):
            enforce_canonical_extraction(
                url="https://example.com",
                fields={"price": ""},
                source_type="http",
                source_context={"source": "api"},
                backend="urllib",
                expected_fields=["price"],
            )

    def test_require_receipt_raises_on_missing(self):
        from browser_harness.extraction.source_selection import require_receipt, MissingReceiptError
        from browser_harness.capabilities.models import ExtractionResult

        result = ExtractionResult(url="https://example.com", source_receipt="")
        with pytest.raises(MissingReceiptError):
            require_receipt(result)

    def test_require_field_coverage_raises_on_missing(self):
        from browser_harness.extraction.source_selection import require_field_coverage, MissingFieldCoverageError
        from browser_harness.capabilities.models import ExtractionResult, ExtractionFieldResult, ExtractionState

        result = ExtractionResult(
            url="https://example.com",
            source_receipt="r1",
            fields=[
                ExtractionFieldResult(name="price", state=ExtractionState.VALUE),
                ExtractionFieldResult(name="stock", state=ExtractionState.NOT_CHECKED),
            ],
        )
        with pytest.raises(MissingFieldCoverageError):
            require_field_coverage(result, ["price", "stock"])

    def test_blocked_state_recorded(self):
        from browser_harness.extraction.source_selection import enforce_canonical_extraction

        result = enforce_canonical_extraction(
            url="https://example.com",
            fields={"price": "__UNOBSERVABLE__"},
            source_type="browser_ui",
            source_context={"page": "product"},
            backend="cdp",
            block_state=ChallengeStatus.BLOCKED,
        )
        assert result.block_state == ChallengeStatus.BLOCKED
        # Blocked sources cannot be canonical per source_receipts contract
        # but they still produce a valid extraction result with the block state


# --- 15. Cross-origin cookie redirect test ---

class TestCrossOriginSecurity:
    def test_session_broker_rejects_cross_origin_materialization(self):
        """Authenticated HTTP cannot leak cookies across origins."""
        broker = SessionBroker()
        ref = broker.store_secret_bundle(
            origin="https://app.example.com",
            cookies=[{"name": "session", "value": "secret123", "domain": ".app.example.com"}],
        )
        # Attempt to materialize for a different origin
        bundle = broker.materialize_for_transport(ref, target_origin="https://evil.example")
        assert bundle is None, "cross-origin materialization must be rejected"

    def test_lease_rejects_cross_origin_request(self):
        """Lease does not allow requests to different origins."""
        lease = LeaseSpec(
            origin="https://app.example.com",
            allowed_methods=["GET"],
            risk_max=RiskLevel.AUTHENTICATED_READ,
            secret_bundle_ref="ref_test",
        )
        cross_origin_req = WebRequest(
            url="https://evil.example/api/data",
            risk=RiskLevel.AUTHENTICATED_READ,
        )
        assert not lease.allows(cross_origin_req)

    def test_public_fetch_does_not_attach_session(self):
        """Public requests must not use any session state."""
        plane = AccessPlane(
            policy=PolicyEngine(),
            broker=SessionBroker(),  # empty broker — no sessions
            http_fn=lambda url, **kw: "public content",
        )
        req = WebRequest(url="https://example.com/public", risk=RiskLevel.PUBLIC_READ, auth_required=False)
        result = plane.execute(req)
        assert result.status == 200
        assert result.source == "http"  # plain HTTP, no session


class TestAuthorityFetchWiring:
    """Prove fetch(source='auto') delegates to AccessPlane by default."""

    def test_auto_source_routes_through_plane(self, monkeypatch):
        """fetch(source='auto') uses AccessPlane, returning authority source."""
        from browser_harness.helpers import fetch
        monkeypatch.setattr(
            "browser_harness.helpers.http_get",
            lambda url, **kw: "fetched via authority",
        )
        resp = fetch("https://example.com/page", source="auto")
        assert resp.source == "authority"
        assert resp.text == "fetched via authority"
        assert resp.status == 200

    def test_explicit_http_still_bypasses_authority(self, monkeypatch):
        """source='http' always uses direct path, not authority pipeline."""
        from browser_harness.helpers import fetch
        monkeypatch.setattr(
            "browser_harness.helpers.http_get",
            lambda url, **kw: "direct http",
        )
        resp = fetch("https://example.com/page", source="http")
        assert resp.source == "http"

    def test_authority_returns_403_on_block(self, monkeypatch):
        """When blocked, authority fetch returns 403, not 200."""
        from browser_harness.helpers import fetch
        monkeypatch.setattr(
            "browser_harness.helpers.http_get",
            lambda url, **kw: "challenge page",
        )
        monkeypatch.setattr(
            "browser_harness.helpers.detect_block_page",
            lambda **kw: {"blocked": True, "kind": "cloudflare", "evidence": []},
        )
        resp = fetch("https://example.com/protected", source="auto")
        assert resp.status == 403
        assert resp.source == "authority"


# --- 17. CDP capability gate ---

class TestCDPCapabilityGate:
    def test_cdp_blocked_in_agent_worker_env(self, monkeypatch):
        """cdp() raises RuntimeError when BH_AGENT_WORKER=1."""
        from browser_harness import helpers
        monkeypatch.setenv("BH_AGENT_WORKER", "1")
        with pytest.raises(RuntimeError, match="not available in agent worker"):
            helpers.cdp("Runtime.evaluate")

    def test_cdp_allowed_in_dev_runtime(self, monkeypatch):
        """cdp() works normally when BH_AGENT_WORKER is unset."""
        from browser_harness import helpers
        monkeypatch.delenv("BH_AGENT_WORKER", raising=False)
        # We can't actually call cdp() without a daemon, but we can verify
        # the gate doesn't raise before the _send call.
        # Patch _send to avoid needing a live daemon.
        monkeypatch.setattr(helpers, "_send", lambda msg, **kw: {"result": {}})
        result = helpers.cdp("Runtime.evaluate")
        assert result == {}


# --- 18. Handoff CLI ---

class TestHandoffCLI:
    def test_handoff_cli_completes_request(self, tmp_path, monkeypatch, capsys):
        """--handoff looks up request, opens browser, waits for user, completes token."""
        from browser_harness.authority.handoff import HandoffBroker

        broker = HandoffBroker(store_dir=tmp_path)
        request = broker.create(
            url="https://example.com/challenge",
            origin="https://example.com",
            challenge_kind="cloudflare",
        )

        # Mock webbrowser.open and input
        monkeypatch.setattr("webbrowser.open", lambda url: None)
        monkeypatch.setattr("builtins.input", lambda: "")

        from browser_harness.run import _run_handoff
        # Point broker at tmp_path
        monkeypatch.setattr(
            "browser_harness.authority.handoff.HandoffBroker.__init__",
            lambda self, store_dir=None: (
                setattr(self, "_store_dir", tmp_path),
                tmp_path.mkdir(parents=True, exist_ok=True),
            )[0],
        )

        _run_handoff(request.handoff_id)
        captured = capsys.readouterr()
        assert "cloudflare" in captured.out
        assert request.url in captured.out
        assert "Resume token signed" in captured.out

        # Request should be cleaned up
        assert broker.get(request.handoff_id) is None

    def test_handoff_cli_rejects_unknown_id(self, tmp_path, monkeypatch, capsys):
        """--handoff exits with error for unknown handoff_id."""
        monkeypatch.setattr(
            "browser_harness.authority.handoff.HandoffBroker.__init__",
            lambda self, store_dir=None: (
                setattr(self, "_store_dir", tmp_path),
                tmp_path.mkdir(parents=True, exist_ok=True),
            )[0],
        )
        from browser_harness.run import _run_handoff
        with pytest.raises(SystemExit, match="1"):
            _run_handoff("nonexistent123")


# --- 19. Handoff session capture (Step 6) ---

class TestHandoffSessionCapture:
    """Prove _run_handoff captures cookies + storage and binds the
    SecretRef to the signed ResumeToken."""

    def _patch_handoff_store(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "browser_harness.authority.handoff.HandoffBroker.__init__",
            lambda self, store_dir=None: (
                setattr(self, "_store_dir", tmp_path),
                tmp_path.mkdir(parents=True, exist_ok=True),
            )[0],
        )

    def test_capture_populates_session_ref_id(self, tmp_path, monkeypatch, capsys):
        from browser_harness import helpers
        from browser_harness.authority.handoff import HandoffBroker
        from browser_harness.run import _run_handoff
        from browser_harness.sessions.broker import SessionBroker

        # Real handoff request stored in tmp_path
        broker = HandoffBroker(store_dir=tmp_path)
        request = broker.create(
            url="https://example.com/protected",
            origin="https://example.com",
            challenge_kind="cloudflare",
        )

        # Daemon: new_tab succeeds
        monkeypatch.setattr(helpers, "new_tab", lambda url: 1)
        # CDP capture: synthetic cookie + storage
        synthetic_cookie = {
            "name": "sid",
            "value": "secret",
            "domain": "example.com",
            "path": "/",
        }
        monkeypatch.setattr(
            "browser_harness.sessions.login_adapter.browser_cookies",
            lambda client, urls, session_id=None: [synthetic_cookie],
        )
        monkeypatch.setattr(
            "browser_harness.sessions.login_adapter.storage_value_snapshot",
            lambda client, session_id=None: {
                "url": "https://example.com/",
                "origin": "https://example.com",
                "localStorage": {"k": "v"},
                "sessionStorage": {},
            },
        )
        monkeypatch.setattr("builtins.input", lambda: "")

        # Force HandoffBroker() inside _run_handoff to point at tmp_path
        self._patch_handoff_store(monkeypatch, tmp_path)

        # Inject a SessionBroker we can inspect after the run
        session_broker = SessionBroker()
        _run_handoff(request.handoff_id, session_broker=session_broker)

        out = capsys.readouterr().out
        assert "Captured session" in out
        assert "sid" in out
        assert "Session ref" in out

        # Broker holds a bundle for the origin, retrievable via the ref
        ref = session_broker.ref_for_origin("https://example.com")
        assert ref is not None
        bundle = session_broker.materialize_for_transport(
            ref, target_origin="https://example.com"
        )
        assert bundle is not None
        assert any(c["name"] == "sid" for c in bundle.cookies)

    def test_resume_token_signature_covers_session_ref_id(self, tmp_path):
        """ResumeToken.session_ref_id is bound by the HMAC."""
        from browser_harness.authority.handoff import HandoffBroker, ResumeToken

        broker = HandoffBroker(store_dir=tmp_path)
        req = broker.create("https://example.com/p", "https://example.com", "cloudflare")
        token = broker.complete(req.handoff_id, session_ref_id="ref_abc")

        assert token.session_ref_id == "ref_abc"

        # Tamper with session_ref_id, signature must fail to verify.
        tampered = ResumeToken(
            origin=token.origin,
            account_id=token.account_id,
            session_ref_id="ref_evil",
            completed_at=token.completed_at,
            expires_at=token.expires_at,
            nonce=token.nonce,
            signature=token.signature,
        )
        assert broker.consume(tampered.to_bytes()) is None


# --- 20. End-to-end handoff flow (Step 7) ---

class TestEndToEndHandoffFlow:
    """The single test that proves the authority claim end-to-end:
    blocked request → handoff_id → user completes via CLI → captured
    session lands in broker → retry succeeds via authenticated_http."""

    def test_blocked_request_through_cli_to_session_capture(
        self, tmp_path, monkeypatch, capsys
    ):
        from browser_harness import helpers
        from browser_harness.authority.handoff import HandoffBroker
        from browser_harness.authority.policy import PolicyEngine
        from browser_harness.authority.challenge import ChallengeStateMachine
        from browser_harness.capabilities.models import (
            ChallengeStatus,
            RiskLevel,
            WebRequest,
        )
        from browser_harness.capabilities.resolver import AccessPlane
        from browser_harness.scheduler.budgets import BudgetController
        from browser_harness.sessions.broker import SessionBroker
        from browser_harness.run import _run_handoff

        # Shared brokers (single-process verification per plan)
        handoff_broker = HandoffBroker(store_dir=tmp_path)
        session_broker = SessionBroker()

        # First run: public_http returns a Cloudflare challenge page → handoff_id
        block_page = "challenge"
        plane = AccessPlane(
            policy=PolicyEngine(),
            budget=BudgetController(BudgetConfig(request_interval_seconds=0.0)),
            broker=session_broker,
            challenge_sm=ChallengeStateMachine(),
            handoff_broker=handoff_broker,
            http_fn=lambda url, **kw: block_page,
            session_http_fn=lambda url, **kw: {
                "status": 200,
                "text": "after-login content",
                "headers": {},
            },
            block_detect_fn=lambda **kw: (
                {"blocked": True, "kind": "cloudflare", "evidence": []}
                if kw.get("html") == block_page
                else {}
            ),
        )

        req = WebRequest(
            url="https://example.com/protected",
            risk=RiskLevel.AUTHENTICATED_READ,
            auth_required=True,
        )
        first = plane.execute(req)
        assert first.block_state == ChallengeStatus.NEED_HANDOFF
        handoff_id = first.extra.get("handoff_id")
        assert handoff_id

        # Second: simulate the user running `browser-harness --handoff <id>`.
        # Patch HandoffBroker() inside _run_handoff to point at our tmp_path.
        monkeypatch.setattr(
            "browser_harness.authority.handoff.HandoffBroker.__init__",
            lambda self, store_dir=None: (
                setattr(self, "_store_dir", tmp_path),
                tmp_path.mkdir(parents=True, exist_ok=True),
            )[0],
        )
        monkeypatch.setattr(helpers, "new_tab", lambda url: 1)
        monkeypatch.setattr(
            "browser_harness.sessions.login_adapter.browser_cookies",
            lambda client, urls, session_id=None: [
                {"name": "sid", "value": "ok", "domain": "example.com", "path": "/"}
            ],
        )
        monkeypatch.setattr(
            "browser_harness.sessions.login_adapter.storage_value_snapshot",
            lambda client, session_id=None: {
                "url": "https://example.com/",
                "origin": "https://example.com",
                "localStorage": {},
                "sessionStorage": {},
            },
        )
        monkeypatch.setattr("builtins.input", lambda: "")

        _run_handoff(handoff_id, session_broker=session_broker)

        # Third: retry the original request.  AccessPlane now finds a
        # SessionBroker ref for the origin and routes through
        # authenticated_http, which returns 200.
        # New plane uses the same brokers; clear cache so the prior 403
        # doesn't shadow this attempt.
        plane._cache.clear()
        retry = plane.execute(req)
        assert retry.status == 200, (
            f"expected 200 via authenticated_http, got {retry.status} "
            f"(source={retry.source}, reason={retry.reason})"
        )
        assert retry.source == "session"
        assert retry.transport.value == "authenticated_http"


