"""Tests for bh_http adapter and handoff protocol."""
import json
import pytest
from pathlib import Path

from browser_harness.transports.bh_http import get, execute, _risk
from browser_harness.authority.handoff import HandoffBroker, HandoffRequest, ResumeToken
from browser_harness.capabilities.models import (
    RiskLevel,
    TransportType,
    WebRequest,
    ChallengeStatus,
)
from browser_harness.capabilities.resolver import AccessPlane, AccessResult
from browser_harness.authority.policy import PolicyEngine
from browser_harness.authority.challenge import ChallengeStateMachine
from browser_harness.sessions.broker import SessionBroker
from browser_harness.scheduler.budgets import BudgetController


# --- bh_http tests ---


class TestBhHttp:
    def test_get_routes_through_access_plane(self):
        """bh_http.get delegates to AccessPlane, returns authority source."""
        plane = AccessPlane(
            policy=PolicyEngine(),
            budget=BudgetController(),
            http_fn=lambda url, **kw: "hello from authority",
        )
        resp = get("https://example.com/page", plane=plane)
        assert resp.source == "authority"
        assert resp.text == "hello from authority"
        assert resp.status == 200

    def test_execute_with_webrequest(self):
        """bh_http.execute accepts a WebRequest and returns Response."""
        plane = AccessPlane(
            policy=PolicyEngine(),
            budget=BudgetController(),
            http_fn=lambda url, **kw: "executed",
        )
        req = WebRequest(url="https://example.com/api", risk=RiskLevel.PUBLIC_READ)
        resp = execute(req, plane=plane)
        assert resp.text == "executed"
        assert resp.status == 200

    def test_blocked_request_returns_403(self):
        """Blocked content returns 403, not 200."""
        plane = AccessPlane(
            policy=PolicyEngine(),
            budget=BudgetController(),
            http_fn=lambda url, **kw: "challenge page",
            block_detect_fn=lambda **kw: {"blocked": True, "kind": "cloudflare", "evidence": []},
        )
        resp = get("https://example.com/protected", plane=plane)
        assert resp.status == 403
        assert resp.block.get("blocked") is True

    def test_risk_parsing(self):
        assert _risk("public_read") == RiskLevel.PUBLIC_READ
        assert _risk("authenticated_read") == RiskLevel.AUTHENTICATED_READ
        assert _risk("invalid_value") == RiskLevel.PUBLIC_READ


# --- handoff tests ---


