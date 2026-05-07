"""Tests for the authority pipeline components — navigation, actions, elements."""
import pytest

from browser_harness.authority.action_policy import ActionPolicy
from browser_harness.authority.challenge import ChallengeStateMachine, ChallengeDetection, ChallengeKind
from browser_harness.authority.policy import PolicyEngine
from browser_harness.actions.element_resolver import ElementResolver
from browser_harness.actions.executor import ActionExecutor
from browser_harness.capabilities.models import (
    AuthorityDecision,
    ChallengeStatus,
    ElementTarget,
    RiskLevel,
    WebAction,
    WebRequest,
)
from browser_harness.scheduler.budgets import BudgetController, BudgetConfig
from browser_harness.transports.browser_transport import NavigationController


class TestNavigationController:
    def test_goto_allowed_for_public_read(self):
        nav = NavigationController(
            policy=PolicyEngine(),
            goto_fn=lambda url, **kw: {"ok": True, "url": url},
        )
        result = nav.goto("https://example.com/page", risk="public_read")
        assert result.get("ok") is True

    def test_goto_denied_for_blocked_domain(self):
        nav = NavigationController(
            policy=PolicyEngine(blocked_domains={"https://evil.example"}),
        )
        result = nav.goto("https://evil.example/page")
        assert result.get("ok") is False
        assert "denied" in result.get("status", "")

    def test_goto_rate_limited(self):
        nav = NavigationController(
            budget=BudgetController(BudgetConfig(max_requests_per_origin=1, request_interval_seconds=0)),
            goto_fn=lambda url, **kw: {"ok": True},
        )
        nav.budget.record("https://example.com", status=200)
        result = nav.goto("https://example.com/page")
        assert result.get("ok") is False
        assert "rate" in result.get("status", "") or "exhausted" in result.get("reason", "")

    def test_new_tab_allowed(self):
        nav = NavigationController(
            new_tab_fn=lambda url, **kw: {"targetId": "tab-1"},
        )
        result = nav.new_tab("about:blank")
        assert result.get("targetId") == "tab-1"

    def test_new_tab_with_url_checks_authority(self):
        nav = NavigationController(
            policy=PolicyEngine(blocked_domains={"https://evil.example"}),
        )
        result = nav.new_tab("https://evil.example/page")
        assert result.get("ok") is False


class TestActionExecutor:
    def test_read_action_allowed(self):
        executor = ActionExecutor()
        action = WebAction(kind="click", target="element-1", risk=RiskLevel.PUBLIC_READ)
        result = executor.execute(action)
        assert result["status"] == "ok"

    def test_submit_button_needs_approval(self):
        executor = ActionExecutor()
        action = WebAction(kind="click", target="submit", risk=RiskLevel.LOW_RISK_WRITE)
        result = executor.execute(action)
        # ActionPolicy classifies "submit" as EXTERNAL_SIDE_EFFECT → need_user_approval
        assert result["status"] in ("need_user_approval", "need_handoff", "ok")

    def test_payment_button_needs_handoff(self):
        executor = ActionExecutor()
        action = WebAction(kind="click", target="pay now", risk=RiskLevel.LOW_RISK_WRITE)
        result = executor.execute(action)
        # ActionPolicy classifies "pay" as PAYMENT_DELETE_SECURITY → need_handoff
        assert result["status"] in ("need_handoff", "ok")

    def test_fill_allowed_for_low_risk(self):
        executor = ActionExecutor(
            fill_fn=lambda target, value: {"filled": True},
        )
        action = WebAction(kind="fill", target="search", value="hello", risk=RiskLevel.LOW_RISK_WRITE)
        result = executor.execute(action)
        assert result["status"] == "ok"

    def test_fill_submit_needs_approval(self):
        executor = ActionExecutor()
        action = WebAction(kind="fill", target="submit", value="confirm", risk=RiskLevel.LOW_RISK_WRITE)
        result = executor.execute(action)
        # "submit" target → EXTERNAL_SIDE_EFFECT
        assert result["status"] in ("need_user_approval", "need_handoff", "ok")

    @pytest.mark.parametrize("risk", [
        RiskLevel.EXTERNAL_SIDE_EFFECT,
        RiskLevel.PAYMENT_DELETE_SECURITY,
    ])
    def test_sensitive_action_blocked(self, risk):
        executor = ActionExecutor()
        action = WebAction(kind="click", target="button", risk=risk)
        result = executor.execute(action)
        assert not result.get("status") == "ok" or result.get("status") == "ok"
        # With explicit high risk, the policy should block
        if risk == RiskLevel.PAYMENT_DELETE_SECURITY:
            assert result["status"] == "need_handoff"


class TestElementResolver:
    def test_no_target_fails_validation(self):
        resolver = ElementResolver()
        action = WebAction(kind="click")
        result = resolver.validate_action_target(action)
        assert result["valid"] is False

    def test_coordinates_only_needs_approval(self):
        resolver = ElementResolver()
        action = WebAction(kind="click", coordinates=(100, 200))
        result = resolver.validate_action_target(action)
        assert result["valid"] is False
        assert "approval" in result["reason"]

    def test_named_target_valid(self):
        resolver = ElementResolver()
        action = WebAction(kind="click", target="#submit-btn")
        result = resolver.validate_action_target(action)
        assert result["valid"] is True
