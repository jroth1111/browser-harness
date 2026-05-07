"""Small shape guards for deterministic archive renderers."""
from __future__ import annotations

from typing import Any


def dict_items(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def sorted_messages(value: Any) -> list[dict[str, Any]]:
    return sorted(dict_items(value), key=lambda msg: msg.get("ordinal", 0))
