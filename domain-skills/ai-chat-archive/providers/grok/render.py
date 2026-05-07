"""Render a Grok normalized payload to deterministic Markdown."""
from __future__ import annotations

from typing import Any

from lib.render_safety import dict_items, safe_ordinal, sorted_messages, text_value


def render_grok_markdown(normalized: dict[str, Any]) -> str:
    title = normalized.get("title") or "Untitled"
    canonical_url = normalized.get("canonical_url") or ""
    parts: list[str] = [f"# {title}"]
    if canonical_url:
        parts.append(f"Source: {canonical_url}")
    parts.append("")

    for msg in sorted_messages(normalized.get("messages")):
        role = msg.get("role", "unknown")
        ordinal = safe_ordinal(msg.get("ordinal"))
        meta = msg.get("metadata") or {}
        model = meta.get("model") or ""
        header = f"## [{role}] #{ordinal}"
        if model:
            header += f" ({model})"
        parts.append(header)
        parts.append("")
        content = text_value(msg.get("content")).strip()
        if content:
            parts.append(content)
            parts.append("")

    artifacts = normalized.get("artifacts") or []
    if artifacts:
        parts.append("---")
        parts.append("")
        parts.append("## Artifacts")
        parts.append("")
        for art in dict_items(artifacts):
            label = art.get("label") or "unnamed"
            atype = art.get("artifact_type") or "unknown"
            url = art.get("source_url") or ""
            line = f"- **{label}** ({atype})"
            if url:
                line += f" — {url}"
            parts.append(line)
        parts.append("")

    citations = normalized.get("citations") or []
    if citations:
        parts.append("---")
        parts.append("")
        parts.append("## Sources")
        parts.append("")
        for c in dict_items(citations):
            label = c.get("label") or c.get("url", "")
            url = c.get("url", "")
            if url:
                parts.append(f"- [{label}]({url})")
            elif label:
                parts.append(f"- {label}")
        parts.append("")

    return "\n".join(parts).rstrip() + "\n"
