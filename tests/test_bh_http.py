"""Tests for bh_http adapter and handoff protocol."""
import json
import pytest
from pathlib import Path

from browser_harness.transports.bh_http import get, execute, post, _risk
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
from browser_harness.scheduler.budgets import BudgetController, BudgetConfig


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
        assert resp.source == "http"
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
        with pytest.raises(ValueError):
            _risk("invalid_value")

    def test_invalid_risk_does_not_downgrade_to_public_read(self):
        """Authority bypass closure: invalid risk must raise, not silently downgrade.

        Before the fix, _risk("typo") returned PUBLIC_READ, letting a caller
        that passed an incorrect risk string bypass the authority pipeline and
        route what should have been an authenticated request through unauthenticated
        public HTTP.
        """
        for bad in ("", "public_red", "authenticate_read", "low_risk", "high_risk", None):
            with pytest.raises(ValueError):
                _risk(bad)

    def test_post_does_not_crash_on_webrequest_construction(self):
        """post() must not pass an 'extra' kwarg to WebRequest — it would crash
        with TypeError. Before the fix, extra={"body": body} was passed but
        WebRequest has no 'extra' field."""
        plane = AccessPlane(
            policy=PolicyEngine(standing_permissions={RiskLevel.LOW_RISK_WRITE}),
            budget=BudgetController(),
            http_fn=lambda url, **kw: "posted",
        )
        resp = post("https://example.com/api", body=b"test", plane=plane)
        assert resp.source == "authority"
        # POST correctly skips GET-only PUBLIC_HTTP transport; no POST-capable
        # transport is available, so the result is 502, not a silent GET-200.
        assert resp.status == 502

    def test_post_encodes_string_body(self):
        """String body must be encoded to bytes, not silently dropped."""
        requests = []

        class CapturingPlane(AccessPlane):
            def execute(self, request):
                requests.append(request)
                return super().execute(request)

        plane = CapturingPlane(
            policy=PolicyEngine(standing_permissions={RiskLevel.LOW_RISK_WRITE}),
            budget=BudgetController(),
        )
        post("https://example.com/api", body="key=value", plane=plane)
        assert len(requests) == 1
        assert requests[0].body == b"key=value", "string body must be encoded to bytes"

    def test_post_rejects_dict_body(self):
        """Dict body must raise TypeError — caller must JSON-encode."""
        with pytest.raises(TypeError, match="body must be"):
            post("https://example.com/api", body={"key": "value"})


