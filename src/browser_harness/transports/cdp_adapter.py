"""CDP adapter — raw CDP behind policy, not agent-facing.

Agent runtime cannot call cdp() directly. This adapter is used only by
transports and controllers that have explicit capability authorization.
"""
from __future__ import annotations

from typing import Any

from ..capabilities.models import Capability, TransportType


class CDPAdapterError(Exception):
    pass


class PolicyDeniedError(CDPAdapterError):
    pass


class CDPAdapter:
    """Wraps low-level CDP access behind capability checks.

    In agent mode, this is the only way CDP commands reach the browser.
    Direct cdp() calls are not available to agents.
    """

    # CDP methods that require explicit capability authorization
    RESTRICTED_METHODS = frozenset({
        "Network.getCookies",
        "Network.getAllCookies",
        "Runtime.evaluate",
        "Page.navigate",
        "Input.dispatchMouseEvent",
        "Input.dispatchKeyEvent",
        "DOM.setAttributeValue",
        "DOM.removeNode",
        "Storage.getCookies",
        "Storage.clearDataForOrigin",
        "Target.attachToTarget",
        "Target.activateTarget",
    })

    def __init__(self, cdp_fn=None):
        self._cdp = cdp_fn

    def send(
        self,
        method: str,
        capability: Capability | None = None,
        **params: Any,
    ) -> dict[str, Any]:
        """Send a CDP command. Restricted methods require a valid capability."""
        if method in self.RESTRICTED_METHODS:
            if not capability:
                raise PolicyDeniedError(
                    f"CDP method {method} requires capability authorization"
                )
            if capability.transport not in (
                TransportType.FULL_BROWSER,
                TransportType.BROWSER_BOOTSTRAP,
            ):
                raise PolicyDeniedError(
                    f"capability {capability.cap_id} does not authorize browser CDP"
                )

        if not self._cdp:
            raise CDPAdapterError("no CDP connection available")

        return self._cdp(method, **params)

    def is_restricted(self, method: str) -> bool:
        return method in self.RESTRICTED_METHODS
