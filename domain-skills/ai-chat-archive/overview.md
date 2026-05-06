# AI Chat Archive Overview

Use this domain skill when the user asks to archive, sync, export, or back up
their own logged-in AI chat accounts through browser-harness. The target
providers are ChatGPT, Claude, Gemini, Grok, Perplexity, and similar browser
chat systems that expose thread history and artifacts only after the user is
already logged in.

This skill is an operating manual for browser-harness collection. It is not a
provider API wrapper, credential harvester, or selector promise. Provider UIs
change often, so every archive run must start with live capability probes and
record the source context that worked.

## Start Here

1. Choose or confirm an archive root outside the repository, or use an ignored
   local path for a private one-off run:
   `domain-skills/ai-chat-archive/.private-data/archive/`.
2. Read `storage-decision.md`: SQLite is the only canonical archive store.
   Markdown is a generated export format, not storage authority.
3. Read `archive-layout.md` before writing the database schema or exports.
4. Read `provider-surfaces.md` for provider-specific discovery rules.
5. Read `sync-strategy.md` before implementing resume, incremental, delta,
   partial, CDC, or upsert behavior.
6. Read `verification.md` before claiming the archive is complete.

## Scope

Archive all user-visible thread material the current logged-in account can
legitimately access:

- conversation text, visible model/tool messages, titles, timestamps, URLs, and
  provider thread identifiers when available
- citations, source links, research plans, deep research reports, reasoning,
  agent reports, or agent progress reports when visible to the user
- generated artifacts such as Claude Artifacts, ChatGPT canvases/reports,
  Gemini canvases/outputs, Grok-generated files, Perplexity pages/reports, code
  files, tables, images, PDFs, CSVs, downloads, and provider export files
- user-uploaded attachment metadata and downloadable user files when the current
  UI exposes them
- collection receipts: provider, account label, run id, thread url, capture
  method, source context, loaded range, redaction status, and gaps

Do not archive credentials, cookies, local storage values, session storage
values, payment data, private organization data outside the user's request, or
content from accounts the user has not asked to include.

## Provider Router

| Provider | Start URL family | First collection route | Artifact families to look for |
|---|---|---|---|
| ChatGPT | `https://chatgpt.com/` | Logged-in history, thread URL, visible export/download controls, same-origin list APIs only after browser proof | Deep research reports, canvases, files, images, tables, citations, project/thread attachments |
| Claude | `https://claude.ai/` | Logged-in recents/projects, thread URL, artifact side panel, downloads | Artifacts, code/text files, project outputs, generated documents, uploaded/downloadable files |
| Gemini | `https://gemini.google.com/` | Logged-in chat history and thread surface, visible share/export/download affordances | Canvases, generated files/images, citations, workspace-linked exports when visible |
| Grok | `https://grok.com/` and account-linked Grok surfaces | Logged-in conversation history and thread URL | Generated images/files, citations, reports, X-linked outputs when visible and in scope |
| Perplexity | `https://www.perplexity.ai/` | Logged-in Library/threads/pages, thread URL, share/export controls | Pages, Spaces outputs, Deep Research reports, citations, source snapshots, uploaded/downloadable files |

Provider rows are starting hypotheses, not acceptance evidence. A run receipt
must say which URL, browser profile, account label, and source family actually
worked.

## Architecture

The skill ships as a generic plugin runner with one provider implementation per
supported service. Files of interest:

```text
ai-chat-archive/
  lib/
    archive_db.py          # SQLite plumbing + key derivations
    cookie_extract.py      # Chromium/Safari/Comet cookie decrypt
    cookie_jar_io.py       # rich ↔ flat cookie shape conversions
    provider_base.py       # Provider ABC + dataclasses (CapturedThread, ...)
    providers_registry.py  # short id → class map
    sync_runner.py         # generic probe → inventory → capture → delta loop
    schema.py              # canonical SQL DDL
  providers/
    chatgpt/  claude/  gemini/  grok/  perplexity/
      __init__.py provider.py http.py render.py
  scripts/
    harvest.py             # sweep cookies into the vault
    sync.py                # drive sync_runner across stored jars
    recon.py               # Camoufox network capture for surface mapping
```

