"""SQLite archive operations: upsert, CDC, sync state, key computation."""
import hashlib
import json
import sqlite3
import time
import secrets
from pathlib import Path

from .schema import init_db


# --- hashing ---------------------------------------------------------------

def compute_content_hash(text: str | bytes) -> str:
    """SHA-256 with a short prefix. Accepts text or bytes."""
    if isinstance(text, str):
        text = text.encode("utf-8")
    return "sha256:" + hashlib.sha256(text).hexdigest()


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def ensure_provider(conn: sqlite3.Connection, provider_id: str, display_name: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO providers (provider_id, display_name) VALUES (?, ?)",
        (provider_id, display_name),
    )
    conn.commit()


def ensure_account(
    conn: sqlite3.Connection,
    provider_id: str,
    account_key: str,
    account_label: str,
) -> None:
    now = _utc_now()
    conn.execute(
        """INSERT INTO accounts (account_key, provider_id, account_label, first_seen_at, last_seen_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(account_key) DO UPDATE SET last_seen_at = excluded.last_seen_at""",
        (account_key, provider_id, account_label, now, now),
    )
    conn.commit()


def compute_thread_key(provider_id: str, provider_thread_id: str) -> str:
    """Stable thread key. ChatGPT/Claude/Perplexity emit globally-unique UUIDs,
    so the provider thread id alone is durable; queries always scope by
    provider_id so cross-provider collisions are guarded at the query layer.
    For surfaces without durable ids, derive a synthetic key from
    (provider, account, canonical_url) at the call site and pass it here."""
    return provider_thread_id


def compute_message_key(
    thread_key: str, role: str, ordinal: int,
) -> str:
    raw = f"{thread_key}:{role}:{ordinal}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def compute_artifact_key(
    thread_key: str, artifact_url_or_name: str, content_hash: str,
) -> str:
    raw = f"{thread_key}:{artifact_url_or_name}:{content_hash}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def compute_account_key(provider_id: str, account_label: str) -> str:
    raw = f"{provider_id}:{account_label}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def generate_run_id() -> str:
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return f"{ts}-{secrets.token_hex(4)}"


def generate_capture_id() -> str:
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return f"{ts}-{secrets.token_hex(4)}"


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# --- runs ---

def new_run(conn: sqlite3.Connection, run_id: str, source_context: dict) -> None:
    conn.execute(
        "INSERT INTO runs (run_id, started_at, status, source_context_json) VALUES (?, ?, 'running', ?)",
        (run_id, _utc_now(), json.dumps(source_context, default=str)),
    )
    conn.commit()


def finish_run(
    conn: sqlite3.Connection, run_id: str, status: str, summary: dict,
) -> None:
    conn.execute(
        "UPDATE runs SET finished_at = ?, status = ?, summary_json = ? WHERE run_id = ?",
        (_utc_now(), status, json.dumps(summary, default=str), run_id),
    )
    conn.commit()


# --- threads ---

def upsert_thread(conn: sqlite3.Connection, thread: dict, run_id: str | None = None) -> None:
    now = _utc_now()
    conn.execute(
        """INSERT INTO threads (
             thread_key, provider_id, account_key, provider_thread_id, canonical_url,
             title, status, current_content_hash, current_artifact_count,
             first_observed_at, last_observed_at, latest_capture_id
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(thread_key) DO UPDATE SET
             provider_thread_id = COALESCE(excluded.provider_thread_id, threads.provider_thread_id),
             canonical_url = COALESCE(excluded.canonical_url, threads.canonical_url),
             title = excluded.title,
             status = excluded.status,
             current_content_hash = COALESCE(excluded.current_content_hash, threads.current_content_hash),
             current_artifact_count = CASE WHEN excluded.current_artifact_count > 0 THEN excluded.current_artifact_count ELSE threads.current_artifact_count END,
             last_observed_at = excluded.last_observed_at,
             latest_capture_id = COALESCE(excluded.latest_capture_id, threads.latest_capture_id)""",
        (
            thread["thread_key"],
            thread["provider_id"],
            thread["account_key"],
            thread.get("provider_thread_id"),
            thread.get("canonical_url"),
            thread.get("title", ""),
            thread.get("status", "listed"),
            thread.get("content_hash"),
            thread.get("artifact_count", 0),
            thread.get("first_observed_at", now),
            thread.get("last_observed_at", now),
            thread.get("capture_id"),
        ),
    )
    conn.commit()


