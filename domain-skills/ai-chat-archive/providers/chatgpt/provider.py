"""ChatGPT provider, implementing the canonical Provider contract.

Fast path is the backend HTTP API (cookies + Bearer from /api/auth/session).
DOM/AX is only required for artifact bytes (canvas, generated files), so
``capabilities`` is ``http+dom`` — but every read other than artifact bytes
works without a browser.
"""
from __future__ import annotations

from typing import Any, Iterator

from lib.archive_db import compute_account_key
from lib.chatgpt_http import ChatGPTHTTPAPI
from lib.provider_base import (
    AccountContext,
    CapturedArtifact,
    CapturedCitation,
    CapturedMessage,
    CapturedThread,
    Provider,
    ProviderContext,
    ThreadStub,
)

from .render import render_chatgpt_markdown


class ChatGPTProvider(Provider):
    provider_id = "chatgpt"
    display_name = "ChatGPT"
    capabilities = "http+dom"
    cookie_domains = [".chatgpt.com", "chatgpt.com", ".openai.com"]

    # --- helpers ---------------------------------------------------------

    def _api(self, ctx: ProviderContext) -> ChatGPTHTTPAPI:
        api = ctx.options.get("_chatgpt_api")
        if api is None:
            api = ChatGPTHTTPAPI(ctx.cookies_by_domain)
            api.authenticate()
            ctx.options["_chatgpt_api"] = api
        return api

    # --- contract --------------------------------------------------------

    def probe_login(self, ctx: ProviderContext) -> AccountContext | None:
        api = ChatGPTHTTPAPI(ctx.cookies_by_domain)
        info = api.authenticate()
        if not info.get("authenticated"):
            return None
        ctx.options["_chatgpt_api"] = api
        label = info.get("email") or info.get("name") or "unknown"
        return AccountContext(
            account_key=compute_account_key(self.provider_id, label),
            account_label=label,
            raw_identity=info,
        )

    def inventory(
        self,
        ctx: ProviderContext,
        *,
        since: float | str | None = None,
        limit: int | None = None,
    ) -> Iterator[ThreadStub]:
        api = self._api(ctx)
        max_pages = ctx.options.get("max_pages", 100)
        items = api.all_conversations(max_pages=max_pages)
        # all_conversations returns newest-first by update_time per the API
        # ordering. Stop early once we cross the previous cursor.
        since_f = _coerce_epoch(since)
        emitted = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            cid = item.get("id")
            if not isinstance(cid, str) or not cid:
                continue
            updated = item.get("update_time")
            updated_f = _coerce_epoch(updated)
            if updated is not None and updated_f is None:
                continue
            if since_f is not None and updated_f is not None and updated_f <= since_f:
                break
            yield ThreadStub(
                thread_key=self.thread_key_for(cid),
                provider_thread_id=cid,
                canonical_url=f"https://chatgpt.com/c/{cid}",
                title=item.get("title") or "",
                updated_at=updated,
                extra={"create_time": item.get("create_time")},
            )
            emitted += 1
            if limit is not None and emitted >= limit:
                return

    def capture_thread(
        self, ctx: ProviderContext, stub: ThreadStub,
    ) -> CapturedThread:
        api = self._api(ctx)
        detail = api.conversation_detail(stub.provider_thread_id)
        if detail is None:
            raise RuntimeError(f"chatgpt: conversation detail failed for {stub.provider_thread_id}")

        raw_messages = ChatGPTHTTPAPI.extract_messages_from_mapping(detail)
        raw_artifacts = ChatGPTHTTPAPI.extract_artifacts_from_mapping(detail)

        messages = [
            CapturedMessage(
                role=m["role"],
                content=m.get("content", ""),
                ordinal=m["ordinal"],
                provider_message_id=m.get("provider_message_id"),
                content_type=m.get("content_type"),
                rich_parts=m.get("rich_parts", []),
                artifact_refs=m.get("artifact_refs", []),
                metadata={
                    "model": m.get("model", ""),
                    "finish_details": m.get("finish_details", {}),
                    "created_at": m.get("created_at"),
                },
            )
            for m in raw_messages
        ]

        artifacts = [
            CapturedArtifact(
                artifact_type=a["artifact_type"],
                label=a.get("label", ""),
                provider_artifact_id=a.get("provider_artifact_id"),
                source_url=_artifact_source_url(a),
                parent_message_id=a.get("parent_message_id"),
                byte_length=a.get("size_bytes"),
                rich_part=a.get("rich_part"),
                storage_kind="metadata",
            )
            for a in raw_artifacts
        ]

        citations = [
            CapturedCitation(
                label=c.get("label") or c.get("title"),
                url=c.get("url"),
                source_json=c,
            )
            for c in _extract_citations_from_mapping(detail)
        ]

        title = detail.get("title") or stub.title or ""
        canonical_url = stub.canonical_url

        normalized = {
            "title": title,
            "provider_thread_id": stub.provider_thread_id,
            "canonical_url": canonical_url,
            "messages": [
                {
                    "role": m.role,
                    "content": m.content,
                    "ordinal": m.ordinal,
                    "provider_message_id": m.provider_message_id,
                    "content_type": m.content_type,
                    "rich_parts": m.rich_parts,
                    "artifact_refs": m.artifact_refs,
                    "metadata": m.metadata,
                }
                for m in messages
            ],
            "artifacts": [
                {
                    "artifact_type": a.artifact_type,
                    "label": a.label,
                    "provider_artifact_id": a.provider_artifact_id,
                    "source_url": a.source_url,
                    "parent_message_id": a.parent_message_id,
                    "byte_length": a.byte_length,
                }
                for a in artifacts
            ],
            "raw_mapping_keys": list((detail.get("mapping") or {}).keys()),
            "create_time": detail.get("create_time"),
            "update_time": detail.get("update_time"),
            "model_slug": detail.get("default_model_slug"),
        }

        rendered = render_chatgpt_markdown(normalized)

        capture_notes: dict[str, Any] = {"stub_updated_at": stub.updated_at}
        completion_state = "complete"
        if artifacts:
            completion_state = "partial"
            capture_notes["artifact_bytes"] = (
                "HTTP mapping exposed artifact metadata, but this provider path "
                "does not download UI-only artifact bytes."
            )
        if not citations:
            capture_notes["citations"] = (
                "No structured citations were present in the backend mapping; "
                "visible Sources controls still require DOM verification."
            )
            if completion_state == "complete":
                completion_state = "partial"

        return CapturedThread(
            stub=stub,
            messages=messages,
            artifacts=artifacts,
            citations=citations,
            normalized_json=normalized,
            rendered_markdown=rendered,
            completion_state=completion_state,
            capture_notes=capture_notes,
        )

    def capture_artifacts(self, ctx: ProviderContext, thread: CapturedThread):
        # HTTP path doesn't download bytes; DOM path is intentionally not
        # plumbed yet (issue #8: parity migration). Re-yielding metadata is
        # a no-op because run_sync stored it from capture_thread already.
        return ()


