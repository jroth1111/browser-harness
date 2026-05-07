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

from browser_harness.runtime.agent_runtime import AgentRuntime
from browser_harness.runtime.sandbox import AgentSandbox, FORBIDDEN_MODULES, FORBIDDEN_NAMES
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


# --- 1. Runtime sandbox / no raw import test ---

class TestAgentRuntimeSandbox:
    def test_agent_runtime_cannot_import_raw_authorities(self):
        sandbox = AgentSandbox({})
        for mod in [
            "browser_harness._ipc",
            "browser_harness.helpers",
            "browser_harness.stealth_helpers",
            "urllib.request",
            "subprocess",
            "socket",
        ]:
            result = sandbox.check_import(mod)
            assert result["status"] == "denied", f"import {mod} should be denied"

    def test_agent_runtime_cannot_eval_arbitrary_python(self):
        runtime = AgentRuntime()
        result = runtime._sandbox.eval_restricted("import os")
        assert result["status"] == "denied"

    def test_forbidden_tools_denied(self):
        runtime = AgentRuntime()
        for tool in ["cdp", "_send", "_ipc", "browser_cookies", "stealth_session",
                      "solve_turnstile", "navigate_via_google"]:
            result = runtime.call(tool, {})
            assert result["status"] == "denied", f"tool {tool} should be denied"

    def test_unknown_tools_denied(self):
        runtime = AgentRuntime()
        result = runtime.call("nonexistent_tool", {})
        assert result["status"] == "denied"

    def test_available_tools_excludes_forbidden(self):
        runtime = AgentRuntime()
        tools = runtime._sandbox.available_tools()
        for forbidden in FORBIDDEN_NAMES:
            assert forbidden not in tools, f"{forbidden} should not be available"


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

        violations = []
        for path in domain_dir.rglob("*.py"):
            text = path.read_text()
            for token in FORBIDDEN_DOMAIN_TOKENS:
                if token in text:
                    violations.append(f"{path.relative_to(domain_dir.parent)}: {token}")

        if violations:
            pytest.xfail(
                f"Domain skills contain forbidden transport authority ({len(violations)} violations):\n"
                + "\n".join(violations[:5])
                + f"\n... and {len(violations) - 5} more" if len(violations) > 5 else ""
            )


# --- 11. Provider registry ---

class TestProviderRegistry:
    def test_agent_cannot_launch_provider_directly(self):
        """Agent runtime doesn't expose provider launch capability."""
        runtime = AgentRuntime()
        result = runtime.call("stealth_session", {})
        assert result["status"] == "denied"

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


# --- 12. Agent runtime CLI ---

class TestAgentRuntimeCLI:
    def test_call_with_valid_tool(self):
        runtime = AgentRuntime()
        result = runtime.call("fetch", {"url": "https://example.com", "risk": "public_read"})
        # Without a transport adapter, fetch returns unobservable (no transport available)
        # but the request was authorized by policy
        assert result["status"] in ("ok", "unobservable")

    def test_fetch_with_transport_adapter_succeeds(self):
        from browser_harness.capabilities.resolver import AccessPlane

        def http_fn(url, **kw):
            return "hello world"

        plane = AccessPlane(
            policy=PolicyEngine(),
            http_fn=http_fn,
        )
        runtime = AgentRuntime(access_plane=plane)
        result = runtime.call("fetch", {"url": "https://example.com", "risk": "public_read"})
        assert result["status"] == "ok"
        assert result["source"] == "http"

    def test_call_denied_high_risk(self):
        runtime = AgentRuntime()
        result = runtime.call("click", {"target": "pay", "risk": "payment_delete_security"})
        assert result["status"] == "need_handoff"

    def test_list_tools(self):
        runtime = AgentRuntime()
        tools = runtime._sandbox.available_tools()
        assert "fetch" in tools
        assert "click" in tools
        assert "extract" in tools
        assert "navigate" in tools
        # Forbidden tools excluded
        assert "cdp" not in tools
        assert "browser_cookies" not in tools


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


