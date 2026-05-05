# AI Chat Archive Storage Decision

Decision: use SQLite as the only canonical archive store.

Markdown is an export format only. A run may generate Markdown views for human
reading, but those files are derived from SQLite and can be deleted and
regenerated. Do not treat Markdown files, attachment folders, or
`date/provider/thread` paths as archive authority.

## Adversarial Debate

### Markdown-first argument

Markdown is easy to inspect, copy, diff, and publish. A directory hierarchy such
as `date/provider/thread/attachments` is immediately understandable. Binary
artifacts fit naturally as files beside the thread. If the only requirement were
"save a readable copy of today's visible threads", Markdown would be the simpler
choice.

Markdown fails the actual archive requirement. Threads mutate over time, titles
change, artifacts can be revised independently from messages, history lists are
virtualized, and incremental sync needs stable identity. A Markdown archive must
invent sidecar indexes, content hashes, tombstones, cursors, and receipts to
avoid duplicates and false deletions. At that point Markdown is no longer the
source of truth; it is a readable projection over a database-shaped problem.

### SQLite-first argument

SQLite matches the semantics the archive needs: stable keys, upserts,
transactions, content hashes, CDC events, sync cursors, tombstones, partial-run
state, FTS, and integrity checks. It can store text, rendered Markdown, JSON,
provider receipts, and artifact bytes as BLOBs in one portable private file.
Atomic commits matter when a provider run captures a thread but fails midway
through artifacts.

SQLite is less pleasant to browse by hand and large BLOBs need care. Those are
operability problems, not correctness problems. They are handled by generated
Markdown/file exports, `VACUUM`, `PRAGMA integrity_check`, backups, and clear
schema contracts.

## Final Rule

Use one canonical SQLite database per archive root:

```text
archive-root/
  archive.sqlite3
  exports/
    markdown/
      ... generated, disposable views ...
```

All provider/account/thread/message/artifact/citation/run/redaction state lives
in `archive.sqlite3`. Generated exports must record the database path, row keys,
capture id, and content hash they came from.