# --- captures ---

def insert_capture(conn: sqlite3.Connection, capture: dict) -> None:
    conn.execute(
        """INSERT INTO captures (
             capture_id, run_id, thread_key, captured_at, source_context,
             completion_state, normalized_json, rendered_markdown,
             content_hash, previous_capture_id, delta_summary_json
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            capture["capture_id"],
            capture["run_id"],
            capture["thread_key"],
            capture["captured_at"],
            capture["source_context"],
            capture["completion_state"],
            capture["normalized_json"],
            capture["rendered_markdown"],
            capture["content_hash"],
            capture.get("previous_capture_id"),
            capture.get("delta_summary_json"),
        ),
    )
    conn.commit()


def thread_last_capture(conn: sqlite3.Connection, thread_key: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM captures WHERE capture_id = "
        "(SELECT latest_capture_id FROM threads WHERE thread_key = ?)",
        (thread_key,),
    ).fetchone()
    return dict(row) if row else None


# --- messages ---

def upsert_message(
    conn: sqlite3.Connection,
    message: dict,
    run_id: str | None = None,
    provider_id: str | None = None,
    account_key: str | None = None,
) -> None:
    content_hash = compute_content_hash(message["current_content"])
    message_key = compute_message_key(
        message["thread_key"], message["role"], message["ordinal"],
    )
    now = _utc_now()

    existing = conn.execute(
        "SELECT current_content_hash FROM messages WHERE message_key = ?",
        (message_key,),
    ).fetchone()

    if existing is None:
        conn.execute(
            """INSERT INTO messages (
                 message_key, thread_key, provider_message_id, role, ordinal,
                 current_content, current_content_hash,
                 first_seen_capture_id, last_seen_capture_id
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                message_key,
                message["thread_key"],
                message.get("provider_message_id"),
                message["role"],
                message["ordinal"],
                message["current_content"],
                content_hash,
                message["capture_id"],
                message["capture_id"],
            ),
        )
        if run_id and provider_id and account_key:
            _append_cdc(conn, run_id, provider_id, account_key, "message", message_key,
                        "insert", None, content_hash, message.get("capture_id"))
    else:
        old_hash = existing["current_content_hash"]
        if old_hash != content_hash:
            conn.execute(
                """UPDATE messages SET
                     current_content = ?,
                     current_content_hash = ?,
                     last_seen_capture_id = ?
                   WHERE message_key = ?""",
                (message["current_content"], content_hash, message["capture_id"], message_key),
            )
            if run_id and provider_id and account_key:
                _append_cdc(conn, run_id, provider_id, account_key, "message", message_key,
                            "update", old_hash, content_hash, message.get("capture_id"))
        else:
            conn.execute(
                "UPDATE messages SET last_seen_capture_id = ? WHERE message_key = ?",
                (message["capture_id"], message_key),
            )
            if run_id and provider_id and account_key:
                _append_cdc(conn, run_id, provider_id, account_key, "message", message_key,
                            "touch", content_hash, content_hash, message.get("capture_id"))
    conn.commit()
    return message_key


# --- artifacts ---

