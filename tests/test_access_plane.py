"""AccessPlane proof tests — verify the pipeline governs authority."""
import time

import pytest

from browser_harness.authority.challenge import ChallengeKind, ChallengeStateMachine
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

    def test_auth_required_skips_public_http(self):
        """auth_required=True must not use PUBLIC_HTTP, even when available.

        Before the fix, auth_required was ignored by AccessPlane — it tried
        PUBLIC_HTTP first regardless, only falling back to authenticated
        transports if public HTTP failed or a session happened to exist.
        """
        public_calls = []
        session_calls = []

        def http_fn(url, **kw):
            public_calls.append(url)
            return "public content"

        def session_http_fn(url, **kw):
            session_calls.append(url)
            return {"text": "authenticated content", "status": 200, "ok": True}

        broker = SessionBroker()
        broker.store_secret_bundle(
            origin="https://example.com",
            cookies=[{"name": "sid", "value": "test", "domain": "example.com", "path": "/"}],
        )
        plane = AccessPlane(
            broker=broker,
            http_fn=http_fn,
            session_http_fn=session_http_fn,
        )
        req = WebRequest(url="https://example.com/api", risk=RiskLevel.AUTHENTICATED_READ, auth_required=True)
        result = plane.execute(req)
        assert result.status == 200
        assert result.source == "session"
        assert public_calls == [], "auth_required=True must skip PUBLIC_HTTP entirely"


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

    def test_cache_does_not_serve_public_read_for_authenticated_read(self):
        """Cache bypass closure: PUBLIC_READ cache hit must not be served
        for AUTHENTICATED_READ requests at the same URL.

        Before the fix, the cache key was method:url without risk level.
        A PUBLIC_READ result cached at GET:https://example.com/api would
        be served to an AUTHENTICATED_READ request for the same URL,
        bypassing the transport selection enforcement.
        """
        session_calls = []

        def http_fn(url, **kw):
            return "public content"

        def session_http_fn(url, **kw):
            session_calls.append(url)
            return {"text": "authenticated content", "status": 200, "ok": True}

        broker = SessionBroker()
        broker.store_secret_bundle(
            origin="https://example.com",
            cookies=[{"name": "s", "value": "v"}],
        )
        plane = AccessPlane(
            broker=broker,
            http_fn=http_fn,
            session_http_fn=session_http_fn,
            budget=BudgetController(BudgetConfig(request_interval_seconds=0)),
        )

        # First: PUBLIC_READ → cached
        r1 = plane.execute(WebRequest(url="https://example.com/api", risk=RiskLevel.PUBLIC_READ))
        assert r1.status == 200
        assert r1.source == "http"
        assert session_calls == []

        # Second: AUTHENTICATED_READ at same URL → must NOT use cache
        r2 = plane.execute(WebRequest(url="https://example.com/api", risk=RiskLevel.AUTHENTICATED_READ))
        assert r2.status == 200
        assert r2.source == "session", "must use authenticated transport, not cached PUBLIC_READ"
        assert session_calls == ["https://example.com/api"]

    def test_cache_does_not_serve_public_read_when_auth_required(self):
        """auth_required=True must bypass cache even with PUBLIC_READ risk."""
        session_calls = []

        def http_fn(url, **kw):
            return "public content"

        def session_http_fn(url, **kw):
            session_calls.append(url)
            return {"text": "authenticated content", "status": 200, "ok": True}

        broker = SessionBroker()
        broker.store_secret_bundle(
            origin="https://example.com",
            cookies=[{"name": "s", "value": "v"}],
        )
        plane = AccessPlane(
            broker=broker,
            http_fn=http_fn,
            session_http_fn=session_http_fn,
            budget=BudgetController(BudgetConfig(request_interval_seconds=0)),
        )

        # Cache a PUBLIC_READ response
        plane.execute(WebRequest(url="https://example.com/api", risk=RiskLevel.PUBLIC_READ))

        # Request same URL with auth_required=True → must bypass cache
        r = plane.execute(WebRequest(url="https://example.com/api", risk=RiskLevel.PUBLIC_READ, auth_required=True))
        assert r.source == "session", "auth_required=True must bypass PUBLIC_READ cache"


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

    def test_expired_bundle_does_not_block_session_http(self):
        """Session HTTP uses daemon live cookies, not stored credentials.
        An expired bundle must not prevent the transport from trying."""
        broker = SessionBroker()
        broker.store_secret_bundle(
            origin="https://example.com",
            cookies=[{"name": "s", "value": "v"}],
            expires_at=time.time() - 100,  # expired 100s ago
        )

        def session_http_fn(url, **kw):
            return {"text": "daemon session content", "status": 200}

        plane = AccessPlane(
            broker=broker,
            session_http_fn=session_http_fn,
            budget=BudgetController(BudgetConfig(request_interval_seconds=0)),
        )
        req = WebRequest(url="https://example.com/api", risk=RiskLevel.AUTHENTICATED_READ, auth_required=True)
        result = plane.execute(req)
        assert result.status == 200
        assert result.source == "session"


