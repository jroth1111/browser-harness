# AI Chat SQLite Archive Layout

Use SQLite as the only canonical archive store. Markdown files and attachment
folders are generated exports, not source data. If an archive run writes
Markdown for readability, it must be reproducible from `archive.sqlite3`.

Do not use a `date/provider/thread/attachments` tree as archive authority. Chat
threads change title, message content, artifacts, and deletion state over time.
A path-based archive makes the same mutable thread look like separate records
and cannot prove upserts, tombstones, partial captures, or CDC without adding a
database beside it.

## Archive Root

```text
archive-root/
  archive.sqlite3
  archive.sqlite3-wal
  archive.sqlite3-shm
  exports/
    markdown/
      YYYY/MM/DD/<provider>/<thread_key>.md
    attachments/
      <artifact_key>/<safe_original_filename>
```

Only `archive.sqlite3` is canonical. WAL/SHM files are SQLite runtime state.
Everything under `exports/` is disposable and must be regenerated from SQLite.

## Identity Keys

Use stable SQLite keys, not filenames, as identity.

- `provider_id`: lowercase provider id such as `chatgpt`, `claude`, `gemini`,
  `grok`, or `perplexity`.
- `account_key`: `sha256(provider_id + account_label + stable_account_hint)[:16]`.
  Store only a redacted `account_label`; never store email addresses unless the
  user explicitly asks and the archive root is private.
- `thread_key`: provider thread id when durable; otherwise
  `sha256(provider_id + account_key + canonical_thread_url_or_title)[:20]`.
- `message_key`: provider message id when durable; otherwise
  `sha256(thread_key + role + visible_ordinal + normalized_content_hash)[:24]`.
- `artifact_key`: provider artifact id when durable; otherwise
  `sha256(thread_key + artifact_url_or_name + artifact_content_hash)[:24]`.
- `capture_id`: UTC timestamp plus short hash, for example
  `20260501T094512Z-7f4a8c1d`.

## SQLite Schema

Minimum schema:

```sql
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
  delta_summary_json TEXT NOT NULL
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
  summary_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_state (
  provider_id TEXT NOT NULL,
  account_key TEXT NOT NULL,
  cursor_name TEXT NOT NULL,
  cursor_value TEXT,
  state_json TEXT NOT NULL,
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
```

### Cookie Jar Vault

`cookie_jars` is the multi-account credential vault that lets the sync runner
re-authenticate against any provider without re-prompting the user. Each row
stores one logged-in browser session for one provider, keyed by
`(provider_id, account_key, source_browser, source_profile)`:

- `cookies_json` is the rich-shape jar produced by `lib.cookie_jar_io` —
  a list of `{name, value, domain, path, expires, ...}` records. It is the
  raw decrypted cookie set for the provider's `cookie_domains`, not flattened.
- `harvested_at` is the ISO8601 UTC timestamp the jar was extracted from the
  browser. `scripts/harvest.py` upserts on this triple-key and skips writes
  when the cookie set is unchanged.
- `last_auth_check_at` / `last_auth_status` / `account_label` are receipts
  populated by the sync runner during `probe_login`. Values for
  `last_auth_status` are `ok`, `expired`, `forbidden`, `error`, or NULL.
- `account_key` is filled in once a provider's `probe_login` has resolved an
  account context. It can be NULL between harvest and first sync.

The vault must never leave the private archive root. Treat `cookies_json` as
secret material — do not include cookie jar rows in exports, fixtures, or
public receipts.

## Export Contract

Markdown export is optional and derived:

```text
exports/markdown/YYYY/MM/DD/<provider>/<thread_key>.md
```

Each exported Markdown file must include front matter that points back to the
database row:

```yaml
---
archive_database: archive.sqlite3
provider: chatgpt
account_key: redacted-or-hash
thread_key: example-thread
capture_id: 20260501T094512Z-7f4a8c1d
content_hash: sha256:...
generated_from: sqlite
generated_at: 2026-05-01T09:45:12Z
---
```

Attachment exports are also derived from `artifact_blobs`. A missing export file
is not data loss when the SQLite blob exists and passes hash verification.

## Privacy Boundaries

The SQLite archive is private user data. Keep it outside git, or under ignored
`.private-data/` for local experiments. Never copy database rows, generated
exports, artifact bytes, cookies, provider payloads, or private receipts into
reusable skill docs. Commit only redacted schemas, recipes, and synthetic
fixtures.