def upsert_artifact(
    conn: sqlite3.Connection,
    artifact: dict,
    run_id: str | None = None,
    provider_id: str | None = None,
    account_key: str | None = None,
) -> str:
    content_hash = artifact.get("content_hash") or compute_content_hash(artifact.get("label", ""))
    artifact_key = compute_artifact_key(
        artifact["thread_key"],
        artifact.get("provider_artifact_id")
        or artifact.get("source_url")
        or artifact.get("label", ""),
        content_hash,
    )

    existing = conn.execute(
        "SELECT content_hash FROM artifacts WHERE artifact_key = ?",
        (artifact_key,),
    ).fetchone()

    if existing is None:
        conn.execute(
            """INSERT INTO artifacts (
                 artifact_key, thread_key, provider_artifact_id, label,
                 artifact_type, source_url, mime_type, byte_length,
                 content_hash, storage_kind,
                 first_seen_capture_id, last_seen_capture_id
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                artifact_key,
                artifact["thread_key"],
                artifact.get("provider_artifact_id"),
                artifact.get("label"),
                artifact["artifact_type"],
                artifact.get("source_url"),
                artifact.get("mime_type"),
                artifact.get("byte_length"),
                content_hash,
                artifact.get("storage_kind", "metadata"),
                artifact["capture_id"],
                artifact["capture_id"],
            ),
        )
        if run_id and provider_id and account_key:
            _append_cdc(conn, run_id, provider_id, account_key, "artifact", artifact_key,
                        "insert", None, content_hash, artifact.get("capture_id"))
    else:
        old_hash = existing["content_hash"]
        conn.execute(
            """UPDATE artifacts SET
                 label = COALESCE(?, label),
                 source_url = COALESCE(?, source_url),
                 content_hash = ?,
                 last_seen_capture_id = ?
               WHERE artifact_key = ?""",
            (artifact.get("label"), artifact.get("source_url"), content_hash, artifact["capture_id"], artifact_key),
        )
        if run_id and provider_id and account_key:
            op = "update" if old_hash != content_hash else "touch"
            _append_cdc(conn, run_id, provider_id, account_key, "artifact", artifact_key,
                        op, old_hash, content_hash, artifact.get("capture_id"))

    conn.commit()
    return artifact_key


def store_artifact_blob(
    conn: sqlite3.Connection, artifact_key: str, content_hash: str, data: bytes,
) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO artifact_blobs (artifact_key, content_hash, bytes) VALUES (?, ?, ?)",
        (artifact_key, content_hash, data),
    )
    conn.commit()


# --- citations ---

def upsert_citation(conn: sqlite3.Connection, citation: dict) -> None:
    raw = f"{citation['thread_key']}:{citation.get('url', '')}:{citation.get('label', '')}"
    citation_key = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    conn.execute(
        """INSERT INTO citations (citation_key, thread_key, capture_id, label, url, source_json)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(citation_key) DO UPDATE SET
             label = excluded.label,
             url = excluded.url,
             source_json = excluded.source_json""",
        (
            citation_key,
            citation["thread_key"],
            citation["capture_id"],
            citation.get("label"),
            citation.get("url"),
            json.dumps(citation.get("source_json", {}), default=str),
        ),
    )
    conn.commit()
    return citation_key


# --- sync state ---

def get_sync_state(
    conn: sqlite3.Connection, provider_id: str, account_key: str, cursor_name: str,
) -> dict | None:
    row = conn.execute(
        "SELECT * FROM sync_state WHERE provider_id = ? AND account_key = ? AND cursor_name = ?",
        (provider_id, account_key, cursor_name),
    ).fetchone()
    if not row:
        return None
    result = dict(row)
    if result.get("state_json"):
        try:
            state_json = json.loads(result["state_json"])
        except Exception:
            state_json = {}
        result["state_json"] = state_json if isinstance(state_json, dict) else {}
    return result


def set_sync_state(
    conn: sqlite3.Connection,
    provider_id: str,
    account_key: str,
    cursor_name: str,
    cursor_value: str | None,
    state_json: dict | None,
) -> None:
    conn.execute(
        """INSERT INTO sync_state (provider_id, account_key, cursor_name, cursor_value, state_json, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(provider_id, account_key, cursor_name) DO UPDATE SET
             cursor_value = excluded.cursor_value,
             state_json = excluded.state_json,
             updated_at = excluded.updated_at""",
        (provider_id, account_key, cursor_name, cursor_value,
         json.dumps(state_json, default=str) if state_json else None, _utc_now()),
    )
    conn.commit()


# --- queries ---

def known_thread_keys(
    conn: sqlite3.Connection, provider_id: str, account_key: str,
) -> set[str]:
    rows = conn.execute(
        "SELECT thread_key FROM threads WHERE provider_id = ? AND account_key = ?",
        (provider_id, account_key),
    ).fetchall()
    return {r["thread_key"] for r in rows}


# --- CDC ---

def _append_cdc(
    conn: sqlite3.Connection,
    run_id: str,
    provider_id: str,
    account_key: str,
    entity_type: str,
    entity_key: str,
    op: str,
    previous_hash: str | None,
    current_hash: str | None,
    capture_id: str | None,
) -> None:
    conn.execute(
        """INSERT INTO cdc_events (
             run_id, provider_id, account_key, entity_type, entity_key,
             op, capture_id, previous_hash, current_hash, event_json, observed_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            run_id,
            provider_id,
            account_key,
            entity_type,
            entity_key,
            op,
            capture_id,
            previous_hash,
            current_hash,
            json.dumps({"entity_type": entity_type, "entity_key": entity_key, "op": op}),
            _utc_now(),
        ),
    )


# --- cookie jars -----------------------------------------------------------

def compute_jar_id(provider_id: str, account_key: str | None, source_browser: str, source_profile: str) -> str:
    raw = f"{provider_id}:{account_key or ''}:{source_browser}:{source_profile}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def upsert_cookie_jar(
    conn: sqlite3.Connection,
    *,
    provider_id: str,
    account_key: str | None,
    account_label: str | None,
    source_browser: str,
    source_profile: str,
    cookies: dict,
    auth_status: str,
    expires_at: str | None,
) -> str:
    """Store or refresh a cookie jar. Returns jar_id."""
    jar_id = compute_jar_id(provider_id, account_key, source_browser, source_profile)
    now = _utc_now()
    conn.execute(
        """INSERT INTO cookie_jars (
             jar_id, provider_id, account_key, source_browser, source_profile,
             cookies_json, harvested_at, last_auth_check_at, last_auth_status,
             expires_at, account_label
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(jar_id) DO UPDATE SET
             account_key = COALESCE(excluded.account_key, cookie_jars.account_key),
             cookies_json = excluded.cookies_json,
             harvested_at = excluded.harvested_at,
             last_auth_check_at = excluded.last_auth_check_at,
             last_auth_status = excluded.last_auth_status,
             expires_at = excluded.expires_at,
             account_label = COALESCE(excluded.account_label, cookie_jars.account_label)""",
        (
            jar_id, provider_id, account_key, source_browser, source_profile,
            json.dumps(cookies, default=str),
            now, now, auth_status, expires_at, account_label,
        ),
    )
    conn.commit()
    return jar_id


