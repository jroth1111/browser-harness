"""Generic sync driver for any Provider.

Walks one account's threads through the canonical lifecycle and writes the
results into the archive. All persistence goes through ``archive_db`` so
schema changes only happen in one place.

Boundaries:
  * The runner OWNS sqlite writes, run/capture id generation, CDC events,
    and sync-state cursor updates.
  * The provider OWNS the provider_id-specific transport, normalization,
    and rendering. It must not write to sqlite directly.
  * The harvest layer (cookie_extract + harvest script) OWNS cookie jars and
    decides which jar to hand to the runner. The runner trusts the supplied
    cookies and only checks identity via ``Provider.probe_login``.
"""
from __future__ import annotations

import json
import sqlite3
import time
import traceback
from dataclasses import dataclass, field
from typing import Any

from . import archive_db
from .provider_base import (
    AccountContext,
    BrowserHarness,
    CapturedThread,
    Provider,
    ProviderContext,
    ThreadStub,
)


@dataclass
class SyncResult:
    provider_id: str
    account_key: str | None
    account_label: str | None
    listed: int = 0
    captured: int = 0
    skipped_unchanged: int = 0
    failed: int = 0
    errors: list[dict[str, Any]] = field(default_factory=list)
    run_id: str | None = None
    auth_status: str = "unknown"  # 'ok' | 'failed' | 'unknown'

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "account_key": self.account_key,
            "account_label": self.account_label,
            "listed": self.listed,
            "captured": self.captured,
            "skipped_unchanged": self.skipped_unchanged,
            "failed": self.failed,
            "errors": self.errors,
            "run_id": self.run_id,
            "auth_status": self.auth_status,
        }


def run_sync(
    provider: Provider,
    *,
    db: sqlite3.Connection,
    cookies_by_domain: dict[str, dict[str, str]],
    harness: BrowserHarness | None = None,
    since: float | str | None = None,
    limit: int | None = None,
    options: dict[str, Any] | None = None,
    fresh: bool = False,
) -> SyncResult:
    """Drive one provider through probe_login → inventory → capture.

    ``since`` overrides the stored cursor; pass ``None`` to use whatever the
    provider last stored. ``fresh=True`` forces re-capture of every listed
    thread even if its content hash matches the archived copy.
    """
    archive_db.ensure_provider(db, provider.provider_id, provider.display_name)

    ctx = ProviderContext(
        provider_id=provider.provider_id,
        cookies_by_domain=cookies_by_domain,
        db=db,
        harness=harness,
        options=options or {},
    )

    result = SyncResult(
        provider_id=provider.provider_id,
        account_key=None,
        account_label=None,
    )

    # Step 1: probe login.
    try:
        account = provider.probe_login(ctx)
    except Exception as e:
        result.auth_status = "failed"
        result.errors.append({"stage": "probe_login", "error": _err(e)})
        return result

    if account is None:
        result.auth_status = "failed"
        return result

    ctx.account = account
    result.account_key = account.account_key
    result.account_label = account.account_label
    result.auth_status = "ok"

    archive_db.ensure_account(
        db, provider.provider_id, account.account_key, account.account_label,
    )

    # Step 2: open a run and resolve cursor.
    run_id = archive_db.generate_run_id()
    ctx.run_id = run_id
    result.run_id = run_id
    archive_db.new_run(db, run_id, {
        "provider_id": provider.provider_id,
        "account_key": account.account_key,
        "options": ctx.options,
    })

    cursor_name = provider.cursor_name()
    if since is None and not fresh:
        existing = archive_db.get_sync_state(
            db, provider.provider_id, account.account_key, cursor_name,
        )
        if existing:
            since = existing.get("cursor_value")

    # Step 3: walk the inventory.
    new_cursor: float | str | None = None
    try:
        for stub in provider.inventory(ctx, since=since, limit=limit):
            result.listed += 1
            new_cursor = _max_cursor(new_cursor, stub.updated_at)
            try:
                _capture_one(provider, ctx, stub, result, fresh=fresh)
            except Exception as e:
                result.failed += 1
                result.errors.append({
                    "stage": "capture_thread",
                    "thread_key": stub.thread_key,
                    "error": _err(e),
                })
            if limit is not None and result.captured >= limit:
                break
    except Exception as e:
        result.errors.append({"stage": "inventory", "error": _err(e)})

    # Step 4: persist cursor and finalize run.
    if new_cursor is not None:
        archive_db.set_sync_state(
            db, provider.provider_id, account.account_key, cursor_name,
            cursor_value=str(new_cursor),
            state_json={"last_run": run_id},
        )

    archive_db.finish_run(
        db, run_id,
        status="complete" if not result.errors else "partial",
        summary=result.as_dict(),
    )
    return result