class TestHandoffBroker:
    def test_create_stores_request(self, tmp_path):
        broker = HandoffBroker(store_dir=tmp_path)
        req = broker.create(
            url="https://example.com/protected",
            origin="https://example.com",
            challenge_kind="cloudflare",
        )
        assert req.handoff_id
        assert req.origin == "https://example.com"
        assert (tmp_path / f"{req.handoff_id}.json").exists()

    def test_get_returns_request(self, tmp_path):
        broker = HandoffBroker(store_dir=tmp_path)
        req = broker.create("https://example.com/p", "https://example.com", "login_redirect")
        retrieved = broker.get(req.handoff_id)
        assert retrieved is not None
        assert retrieved.origin == "https://example.com"

    def test_get_expired_returns_none(self, tmp_path):
        broker = HandoffBroker(store_dir=tmp_path)
        req = broker.create("https://example.com/p", "https://example.com", "captcha", ttl=-1.0)
        assert broker.get(req.handoff_id) is None

    def test_get_unknown_returns_none(self, tmp_path):
        broker = HandoffBroker(store_dir=tmp_path)
        assert broker.get("nonexistent") is None

    def test_complete_signs_resume_token(self, tmp_path):
        broker = HandoffBroker(store_dir=tmp_path)
        req = broker.create("https://example.com/p", "https://example.com", "cloudflare")
        token = broker.complete(req.handoff_id, account_id="user1")
        assert token.signature
        assert len(token.signature) == 32  # SHA256

    def test_consume_valid_token(self, tmp_path):
        broker = HandoffBroker(store_dir=tmp_path)
        req = broker.create("https://example.com/p", "https://example.com", "cloudflare")
        token = broker.complete(req.handoff_id)
        token_bytes = token.to_bytes()
        consumed = broker.consume(token_bytes)
        assert consumed is not None
        assert consumed.origin == "https://example.com"

    def test_consume_expired_token(self, tmp_path):
        broker = HandoffBroker(store_dir=tmp_path)
        req = broker.create("https://example.com/p", "https://example.com", "cloudflare")
        token = broker.complete(req.handoff_id, ttl=-1.0)
        consumed = broker.consume(token.to_bytes())
        assert consumed is None

    def test_consume_tampered_token(self, tmp_path):
        broker = HandoffBroker(store_dir=tmp_path)
        req = broker.create("https://example.com/p", "https://example.com", "cloudflare")
        token = broker.complete(req.handoff_id)
        # Tamper with the origin
        tampered = ResumeToken(
            origin="https://evil.example",
            account_id=token.account_id,
            session_ref_id=token.session_ref_id,
            completed_at=token.completed_at,
            expires_at=token.expires_at,
            nonce=token.nonce,
            signature=token.signature,
        )
        consumed = broker.consume(tampered.to_bytes())
        assert consumed is None

    def test_complete_cleans_up_request(self, tmp_path):
        broker = HandoffBroker(store_dir=tmp_path)
        req = broker.create("https://example.com/p", "https://example.com", "cloudflare")
        path = tmp_path / f"{req.handoff_id}.json"
        assert path.exists()
        broker.complete(req.handoff_id)
        assert not path.exists()

    def test_access_plane_produces_handoff_id(self, tmp_path):
        """Blocked fetch with handoff broker returns handoff_id in extra."""
        from browser_harness.authority.handoff import HandoffBroker
        broker = HandoffBroker(store_dir=tmp_path)
        plane = AccessPlane(
            policy=PolicyEngine(),
            budget=BudgetController(),
            challenge_sm=ChallengeStateMachine(),
            handoff_broker=broker,
            http_fn=lambda url, **kw: "challenge page",
            block_detect_fn=lambda **kw: {"blocked": True, "kind": "cloudflare", "evidence": []},
        )
        req = WebRequest(url="https://example.com/protected", risk=RiskLevel.PUBLIC_READ)
        result = plane.execute(req)
        assert result.block_state == ChallengeStatus.NEED_HANDOFF
        assert result.extra.get("handoff_id")

    def test_authenticated_http_blocked_emits_handoff_id(self, tmp_path):
        """When session HTTP returns a Cloudflare-block, AccessPlane emits a handoff_id."""
        broker = HandoffBroker(store_dir=tmp_path)

        # Pre-seed a session ref so authenticated_http is attempted.
        sess_broker = SessionBroker()
        ref = sess_broker.store_secret_bundle(
            origin="https://example.com",
            cookies=[{"name": "sid", "value": "x", "domain": "example.com", "path": "/"}],
        )

        plane = AccessPlane(
            policy=PolicyEngine(),
            budget=BudgetController(),
            broker=sess_broker,
            challenge_sm=ChallengeStateMachine(),
            handoff_broker=broker,
            session_http_fn=lambda url, **kw: {
                "status": 403,
                "text": "challenge",
                "block": {"blocked": True, "kind": "cloudflare", "evidence": []},
            },
        )
        req = WebRequest(
            url="https://example.com/api",
            risk=RiskLevel.AUTHENTICATED_READ,
            auth_required=True,
        )
        result = plane.execute(req)
        assert result.block_state == ChallengeStatus.NEED_HANDOFF
        assert result.extra.get("handoff_id")

    def test_browser_blocked_emits_handoff_id(self, tmp_path):
        """When browser navigation lands on a Cloudflare-block, AccessPlane emits a handoff_id.

        Uses AUTHENTICATED_READ so the policy admits the browser transport;
        public_http and authenticated_http both decline (no http_fn / no
        session ref), so the resolver falls through to ``_try_browser``.
        """
        broker = HandoffBroker(store_dir=tmp_path)
        plane = AccessPlane(
            policy=PolicyEngine(),
            budget=BudgetController(),
            challenge_sm=ChallengeStateMachine(),
            handoff_broker=broker,
            browser_fn=lambda url, **kw: {
                "ok": False,
                "text": "challenge",
                "html": "<html>cf</html>",
                "url": url,
                "block": {"blocked": True, "kind": "cloudflare", "evidence": []},
            },
        )
        req = WebRequest(
            url="https://example.com/protected",
            risk=RiskLevel.AUTHENTICATED_READ,
        )
        result = plane.execute(req)
        assert result.block_state == ChallengeStatus.NEED_HANDOFF
        assert result.extra.get("handoff_id")


class TestDefaultPlane:
    """Step 5: bh_http._default_plane serves public_http when daemon absent."""

    def test_default_plane_serves_public_http(self, monkeypatch):
        """get(url) with no explicit plane returns 200 via the default urllib path."""
        from browser_harness.transports import bh_http

        captured = {}

        class FakeResp:
            headers = type("H", (), {"get_content_charset": staticmethod(lambda: "utf-8")})()

            def __init__(self, body):
                self._body = body

            def read(self):
                return self._body

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url if hasattr(req, "full_url") else req
            return FakeResp(b"hello world")

        monkeypatch.setattr(bh_http.urllib.request, "urlopen", fake_urlopen)

        resp = bh_http.get("https://example.com/page")
        assert resp.status == 200
        assert resp.text == "hello world"
        assert captured["url"] == "https://example.com/page"

    def test_default_plane_session_http_returns_none_without_daemon(self):
        """Session HTTP closure tolerates missing daemon by returning None."""
        from browser_harness.transports import bh_http

        # Without a live daemon, the closure should not crash; it should return None.
        result = bh_http._session_http("https://example.com/")
        # Either None (helpers fn missing/raises) or a dict — must not crash.
        assert result is None or isinstance(result, dict)

    def test_default_plane_wires_handoff_broker(self):
        """_default_plane attaches a HandoffBroker so blocked paths can emit handoff_ids."""
        from browser_harness.transports import bh_http

        plane = bh_http._default_plane()
        assert plane._handoff_broker is not None