class TestAgentHostRiskFromStr:
    """Agent host uses _risk_from_str with identical semantics — must also raise."""

    def test_valid_risk_levels(self):
        from browser_harness.runtime.agent_host import _risk_from_str

        assert _risk_from_str("public_read") == RiskLevel.PUBLIC_READ
        assert _risk_from_str("authenticated_read") == RiskLevel.AUTHENTICATED_READ
        assert _risk_from_str("low_risk_write") == RiskLevel.LOW_RISK_WRITE
        assert _risk_from_str("external_side_effect") == RiskLevel.EXTERNAL_SIDE_EFFECT

    def test_invalid_risk_raises(self):
        """A compromised worker must not bypass authority by sending an invalid risk."""
        from browser_harness.runtime.agent_host import _risk_from_str

        for bad in ("", "bypass", "admin", "sudo", None):
            with pytest.raises(ValueError):
                _risk_from_str(bad)


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

    def test_complete_expired_returns_none(self, tmp_path):
        broker = HandoffBroker(store_dir=tmp_path)
        req = broker.create("https://example.com/p", "https://example.com", "cloudflare", ttl=-1.0)
        assert broker.complete(req.handoff_id) is None

    def test_complete_nonexistent_returns_none(self, tmp_path):
        broker = HandoffBroker(store_dir=tmp_path)
        assert broker.complete("nonexistent_id") is None

    def test_get_rejects_path_traversal(self, tmp_path):
        """handoff_id with path traversal characters must not escape store dir."""
        broker = HandoffBroker(store_dir=tmp_path)

    def test_get_handles_concurrent_file_deletion(self, tmp_path):
        """get() must return None if the file vanishes between exists check and read.

        Before the fix, a TOCTOU race between exists() and read_text() would
        raise FileNotFoundError — unhandled, because the except clause only
        caught json.JSONDecodeError and TypeError.
        """
        broker = HandoffBroker(store_dir=tmp_path)
        req = broker.create("https://example.com/p", "https://example.com", "cloudflare")
        # Delete the file to simulate concurrent complete() or manual cleanup
        (tmp_path / f"{req.handoff_id}.json").unlink()
        assert broker.get(req.handoff_id) is None
        # Create a file outside the store dir to prove it can't be read
        outside = tmp_path.parent / "secret.json"
        outside.write_text('{"handoff_id":"../../secret","origin":"x","url":"x","challenge_kind":"x","created_at":0,"expires_at":9999999999}')
        try:
            result = broker.get("../../secret")
            assert result is None, "path traversal must be rejected"
        finally:
            outside.unlink(missing_ok=True)

    def test_get_rejects_non_hex_id(self, tmp_path):
        """handoff_id must be hex only — rejects slashes, dots, special chars."""
        broker = HandoffBroker(store_dir=tmp_path)
        assert broker.get("../etc/passwd") is None
        assert broker.get("abc/def") is None
        assert broker.get("id with spaces") is None
        assert broker.get("id\x00evil") is None

    def test_complete_rejects_path_traversal(self, tmp_path):
        """complete() must not delete files outside the store dir."""
        broker = HandoffBroker(store_dir=tmp_path)
        outside = tmp_path.parent / "target.json"
        outside.write_text('{"handoff_id":"../../target","origin":"x","url":"x","challenge_kind":"x","created_at":0,"expires_at":9999999999}')
        try:
            result = broker.complete("../../target")
            assert result is None, "path traversal must be rejected"
            assert outside.exists(), "file outside store dir must NOT be deleted"
        finally:
            outside.unlink(missing_ok=True)

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

    def test_access_plane_propagates_challenge_kind(self, tmp_path):
        """Blocked fetch stores the detected challenge kind, not 'unknown'."""
        broker = HandoffBroker(store_dir=tmp_path)
        plane = AccessPlane(
            policy=PolicyEngine(),
            budget=BudgetController(),
            challenge_sm=ChallengeStateMachine(),
            handoff_broker=broker,
            http_fn=lambda url, **kw: "challenge page",
            block_detect_fn=lambda **kw: {"blocked": True, "kind": "captcha", "evidence": []},
        )
        req = WebRequest(url="https://example.com/protected", risk=RiskLevel.PUBLIC_READ)
        result = plane.execute(req)
        handoff_id = result.extra.get("handoff_id")
        assert handoff_id
        stored = broker.get(handoff_id)
        assert stored is not None
        assert stored.challenge_kind == "captcha"

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

    def test_browser_failure_without_block_reports_unobservable(self, tmp_path):
        """When browser fails (ok=False) but no block detected, block_state is UNOBSERVABLE.

        Before the fix, block_state was OK, causing agent_host to report
        status="ok" for a 502 response.
        """
        plane = AccessPlane(
            policy=PolicyEngine(),
            budget=BudgetController(),
            challenge_sm=ChallengeStateMachine(),
            browser_fn=lambda url, **kw: {
                "ok": False,
                "text": "",
                "html": "",
                "url": url,
                "reason": "timeout",
            },
        )
        req = WebRequest(
            url="https://example.com/timeout-page",
            risk=RiskLevel.AUTHENTICATED_READ,
        )
        result = plane.execute(req)
        assert result.status == 502
        assert result.block_state == ChallengeStatus.UNOBSERVABLE
        assert result.reason == "timeout"

    def test_post_skips_authenticated_http(self, tmp_path):
        """POST requests must not silently become GETs through AUTHENTICATED_HTTP.

        Before the fix, _try_authenticated_http ignored the request method.
        A POST with a session ref available would succeed via session HTTP
        with a GET response — the method and body silently dropped.
        """
        sess_broker = SessionBroker()
        sess_broker.store_secret_bundle(
            origin="https://example.com",
            cookies=[{"name": "sid", "value": "x", "domain": "example.com", "path": "/"}],
        )
        session_calls = []
        def session_http(url, **kw):
            session_calls.append(url)
            return {"status": 200, "text": "session content"}

        plane = AccessPlane(
            policy=PolicyEngine(standing_permissions={RiskLevel.AUTHENTICATED_READ}),
            budget=BudgetController(),
            broker=sess_broker,
            session_http_fn=session_http,
        )
        req = WebRequest(
            url="https://example.com/api",
            method="POST",
            risk=RiskLevel.AUTHENTICATED_READ,
            auth_required=True,
            body=b"test data",
        )
        result = plane.execute(req)
        assert len(session_calls) == 0, "POST must not be routed through GET-only AUTHENTICATED_HTTP"
        assert result.status == 502

    def test_unrecognized_block_kind_does_not_crash(self, tmp_path):
        """Blocked page with unrecognized challenge kind must not crash the pipeline.

        Before the fix, _block_kind_to_challenge_kind returned ChallengeKind.BLOCKED
        which did not exist in the enum — AttributeError at runtime. Any blocked
        page with an unrecognized kind (e.g. a new bot-protection vendor) would
        crash the entire request pipeline instead of triggering a handoff.
        """
        broker = HandoffBroker(store_dir=tmp_path)
        plane = AccessPlane(
            policy=PolicyEngine(),
            budget=BudgetController(),
            challenge_sm=ChallengeStateMachine(),
            handoff_broker=broker,
            http_fn=lambda url, **kw: "access denied",
            block_detect_fn=lambda **kw: {
                "blocked": True,
                "kind": "some_new_vendor_we_have_never_seen",
                "evidence": ["unknown challenge page"],
            },
        )
        req = WebRequest(url="https://example.com/protected", risk=RiskLevel.PUBLIC_READ)
        result = plane.execute(req)
        assert result.status == 403
        assert result.block_state == ChallengeStatus.NEED_HANDOFF
        assert result.extra.get("handoff_id")

    def test_turnstile_not_misclassified_as_cloudflare_challenge(self, tmp_path):
        """cloudflare_turnstile kind must classify as TURNSTILE, not CHALLENGE.

        Before the fix, the mapping checked "cloudflare" before "turnstile",
        so "cloudflare_turnstile" matched CLOUDFLARE_CHALLENGE instead of
        CLOUDFLARE_TURNSTILE. Both resolve to NEED_HANDOFF, but the stored
        handoff metadata was wrong.
        """
        from browser_harness.authority.challenge import ChallengeKind
        from browser_harness.capabilities.resolver import AccessPlane as AP

        block = {"blocked": True, "kind": "cloudflare_turnstile", "evidence": []}
        assert AP._block_kind_to_challenge_kind(block) == ChallengeKind.CLOUDFLARE_TURNSTILE

        # Verify standalone "cloudflare" still works
        block_cf = {"blocked": True, "kind": "cloudflare", "evidence": []}
        assert AP._block_kind_to_challenge_kind(block_cf) == ChallengeKind.CLOUDFLARE_CHALLENGE

        # Verify standalone "turnstile" also maps to TURNSTILE
        block_ts = {"blocked": True, "kind": "turnstile", "evidence": []}
        assert AP._block_kind_to_challenge_kind(block_ts) == ChallengeKind.CLOUDFLARE_TURNSTILE


