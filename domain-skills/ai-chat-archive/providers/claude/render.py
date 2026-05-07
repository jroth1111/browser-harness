"""Render a Claude normalized payload to deterministic Markdown."""
from __future__ import annotations

from typing import Any

from lib.render_safety import dict_items, safe_count, safe_ordinal, sorted_messages, text_value


def render_claude_markdown(normalized: dict[str, Any]) -> str:
    title = normalized.get("title") or "Untitled"
    canonical_url = normalized.get("canonical_url") or ""
    parts: list[str] = [f"# {title}"]
    if canonical_url:
        parts.append(f"Source: {canonical_url}")
    if normalized.get("model"):
        parts.append(f"Default model: `{normalized['model']}`")
    parts.append("")

    for msg in sorted_messages(normalized.get("messages")):
        role = msg.get("role", "unknown")
        ordinal = safe_ordinal(msg.get("ordinal"))
        meta = msg.get("metadata") or {}
        model = meta.get("model") or ""
        ctype = msg.get("content_type") or ""

        header = f"## [{role}] #{ordinal}"
        suffix_bits = [b for b in [model, ctype if ctype not in ("", "text") else None] if b]
        if suffix_bits:
            header += f" ({', '.join(suffix_bits)})"
        parts.append(header)
        parts.append("")

        content = text_value(msg.get("content")).strip()
        if content:
            parts.append(content)
            parts.append("")

        rich = msg.get("rich_parts") or []
        for block in dict_items(rich):
            btype = block.get("type")
            if btype == "thinking":
                t = text_value(block.get("thinking") or block.get("text")).strip()
                if t:
                    parts.append("> _thinking:_")
                    for line in t.splitlines():
                        parts.append(f"> {line}")
                    parts.append("")
            elif btype == "tool_use":
                name = block.get("name") or "tool"
                parts.append(f"_tool call: `{name}`_")
                parts.append("")
            elif btype == "tool_result":
                parts.append("_tool result_")
                parts.append("")

        for ref in dict_items(msg.get("artifact_refs")):
            parts.append(f"- attachment: `{ref.get('file_uuid', '?')}` ({ref.get('kind')})")
        if msg.get("artifact_refs"):
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
            byte_length = safe_count(art.get("byte_length"))
            mime = art.get("mime_type")
            extras = []
            if mime:
                extras.append(mime)
            if byte_length:
                extras.append(_human_bytes(byte_length))
            extra = f" — {', '.join(extras)}" if extras else ""
            parts.append(f"- **{label}** ({atype}){extra}")
        parts.append("")

    return "\n".join(parts).rstrip() + "\n"


def _human_bytes(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}MB"
    if n >= 1_000:
        return f"{n // 1_000}KB"
    return f"{n}B"