def _coerce_epoch(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _artifact_source_url(a: dict[str, Any]) -> str | None:
    rp = a.get("rich_part") or {}
    return rp.get("source_url") or rp.get("url") or rp.get("download_url")


def _extract_citations_from_mapping(detail: dict[str, Any]) -> list[dict[str, Any]]:
    """Best-effort citation extraction from ChatGPT backend metadata.

    ChatGPT does not consistently expose the UI Sources panel in the mapping
    response. When URL-bearing citation/source entries are present, preserve
    them; when absent, the provider marks the capture partial instead of
    pretending the HTTP surface proved citation completeness.
    """
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    mapping = detail.get("mapping") or {}
    for node in mapping.values():
        msg = (node or {}).get("message") or {}
        metadata = msg.get("metadata") or {}
        for item in _walk_citation_candidates(metadata):
            url = item.get("url")
            if not url:
                continue
            title = item.get("title") or item.get("name") or item.get("label")
            key = (url, title or "")
            if key in seen:
                continue
            seen.add(key)
            out.append({"url": url, "title": title, "source": item})
    return out


def _walk_citation_candidates(value: Any):
    if isinstance(value, dict):
        url = value.get("url")
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            yield value
        for key, child in value.items():
            if key.lower() in {"citations", "sources", "source", "references"}:
                yield from _walk_citation_candidates(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_citation_candidates(child)
