import sqlite3
import sys
from pathlib import Path


SKILL_ROOT = (
    Path(__file__).resolve().parents[3]
    / "domain-skills"
    / "ai-chat-archive"
)
sys.path.insert(0, str(SKILL_ROOT))

from lib import archive_db, schema, sync_runner  # noqa: E402
from lib.provider_base import (  # noqa: E402
    AccountContext,
    CapturedArtifact,
    CapturedMessage,
    CapturedThread,
    Provider,
    ProviderContext,
    ThreadStub,
)
from providers.claude.provider import ClaudeProvider  # noqa: E402
from providers.chatgpt.provider import ChatGPTProvider  # noqa: E402
from providers.chatgpt.provider import _coerce_epoch as chatgpt_coerce_epoch  # noqa: E402
from providers.gemini.provider import GeminiProvider  # noqa: E402
from providers.gemini.provider import _coerce_float as gemini_coerce_float  # noqa: E402
from providers.gemini.http import GeminiHTTPAPI  # noqa: E402
from providers.grok.provider import GrokProvider  # noqa: E402
from providers.perplexity.provider import PerplexityProvider  # noqa: E402


class BlobProvider(Provider):
    provider_id = "blobtest"
    display_name = "Blob Test"
    cookie_domains = ["blob.test"]

    def probe_login(self, ctx: ProviderContext):
        return AccountContext(account_key="acct", account_label="acct@example.test")

    def inventory(self, ctx: ProviderContext, *, since=None, limit=None):
        yield ThreadStub(
            thread_key="thread-1",
            provider_thread_id="thread-1",
            canonical_url="https://blob.test/c/thread-1",
            title="Thread With Artifact",
            updated_at=1,
        )

    def capture_thread(self, ctx: ProviderContext, stub: ThreadStub):
        return CapturedThread(
            stub=stub,
            messages=[
                CapturedMessage(
                    role="assistant",
                    content="Download attached.",
                    ordinal=1,
                    provider_message_id="m1",
                )
            ],
            artifacts=[
                CapturedArtifact(
                    artifact_type="document",
                    label="report.txt",
                    provider_artifact_id="artifact-1",
                    storage_kind="metadata",
                )
            ],
            citations=[],
            normalized_json={"title": stub.title},
            rendered_markdown="# Thread With Artifact\n\nDownload attached.\n",
            completion_state="complete",
            capture_notes={"stub_updated_at": stub.updated_at},
        )

    def capture_artifacts(self, ctx: ProviderContext, thread: CapturedThread):
        yield CapturedArtifact(
            artifact_type="document",
            label="report.txt",
            provider_artifact_id="artifact-1",
            storage_kind="inline_blob",
            bytes=b"report bytes",
        )


class MalformedBlobSizeProvider(BlobProvider):
    provider_id = "malformedblobsize"

    def capture_artifacts(self, ctx: ProviderContext, thread: CapturedThread):
        yield CapturedArtifact(
            artifact_type="document",
            label="report.txt",
            provider_artifact_id="artifact-1",
            storage_kind="inline_blob",
            byte_length=True,
            bytes=b"report bytes",
        )


def test_artifact_blob_has_parent_artifact_row(tmp_path):
    db_path = tmp_path / "archive.sqlite3"
    schema.init_db(db_path).close()
    db = archive_db.connect(db_path)

    result = sync_runner.run_sync(
        BlobProvider(),
        db=db,
        cookies_by_domain={"blob.test": {"session": "redacted"}},
    )

    assert result.errors == []
    assert result.captured == 1
    assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert db.execute("SELECT COUNT(*) FROM artifact_blobs").fetchone()[0] == 1
    assert db.execute(
        """
        SELECT COUNT(*)
        FROM artifact_blobs b
        JOIN artifacts a ON a.artifact_key = b.artifact_key
        WHERE a.storage_kind = 'inline_blob'
        """
    ).fetchone()[0] == 1


def test_artifact_blob_uses_downloaded_size_when_metadata_size_is_malformed(tmp_path):
    db_path = tmp_path / "archive.sqlite3"
    schema.init_db(db_path).close()
    db = archive_db.connect(db_path)

    result = sync_runner.run_sync(
        MalformedBlobSizeProvider(),
        db=db,
        cookies_by_domain={"blob.test": {"session": "redacted"}},
    )

    assert result.errors == []
    row = db.execute(
        """
        SELECT byte_length
        FROM artifacts
        WHERE storage_kind = 'inline_blob'
        """
    ).fetchone()
    assert row["byte_length"] == len(b"report bytes")


