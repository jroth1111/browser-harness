from pathlib import Path


ROOT = Path(__file__).resolve().parent
SKILL_DIR = ROOT / "agent-workspace/domain-skills" / "ai-chat-archive"


def read(name: str) -> str:
    return (SKILL_DIR / name).read_text(encoding="utf-8")


def test_ai_chat_archive_skill_documents_required_providers_and_artifacts():
    overview = read("overview.md").lower()

    for provider in ["chatgpt", "claude", "gemini", "grok", "perplexity"]:
        assert provider in overview

    for artifact in ["deep research", "agent reports", "agent progress reports", "attachments", "citations"]:
        assert artifact in overview


def test_ai_chat_archive_skill_defines_sqlite_only_archive_layout():
    layout = read("archive-layout.md")
    decision = read("storage-decision.md").lower()
    overview = read("overview.md").lower()

    assert "sqlite as the only canonical archive store" in layout.lower()
    assert "archive.sqlite3" in layout
    assert "exports/" in layout
    assert "generated exports, not source data" in layout
    assert "artifact_blobs" in layout
    assert "CREATE TABLE IF NOT EXISTS threads" in layout
    assert "CREATE TABLE IF NOT EXISTS cdc_events" in layout
    assert "decision: use sqlite as the only canonical archive store" in decision
    assert "markdown is an export format only" in decision
    assert "sqlite is the only canonical archive store" in overview
    forbidden = "hy" + "brid"
    assert forbidden not in "\n".join([layout.lower(), decision, overview])


def test_ai_chat_archive_skill_covers_incremental_delta_patch_cdc_and_upsert():
    sync = read("sync-strategy.md").lower()

    for term in [
        "incremental update",
        "delta update",
        "partial update / patching",
        "cdc",
        "upsert",
    ]:
        assert term in sync

    assert "do not create a duplicate capture" in sync
    assert "do not tombstone absent entities" in sync
    assert "current_content_hash = excluded.current_content_hash" in sync
    assert "current_artifact_count = excluded.current_artifact_count" in sync
    assert "idempotent" in sync


def test_ai_chat_archive_skill_requires_completion_and_redaction_probes():
    verification = read("verification.md").lower()

    for probe in [
        "inventory probe",
        "artifact probe",
        "incremental probe",
        "delta probe",
        "upsert probe",
        "export probe",
        "secret scan",
        "partial deletion guard",
        "idempotency guard",
    ]:
        assert probe in verification

    assert "do not merge `partial`, `blocked`, or `failed` into `complete`" in verification


def test_ai_chat_archive_skill_documents_chatgpt_comet_capture_findings():
    provider = read("provider-surfaces.md").lower()
    verification = read("verification.md").lower()
    sync = read("sync-strategy.md").lower()

    for phrase in [
        "accessibility/dom tree",
        "show more",
        "response variants",
        "internal://deep-research",
        "generated documents",
        "sources controls",
        "mutating actions such as pin, archive, and delete",
        "webpage to markdown",
    ]:
        assert phrase in provider

    for phrase in [
        "chatgpt-specific probes",
        "search/history probe",
        "expansion probe",
        "variant probe",
        "tool-event probe",
        "chatgpt mutation guard",
        "chatgpt extension guard",
    ]:
        assert phrase in verification

    assert "chatgpt.com/c/<id>" in sync
    assert "do not treat visible \"recent\" rows as the whole account archive" in sync
