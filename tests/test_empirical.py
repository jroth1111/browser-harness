"""Empirical integration tests — authority pipeline, domain skills, and live HTTP.

These tests make real network requests and load real skill manifests.
Marked with pytest.mark.network so they can be skipped in offline CI:
    pytest -m "not network"    # skip live tests
    pytest -m network           # run only live tests
"""
import json
import time
from pathlib import Path

import pytest

from browser_harness.authority.action_policy import ActionPolicy
from browser_harness.authority.challenge import ChallengeStateMachine
from browser_harness.authority.handoff import HandoffBroker
from browser_harness.authority.policy import PolicyEngine
from browser_harness.capabilities.models import (
    AuthorityDecision,
    ChallengeStatus,
    RiskLevel,
    RouteRule,
    TransportType,
    WebAction,
    WebRequest,
)
from browser_harness.capabilities.resolver import AccessPlane, AccessResult
from browser_harness.projections.skill_router import SkillRouter
from browser_harness.scheduler.budgets import BudgetController, BudgetConfig
from browser_harness.sessions.broker import SessionBroker
from browser_harness.transports.bh_http import (
    _block_detect,
    _default_plane,
    _risk,
    execute,
    get,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
DOMAIN_SKILLS_DIR = REPO_ROOT / "domain-skills"

network = pytest.mark.network


def _skill_manifests():
    """Collect (name, path) for every domain skill that has a manifest."""
    if not DOMAIN_SKILLS_DIR.exists():
        return []
    out = []
    for child in sorted(DOMAIN_SKILLS_DIR.iterdir()):
        if not child.is_dir():
            continue
        for fname in ("manifest.json", "skill.json"):
            p = child / fname
            if p.exists():
                out.append((child.name, p))
                break
    return out


# ===========================================================================
# 1. Authority pipeline — live HTTP
# ===========================================================================

class TestAuthorityPipelineLive:
    """Fire real HTTP requests through bh_http and verify every gate."""

    @network
    def test_get_example_com_returns_200(self):
        r = get("https://example.com")
        assert r.status == 200
        assert len(r.text) > 0
        assert r.source == "authority"

    @network
    def test_get_includes_html_and_text(self):
        r = get("https://example.com")
        assert "<html" in r.html.lower() or "<!doctype" in r.html.lower()
        assert "example" in r.text.lower()

    @network
    def test_block_detection_on_normal_page(self):
        """Block detection should return empty for a normal page."""
        r = get("https://example.com")
        block = _block_detect(html=r.html, text=r.text, url="https://example.com")
        assert isinstance(block, dict)
        assert not block.get("blocked", False)

    @network
    def test_risk_validation_raises_on_invalid(self):
        """_risk() must raise ValueError, not silently downgrade."""
        with pytest.raises(ValueError):
            _risk("bogus_risk_level")
        with pytest.raises(ValueError):
            _risk("")

    @network
    def test_blocked_domain_returns_403(self):
        """PolicyEngine blocks requests to blocked domains."""
        plane = AccessPlane(
            policy=PolicyEngine(blocked_domains={"https://example.com"}),
        )
        result = plane.execute(WebRequest(url="https://example.com", risk=RiskLevel.PUBLIC_READ))
        assert result.status == 403
        assert result.block_state == ChallengeStatus.BLOCKED

    @network
    def test_allowlist_denies_unlisted_domain(self):
        """PolicyEngine with allowlist rejects domains not on the list."""
        plane = AccessPlane(
            policy=PolicyEngine(allowed_domains={"https://httpbin.org"}),
        )
        result = plane.execute(WebRequest(url="https://example.com", risk=RiskLevel.PUBLIC_READ))
        assert result.status == 403

    @network
    def test_budget_exhaustion_stops_live_requests(self):
        """Budget gate stops requests after per-origin limit hit."""
        plane = AccessPlane(
            budget=BudgetController(BudgetConfig(
                max_requests_per_origin=1,
                request_interval_seconds=0,
            )),
            http_fn=lambda url, **kw: "content",
        )
        # First request succeeds
        r1 = plane.execute(WebRequest(url="https://example.com/a", risk=RiskLevel.PUBLIC_READ))
        assert r1.status == 200
        # Second request blocked by budget
        r2 = plane.execute(WebRequest(url="https://example.com/b", risk=RiskLevel.PUBLIC_READ))
        assert r2.status == 429

    @network
    def test_circuit_breaker_on_repeated_blocks(self):
        """Circuit breaker opens after repeated failures."""
        ctrl = BudgetController(BudgetConfig(
            circuit_breaker_threshold=2,
            request_interval_seconds=0,
        ))
        plane = AccessPlane(
            budget=ctrl,
            http_fn=lambda url, **kw: "cloudflare challenge page",
            block_detect_fn=lambda **kw: {"blocked": True, "kind": "cloudflare", "evidence": []},
        )
        req = WebRequest(url="https://example.com", risk=RiskLevel.PUBLIC_READ)
        r1 = plane.execute(req)
        assert r1.status == 403
        r2 = plane.execute(req)
        assert r2.status == 403
        r3 = plane.execute(req)
        assert r3.status == 429
        assert "circuit" in r3.reason.lower()

    @network
    def test_cache_serves_same_result_twice(self):
        """Cache hit on second identical PUBLIC_READ request."""
        calls = [0]
        def counting_http(url, **kw):
            calls[0] += 1
            return f"response-{calls[0]}"

        plane = AccessPlane(
            http_fn=counting_http,
            budget=BudgetController(BudgetConfig(request_interval_seconds=0)),
        )
        r1 = plane.execute(WebRequest(url="https://example.com/x", risk=RiskLevel.PUBLIC_READ))
        r2 = plane.execute(WebRequest(url="https://example.com/x", risk=RiskLevel.PUBLIC_READ))
        assert r1.text == r2.text
        assert calls[0] == 1

    @network
    def test_auth_required_skips_public_http(self):
        """auth_required=True must not use PUBLIC_HTTP transport."""
        public_calls = []
        def http_fn(url, **kw):
            public_calls.append(url)
            return "public"

        plane = AccessPlane(
            http_fn=http_fn,
            budget=BudgetController(BudgetConfig(request_interval_seconds=0)),
        )
        result = plane.execute(WebRequest(
            url="https://example.com/api",
            risk=RiskLevel.AUTHENTICATED_READ,
            auth_required=True,
        ))
        assert len(public_calls) == 0, "auth_required=True must skip PUBLIC_HTTP"
        assert result.status == 502  # no authenticated transport available

    @network
    def test_challenge_detection_cloudflare(self):
        """Cloudflare challenge page triggers NEED_HANDOFF."""
        plane = AccessPlane(
            http_fn=lambda url, **kw: "just a moment... cloudflare challenge",
            block_detect_fn=lambda **kw: {"blocked": True, "kind": "cloudflare", "evidence": ["just a moment"]},
            budget=BudgetController(BudgetConfig(request_interval_seconds=0)),
        )
        result = plane.execute(WebRequest(url="https://example.com", risk=RiskLevel.PUBLIC_READ))
        assert result.block_state == ChallengeStatus.NEED_HANDOFF
        assert result.status == 403

    @network
    def test_handoff_id_emitted_on_block(self, tmp_path):
        """Blocked request with HandoffBroker produces handoff_id."""
        broker = HandoffBroker(store_dir=tmp_path)
        plane = AccessPlane(
            http_fn=lambda url, **kw: "cloudflare turnstile challenge",
            block_detect_fn=lambda **kw: {"blocked": True, "kind": "cloudflare", "evidence": []},
            budget=BudgetController(BudgetConfig(request_interval_seconds=0)),
            handoff_broker=broker,
        )
        result = plane.execute(WebRequest(url="https://example.com", risk=RiskLevel.PUBLIC_READ))
        assert "handoff_id" in result.extra
        assert result.extra["handoff_id"]


# ===========================================================================
# 2. Domain skills — SkillRouter with real manifests
# ===========================================================================

class TestDomainSkillsEmpirical:
    """Load real domain skill manifests and verify routing."""

    @pytest.mark.parametrize("skill_name,manifest_path", _skill_manifests(),
                             ids=[name for name, _ in _skill_manifests()])
    def test_skill_manifest_loads(self, skill_name, manifest_path):
        router = SkillRouter()
        manifest = router.load_manifest(skill_name, manifest_path)
        assert manifest is not None, f"Failed to load {manifest_path}"
        assert manifest.name == skill_name
        assert manifest.version
        assert isinstance(manifest.route_rules, list)
        assert isinstance(manifest.surfaces, list)

    @pytest.mark.parametrize("skill_name,manifest_path", _skill_manifests(),
                             ids=[name for name, _ in _skill_manifests()])
    def test_skill_route_rules_have_valid_risk(self, skill_name, manifest_path):
        """Every route rule must have a valid RiskLevel."""
        router = SkillRouter()
        manifest = router.load_manifest(skill_name, manifest_path)
        assert manifest is not None
        for rule in manifest.route_rules:
            assert isinstance(rule.risk_max, RiskLevel), (
                f"{skill_name}: invalid risk_max in route rule for {rule.origin}"
            )

    @pytest.mark.parametrize("skill_name,manifest_path", _skill_manifests(),
                             ids=[name for name, _ in _skill_manifests()])
    def test_skill_route_rules_have_valid_transport(self, skill_name, manifest_path):
        """Every route rule must have a valid TransportType."""
        router = SkillRouter()
        manifest = router.load_manifest(skill_name, manifest_path)
        assert manifest is not None
        for rule in manifest.route_rules:
            assert isinstance(rule.transport_preference, TransportType), (
                f"{skill_name}: invalid transport in route rule for {rule.origin}"
            )

    @pytest.mark.parametrize("skill_name,manifest_path", _skill_manifests(),
                             ids=[name for name, _ in _skill_manifests()])
    def test_skill_forbidden_patterns_exist(self, skill_name, manifest_path):
        """Every skill should have forbidden patterns (security surface)."""
        router = SkillRouter()
        manifest = router.load_manifest(skill_name, manifest_path)
        assert manifest is not None
        assert len(manifest.forbidden_patterns) > 0, (
            f"{skill_name}: no forbidden_patterns defined"
        )

    def test_airbnb_routes_correctly(self):
        """Airbnb manifest routes public pages vs authenticated pages."""
        router = SkillRouter(skill_dir=DOMAIN_SKILLS_DIR)
        manifest = router.load_manifest("airbnb")
        assert manifest is not None

        matches = router.route_for_url("https://www.airbnb.com.au/rooms/12345")
        assert len(matches) == 1
        assert matches[0].name == "airbnb"

    def test_airbnb_risk_policies(self):
        """Airbnb risk policies assign correct levels."""
        router = SkillRouter(skill_dir=DOMAIN_SKILLS_DIR)
        manifest = router.load_manifest("airbnb")
        assert manifest is not None

        assert router.risk_for_action("airbnb", "public_comp_search") == "public_read"
        assert router.risk_for_action("airbnb", "host_listing_inventory") == "authenticated_read"
        assert router.risk_for_action("airbnb", "nonexistent_action") == "low_risk_write"


# ===========================================================================
# 3. Action policy — live classification
# ===========================================================================

class TestActionPolicyEmpirical:
    """Verify action classification with realistic action descriptions."""

    def test_click_pay_now_classified_as_payment(self):
        policy = ActionPolicy()
        action = WebAction(kind="click", target="Pay Now", risk=RiskLevel.LOW_RISK_WRITE)
        assert policy.classify(action) == RiskLevel.PAYMENT_DELETE_SECURITY

    def test_click_pay_now_escalates_from_public_read(self):
        """Even if caller says PUBLIC_READ, keyword escalation catches it."""
        policy = ActionPolicy()
        action = WebAction(kind="click", target="Pay Now", risk=RiskLevel.PUBLIC_READ)
        assert policy.classify(action) == RiskLevel.PAYMENT_DELETE_SECURITY

    def test_click_submit_classified_as_side_effect(self):
        policy = ActionPolicy()
        action = WebAction(kind="click", target="Submit Order", risk=RiskLevel.LOW_RISK_WRITE)
        assert policy.classify(action) == RiskLevel.EXTERNAL_SIDE_EFFECT

    def test_screenshot_classified_as_read_only(self):
        policy = ActionPolicy()
        action = WebAction(kind="screenshot", risk=RiskLevel.LOW_RISK_WRITE)
        assert policy.classify(action) == RiskLevel.PUBLIC_READ

    def test_fill_password_field_allows_low_risk(self):
        policy = ActionPolicy()
        action = WebAction(kind="fill", target="password", value="secret123", risk=RiskLevel.LOW_RISK_WRITE)
        risk = policy.classify(action)
        # "password" is not in HIGH_RISK_HINTS (change_password is, not password alone)
        # and "fill" is not in EXTERNAL_SIDE_EFFECT_HINTS
        assert risk == RiskLevel.LOW_RISK_WRITE

    def test_click_change_password_is_high_risk(self):
        """'change_password' hint matches natural space-separated target."""
        policy = ActionPolicy()
        action = WebAction(kind="click", target="Change Password", risk=RiskLevel.LOW_RISK_WRITE)
        assert policy.classify(action) == RiskLevel.PAYMENT_DELETE_SECURITY

    def test_click_remove_account_is_high_risk(self):
        """'remove_account' hint matches natural space-separated target."""
        policy = ActionPolicy()
        action = WebAction(kind="click", target="Remove Account", risk=RiskLevel.LOW_RISK_WRITE)
        assert policy.classify(action) == RiskLevel.PAYMENT_DELETE_SECURITY

    def test_click_change_email_is_high_risk(self):
        """'change_email' hint matches natural space-separated target."""
        policy = ActionPolicy()
        action = WebAction(kind="click", target="Change Email", risk=RiskLevel.LOW_RISK_WRITE)
        assert policy.classify(action) == RiskLevel.PAYMENT_DELETE_SECURITY

    def test_click_place_order_is_side_effect(self):
        """'place_order' hint matches natural space-separated target."""
        policy = ActionPolicy()
        action = WebAction(kind="click", target="Place Order", risk=RiskLevel.LOW_RISK_WRITE)
        assert policy.classify(action) == RiskLevel.EXTERNAL_SIDE_EFFECT

    def test_display_settings_not_escalated_by_pay_hint(self):
        """'pay' must not match as a substring of 'display'. Word boundary
        matching prevents false-positive escalation to PAYMENT_DELETE_SECURITY
        for harmless UI interactions like 'Display Settings'."""
        policy = ActionPolicy()
        action = WebAction(kind="click", target="Display Settings", risk=RiskLevel.LOW_RISK_WRITE)
        assert policy.classify(action) == RiskLevel.LOW_RISK_WRITE

    def test_buy_textbook_not_escalated_by_book_hint(self):
        """'book' must not match as a substring of 'textbook'. Word boundary
        matching prevents false-positive escalation."""
        policy = ActionPolicy()
        action = WebAction(kind="click", target="Buy Textbook", risk=RiskLevel.LOW_RISK_WRITE)
        assert policy.classify(action) != RiskLevel.EXTERNAL_SIDE_EFFECT

    def test_message_sender_not_escalated_by_send_hint(self):
        """'send' must not match as a substring of 'sender'. Word boundary
        matching prevents false-positive escalation."""
        policy = ActionPolicy()
        action = WebAction(kind="click", target="Message Sender", risk=RiskLevel.LOW_RISK_WRITE)
        assert policy.classify(action) != RiskLevel.EXTERNAL_SIDE_EFFECT

    def test_full_authorize_pipeline_payment(self):
        """Full pipeline: classify + authorize for payment action."""
        policy = ActionPolicy()
        action = WebAction(kind="click", target="Confirm Payment", risk=RiskLevel.PUBLIC_READ)
        decision = policy.authorize(action)
        assert not decision.allowed
        assert decision.status == "need_handoff"

    def test_full_authorize_pipeline_submit(self):
        """Full pipeline: classify + authorize for submit action."""
        policy = ActionPolicy()
        action = WebAction(kind="click", target="Submit Form", risk=RiskLevel.PUBLIC_READ)
        decision = policy.authorize(action)
        assert not decision.allowed
        assert decision.status == "need_user_approval"


# ===========================================================================
# 4. HandoffBroker — disk operations
# ===========================================================================

class TestHandoffBrokerEmpirical:
    """Verify handoff lifecycle with real filesystem operations."""

    def test_full_handoff_lifecycle(self, tmp_path):
        """Create → get → complete → consume — full lifecycle."""
        broker = HandoffBroker(store_dir=tmp_path)
        request = broker.create(
            url="https://example.com/login",
            origin="https://example.com",
            challenge_kind="cloudflare",
        )
        assert request.handoff_id
        assert (tmp_path / f"{request.handoff_id}.json").exists()

        retrieved = broker.get(request.handoff_id)
        assert retrieved is not None
        assert retrieved.url == "https://example.com/login"

        token = broker.complete(request.handoff_id, account_id="user@example.com")
        assert token is not None
        assert token.signature
        assert len(token.signature) == 32

        consumed = broker.consume(token.to_bytes())
        assert consumed is not None
        assert consumed.origin == "https://example.com"

    def test_path_traversal_blocked(self, tmp_path):
        """Path traversal in handoff_id is rejected."""
        broker = HandoffBroker(store_dir=tmp_path)
        assert broker.get("../../etc/passwd") is None
        assert broker.get("abc/def") is None
        assert broker.get("id with spaces") is None
        assert broker.complete("../../target") is None


# ===========================================================================
# 5. Budget controller — real timing
# ===========================================================================

class TestBudgetEmpirical:
    """Verify budget controller with real time intervals."""

    def test_rate_limit_enforces_interval(self):
        ctrl = BudgetController(BudgetConfig(
            request_interval_seconds=0.3,
            max_requests_per_origin=100,
        ))
        origin = "https://example.com"
        ok, _ = ctrl.ok(origin)
        assert ok
        ctrl.record(origin, status=200)

        ok, reason = ctrl.ok(origin)
        assert not ok
        assert "rate" in reason.lower()

        # Wait for interval to pass
        time.sleep(0.4)
        ok, _ = ctrl.ok(origin)
        assert ok

    def test_total_budget_global_limit(self):
        ctrl = BudgetController(BudgetConfig(
            max_total_requests=2,
            request_interval_seconds=0,
        ))
        ctrl.record("https://a.com", status=200)
        ctrl.record("https://b.com", status=200)
        ok, reason = ctrl.ok("https://c.com")
        assert not ok
        assert "total" in reason.lower()


# ===========================================================================
# 6. Session broker — secret management
# ===========================================================================

class TestSessionBrokerEmpirical:
    """Verify session broker with realistic secret storage."""

    def test_store_and_materialize_round_trip(self):
        broker = SessionBroker()
        ref = broker.store_secret_bundle(
            origin="https://example.com",
            cookies=[{"name": "session", "value": "abc123", "domain": ".example.com"}],
            local_storage={"token": "xyz"},
        )
        assert ref.origin == "https://example.com"

        bundle = broker.materialize_for_transport(ref, target_origin="https://example.com")
        assert bundle is not None
        assert len(bundle.cookies) == 1
        assert bundle.cookies[0]["value"] == "abc123"
        assert bundle.local_storage["token"] == "xyz"

    def test_cross_origin_materialization_blocked(self):
        broker = SessionBroker()
        ref = broker.store_secret_bundle(
            origin="https://example.com",
            cookies=[{"name": "s", "value": "v"}],
        )
        # Wrong origin — must be blocked
        bundle = broker.materialize_for_transport(ref, target_origin="https://evil.com")
        assert bundle is None

    def test_manifest_redacts_values(self):
        broker = SessionBroker()
        ref = broker.store_secret_bundle(
            origin="https://example.com",
            cookies=[{"name": "secret_cookie", "value": "super_secret_123"}],
            local_storage={"api_key": "hidden_key"},
        )
        manifest = broker.redacted_manifest(ref)
        assert manifest is not None
        assert "secret_cookie" in manifest.cookie_names
        assert manifest.has_local_storage
        # Manifest should NOT contain raw values
        manifest_text = json.dumps(manifest.__dict__)
        assert "super_secret_123" not in manifest_text
        assert "hidden_key" not in manifest_text
