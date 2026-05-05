"""Perplexity provider — partial HTTP path.

State as of 2026-05:
* ``probe_login`` works against ``/api/auth/session`` (NextAuth).
* ``capture_thread`` works against ``GET /rest/thread/{uuid}``.
* ``inventory`` does NOT work — Perplexity's library-list endpoint is not
  exposed under the obvious /rest paths and likely requires the live page
  bundle's JS to discover. Until DOM inventory is added, sync runs return
  zero captures even with a valid cookie jar. The cookie jar is still
  stored so a later DOM-aware run can use it.

Set ``capture_thread`` works for individual UUIDs supplied externally
(e.g. by a browser-harness inventory pass). The ``Provider`` contract is
indifferent to where stubs come from: the runner accepts any iterator of
ThreadStubs from inventory, including future DOM-extracted ones.
"""
from __future__ import annotations

from typing import Any, Iterator

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

from .http import PerplexityHTTPAPI
from .render import render_perplexity_markdown


class PerplexityProvider(Provider):
    provider_id = "perplexity"
    display_name = "Perplexity"
    capabilities = "http"
    cookie_domains = [".perplexity.ai", "perplexity.ai", "www.perplexity.ai"]

    def _api(self, ctx: ProviderContext) -> PerplexityHTTPAPI:
        api = ctx.options.get("_pplx_api")
        if api is None:
            api = PerplexityHTTPAPI(ctx.cookies_by_domain)
            api.authenticate()
            ctx.options["_pplx_api"] = api
        return api

    def probe_login(self, ctx: ProviderContext) -> AccountContext | None:
        api = PerplexityHTTPAPI(ctx.cookies_by_domain)
        info = api.authenticate()
        if not info.get("authenticated"):
            return None
        ctx.options["_pplx_api"] = api
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
        threads = api.all_threads()
        threads.sort(
            key=lambda t: t.get("last_query_datetime") or t.get("updated_datetime") or "",
            reverse=True,
        )
        emitted = 0
        for t in threads:
            updated = (
                t.get("last_query_datetime")
                or t.get("updated_datetime")
                or t.get("stream_created_at")
            )
            if since is not None and updated is not None and str(updated) <= str(since):
                break
            tid = t.get("uuid") or t.get("backend_uuid") or t.get("id") or t.get("slug")
            if not tid:
                continue
            slug = t.get("slug") or tid
            url = t.get("url") or f"https://www.perplexity.ai/search/{slug}"
            yield ThreadStub(
                thread_key=self.thread_key_for(tid),
                provider_thread_id=tid,
                canonical_url=url,
                title=t.get("title") or t.get("query_str") or t.get("display_name") or "",
                updated_at=updated,
                extra={
                    "raw_stub": t,
                    "thread_number": t.get("thread_number"),
                    "mode": t.get("mode"),
                    "display_model": t.get("display_model"),
                    "query_count": t.get("query_count"),
                },
            )
            emitted += 1
            if limit is not None and emitted >= limit:
                return

    def capture_thread(
        self, ctx: ProviderContext, stub: ThreadStub,
    ) -> CapturedThread:
        api = self._api(ctx)
        detail = api.thread_detail(stub.provider_thread_id)
        if detail is None:
            # Surface drift: keep the stub recorded as a partial capture so
            # the row in `threads` updates updated_at, but don't fabricate
            # message content.
            normalized = {
                "title": stub.title or "",
                "provider_thread_id": stub.provider_thread_id,
                "canonical_url": stub.canonical_url,
                "messages": [],
                "citations": [],
            }
            return CapturedThread(
                stub=stub,
                messages=[],
                artifacts=[],
                citations=[],
                normalized_json=normalized,
                rendered_markdown=render_perplexity_markdown(normalized),
                completion_state="partial",
                capture_notes={
                    "stub_updated_at": stub.updated_at,
                    "warning": "thread_detail returned None; surface may have drifted",
                },
            )

        raw_messages = PerplexityHTTPAPI.extract_messages(detail)
        raw_citations = PerplexityHTTPAPI.extract_citations(detail)

        messages = [
            CapturedMessage(
                role=m["role"],
                content=m["content"],
                ordinal=m["ordinal"],
                provider_message_id=m["provider_message_id"],
                content_type=m["content_type"],
                rich_parts=m["rich_parts"],
                artifact_refs=m["artifact_refs"],
                metadata=m["metadata"],
            )
            for m in raw_messages
        ]
        citations = [
            CapturedCitation(label=c["label"], url=c["url"], source_json=c["source_json"])
            for c in raw_citations
        ]

        normalized = {
            "title": detail.get("display_name") or detail.get("title") or stub.title or "",
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
            "citations": [
                {"label": c.label, "url": c.url, "source_json": c.source_json}
                for c in citations
            ],
        }

        return CapturedThread(
            stub=stub,
            messages=messages,
            artifacts=[],
            citations=citations,
            normalized_json=normalized,
            rendered_markdown=render_perplexity_markdown(normalized),
            completion_state="complete",
            capture_notes={"stub_updated_at": stub.updated_at},
        )
