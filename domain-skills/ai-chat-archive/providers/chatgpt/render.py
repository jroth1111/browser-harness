"""Render a ChatGPT normalized payload to Markdown.

Operates on the ``normalized_json`` shape produced by ``ChatGPTProvider``.
Stable, deterministic output — content_hash over this string is the dedup
signal in the runner.
"""
from __future__ import annotations

from typing import Any

from lib.render_safety import dict_items, safe_ordinal, sorted_messages, text_value


def render_chatgpt_markdown(normalized: dict[str, Any]) -> str:
    title = normalized.get("title") or "Untitled"
    canonical_url = normalized.get("canonical_url") or ""
    parts: list[str] = [f"# {title}"]
    if canonical_url:
        parts.append(f"Source: {canonical_url}")
    if normalized.get("model_slug"):
        parts.append(f"Default model: `{normalized['model_slug']}`")
    parts.append("")

    for msg in sorted_messages(normalized.get("messages")):
        role = msg.get("role", "unknown")
        ordinal = safe_ordinal(msg.get("ordinal"))
        meta = msg.get("metadata") or {}
        model = meta.get("model") or ""
        ctype = msg.get("content_type") or ""

        header = f"## [{role}] #{ordinal}"
        suffix_bits = []
        if model:
            suffix_bits.append(model)
        if ctype and ctype not in ("text", ""):
            suffix_bits.append(ctype)
        if suffix_bits:
            header += f" ({', '.join(suffix_bits)})"
        parts.append(header)
        parts.append("")

        content = text_value(msg.get("content")).strip()
        if content:
            parts.append(content)
            parts.append("")

        for ref in dict_items(msg.get("artifact_refs")):
            parts.append(f"- artifact ref: `{_short_ref(ref)}`")
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
            detail = ""
            byte_length = art.get("byte_length")
            if byte_length:
                detail = f" — {_human_bytes(byte_length)}"
            url = art.get("source_url")
            line = f"- **{label}** ({atype}){detail}"
            if url:
                line += f" — {url}"
            parts.append(line)
        parts.append("")

    return "\n".join(parts).rstrip() + "\n"


def _short_ref(ref: dict[str, Any]) -> str:
    for key in ("file_id", "image_asset", "path"):
        if ref.get(key):
            v = str(ref[key])
            return v if len(v) <= 80 else v[:77] + "..."
    return ", ".join(f"{k}={v}" for k, v in ref.items() if v)[:80] or "?"


def _human_bytes(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}MB"
    if n >= 1_000:
        return f"{n // 1_000}KB"
    return f"{n}B"