class TestAccessPlaneCache:
    """Verify cache behavior: hits, misses, and bounded eviction."""

    def test_cache_returns_same_result_on_hit(self):
        plane = AccessPlane(
            policy=PolicyEngine(),
            budget=BudgetController(BudgetConfig(request_interval_seconds=0)),
            http_fn=lambda url, **kw: f"content from {url}",
        )
        req1 = WebRequest(url="https://example.com/page", risk=RiskLevel.PUBLIC_READ)
        result1 = plane.execute(req1)
        assert result1.status == 200

        # Second request should return cached result (same object)
        req2 = WebRequest(url="https://example.com/page", risk=RiskLevel.PUBLIC_READ)
        result2 = plane.execute(req2)
        assert result2 is result1

    def test_cache_evicts_oldest_when_full(self):
        from browser_harness.capabilities.resolver import _MAX_CACHE_ENTRIES
        call_count = 0

        def counting_http(url, **kw):
            nonlocal call_count
            call_count += 1
            return f"response {call_count}"

        plane = AccessPlane(
            policy=PolicyEngine(),
            budget=BudgetController(BudgetConfig(
                request_interval_seconds=0,
                max_requests_per_origin=_MAX_CACHE_ENTRIES + 20,
                max_total_requests=_MAX_CACHE_ENTRIES + 20,
            )),
            http_fn=counting_http,
        )
        # Fill cache past capacity to trigger eviction of page0
        for i in range(_MAX_CACHE_ENTRIES + 1):
            req = WebRequest(url=f"https://example.com/page{i}", risk=RiskLevel.PUBLIC_READ)
            plane.execute(req)
        assert call_count == _MAX_CACHE_ENTRIES + 1

        # page0 was evicted — re-requesting must call the transport again
        req_again = WebRequest(url="https://example.com/page0", risk=RiskLevel.PUBLIC_READ)
        plane.execute(req_again)
        assert call_count == _MAX_CACHE_ENTRIES + 2

    def test_cache_skips_non_public_read(self):
        plane = AccessPlane(
            policy=PolicyEngine(),
            budget=BudgetController(BudgetConfig(request_interval_seconds=0)),
            http_fn=lambda url, **kw: "auth content",
        )
        req1 = WebRequest(url="https://example.com/api", risk=RiskLevel.AUTHENTICATED_READ)
        result1 = plane.execute(req1)
        assert result1.status == 200

        # Authenticated reads should NOT be cached
        assert len(plane._cache) == 0