A `cookie_jars` table acts as the multi-account vault, keyed by
`(provider_id, account_key, source_browser, source_profile)`. Each provider
declares its `cookie_domains`; harvest filters the raw browser sweep to those
domains before writing a jar.

## Required Run Shape

Two capture modes are available. Prefer HTTP sync when possible; fall back to
browser automation when the provider blocks direct API access.

### Mode 1: HTTP Sync (default for all providers)

Extract cookies from a logged-in browser once, store them in the vault, then
let the sync runner drive every provider through `probe_login → inventory →
capture_thread`:

```bash
# 1. Harvest cookies for every provider (idempotent; skips unchanged jars)
python3 -m scripts.harvest --db .private-data/archive/archive.sqlite3

# 2. Sync stored jars (all providers, all accounts)
python3 -m scripts.sync --db .private-data/archive/archive.sqlite3

# Restrict by provider, account, or capture cap
python3 -m scripts.sync --provider gemini --limit 5
python3 -m scripts.sync --provider chatgpt --account me@example.com --fresh
```

Prerequisites:
- A logged-in browser profile for each target provider (Chrome, Comet, Edge,
  Safari, Arc, Brave, ...)
- macOS Keychain access for Chromium-family Safe Storage entries
- The `cryptography` Python package
- `camoufox` only when running `scripts/recon.py` to remap a drifted surface

The runner is provider-agnostic: it computes the deltas, writes the schema rows,
and stores the rendered Markdown. Per-provider quirks (mapping tree walking for
ChatGPT, batchexecute RPCs for Gemini, NextAuth + step-decomposed answers for
Perplexity) live entirely inside `providers/<id>/http.py`.

### Mode 2: Browser Automation (fallback)

Use browser-harness against the user's currently logged-in browser profile.
Never type credentials or scrape hidden auth state. If a provider shows login,
MFA, account selection, CAPTCHA, enterprise policy, or consent screens, stop and
ask the user to handle the browser interaction.

Archive runs should follow this shape:

1. `capability_probe`: open a safe provider page, prove logged-in state, record
   account label and source context without secrets.
2. `thread_inventory`: enumerate visible thread rows and same-origin history
   endpoints discovered from the logged-in page. Record stable provider ids when
   available; otherwise derive a stable synthetic key from provider, account,
   canonical thread URL, and first observed title.
3. `candidate_selection`: use SQLite sync state to pick new, changed, or
   uncertain threads. Unknown provider timestamps or virtualized lists are
   uncertain and must be sampled, not skipped.
4. `thread_capture`: load the full thread, defeat UI virtualization by scrolling
   or route paging until the top and bottom boundaries are observed, then store
   normalized JSON and rendered Markdown text in SQLite.
5. `artifact_capture`: download every visible artifact/download and save
   citation/source metadata. Store artifact bytes or captured text in SQLite.
   Prefer provider export/download buttons when they preserve fidelity;
   otherwise capture DOM text, rendered HTML, screenshots, and same-origin fetch
   payloads with receipts.
6. `delta_apply`: compare the current capture to the last revision, store only
   new capture rows and CDC events when content changed, and upsert current
   thread/message/artifact rows.
7. `verify`: run the positive and negative probes in `verification.md`.

## Completion Rule

Do not say "all threads" or "all artifacts" unless the provider inventory,
thread capture, artifact capture, SQLite rows/blobs, hashes, and redaction probes
all passed. If any provider blocks history pagination, hides old messages behind
virtualization you cannot exhaust, or prevents artifact downloads, mark that
provider or thread `partial` with the exact residual gap.