def test_artifact_upsert_preserves_metadata_when_incoming_strings_are_empty(tmp_path):
    db_path = tmp_path / "archive.sqlite3"
    schema.init_db(db_path).close()
    db = archive_db.connect(db_path)
    archive_db.ensure_provider(db, "blobtest", "Blob Test")
    archive_db.ensure_account(db, "blobtest", "acct", "acct@example.test")
    archive_db.upsert_thread(db, {
        "thread_key": "thread-1",
        "provider_id": "blobtest",
        "account_key": "acct",
        "provider_thread_id": "thread-1",
        "canonical_url": "https://blob.test/c/thread-1",
        "title": "Thread With Artifact",
        "status": "complete",
        "content_hash": "thread-hash",
    })

    artifact = {
        "thread_key": "thread-1",
        "provider_artifact_id": "artifact-1",
        "label": "report.txt",
        "artifact_type": "document",
        "source_url": "https://example.test/report.txt",
        "capture_id": "capture-1",
        "content_hash": "hash-1",
    }
    artifact_key = archive_db.upsert_artifact(db, artifact)

    archive_db.upsert_artifact(db, {
        **artifact,
        "label": "",
        "source_url": "",
        "capture_id": "capture-2",
    })

    row = db.execute(
        "SELECT label, source_url, last_seen_capture_id FROM artifacts WHERE artifact_key = ?",
        (artifact_key,),
    ).fetchone()
    assert dict(row) == {
        "label": "report.txt",
        "source_url": "https://example.test/report.txt",
        "last_seen_capture_id": "capture-2",
    }


def test_run_sync_honors_zero_limit_before_inventory_capture(tmp_path):
    class LimitIgnoringProvider(BlobProvider):
        provider_id = "limitignore"

        def inventory(self, ctx: ProviderContext, *, since=None, limit=None):
            yield ThreadStub(
                thread_key="thread-1",
                provider_thread_id="thread-1",
                canonical_url="https://blob.test/c/thread-1",
                title="Should Not Capture",
                updated_at=1,
            )

        def capture_thread(self, ctx: ProviderContext, stub: ThreadStub):
            raise AssertionError("limit=0 must prevent capture")

    db_path = tmp_path / "archive.sqlite3"
    schema.init_db(db_path).close()
    db = archive_db.connect(db_path)

    result = sync_runner.run_sync(
        LimitIgnoringProvider(),
        db=db,
        cookies_by_domain={"blob.test": {"session": "redacted"}},
        limit=0,
    )

    assert result.errors == []
    assert result.listed == 0
    assert result.captured == 0
    assert db.execute("SELECT COUNT(*) FROM threads").fetchone()[0] == 0
    assert db.execute("SELECT status FROM runs").fetchone()[0] == "complete"


def test_stub_unchanged_rejects_malformed_delta_summary_shape():
    stub = ThreadStub(
        thread_key="thread-1",
        provider_thread_id="thread-1",
        canonical_url="https://example.test/thread-1",
        title="Thread",
        updated_at=123,
    )

    assert sync_runner._stub_unchanged(
        stub,
        {"delta_summary_json": '["not", "an", "object"]'},
    ) is False


def test_max_cursor_compares_numeric_values_numerically():
    assert sync_runner._max_cursor(9, 10) == 10
    assert sync_runner._max_cursor("9", "10") == "10"
    assert sync_runner._max_cursor("2026-05-02", "2026-05-10") == "2026-05-10"


def test_archive_timestamp_coercers_reject_booleans():
    assert chatgpt_coerce_epoch(True) is None
    assert chatgpt_coerce_epoch(False) is None
    assert gemini_coerce_float(True) is None
    assert gemini_coerce_float(False) is None


class FakeChatGPTAPI:
    def __init__(self, detail=None, conversations=None):
        self.detail = detail
        self.conversations = conversations or []

    def all_conversations(self, max_pages=100):
        return self.conversations

    def conversation_detail(self, conversation_id: str):
        return self.detail


def test_chatgpt_inventory_skips_malformed_conversation_rows():
    db = sqlite3.connect(":memory:")
    provider = ChatGPTProvider()
    ctx = ProviderContext(
        provider_id="chatgpt",
        cookies_by_domain={},
        db=db,
        options={"_chatgpt_api": FakeChatGPTAPI(conversations=[
            "not a row",
            {"title": "Missing id", "update_time": 2},
            {"id": "", "title": "Blank id", "update_time": 2},
            {"id": "bad-time", "title": "Bad time", "update_time": "not-float"},
            {"id": "ok", "title": "Valid", "update_time": 3, "create_time": 1},
        ])},
    )

    stubs = list(provider.inventory(ctx, since=1))

    assert len(stubs) == 1
    assert stubs[0].provider_thread_id == "ok"
    assert stubs[0].thread_key == "chatgpt:ok"
    assert stubs[0].canonical_url == "https://chatgpt.com/c/ok"
    assert stubs[0].title == "Valid"