def list_cookie_jars(
    conn: sqlite3.Connection,
    provider_id: str | None = None,
    account_key: str | None = None,
    only_active: bool = True,
) -> list[dict]:
    sql = "SELECT * FROM cookie_jars WHERE 1=1"
    params: list = []
    if provider_id:
        sql += " AND provider_id = ?"; params.append(provider_id)
    if account_key:
        sql += " AND account_key = ?"; params.append(account_key)
    if only_active:
        sql += " AND (last_auth_status IS NULL OR last_auth_status IN ('ok', 'unknown'))"
    sql += " ORDER BY last_auth_check_at DESC"
    rows = conn.execute(sql, params).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["cookies"] = json.loads(d["cookies_json"])
        except Exception:
            d["cookies"] = {}
        out.append(d)
    return out


def mark_jar_status(
    conn: sqlite3.Connection,
    jar_id: str,
    status: str,
    *,
    used: bool = False,
) -> None:
    now = _utc_now()
    if used:
        conn.execute(
            "UPDATE cookie_jars SET last_auth_status = ?, last_auth_check_at = ?, last_used_at = ? WHERE jar_id = ?",
            (status, now, now, jar_id),
        )
    else:
        conn.execute(
            "UPDATE cookie_jars SET last_auth_status = ?, last_auth_check_at = ? WHERE jar_id = ?",
            (status, now, jar_id),
        )
    conn.commit()


def attach_account_to_jar(
    conn: sqlite3.Connection, jar_id: str, account_key: str, account_label: str | None,
) -> None:
    conn.execute(
        "UPDATE cookie_jars SET account_key = ?, account_label = COALESCE(?, account_label) WHERE jar_id = ?",
        (account_key, account_label, jar_id),
    )
    conn.commit()
