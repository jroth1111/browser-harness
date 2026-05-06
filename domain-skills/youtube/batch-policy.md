# YouTube Batch Policy

Batch work is not a default browser-harness surface-mapping operation. Use this
policy before adding or running broad channel, playlist, transcript, or comment
collection workflows.

## Required Bounds

- Explicit user scope: channel/playlist/video set, maximum pages/items, and
  desired output fields.
- Maximum concurrency: default 1 browser tab for interactive surfaces; raise only
  with a reason and cleanup proof.
- Maximum pages: define before the run. Never rely on "until it stops" without a
  checkpoint and stop condition.
- Retry limit: at most two retries per item unless the user approves more.
- Backoff: record delay policy for live public reads.

## Checkpoint Shape

Each batch checkpoint should include:

- `scope_id`: channel, playlist, or query identifier.
- `started_at` and latest checkpoint timestamp.
- `frontier`: next continuation token or next URL.
- `processed`: stable IDs already handled.
- `skipped`: IDs with terminal reasons.
- `failures`: retryable errors with counts.
- `redaction_check`: proof that committed artifacts do not contain cookies,
  playback URLs, page keys, visitor IDs, or caption URLs.

## Stop Conditions

Stop when any one is true:

- requested item/page limit reached;
- no continuation remains;
- terminal access state appears (`login_required`, `members_only`,
  `age_restricted`);
- repeated `unsupported_shape` indicates layout drift;
- browser/backend is blocked or degraded;
- user scope would be exceeded.

## Receipts

Batch receipts must report:

- primitive chain used;
- per-item status and terminal reason;
- fallback attempts;
- skip ledger;
- cleanup status for tabs/temp files;
- whether optional `yt-dlp` was absent, skipped, or used with no-media flags.

Do not add a broad live batch runner until the checkpoint, retry, skip, and
cleanup behavior can be tested without network.
