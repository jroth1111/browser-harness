# AI Chat Archive Sync Strategy

The archive must handle mutable provider threads. A chat thread can gain
messages, lose messages, rename itself, add generated artifacts, replace a deep
research report, or hide old content behind provider-side pagination.

## Definitions In This Skill

- Incremental update: choose only candidate providers, accounts, threads, and
  artifacts whose inventory metadata suggests work is needed since the last run.
- Delta update: compare the prior archived state with the newly captured state,
  compute added/changed/deleted entities, and store the diff and event records.
- Partial update / patching: update only affected rows or documents, such as one
  changed artifact or one message revision, while leaving unchanged records in
  place.
- CDC: append durable `cdc_events` for observed changes so later jobs can replay
  or audit what changed without re-reading every snapshot.
- Upsert: insert new rows or update existing rows by stable identity keys.

## Source Of Truth

SQLite is the only archive source of truth. Markdown, JSON, and attachment files
are exports derived from SQLite rows and BLOBs. A generated export is trusted
only when its front matter points back to a capture row and its content hash
matches the database.

The current thread state is:

```text
threads.latest_capture_id -> captures.content_hash -> captures.rendered_markdown
```

The latest human-readable export is derived from:

```text
SELECT rendered_markdown FROM captures WHERE capture_id = threads.latest_capture_id
```

Capture rows and CDC events are append-only. Export files may be overwritten or
deleted because they are not canonical.

## Incremental Candidate Selection

For each provider/account:

1. Load `sync_state` for the provider inventory cursor, last seen thread ids,
   last seen list hashes, and last successful run.
2. Open the logged-in provider history/list page and capture visible inventory:
   provider thread id, URL, title, visible updated time, preview text, archive/
   folder/project label, and any provider cursor.
3. Normalize inventory rows and compute `inventory_row_hash`.
4. Select candidates:
   - new thread id or canonical URL
   - changed title, updated time, preview, project/folder, or row hash
   - unknown timestamp or missing provider id
   - threads not sampled for longer than the configured freshness window
   - prior capture marked `partial`, `blocked`, or `uncertain`
5. Skip only rows whose provider id or synthetic key, list metadata, and
   freshness policy all prove no change is likely.

Never assume the provider list is complete after one viewport. Scroll or page
until the oldest required boundary is observed, or record the inventory as
partial.

For ChatGPT specifically, the search/history modal can expose stable
`chatgpt.com/c/<id>` links quickly, but it is still a viewport inventory unless
the collector proves pagination or an official/same-origin complete boundary.
Do not treat visible "recent" rows as the whole account archive.

## Thread Delta Algorithm

Capture the full current thread state for every selected candidate. Provider
threads are mutable enough that patching directly from list metadata is unsafe.

For each candidate:

1. Load the last `capture_id`, `content_hash`, message keys, artifact keys, and
   completion state from SQLite.
2. Capture the current thread into normalized structured JSON:
   `thread`, `messages[]`, `artifacts[]`, `citations[]`, `receipts[]`.
   For ChatGPT, expand visible collapsed content first, preserve selected
   response variants, and store tool-call markers separately from message text.
3. Render deterministic Markdown from the structured JSON.
4. Compute hashes:
   - `thread_content_hash`: normalized Markdown plus structured artifact refs
   - `message_content_hash`: normalized role/content/citations per message
   - `artifact_content_hash`: downloaded bytes when available, otherwise
     normalized metadata plus provider source URL
5. If `thread_content_hash` equals the prior hash and artifact hashes match,
   update `last_observed_at` and run receipts only. Do not create a duplicate capture.
6. If hashes differ, insert a new `captures` row with normalized JSON and
   rendered Markdown, store the delta summary in SQLite, and append `cdc_events`.

## Upsert Pattern

Use stable keys. Do not upsert by title alone.

```sql
INSERT INTO threads (
  thread_key, provider_id, account_key, provider_thread_id, canonical_url,
  title, status, current_content_hash, current_artifact_count, first_observed_at,
  last_observed_at, latest_capture_id
) VALUES (
  :thread_key, :provider_id, :account_key, :provider_thread_id, :canonical_url,
  :title, :status, :content_hash, :artifact_count, :observed_at,
  :observed_at, :capture_id
)
ON CONFLICT(thread_key) DO UPDATE SET
  provider_thread_id = COALESCE(excluded.provider_thread_id, threads.provider_thread_id),
  canonical_url = COALESCE(excluded.canonical_url, threads.canonical_url),
  title = excluded.title,
  status = excluded.status,
  current_content_hash = excluded.current_content_hash,
  current_artifact_count = excluded.current_artifact_count,
  last_observed_at = excluded.last_observed_at,
  latest_capture_id = excluded.latest_capture_id;
```

For messages and artifacts, upsert the current row and append a CDC event when
the content hash changes. If a previously seen entity is absent from a complete
capture, mark `deleted_at` and append a `delete` event. If the capture is
partial, do not tombstone absent entities.

## CDC Event Semantics

Use these `op` values:

- `insert`: first observation of a provider, account, thread, message, artifact,
  citation, or attachment
- `update`: stable key exists and content hash changed
- `delete`: stable key existed and a complete current capture proves absence
- `touch`: stable key exists, content unchanged, observed in this run
- `partial`: capture saw only a bounded subset or uncertain state
- `blocked`: provider or UI prevented capture

Every event must include `run_id`, `provider_id`, `account_key`, `entity_type`,
`entity_key`, previous/current hashes when applicable, capture id, and a compact
JSON payload.

## Partial Update Rules

Patch individual records only after a complete enough source boundary is proven:

- A message can be patched when its provider message id or synthetic message key
  is stable and its old/new content hash differs.
- An artifact can be patched when its artifact key is stable and a new SQLite
  BLOB hash or metadata hash differs.
- A thread title can be patched from inventory without full thread capture, but
  that title-only update must not create a new content snapshot.
- A deletion can be recorded only from a complete thread capture or a provider
  deletion marker. Missing from a partial viewport is not deletion evidence.

## Resume And Retry

Each run inserts a `runs` row before provider work starts.
On retry:

- resume incomplete providers before starting new providers
- skip unchanged successful thread captures by database content hash
- retry failed artifact downloads independently from thread text capture
- preserve failed attempt receipts in the `runs` and `cdc_events` tables
- keep the last known good `threads.latest_capture_id` when a new partial
  capture fails

The archive should be idempotent: running the same provider twice with no source
changes may update run receipts and `last_observed_at`, but must not create
duplicate threads, duplicate artifact BLOBs, or duplicate captures.
