"""Gemini provider — HTTP path against the batchexecute RPC gateway.

Surface mapped via Camoufox network capture (2026-05): chat inventory and
thread detail both ride the ``/_/BardChatUi/data/batchexecute`` endpoint
with rpc ids ``MaZiqc`` (paginated chat list) and ``hNvQHb`` (full thread).
Bootstrap params (``SNlM0e``, ``cfb2h``, ``FdrFJe``) are scraped once from
``/app`` HTML; the rest of the run is plain HTTPS. See ``http.py`` for wire-
format details.

Authentication relies on the ``.google.com`` SAPISID + ``__Secure-1PSID``
cookie pair. The account label is derived from a SAPISID prefix so two
different signed-in Google accounts get distinct ``account_key`` values.
"""
from __future__ import annotations

from typing import Iterator

from lib.archive_db import compute_account_key
from lib.provider_base import (
    AccountContext,
    CapturedCitation,
    CapturedMessage,
    CapturedThread,
    Provider,
    ProviderContext,
    ThreadStub,
)

from .http import GeminiHTTPAPI
from .render import render_gemini_markdown


class GeminiProvider(Provider):
    provider_id = "gemini"
    display_name = "Gemini"
    capabilities = "http"
    cookie_domains = [
        ".google.com",
        "google.com",
        "gemini.google.com",
        ".gemini.google.com",
        "accounts.google.com",
        ".accounts.google.com",
    ]

    def _api(self, ctx: ProviderContext) -> GeminiHTTPAPI:
        api = ctx.options.get("_gemini_api")
        if api is None:
            api = GeminiHTTPAPI(ctx.cookies_by_domain)
            api.authenticate()
            ctx.options["_gemini_api"] = api
        return api

    def probe_login(self, ctx: ProviderContext) -> AccountContext | None:
        # Both the SAPISID + __Secure-1PSID cookie pair AND a successful
        # /app bootstrap are required: SAPISID alone often survives logout
        # in the Comet jar even though batchexecute calls then 401.
        google = ctx.cookies_by_domain.get(".google.com", {})
        if not (google.get("SAPISID") and google.get("__Secure-1PSID")):
            return None
        api = GeminiHTTPAPI(ctx.cookies_by_domain)
        info = api.authenticate()
        if not info.get("authenticated"):
            return None
        ctx.options["_gemini_api"] = api
        sapisid = google.get("SAPISID", "")
        label = f"Google user ({sapisid[:8]})" if sapisid else "Google user"
        return AccountContext(
            account_key=compute_account_key(self.provider_id, sapisid or label),
            account_label=label,
            raw_identity={"sapisid_prefix": sapisid[:8]},
        )

    def inventory(
        self, ctx: ProviderContext, *,
        since: float | str | None = None,
        limit: int | None = None,
    ) -> Iterator[ThreadStub]:
        api = self._api(ctx)
        chats = api.all_chats(page_size=50)
        chats = [chat for chat in chats if isinstance(chat, dict)]
        # Newest-first order: MaZiqc returns chats sorted by recency, but
        # paginate sweeps may interleave across pages, so re-sort by updated_unix.
        chats.sort(key=lambda c: _coerce_float(c.get("updated_unix")) or 0, reverse=True)
        emitted = 0
        since_f = _coerce_float(since)
        for c in chats:
            updated = c.get("updated_unix")
            updated_f = _coerce_float(updated)
            if updated is not None and updated_f is None:
                continue
            if since_f is not None and updated_f is not None and updated_f <= since_f:
                break
            chat_id = c.get("chat_id")
            if not isinstance(chat_id, str) or not chat_id:
                continue
            response_id = c.get("response_id")
            url_path = chat_id
            if response_id:
                url_path = f"{chat_id}/{response_id}"
            yield ThreadStub(
                thread_key=self.thread_key_for(chat_id),
                provider_thread_id=chat_id,
                canonical_url=f"https://gemini.google.com/app/{url_path}",
                title=c.get("title") or "",
                updated_at=updated,
                extra={"raw_stub": c.get("raw"), "response_id": response_id},
            )
            emitted += 1
            if limit is not None and emitted >= limit:
                return

    def capture_thread(self, ctx: ProviderContext, stub: ThreadStub) -> CapturedThread:
        api = self._api(ctx)
        detail = api.chat_detail(stub.provider_thread_id)
        if detail is None:
            normalized = {
                "title": stub.title or "",
                "provider_thread_id": stub.provider_thread_id,
                "canonical_url": stub.canonical_url,
                "messages": [],
                "citations": [],
            }
            return CapturedThread(
                stub=stub, messages=[], artifacts=[], citations=[],
                normalized_json=normalized,
                rendered_markdown=render_gemini_markdown(normalized),
                completion_state="partial",
                capture_notes={
                    "stub_updated_at": stub.updated_at,
                    "warning": "chat_detail returned None; surface may have drifted",
                },
            )

        raw_messages = GeminiHTTPAPI.extract_messages(detail)
        raw_citations = GeminiHTTPAPI.extract_citations(detail)

        messages = [
            CapturedMessage(
                role=m["role"], content=m["content"], ordinal=m["ordinal"],
                provider_message_id=m["provider_message_id"],
                content_type=m["content_type"],
                rich_parts=m["rich_parts"], artifact_refs=m["artifact_refs"],
                metadata=m["metadata"],
            )
            for m in raw_messages
        ]
        citations = [
            CapturedCitation(label=c["label"], url=c["url"], source_json=c["source_json"])
            for c in raw_citations
        ]

        normalized = {
            "title": stub.title or "",
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
            rendered_markdown=render_gemini_markdown(normalized),
            completion_state="complete",
            capture_notes={"stub_updated_at": stub.updated_at},
        )


def _coerce_float(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
