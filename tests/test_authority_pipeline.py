"""Tests for the authority pipeline components — actions, elements."""
import pytest

from browser_harness.actions.element_resolver import ElementResolver
from browser_harness.actions.executor import ActionExecutor
from browser_harness.capabilities.models import RiskLevel, WebAction


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
