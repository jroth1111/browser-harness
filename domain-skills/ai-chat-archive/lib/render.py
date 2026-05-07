"""Render structured capture data to deterministic Markdown."""

from lib.render_safety import dict_items, sorted_messages, text_value


def render_thread_markdown(capture: dict) -> str:
    title = capture.get("title") or "Untitled"
    url = capture.get("canonical_url", "")
    parts = [f"# {title}"]
    if url:
        parts.append(f"Source: {url}")
    parts.append("")

    for msg in sorted_messages(capture.get("messages")):
        role = msg.get("role", "unknown")
        content = text_value(msg.get("content"))
        ordinal = msg.get("ordinal", 0)
        model = msg.get("model", "")
        header = f"## [{role}] #{ordinal}"
        if model:
            header += f" ({model})"
        parts.append(header)
        parts.append("")
        parts.append(content.strip())
        parts.append("")

    artifacts = capture.get("artifacts", [])
    if artifacts:
        parts.append("---")
        parts.append("")
        parts.append("## Artifacts")
        parts.append("")
        for art in dict_items(artifacts):
            label = art.get("label", "unnamed")
            art_type = art.get("artifact_type", "unknown")
            detail = ""
            storage = art.get("storage_kind", "")
            byte_length = art.get("byte_length")
            if storage == "text":
                text_len = art.get("text_length", 0)
                if text_len > 0:
                    words = text_len // 5
                    detail = f" - {words:,} words, captured"
                else:
                    detail = " - captured"
            elif storage == "binary" and byte_length:
                if byte_length >= 1_000_000:
                    detail = f" - {byte_length / 1_000_000:.0f}MB, captured"
                elif byte_length >= 1_000:
                    detail = f" - {byte_length // 1_000}KB, captured"
                else:
                    detail = f" - {byte_length}B, captured"
            elif storage == "metadata":
                detail = " - metadata only"
            parts.append(f"- **{label}** ({art_type}){detail}")
        parts.append("")

    citations = capture.get("citations", [])
    if citations:
        parts.append("---")
        parts.append("")
        parts.append("## Sources")
        parts.append("")
        for cit in dict_items(citations):
            label = cit.get("label", "")
            url = cit.get("url", "")
            if url:
                parts.append(f"- [{label or url}]({url})")
            elif label:
                parts.append(f"- {label}")
        parts.append("")

    return "\n".join(parts)
