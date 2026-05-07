"""Claude provider — implements the canonical Provider contract for claude.ai."""
from __future__ import annotations

from typing import Any, Iterator

from lib.archive_db import compute_account_key
from lib.provider_base import (
    AccountContext,
    CapturedArtifact,
    CapturedMessage,
    CapturedThread,
    Provider,
    ProviderContext,
    ThreadStub,
)

from .http import ClaudeHTTPAPI
from .render import render_claude_markdown


class ClaudeProvider(Provider):
    provider_id = "claude"
    display_name = "Claude"
    capabilities = "http"
    cookie_domains = [".claude.ai", "claude.ai"]

    def _api(self, ctx: ProviderContext) -> ClaudeHTTPAPI:
        api = ctx.options.get("_claude_api")
        if api is None:
            api = ClaudeHTTPAPI(ctx.cookies_by_domain)
            api.authenticate()
            ctx.options["_claude_api"] = api
        return api

    def probe_login(self, ctx: ProviderContext) -> AccountContext | None:
        api = ClaudeHTTPAPI(ctx.cookies_by_domain)
        info = api.authenticate()
        if not info.get("authenticated"):
            return None
        ctx.options["_claude_api"] = api
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
        items = api.all_conversations()
        items = [item for item in items if isinstance(item, dict)]
        # Sort newest-first by updated_at so the cursor short-circuit works.
        items.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
        emitted = 0
        for item in items:
            updated = item.get("updated_at")
            if since is not None and updated is not None and str(updated) <= str(since):
                break
            uuid = item.get("uuid")
            if not isinstance(uuid, str) or not uuid:
                continue
            yield ThreadStub(
                thread_key=self.thread_key_for(uuid),
                provider_thread_id=uuid,
                canonical_url=f"https://claude.ai/chat/{uuid}",
                title=item.get("name") or "",
                updated_at=updated,
                extra={
                    "summary": item.get("summary"),
                    "model": item.get("model"),
                    "created_at": item.get("created_at"),
                },
            )
            emitted += 1
            if limit is not None and emitted >= limit:
                return

    def cursor_name(self) -> str:
        return "inventory_updated_at"

    def capture_thread(
        self, ctx: ProviderContext, stub: ThreadStub,
    ) -> CapturedThread:
        api = self._api(ctx)
        detail = api.conversation_detail(stub.provider_thread_id)
        if detail is None:
            raise RuntimeError(
                f"claude: conversation detail failed for {stub.provider_thread_id}",
            )

        raw_messages = ClaudeHTTPAPI.extract_messages(detail)
        raw_artifacts = ClaudeHTTPAPI.extract_artifacts(detail)

        messages = [
            CapturedMessage(
                role=m["role"],
                content=m.get("content", ""),
                ordinal=m["ordinal"],
                provider_message_id=m.get("provider_message_id"),
                content_type=m.get("content_type"),
                rich_parts=m.get("rich_parts", []),
                artifact_refs=m.get("artifact_refs", []),
                metadata=m.get("metadata", {}),
            )
            for m in raw_messages
        ]
        artifacts = [
            CapturedArtifact(
                artifact_type=a["artifact_type"],
                label=a.get("label", ""),
                provider_artifact_id=a.get("provider_artifact_id"),
                source_url=None,
                parent_message_id=a.get("parent_message_id"),
                mime_type=a.get("mime_type"),
                byte_length=a.get("byte_length"),
                rich_part=a.get("rich_part"),
                storage_kind="metadata",
            )
            for a in raw_artifacts
        ]

        normalized = {
            "title": detail.get("name") or stub.title or "",
            "provider_thread_id": stub.provider_thread_id,
            "canonical_url": stub.canonical_url,
            "summary": detail.get("summary") or "",
            "model": detail.get("model") or stub.extra.get("model"),
            "created_at": detail.get("created_at"),
            "updated_at": detail.get("updated_at"),
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
                    "parent_message_id": a.parent_message_id,
                    "mime_type": a.mime_type,
                    "byte_length": a.byte_length,
                }
                for a in artifacts
            ],
        }

        rendered = render_claude_markdown(normalized)

        return CapturedThread(
            stub=stub,
            messages=messages,
            artifacts=artifacts,
            citations=[],
            normalized_json=normalized,
            rendered_markdown=rendered,
            completion_state="complete",
            capture_notes={"stub_updated_at": stub.updated_at},
        )
