"""bh_http — authority-routed HTTP adapter for domain skills.

Domain skills should use this instead of urllib.request.urlopen.
Routes every request through AccessPlane with policy/budget/challenge gates.

The default plane wires three transport functions:
- ``public_http`` — direct ``urllib.request`` (Gate 6 approves this module).
- ``session_http`` — browser-cookie-augmented HTTP via the daemon; lazily
  imported from ``browser_harness.helpers``.  Returns ``None`` if the daemon
  is unreachable, letting AccessPlane fall back to public HTTP.
- ``browser`` — full browser navigation via the daemon; same fallback
  semantics.

Callers running in pure HTTP environments (no daemon) still get the
public_http path; the session/browser closures degrade gracefully.

Usage:
    from browser_harness.transports.bh_http import get, execute

    resp = get("https://example.com/api/data")
    resp = execute(WebRequest(url="...", risk="authenticated_read", auth_required=True))
"""
from __future__ import annotations

import urllib.error
import urllib.request
from typing import Any

from ..authority.challenge import ChallengeStateMachine
from ..authority.handoff import HandoffBroker
from ..authority.policy import PolicyEngine
from ..capabilities.models import (
    Capability,
    ChallengeStatus,
    RiskLevel,
    TransportType,
    WebRequest,
)
from ..capabilities.resolver import AccessPlane, AccessResult
from ..scheduler.budgets import BudgetController
from ..sessions.broker import SessionBroker
from ..response import Response


_DEFAULT_TIMEOUT = 20.0


def _public_http(url: str, headers: dict[str, str] | None = None, **_: Any) -> str | None:
    """Direct urllib.request GET.  Returns text on success, None on failure."""
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=_DEFAULT_TIMEOUT) as resp:
            data = resp.read()
            charset = resp.headers.get_content_charset() or "utf-8"
            return data.decode(charset, errors="replace")
    except (urllib.error.HTTPError, urllib.error.URLError, OSError):
        return None


def _session_http(url: str, headers: dict[str, str] | None = None, **_: Any) -> dict | None:
    """Daemon-backed session HTTP.  Returns None when daemon is unreachable."""
    try:
        from .. import helpers  # lazy: avoids circular import on package init
    except ImportError:
        return None
    fn = getattr(helpers, "http_get_browser_session_response", None)
    if fn is None:
        return None
    try:
        return fn(url, headers=headers, timeout=_DEFAULT_TIMEOUT)
    except Exception:
        return None


def _browser(url: str, **_: Any) -> dict | None:
    """Daemon-backed browser navigation.  Returns None when daemon is unreachable."""
    try:
        from .. import helpers
    except ImportError:
        return None
    new_tab = getattr(helpers, "new_tab", None)
    wait_for_load = getattr(helpers, "wait_for_load", None)
    wait_for_content = getattr(helpers, "wait_for_content", None)
    js = getattr(helpers, "js", None)
    close_tab = getattr(helpers, "close_tab", None)
    if not all([new_tab, wait_for_load, wait_for_content, js, close_tab]):
        return None
    tid = None
    try:
        tid = new_tab(url)
        wait_for_load(timeout=_DEFAULT_TIMEOUT)
        status = wait_for_content(min_text=500, timeout=_DEFAULT_TIMEOUT)
        html = js("document.documentElement.outerHTML") or ""
        return {
            "ok": status.get("ok", False),
            "text": status.get("text", ""),
            "html": html,
            "url": status.get("url", url),
            "status": 200 if status.get("ok") else 502,
            "reason": status.get("reason", ""),
            "block": status.get("block") or {},
        }
    except Exception:
        return None
    finally:
        if tid:
            try:
                close_tab(tid)
            except Exception:
                pass


def _block_detect(html: str = "", text: str = "", url: str = "", **_: Any) -> dict:
    try:
        from .. import helpers
    except ImportError:
        return {}
    fn = getattr(helpers, "detect_block_page", None)
    if fn is None:
        return {}
    try:
        return fn(html=html, text=text, url=url) or {}
    except Exception:
        return {}


def _default_plane() -> AccessPlane:
    return AccessPlane(
        policy=PolicyEngine(),
        budget=BudgetController(),
        broker=SessionBroker(),
        challenge_sm=ChallengeStateMachine(),
        http_fn=_public_http,
        session_http_fn=_session_http,
        browser_fn=_browser,
        block_detect_fn=_block_detect,
        handoff_broker=HandoffBroker(),
    )


def execute(
    request: WebRequest,
    capability: Capability | None = None,
    plane: AccessPlane | None = None,
) -> Response:
    """Execute a WebRequest through the authority pipeline.

    Returns a Response object with the same interface as helpers.fetch().
    """
    p = plane or _default_plane()
    result = p.execute(request)
    return _result_to_response(result)


def get(
    url: str,
    *,
    risk: str = "public_read",
    headers: dict[str, str] | None = None,
    plane: AccessPlane | None = None,
) -> Response:
    """HTTP GET through the authority pipeline.

    Drop-in replacement for urllib.request.urlopen(url).read().
    """
    request = WebRequest(
        url=url,
        risk=_risk(risk),
        method="GET",
        headers=headers or {},
        auth_required=False,
    )
    return execute(request, plane=plane)


def post(
    url: str,
    *,
    risk: str = "low_risk_write",
    body: Any = None,
    headers: dict[str, str] | None = None,
    plane: AccessPlane | None = None,
) -> Response:
    """HTTP POST through the authority pipeline."""
    request = WebRequest(
        url=url,
        risk=_risk(risk),
        method="POST",
        headers=headers or {},
        auth_required=False,
        body=body if isinstance(body, (bytes, type(None))) else None,
    )
    return execute(request, plane=plane)


def _risk(risk: str) -> RiskLevel:
    """Convert a risk string to RiskLevel. Raises ValueError on invalid input.

    Silent downgrade to PUBLIC_READ would be an authority bypass — a caller
    that passes an invalid risk string has a bug and must be told about it.
    """
    return RiskLevel(risk)


def _result_to_response(result: AccessResult) -> Response:
    return Response(
        html=result.html,
        text=result.text,
        url=result.url,
        status=result.status,
        source="authority",
        headers=result.headers,
        reason=result.reason,
        block=result.block,
    )
