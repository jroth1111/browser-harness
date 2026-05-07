"""Grok provider against grok.com /rest/app-chat/* endpoints."""
from __future__ import annotations

from typing import Iterator

from lib.archive_db import compute_account_key
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

from .http import GrokHTTPAPI
from .render import render_grok_markdown


class GrokProvider(Provider):
    provider_id = "grok"
    display_name = "Grok"
    capabilities = "http"
    cookie_domains = [".grok.com", "grok.com"]

    def _api(self, ctx: ProviderContext) -> GrokHTTPAPI:
        api = ctx.options.get("_grok_api")
        if api is None:
            api = GrokHTTPAPI(ctx.cookies_by_domain)
            api.authenticate()
            ctx.options["_grok_api"] = api
        return api

    def probe_login(self, ctx: ProviderContext) -> AccountContext | None:
        api = GrokHTTPAPI(ctx.cookies_by_domain)
        info = api.authenticate()
        if not info.get("authenticated"):
            return None
        ctx.options["_grok_api"] = api
        # Grok carries no email/name. Use session_id as the disambiguator
        # so multiple Grok jars stay distinct.
        sid = info.get("session_id") or ""
        label = f"Grok user ({sid[:8]})" if sid else "Grok user"
        return AccountContext(
            account_key=compute_account_key(self.provider_id, sid or label),
            account_label=label,
            raw_identity=info,
        )

    def inventory(
        self, ctx: ProviderContext, *,
        since: float | str | None = None,
        limit: int | None = None,
    ) -> Iterator[ThreadStub]:
        api = self._api(ctx)
        items = api.all_conversations()
        items = [item for item in items if isinstance(item, dict)]
        items.sort(key=lambda x: x.get("modifyTime") or x.get("createTime") or "", reverse=True)
        emitted = 0
        for it in items:
            updated = it.get("modifyTime") or it.get("createTime")
            if since is not None and updated is not None and str(updated) <= str(since):
                break
            cid = it.get("conversationId")
            if not isinstance(cid, str) or not cid:
                continue
            yield ThreadStub(
                thread_key=self.thread_key_for(cid),
                provider_thread_id=cid,
                canonical_url=f"https://grok.com/c/{cid}",
                title=it.get("title") or "",
                updated_at=updated,
                extra={
                    "starred": it.get("starred"),
                    "create_time": it.get("createTime"),
                    "system_prompt_name": it.get("systemPromptName"),
                },
            )
            emitted += 1
            if limit is not None and emitted >= limit:
                return

    def capture_thread(self, ctx: ProviderContext, stub: ThreadStub) -> CapturedThread:
        api = self._api(ctx)
        detail = api.conversation_detail(stub.provider_thread_id)
        if detail is None:
            raise RuntimeError(f"grok: conversation detail failed for {stub.provider_thread_id}")

        raw_messages = GrokHTTPAPI.extract_messages(detail)
        raw_artifacts = GrokHTTPAPI.extract_artifacts(detail)
        raw_citations = GrokHTTPAPI.extract_citations(detail)

        messages = [
            CapturedMessage(
                role=m["role"], content=m["content"], ordinal=m["ordinal"],
                provider_message_id=m["provider_message_id"],
                content_type=m["content_type"],
                rich_parts=m["rich_parts"],
                artifact_refs=m["artifact_refs"],
                metadata=m["metadata"],
            )
            for m in raw_messages
        ]
        artifacts = [
            CapturedArtifact(
                artifact_type=a["artifact_type"], label=a.get("label", ""),
                provider_artifact_id=a.get("provider_artifact_id"),
                source_url=a.get("source_url"),
                parent_message_id=a.get("parent_message_id"),
                byte_length=a.get("byte_length"),
                rich_part=a.get("rich_part"),
                storage_kind="metadata",
            )
            for a in raw_artifacts
        ]
        citations = [
            CapturedCitation(label=c["label"], url=c["url"], source_json=c["source_json"])
            for c in raw_citations
        ]

        normalized = {
            "title": detail["meta"].get("title") or stub.title or "",
            "provider_thread_id": stub.provider_thread_id,
            "canonical_url": stub.canonical_url,
            "messages": [
                {
                    "role": m.role, "content": m.content, "ordinal": m.ordinal,
                    "provider_message_id": m.provider_message_id,
                    "content_type": m.content_type, "rich_parts": m.rich_parts,
                    "artifact_refs": m.artifact_refs, "metadata": m.metadata,
                } for m in messages
            ],
            "artifacts": [
                {"artifact_type": a.artifact_type, "label": a.label,
                 "provider_artifact_id": a.provider_artifact_id,
                 "source_url": a.source_url,
                 "parent_message_id": a.parent_message_id,
                 "byte_length": a.byte_length}
                for a in artifacts
            ],
            "citations": [
                {"label": c.label, "url": c.url, "source_json": c.source_json}
                for c in citations
            ],
        }

        return CapturedThread(
            stub=stub,
            messages=messages,
            artifacts=artifacts,
            citations=citations,
            normalized_json=normalized,
            rendered_markdown=render_grok_markdown(normalized),
            completion_state="complete",
            capture_notes={"stub_updated_at": stub.updated_at},
        )
