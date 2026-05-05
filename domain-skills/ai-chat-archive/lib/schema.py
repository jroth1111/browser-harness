"""SQLite schema for the AI chat archive. Source of truth: archive-layout.md."""
import sqlite3
from pathlib import Path

SCHEMA_SQL = """\
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS providers (
  provider_id TEXT PRIMARY KEY,
  display_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
  account_key TEXT PRIMARY KEY,
  provider_id TEXT NOT NULL REFERENCES providers(provider_id),
  account_label TEXT NOT NULL,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS threads (
  thread_key TEXT PRIMARY KEY,
  provider_id TEXT NOT NULL REFERENCES providers(provider_id),
  account_key TEXT NOT NULL REFERENCES accounts(account_key),
  provider_thread_id TEXT,
  canonical_url TEXT,
  title TEXT,
  status TEXT NOT NULL,
  current_content_hash TEXT,
  current_artifact_count INTEGER NOT NULL DEFAULT 0,
  first_observed_at TEXT NOT NULL,
  last_observed_at TEXT NOT NULL,
  latest_capture_id TEXT
);

CREATE TABLE IF NOT EXISTS captures (
  capture_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  thread_key TEXT NOT NULL REFERENCES threads(thread_key),
  captured_at TEXT NOT NULL,
  source_context TEXT NOT NULL,
  completion_state TEXT NOT NULL,
  normalized_json TEXT NOT NULL,
  rendered_markdown TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  previous_capture_id TEXT,
  delta_summary_json TEXT
);

CREATE TABLE IF NOT EXISTS messages (
  message_key TEXT PRIMARY KEY,
  thread_key TEXT NOT NULL REFERENCES threads(thread_key),
  provider_message_id TEXT,
  role TEXT NOT NULL,
  ordinal INTEGER NOT NULL,
  current_content TEXT NOT NULL,
  current_content_hash TEXT NOT NULL,
  first_seen_capture_id TEXT NOT NULL,
  last_seen_capture_id TEXT NOT NULL,
  deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS artifacts (
  artifact_key TEXT PRIMARY KEY,
  thread_key TEXT NOT NULL REFERENCES threads(thread_key),
  provider_artifact_id TEXT,
  label TEXT,
  artifact_type TEXT NOT NULL,
  source_url TEXT,
  mime_type TEXT,
  byte_length INTEGER,
  content_hash TEXT,
  storage_kind TEXT NOT NULL,
  first_seen_capture_id TEXT NOT NULL,
  last_seen_capture_id TEXT NOT NULL,
  deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS artifact_blobs (
  artifact_key TEXT PRIMARY KEY REFERENCES artifacts(artifact_key),
  content_hash TEXT NOT NULL,
  bytes BLOB NOT NULL
);

CREATE TABLE IF NOT EXISTS citations (
  citation_key TEXT PRIMARY KEY,
  thread_key TEXT NOT NULL REFERENCES threads(thread_key),
  capture_id TEXT NOT NULL REFERENCES captures(capture_id),
  label TEXT,
  url TEXT,
  source_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,
  source_context_json TEXT NOT NULL,
  summary_json TEXT
);

CREATE TABLE IF NOT EXISTS sync_state (
  provider_id TEXT NOT NULL,
  account_key TEXT NOT NULL,
  cursor_name TEXT NOT NULL,
  cursor_value TEXT,
  state_json TEXT,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (provider_id, account_key, cursor_name)
);

CREATE TABLE IF NOT EXISTS cdc_events (
  event_id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL REFERENCES runs(run_id),
  provider_id TEXT NOT NULL,
  account_key TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_key TEXT NOT NULL,
  op TEXT NOT NULL,
  capture_id TEXT,
  previous_hash TEXT,
  current_hash TEXT,
  event_json TEXT NOT NULL,
  observed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cookie_jars (
  jar_id TEXT PRIMARY KEY,
  provider_id TEXT NOT NULL REFERENCES providers(provider_id),
  account_key TEXT REFERENCES accounts(account_key),
  source_browser TEXT NOT NULL,
  source_profile TEXT NOT NULL DEFAULT 'Default',
  cookies_json TEXT NOT NULL,
  harvested_at TEXT NOT NULL,
  last_used_at TEXT,
  last_auth_check_at TEXT,
  last_auth_status TEXT,
  expires_at TEXT,
  account_label TEXT
);

CREATE INDEX IF NOT EXISTS idx_cookie_jars_provider_account
  ON cookie_jars(provider_id, account_key);

CREATE INDEX IF NOT EXISTS idx_cookie_jars_provider_status
  ON cookie_jars(provider_id, last_auth_status, last_auth_check_at);

CREATE VIRTUAL TABLE IF NOT EXISTS capture_fts
USING fts5(thread_key, title, rendered_markdown, content='');
"""


def init_db(db_path: str | Path) -> sqlite3.Connection:
    """Create or open the archive database with the full schema."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    return conn