def _capture_one(
    provider: Provider,
    ctx: ProviderContext,
    stub: ThreadStub,
    result: SyncResult,
    *,
    fresh: bool,
) -> None:
    """Capture one thread, deduping against the archive when possible."""
    db = ctx.db

    # Fast path: if we have an archived copy and the provider's stub looks
    # unchanged (same updated_at as cursor), skip the full fetch unless
    # fresh=True. Provider may also override by setting stub.extra['force'].
    last = archive_db.thread_last_capture(db, stub.thread_key)
    force = bool(stub.extra.get("force"))
    if last and not fresh and not force and _stub_unchanged(stub, last):
        result.skipped_unchanged += 1
        return

    captured = provider.capture_thread(ctx, stub)
    capture_id = archive_db.generate_capture_id()

    # Hash the rendered markdown so re-captures with identical content are
    # idempotent at the capture-row level.
    content_hash = archive_db.compute_content_hash(captured.rendered_markdown)
    if last and last.get("content_hash") == content_hash and not fresh:
        result.skipped_unchanged += 1
        return

    # Store thread row.
    archive_db.upsert_thread(db, {
        "thread_key": stub.thread_key,
        "provider_id": provider.provider_id,
        "account_key": ctx.account.account_key,
        "provider_thread_id": stub.provider_thread_id,
        "canonical_url": stub.canonical_url,
        "title": stub.title or captured.normalized_json.get("title", ""),
        "status": captured.completion_state,
        "content_hash": content_hash,
        "artifact_count": len(captured.artifacts),
        "capture_id": capture_id,
    }, run_id=ctx.run_id)

    # Store capture row.
    archive_db.insert_capture(db, {
        "capture_id": capture_id,
        "run_id": ctx.run_id,
        "thread_key": stub.thread_key,
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_context": json.dumps({
            "provider_id": provider.provider_id,
            "capabilities": provider.capabilities,
            "account_key": ctx.account.account_key,
        }),
        "completion_state": captured.completion_state,
        "normalized_json": json.dumps(captured.normalized_json, default=str),
        "rendered_markdown": captured.rendered_markdown,
        "content_hash": content_hash,
        "previous_capture_id": last.get("capture_id") if last else None,
        "delta_summary_json": json.dumps(captured.capture_notes, default=str)
            if captured.capture_notes else None,
    })

    # Messages.
    for msg in captured.messages:
        archive_db.upsert_message(
            db,
            {
                "thread_key": stub.thread_key,
                "provider_message_id": msg.provider_message_id,
                "role": msg.role,
                "ordinal": msg.ordinal,
                "current_content": msg.content,
                "capture_id": capture_id,
            },
            run_id=ctx.run_id,
            provider_id=provider.provider_id,
            account_key=ctx.account.account_key,
        )

    # Artifacts metadata (bytes come later via capture_artifacts).
    for art in captured.artifacts:
        artifact_key = archive_db.upsert_artifact(
            db,
            {
                "thread_key": stub.thread_key,
                "provider_artifact_id": art.provider_artifact_id,
                "label": art.label,
                "artifact_type": art.artifact_type,
                "source_url": art.source_url,
                "mime_type": art.mime_type,
                "byte_length": art.byte_length,
                "content_hash": art.content_hash,
                "storage_kind": art.storage_kind,
                "capture_id": capture_id,
            },
            run_id=ctx.run_id,
            provider_id=provider.provider_id,
            account_key=ctx.account.account_key,
        )
        art.provider_artifact_id = art.provider_artifact_id or artifact_key

    # Citations.
    for cit in captured.citations:
        archive_db.upsert_citation(db, {
            "thread_key": stub.thread_key,
            "capture_id": capture_id,
            "label": cit.label,
            "url": cit.url,
            "source_json": cit.source_json,
        })

    # Step 5: artifact bytes (if the provider supports it).
    try:
        for art in provider.capture_artifacts(ctx, captured):
            if art.bytes is None:
                continue
            ah = art.content_hash or archive_db.compute_content_hash(art.bytes)
            artifact_key = archive_db.compute_artifact_key(
                stub.thread_key,
                art.provider_artifact_id or art.source_url or art.label,
                ah,
            )
            archive_db.store_artifact_blob(db, artifact_key, ah, art.bytes)
    except Exception as e:
        result.errors.append({
            "stage": "capture_artifacts",
            "thread_key": stub.thread_key,
            "error": _err(e),
        })

    result.captured += 1


def _stub_unchanged(stub: ThreadStub, last_capture: dict[str, Any]) -> bool:
    """Heuristic: if the stub doesn't carry an updated_at, we cannot dedupe
    safely without fetching, so always return False. If it does, compare
    against the previous capture's stored updated_at hint in
    delta_summary_json."""
    if stub.updated_at is None:
        return False
    prev = last_capture.get("delta_summary_json")
    if not prev:
        return False
    try:
        data = json.loads(prev)
    except Exception:
        return False
    prev_updated = data.get("stub_updated_at")
    return prev_updated is not None and str(prev_updated) == str(stub.updated_at)


def _max_cursor(a: Any, b: Any) -> Any:
    if a is None:
        return b
    if b is None:
        return a
    try:
        return a if str(a) >= str(b) else b
    except Exception:
        return a


def _err(e: Exception) -> dict[str, str]:
    return {
        "type": type(e).__name__,
        "message": str(e)[:500],
        "trace": "".join(traceback.format_exception_only(type(e), e))[:500],
    }
