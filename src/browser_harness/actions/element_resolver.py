"""Element resolver — produce ElementTarget with evidence before actions.

Requires target evidence (AX ref, selector, or screenshot-backed coordinates)
before clicking or filling. Arbitrary coordinate clicks fail without explicit
user approval.
"""
from __future__ import annotations

from typing import Any, Callable

from ..capabilities.models import ElementTarget, WebAction, RiskLevel


class ElementResolver:
    """Resolve element targets from evidence sources.

    Adapters: AX snapshot, DOM selector, screenshot/OCR.
    Produces ElementTarget that ActionExecutor uses for actions.
    """

    def __init__(
        self,
        ax_snapshot_fn: Callable[..., Any] | None = None,
        find_element_fn: Callable[..., Any] | None = None,
        screenshot_fn: Callable[..., Any] | None = None,
    ):
        self._ax_fn = ax_snapshot_fn
        self._find_fn = find_element_fn
        self._screenshot_fn = screenshot_fn

    def resolve(self, target: str, method: str = "auto") -> ElementTarget | None:
        """Resolve a target string into an ElementTarget with evidence."""
        if method in ("ax", "auto") and self._ax_fn:
            try:
                result = self._ax_fn()
                if result and target in str(result):
                    return ElementTarget(
                        evidence_type="ax_ref",
                        evidence_id=target,
                        confidence=0.9,
                    )
            except Exception:
                pass

        if method in ("selector", "auto") and self._find_fn:
            try:
                result = self._find_fn(target)
                if result:
                    return ElementTarget(
                        evidence_type="selector",
                        selector=target,
                        confidence=0.85,
                    )
            except Exception:
                pass

        return None

    def validate_action_target(self, action: WebAction) -> dict[str, Any]:
        """Validate that an action has a properly resolved target."""
        if not action.target and not action.coordinates:
            return {"valid": False, "reason": "action has no target or coordinates"}

        # Coordinates need explicit approval (user-approved)
        if action.coordinates and not action.target:
            return {
                "valid": False,
                "reason": "coordinate-only clicks require explicit user approval",
                "risk_override": RiskLevel.EXTERNAL_SIDE_EFFECT.value,
            }

        return {"valid": True, "target": action.target}