class TestDefaultPlane:
    """Step 5: bh_http._default_plane serves public_http when daemon absent."""

    def test_default_plane_serves_public_http(self, monkeypatch):
        """get(url) with no explicit plane returns 200 via the default urllib path."""
        from browser_harness.transports import bh_http

        captured = {}

        class FakeResp:
            status = 200
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

    def test_public_http_returns_error_body_on_httperror(self, monkeypatch):
        """_public_http returns HTTPError body and status for 4xx/5xx.

        Before the fix, _public_http caught HTTPError and returned None,
        discarding the response body. Challenge pages served as 403 were
        invisible to block detection. Now it returns {"text": ..., "status": ...}
        so AccessPlane sees the real HTTP status code.
        """
        from browser_harness.transports import bh_http
        import urllib.error
        import email.message

        err = urllib.error.HTTPError(
            url="https://example.com/protected",
            code=403,
            msg="Forbidden",
            hdrs=email.message.Message(),
            fp=None,
        )
        err._body = b"just a moment... cloudflare challenge"
        err.read = lambda: err._body

        def fake_urlopen(req, timeout=None):
            raise err

        monkeypatch.setattr(bh_http.urllib.request, "urlopen", fake_urlopen)
        result = bh_http._public_http("https://example.com/protected")
        assert result is not None, "HTTPError body must be returned, not None"
        assert isinstance(result, dict)
        assert "cloudflare" in result["text"]
        assert result["status"] == 403

    def test_public_http_returns_status_on_success(self, monkeypatch):
        """_public_http returns dict with status=200 on success."""
        from browser_harness.transports import bh_http
        import io

        class FakeResp:
            status = 200
            headers = type("h", (), {"get_content_charset": lambda s: "utf-8"})()
            def read(self):
                return b"hello world"
            def __enter__(self):
                return self
            def __exit__(self, *a):
                pass

        monkeypatch.setattr(bh_http.urllib.request, "urlopen",
                            lambda req, timeout=None: FakeResp())
        result = bh_http._public_http("https://example.com/")
        assert result == {"text": "hello world", "status": 200}

    def test_http_404_propagates_through_pipeline(self):
        """A 404 response must not be misreported as status=200.

        Before the fix, _public_http returned the error body as a plain
        string, and _try_public_http hardcoded status=200 for any non-None
        text result. Genuine HTTP errors (404, 500, etc.) were invisible
        to callers.
        """
        plane = AccessPlane(
            policy=PolicyEngine(),
            http_fn=lambda url, **kw: {"text": "Not Found", "status": 404},
        )
        req = WebRequest(url="https://example.com/nonexistent", risk=RiskLevel.PUBLIC_READ)
        result = plane.execute(req)
        assert result.status == 404, f"expected 404, got {result.status}"
        assert result.text == "Not Found"

    def test_http_500_propagates_through_pipeline(self):
        """A 500 response must propagate its real status."""
        plane = AccessPlane(
            policy=PolicyEngine(),
            http_fn=lambda url, **kw: {"text": "Internal Server Error", "status": 500},
        )
        req = WebRequest(url="https://example.com/broken", risk=RiskLevel.PUBLIC_READ)
        result = plane.execute(req)
        assert result.status == 500


