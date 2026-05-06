# AI Chat Archive Verification

Verification is part of the archive contract. Do not claim a provider, account,
or whole archive is complete until the required probes pass.

## Required Evidence

For each provider/account run, capture:

- command or browser-harness transcript used to start the run
- UTC start/end time and archive root
- provider start URL and account label
- source family used: browser DOM, same-origin browser-session HTTP, official
  export/download, or mixed
- inventory count and inventory completion state
- number of selected, skipped, captured, partial, blocked, and failed threads
- artifact count by type and download/capture method
- SQLite path, schema version, and `PRAGMA integrity_check` result
- redaction report row or generated report path

## Positive Probes

Run these before marking a provider/account `complete`:

1. Inventory probe: the run scrolled or paged history until the requested
   boundary was observed, or an official complete export was imported.
2. Thread probe: at least one known changed or newly selected thread has a
   SQLite `threads` row, `messages` rows, and a `captures` row with normalized
   JSON, rendered Markdown, and matching content hash.
3. Artifact probe: every artifact visible in the sampled thread is either saved
   in `artifacts` plus `artifact_blobs` with a hash, or listed in the receipt as
   a blocked/unsupported artifact with reason.
4. Incremental probe: rerunning without source changes does not create duplicate
   thread rows, duplicate artifact rows, duplicate BLOBs, or duplicate captures.
5. Delta probe: changing or selecting a known mutable thread creates a new
   capture row, a delta summary, and `cdc_events` entries for inserted/updated/deleted
   entities.
6. Upsert probe: renamed titles, changed URLs, or reobserved artifacts update
   existing rows by stable keys instead of creating parallel records.
7. Export probe: generated Markdown and attachment exports are reproducible from
   SQLite rows and BLOBs, and can be deleted without losing archive data.

### ChatGPT-Specific Probes

These probes apply when the provider is ChatGPT:

1. Search/history probe: visible `chatgpt.com/c/<id>` rows from the search or
   history surface were recorded with viewport/boundary state. If only one
   modal viewport was visible, inventory status is `partial`.
2. Expansion probe: every observed `Show more` control in sampled messages was
   expanded before hashing, or the capture row is marked `partial` with the
   unexpanded control count.
3. Variant probe: every sampled response with previous/next controls records
   selected variant, visible variant count, and whether other variants were
   opened or intentionally skipped.
4. Tool-event probe: each visible tool-call marker is stored as a structured
   event linked to the following assistant output or artifact rows.
5. File/artifact probe: uploaded file chips, generated documents, generated
   archives, diffs, inline previews, and download buttons in the sampled thread
   are represented in `artifacts`; downloaded bytes are represented in
   `artifact_blobs`.
6. Sources probe: visible `Sources` controls and source links are represented in
   `citations` with URL/title/provider metadata when exposed by the UI.

## Negative Probes

Run these before marking a provider/account `complete`:

1. Secret scan: no cookies, bearer tokens, local storage values, session storage
   values, HAR files, raw browser profile files, or credential-looking fields
   exist in the archive output or receipts.
2. Scope scan: the archive does not include providers, organizations, cloud
   drives, social accounts, or workspaces that the user did not request.
3. Partial deletion guard: missing messages or artifacts from a partial capture
   did not create `delete` CDC events or tombstones.
4. Markdown guard: Markdown files and `date/provider/thread` paths are generated
   exports only; canonical identity remains in SQLite keys.
5. Idempotency guard: a no-change rerun updates run receipts at most, not
   capture rows or artifact BLOBs.
6. ChatGPT mutation guard: collection did not invoke share publication,
   archive, delete, pin, profile/account changes, extension permission grants,
   or cross-provider cloud-drive access.
7. ChatGPT extension guard: browser extension output, if captured with explicit
   approval, is stored only as a receipt and never as canonical thread or
   artifact state.

## Redaction Scan Hints

Query the database and scan generated exports before reporting completion:

```bash
sqlite3 ARCHIVE_ROOT/archive.sqlite3 "
SELECT 'captures', capture_id FROM captures
WHERE lower(normalized_json || ' ' || rendered_markdown) GLOB '*access_token*'
   OR lower(normalized_json || ' ' || rendered_markdown) GLOB '*refresh_token*'
   OR lower(normalized_json || ' ' || rendered_markdown) GLOB '*authorization:*'
   OR lower(normalized_json || ' ' || rendered_markdown) GLOB '*set-cookie*';
"

rg -n --hidden \
  'cookie|set-cookie|authorization:|bearer [A-Za-z0-9._-]+|sessionStorage|localStorage|access_token|refresh_token|id_token|csrf|xsrf|password' \
  ARCHIVE_ROOT/exports
```

Any hit must be inspected. Some words may appear in normal chat content; mark
the hit as user content, redacted metadata, or a real leak. A real leak blocks
completion until removed and the database/file hashes are repaired.

## Completion Labels

Use these labels in run receipts and final reports:

- `complete`: inventory boundary, thread content, artifacts, hashes, SQLite
  rows, CDC events, and redaction probes passed.
- `partial`: useful content was archived, but a known boundary was not reached.
- `blocked`: provider access, UI, account policy, network, or user action
  prevented capture.
- `unchanged`: provider/thread was rechecked and matched prior hashes.
- `failed`: implementation or environment error prevented reliable archival.

Do not merge `partial`, `blocked`, or `failed` into `complete` at the provider
or archive level. Report exact counts by provider.