class TestSessionHttpStatusNone:
    """When session HTTP returns status=None (network error), AccessResult
    must use a valid integer status, not None."""

    def test_session_none_status_uses_200_on_success(self):
        broker = SessionBroker()
        broker.store_secret_bundle(
            origin="https://example.com",
            cookies=[{"name": "s", "value": "v"}],
        )

        def session_http_fn(url, **kw):
            return {"ok": True, "status": None, "text": "content"}

        plane = AccessPlane(
            broker=broker,
            session_http_fn=session_http_fn,
            budget=BudgetController(BudgetConfig(request_interval_seconds=0)),
        )
        req = WebRequest(url="https://example.com/api", risk=RiskLevel.AUTHENTICATED_READ, auth_required=True)
        result = plane.execute(req)
        assert result.status == 200, f"expected 200, got {result.status!r}"
        assert result.source == "session"

    def test_session_none_status_blocked_uses_403(self):
        broker = SessionBroker()
        broker.store_secret_bundle(
            origin="https://example.com",
            cookies=[{"name": "s", "value": "v"}],
        )

        def session_http_fn(url, **kw):
            return {
                "ok": False, "status": None, "text": "access denied",
                "block": {"blocked": True, "kind": "cloudflare", "evidence": ["denied"]},
            }

        plane = AccessPlane(
            broker=broker,
            session_http_fn=session_http_fn,
            budget=BudgetController(BudgetConfig(request_interval_seconds=0)),
        )
        req = WebRequest(url="https://example.com/api", risk=RiskLevel.AUTHENTICATED_READ, auth_required=True)
        result = plane.execute(req)
        assert result.status == 403, f"expected 403, got {result.status!r}"


class TestBrowserNoDoubleExecution:
    def test_browser_fn_called_once_not_twice_for_authenticated_read(self):
        """BROWSER_BOOTSTRAP and FULL_BROWSER share the same handler.
        Before the fix, both appeared in the transport order, causing
        _try_browser (and the real _browser_fn) to be called twice when
        the first attempt returned None — opening two browser tabs.
        """
        calls = []

        def browser_fn(url, **kw):
            calls.append(url)
            return None  # simulate failure

        plane = AccessPlane(
            browser_fn=browser_fn,
            budget=BudgetController(BudgetConfig(request_interval_seconds=0)),
        )
        req = WebRequest(url="https://example.com/page", risk=RiskLevel.AUTHENTICATED_READ)
        result = plane.execute(req)
        assert result.status == 502
        assert calls == ["https://example.com/page"], (
            f"browser_fn called {len(calls)} times, expected 1"
        )


class TestBrowserBlockDetectFallback:
    """_try_browser must call _detect_block as fallback when the browser
    function returns ok=True with no block — mirroring _try_authenticated_http."""

    def _make_plane(self, browser_fn, block_fn=None, http_fn=None, session_http_fn=None):
        return AccessPlane(
            browser_fn=browser_fn,
            block_detect_fn=block_fn or (lambda **kw: {}),
            http_fn=http_fn,
            session_http_fn=session_http_fn,
            budget=BudgetController(BudgetConfig(request_interval_seconds=0)),
        )

    def _browser_request(self, url="https://example.com/page"):
        return WebRequest(url=url, risk=RiskLevel.AUTHENTICATED_READ)

    def test_browser_ok_with_hidden_block_detected_by_fallback(self):
        """Browser returns ok=True, no block; fallback detects Cloudflare."""
        def browser_fn(url, **kw):
            return {
                "ok": True, "text": "just a moment... cloudflare challenge page",
                "html": "<html>just a moment...</html>", "url": url, "status": 200,
                "block": {},
            }

        def block_fn(html="", text="", url=""):
            return {"blocked": True, "kind": "cloudflare", "evidence": ["just a moment"]}

        plane = self._make_plane(browser_fn, block_fn)
        result = plane.execute(self._browser_request())
        assert result.status == 403, f"expected 403, got {result.status}"
        assert result.block_state != ChallengeStatus.OK
        assert result.block.get("blocked") is True
        assert result.transport == TransportType.FULL_BROWSER

    def test_browser_ok_with_no_block_passes_through(self):
        """When browser ok=True and no block anywhere, result is 200."""
        def browser_fn(url, **kw):
            return {"ok": True, "text": "real content", "html": "<p>ok</p>", "url": url, "status": 200, "block": {}}

        plane = self._make_plane(browser_fn)
        result = plane.execute(self._browser_request())
        assert result.status == 200
        assert result.block_state == ChallengeStatus.OK

    def test_browser_block_already_set_skips_fallback(self):
        """When browser function already returns a block, fallback is not needed."""
        def browser_fn(url, **kw):
            return {
                "ok": False, "text": "blocked", "html": "blocked", "url": url,
                "status": 403, "block": {"blocked": True, "kind": "cloudflare", "evidence": ["blocked"]},
            }

        fallback_calls = []
        def block_fn(**kw):
            fallback_calls.append(1)
            return {}

        plane = self._make_plane(browser_fn, block_fn)
        result = plane.execute(self._browser_request())
        assert result.status == 403
        assert result.block.get("kind") == "cloudflare"
        assert fallback_calls == [], "fallback should not be called when browser already detected block"


class TestBlockKindMapping:
    """Every block kind from detect_block_page must map to the correct ChallengeKind."""

    # Block kinds produced by helpers.detect_block_page
    _BLOCK_KINDS = {
        "kasada_kpsdk": ChallengeKind.KASADA_KPSDK,
        "cloudflare": ChallengeKind.CLOUDFLARE_CHALLENGE,
        "akamai": ChallengeKind.AKAMAI,
        "perimeterx": ChallengeKind.PERIMETERX,
        "imperva": ChallengeKind.BLOCKED,
        "datadome": ChallengeKind.DATADOME,
        "waf_generic": ChallengeKind.BLOCKED,
        "auth_gate": ChallengeKind.LOGIN_REDIRECT,
    }

    @pytest.mark.parametrize("kind,expected", list(_BLOCK_KINDS.items()))
    def test_block_kind_maps_correctly(self, kind, expected):
        block = {"kind": kind, "blocked": True}
        result = AccessPlane._block_kind_to_challenge_kind(block)
        assert result == expected, f"{kind!r} mapped to {result!r}, expected {expected!r}"
