"""AccessPlane proof tests — verify the pipeline governs authority."""
import pytest

from browser_harness.authority.challenge import ChallengeStateMachine
from browser_harness.authority.policy import PolicyEngine
from browser_harness.capabilities.models import (
    ChallengeStatus,
    LeaseSpec,
    RiskLevel,
    TransportType,
    WebRequest,
)
from browser_harness.capabilities.resolver import AccessPlane, AccessResult
from browser_harness.scheduler.budgets import BudgetController, BudgetConfig
from browser_harness.sessions.broker import SessionBroker


def _public_request(url="https://example.com/page"):
    return WebRequest(url=url, risk=RiskLevel.PUBLIC_READ)


class TestAccessPlanePolicyGate:
    def test_blocked_domain_denied(self):
        plane = AccessPlane(policy=PolicyEngine(blocked_domains={"https://evil.example"}))
        result = plane.execute(WebRequest(url="https://evil.example/page", risk=RiskLevel.PUBLIC_READ))
        assert result.status == 403
        assert result.block_state == ChallengeStatus.BLOCKED

    def test_allowed_domain_passes(self):
        plane = AccessPlane(
            policy=PolicyEngine(),
            http_fn=lambda url, **kw: "some content",
        )
        result = plane.execute(_public_request())
        assert result.status == 200

    def test_public_request_does_not_attach_account_cookies(self):
        """Least authority: public fetch must not use session state."""
        broker = SessionBroker()
        broker.store_secret_bundle(
            origin="https://example.com",
            cookies=[{"name": "session", "value": "secret"}],
        )
        calls = []

        def http_fn(url, **kw):
            calls.append({"url": url, "headers": kw.get("headers", {})})
            return "public content"

        plane = AccessPlane(
            broker=broker,
            http_fn=http_fn,
        )
        result = plane.execute(_public_request())
        assert result.status == 200
        assert result.source == "http"
        # No session HTTP call was made — only plain HTTP
        assert len(calls) == 1

    def test_authenticated_read_uses_session_when_available(self):
        """R1: authenticated read should use session HTTP if available."""
        broker = SessionBroker()
        broker.store_secret_bundle(
            origin="https://example.com",
            cookies=[{"name": "session", "value": "secret"}],
        )

        def session_http_fn(url, **kw):
            return {"text": "authenticated content", "status": 200, "ok": True}

        plane = AccessPlane(
            broker=broker,
            session_http_fn=session_http_fn,
        )
        req = WebRequest(url="https://example.com/api", risk=RiskLevel.AUTHENTICATED_READ, auth_required=True)
        result = plane.execute(req)
        assert result.status == 200
        assert result.source == "session"


class TestAccessPlaneBudgetGate:
    def test_circuit_breaker_stops_requests(self):
        plane = AccessPlane(
            budget=BudgetController(BudgetConfig(
                circuit_breaker_threshold=2,
                request_interval_seconds=0,
            )),
            http_fn=lambda url, **kw: "ok",
        )
        # Trigger circuit breaker
        plane.budget.record("https://example.com", status=403, block=True)
        plane.budget.record("https://example.com", status=403, block=True)
        result = plane.execute(_public_request())
        assert result.status == 429
        assert "circuit" in result.reason.lower()


class TestAccessPlaneChallenge:
    def test_blocked_content_returns_blocked_not_solver(self):
        """When content is blocked, return blocked status — do NOT invoke solver."""
        def http_fn(url, **kw):
            return "just a moment... cloudflare challenge page"

        def block_fn(html="", text="", url=""):
            return {"blocked": True, "kind": "cloudflare", "evidence": ["just a moment"]}

        plane = AccessPlane(
            http_fn=http_fn,
            block_detect_fn=block_fn,
            budget=BudgetController(BudgetConfig(request_interval_seconds=0)),
        )
        result = plane.execute(_public_request())
        # Cloudflare challenge returns need_handoff (human required), not solver invocation
        assert result.block_state == ChallengeStatus.NEED_HANDOFF
        assert result.status == 403
        assert "solve_turnstile" not in repr(result)  # no solver invocation

    def test_production_fetch_does_not_reference_solve_turnstile(self):
        """Static proof: the AccessPlane module has no reference to solve_turnstile."""
        import inspect
        from browser_harness.capabilities import resolver
        source = inspect.getsource(resolver)
        assert "solve_turnstile" not in source
        assert "navigate_via_google" not in source


class TestAccessPlaneCache:
    def test_cache_hit_on_second_public_request(self):
        call_count = [0]

        def http_fn(url, **kw):
            call_count[0] += 1
            return f"content-{call_count[0]}"

        plane = AccessPlane(
            http_fn=http_fn,
            budget=BudgetController(BudgetConfig(request_interval_seconds=0)),
        )
        r1 = plane.execute(_public_request())
        r2 = plane.execute(_public_request())
        assert r1.text == "content-1"
        assert r2.text == "content-1"  # cached
        assert call_count[0] == 1  # only one actual fetch


class TestAccessPlaneTransportFallback:
    def test_falls_back_from_http_to_session(self):
        """When HTTP fails for an authenticated read, try session HTTP."""
        broker = SessionBroker()
        broker.store_secret_bundle(
            origin="https://example.com",
            cookies=[{"name": "s", "value": "v"}],
        )

        def http_fn(url, **kw):
            raise ConnectionError("HTTP failed")

        def session_http_fn(url, **kw):
            return {"text": "session content", "status": 200, "ok": True}

        plane = AccessPlane(
            broker=broker,
            http_fn=http_fn,
            session_http_fn=session_http_fn,
            budget=BudgetController(BudgetConfig(request_interval_seconds=0)),
        )
        req = WebRequest(url="https://example.com/api", risk=RiskLevel.AUTHENTICATED_READ, auth_required=True)
        result = plane.execute(req)
        assert result.status == 200
        assert result.source == "session"

    def test_all_transports_fail_returns_502(self):
        plane = AccessPlane()  # no transport fns at all
        result = plane.execute(_public_request())
        assert result.status == 502
        assert result.block_state == ChallengeStatus.UNOBSERVABLE