def test_provider_inventories_skip_malformed_remote_rows():
    db = sqlite3.connect(":memory:")

    class ClaudeAPI:
        def all_conversations(self):
            return [
                "not a row",
                {"name": "Missing uuid", "updated_at": "2026-05-01T00:00:00Z"},
                {"uuid": "", "name": "Blank uuid", "updated_at": "2026-05-01T00:00:00Z"},
                {"uuid": "claude-ok", "name": "Claude valid", "updated_at": "2026-05-02T00:00:00Z"},
            ]

    class PerplexityAPI:
        def all_threads(self):
            return [
                "not a row",
                {"title": "Missing id", "last_query_datetime": "2026-05-01T00:00:00Z"},
                {"uuid": "", "title": "Blank id", "last_query_datetime": "2026-05-01T00:00:00Z"},
                {"uuid": "pplx-ok", "title": "Perplexity valid", "last_query_datetime": "2026-05-02T00:00:00Z"},
            ]

    class GeminiAPI:
        def all_chats(self, page_size=50):
            return [
                "not a row",
                {"title": "Missing id", "updated_unix": 2},
                {"chat_id": "", "title": "Blank id", "updated_unix": 2},
                {"chat_id": "bad-time", "title": "Bad time", "updated_unix": "not-float"},
                {"chat_id": "gemini-ok", "title": "Gemini valid", "updated_unix": 3},
            ]

    class GrokAPI:
        def all_conversations(self):
            return [
                "not a row",
                {"title": "Missing id", "modifyTime": "2026-05-01T00:00:00Z"},
                {"conversationId": "", "title": "Blank id", "modifyTime": "2026-05-01T00:00:00Z"},
                {"conversationId": "grok-ok", "title": "Grok valid", "modifyTime": "2026-05-02T00:00:00Z"},
            ]

    cases = [
        (ClaudeProvider(), "_claude_api", ClaudeAPI(), "claude-ok"),
        (PerplexityProvider(), "_pplx_api", PerplexityAPI(), "pplx-ok"),
        (GeminiProvider(), "_gemini_api", GeminiAPI(), "gemini-ok"),
        (GrokProvider(), "_grok_api", GrokAPI(), "grok-ok"),
    ]

    for provider, option_key, api, expected_id in cases:
        ctx = ProviderContext(
            provider_id=provider.provider_id,
            cookies_by_domain={},
            db=db,
            options={option_key: api},
        )
        stubs = list(provider.inventory(ctx, since=1))
        assert [stub.provider_thread_id for stub in stubs] == [expected_id]


def test_perplexity_inventory_sorts_stream_created_at_fallback_before_since_break():
    db = sqlite3.connect(":memory:")

    class PerplexityAPI:
        def all_threads(self):
            return [
                {"uuid": "old", "title": "Old", "stream_created_at": "2026-05-01T00:00:00Z"},
                {"uuid": "new", "title": "New", "stream_created_at": "2026-05-03T00:00:00Z"},
            ]

    ctx = ProviderContext(
        provider_id="perplexity",
        cookies_by_domain={},
        db=db,
        options={"_pplx_api": PerplexityAPI()},
    )

    stubs = list(PerplexityProvider().inventory(ctx, since="2026-05-02T00:00:00Z"))

    assert [stub.provider_thread_id for stub in stubs] == ["new"]
    assert stubs[0].updated_at == "2026-05-03T00:00:00Z"


def test_gemini_inventory_drops_malformed_response_ids():
    db = sqlite3.connect(":memory:")
    api = GeminiHTTPAPI({})
    api._rpc = lambda *_args, **_kwargs: [
        None,
        None,
        [
            [
                "chat-ok",
                "Title",
                None,
                None,
                None,
                [10],
                [["chat-ok", ["bad-response-id"]]],
            ]
        ],
    ]
    ctx = ProviderContext(
        provider_id="gemini",
        cookies_by_domain={},
        db=db,
        options={"_gemini_api": api},
    )

    stubs = list(GeminiProvider().inventory(ctx))

    assert len(stubs) == 1
    assert stubs[0].canonical_url == "https://gemini.google.com/app/chat-ok"
    assert stubs[0].extra["response_id"] is None


def test_chatgpt_http_artifact_metadata_is_partial_not_complete():
    detail = {
        "title": "Artifact Thread",
        "mapping": {
            "a1": {
                "message": {
                    "id": "a1",
                    "author": {"role": "assistant"},
                    "create_time": 1,
                    "content": {
                        "content_type": "text",
                        "parts": [
                            "Here is an image.",
                            {
                                "content_type": "image_asset_pointer",
                                "asset_pointer": "file-service://image-1",
                                "width": 512,
                                "height": 512,
                                "metadata": {"dalle": {}},
                                "size_bytes": 1024,
                            },
                        ],
                    },
                    "metadata": {},
                }
            }
        },
    }
    db = sqlite3.connect(":memory:")
    provider = ChatGPTProvider()
    ctx = ProviderContext(
        provider_id="chatgpt",
        cookies_by_domain={},
        db=db,
        options={"_chatgpt_api": FakeChatGPTAPI(detail)},
    )

    captured = provider.capture_thread(
        ctx,
        ThreadStub(
            thread_key="thread-1",
            provider_thread_id="thread-1",
            canonical_url="https://chatgpt.com/c/thread-1",
            title="Artifact Thread",
        ),
    )

    assert captured.artifacts
    assert captured.completion_state == "partial"
    assert "artifact_bytes" in captured.capture_notes
