"""Render a Gemini normalized payload to deterministic Markdown."""
from __future__ import annotations

from typing import Any

from lib.render_safety import dict_items, sorted_messages, text_value


def render_gemini_markdown(normalized: dict[str, Any]) -> str:
    title = normalized.get("title") or "Untitled"
    canonical_url = normalized.get("canonical_url") or ""
    parts: list[str] = [f"# {title}"]
    if canonical_url:
        parts.append(f"Source: {canonical_url}")
    parts.append("")

    for msg in sorted_messages(normalized.get("messages")):
        role = msg.get("role", "unknown")
        ordinal = msg.get("ordinal", 0)
        parts.append(f"## [{role}] #{ordinal}")
        parts.append("")
        content = text_value(msg.get("content")).strip()
        if content:
            parts.append(content)
            parts.append("")
        refs = dict_items(msg.get("artifact_refs"))
        if refs:
            for r in refs:
                url = r.get("url")
                if url:
                    parts.append(f"![]({url})")
            parts.append("")

    return "\n".join(parts).rstrip() + "\n"