class TestResultToResponseMapping:
    """_result_to_response must preserve source and extra from AccessResult."""

    def test_source_preserved_from_access_result(self):
        from browser_harness.transports.bh_http import _result_to_response
        result = AccessResult(
            url="https://example.com/api",
            status=200,
            text="session content",
            html="session content",
            source="session",
        )
        resp = _result_to_response(result)
        assert resp.source == "session"

    def test_source_falls_back_to_authority_when_empty(self):
        from browser_harness.transports.bh_http import _result_to_response
        result = AccessResult(
            url="https://example.com/api",
            status=502,
            text="",
            source="",
        )
        resp = _result_to_response(result)
        assert resp.source == "authority"

    def test_handoff_id_merged_into_block(self):
        from browser_harness.transports.bh_http import _result_to_response
        result = AccessResult(
            url="https://example.com/protected",
            status=403,
            text="blocked",
            source="http",
            block={"blocked": True, "kind": "cloudflare", "evidence": ["challenge"]},
            extra={"handoff_id": "abc-123"},
        )
        resp = _result_to_response(result)
        assert resp.block["handoff_id"] == "abc-123"
        assert resp.block["blocked"] is True
        assert resp.block["kind"] == "cloudflare"


class TestBrowserBlockDetection:
    """_browser must detect block pages even when wait_for_content returns no block."""

    def test_browser_detects_block_when_wait_for_content_reports_ok(self):
        """When wait_for_content says ok but detect_block_page finds a WAF block,
        _browser must return blocked, not success."""
        from browser_harness.transports import bh_http
        from browser_harness.capabilities.models import WebRequest, RiskLevel
        from browser_harness.scheduler.budgets import BudgetController, BudgetConfig

        def mock_browser_fn(url, **kw):
            return {
                "ok": False,
                "text": "just a moment",
                "html": "<html>just a moment</html>",
                "url": url,
                "status": 403,
                "reason": "blocked",
                "block": {"blocked": True, "kind": "cloudflare", "evidence": ["just a moment"]},
            }

        plane = AccessPlane(
            browser_fn=mock_browser_fn,
            budget=BudgetController(BudgetConfig(request_interval_seconds=0)),
        )
        req = WebRequest(url="https://example.com/protected", risk=RiskLevel.AUTHENTICATED_READ)
        result = plane.execute(req)
        assert result.status == 403
        assert result.block.get("blocked") is True

    def test_browser_fn_calls_block_detect_when_wait_for_content_has_no_block(self):
        """The _browser transport in bh_http must call _block_detect as fallback
        when wait_for_content returns an empty block dict."""
        from unittest.mock import patch, MagicMock
        from browser_harness.transports import bh_http as bh_module

        # Direct unit test of the block-detect fallback via mock browser:
        calls = {"detect": []}
        orig_detect = bh_module._block_detect

        def capturing_detect(**kw):
            calls["detect"].append(kw)
            return {"blocked": True, "kind": "akamai", "evidence": ["blocked"]}

        bh_module._block_detect = capturing_detect
        try:
            with patch("browser_harness.helpers.new_tab", return_value="t1"), \
                 patch("browser_harness.helpers.wait_for_load"), \
                 patch("browser_harness.helpers.wait_for_content", return_value={
                     "ok": False, "text": "", "url": "https://example.com/x", "block": {},
                 }), \
                 patch("browser_harness.helpers.js", return_value="<html>blocked</html>"), \
                 patch("browser_harness.helpers.close_tab"):
                result = bh_module._browser("https://example.com/x")
        finally:
            bh_module._block_detect = orig_detect

        assert result is not None
        assert result["block"]["blocked"] is True
        assert result["block"]["kind"] == "akamai"
        assert result["status"] == 403
        assert result["ok"] is False
        assert calls["detect"], "_block_detect was never called as fallback"
