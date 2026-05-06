# AI Chat Provider Surfaces

Provider surfaces are discovered at run time from the user's logged-in browser.
Do not hard-code selectors as authoritative unless a receipt proves they worked
for the current provider build, account type, and browser context.

## Common Discovery Flow

Use this flow for each provider:

1. Open a new tab to the provider start URL.
2. Verify the page is logged in by looking for account UI, recent thread lists,
   or a safe private page that does not expose secrets.
3. If login or account selection appears, stop and ask the user to complete it.
4. Capture screenshot and page info before interaction.
5. Discover history/list loading:
   - visible DOM rows
   - same-origin XHR/fetch calls initiated by scrolling or opening history
   - provider export/download controls visible to the logged-in user
6. Prefer official export/download controls when they produce complete data.
7. Use same-origin browser-session HTTP only after the page has proved logged-in
   state and only for URLs the current browser can legitimately load.
8. Capture a redacted source receipt before storing private content.

## Provider Notes

### ChatGPT

Start from `https://chatgpt.com/`. Treat conversation history, Projects, Deep
Research, generated files, images, canvases, citations, and uploaded attachments
as separate artifact families. Prefer provider download/export affordances when
visible because they can preserve report fidelity better than DOM text.

Watch for virtualized history lists and lazy-loaded old messages. A visible
thread URL alone is not proof that all messages or attachments were loaded.

### ChatGPT HTTP API (proven, preferred over browser automation)

ChatGPT's backend API is accessible via direct HTTP using cookies extracted from
any logged-in Chromium-based browser. This is the fastest and most reliable
capture path.

**Authentication requires dual auth:**
1. Cookie header with all session cookies (especially `cf_clearance`, `oai-sc`,
   `__Secure-next-auth.session-token`). Without `cf_clearance`, Cloudflare
   returns 403.
2. Authorization Bearer token from `/api/auth/session`. The endpoint returns
   a fresh JWT access token using the session cookie. Without this, the
   backend API returns 403.
3. The `oai-sc` cookie value must also be sent as an HTTP header `oai-sc`.

**Cookie extraction from Chromium browsers on macOS:**
- Format: `v10` (3 bytes) + 16-byte unknown prefix + 16-byte IV + AES-CBC ciphertext
- Key: PBKDF2-HMAC-SHA1(password=keychain_password.encode('utf-8'), salt=b'saltysalt', iterations=1003, dklen=16)
- Keychain entry: `"{Browser} Safe Storage"` (e.g. "Comet Safe Storage")
- Standard Chrome docs claim a fixed IV of 16 spaces — this is WRONG for current
  Chromium forks. The IV is embedded at offset 16-32 after the v10 prefix.
- See `lib/cookie_extract.py` for the working implementation.

**Backend API endpoints:**
- `GET /api/auth/session` → returns `{user, accessToken, ...}` using cookies only
- `GET /backend-api/me` → user info (requires Cookie + Bearer)
- `GET /backend-api/conversations?offset=0&limit=28&order=updated` → paginated inventory
- `GET /backend-api/conversation/{id}` → full thread detail as mapping node tree

**Mapping node tree format:**
The conversation detail API returns `{mapping: {node_id: {message, children, parent}}}`.
Walk all nodes, skip `role=system`, extract `content.parts[]` as text, sort by
`message.create_time` for stable ordering. Messages have `metadata.model_slug`
for the model name.

**Known limitations:**
- The API does not return deep research report text inline. Deep research appears
  as tool-call markers in the mapping. Full report capture still requires browser
  automation or a separate API.
- Canvas/artifact content is not in the conversation detail API.
- Artifacts must be captured via browser DOM/download if needed.

### Browser Automation Path (Comet/Chrome)

1. Use the logged-in ChatGPT home page as the account proof. The collapsed
   sidebar exposes New Chat, search/history, Library, and profile controls.
2. Open search/history to enumerate visible `https://chatgpt.com/c/<id>` thread
   links. Treat this as a viewport inventory only until scrolling, paging, or a
   same-origin provider call proves the requested boundary.
3. Open each selected thread URL directly. Capture the browser address, page
   title, Memory state, and visible thread controls as thread metadata.
4. Use the accessibility/DOM tree as the first-pass capture surface. It exposes
   user messages, assistant responses, tables, citations/source links, response
   actions, file chips, generated artifact buttons, and tool-call markers.
5. Expand every `Show more` control before claiming full message coverage.
   Collapsed user prompts and long assistant outputs are partial content until
   expanded and re-read.
6. Record response variants when present: selected variant label, previous/next
   buttons, disabled state, and visible count such as `2/2`. A non-selected
   variant is not archived unless opened and captured as its own message
   revision.
7. Treat tool-call containers, including Deep Research surfaces such as
   `internal://deep-research`, as tool events linked to later report/artifact
   rows. Do not flatten them into plain assistant prose.
8. Treat uploaded files, generated documents, generated zips, diffs, source
   attachments, and inline file previews as artifact rows. Store visible name,
   provider type label, parent message key, action/download affordance, byte
   hash when downloaded, and metadata hash when not downloaded.
9. Use Sources controls and visible source links as structured citations. A
   source summary button is not enough; capture each visible URL/title pair that
   the UI exposes.
10. Conversation options can expose a file inventory action, but the same menu
    also exposes mutating actions such as pin, archive, and delete. Use only
    read-only inventory actions; never invoke archive/delete/pin while
    collecting.
11. Do not rely on browser extensions such as "webpage to markdown" as the
    canonical capture path. Extensions may require site permissions and usually
    miss provider artifact semantics; at most they are an optional receipt after
    explicit user approval.

The best default ChatGPT strategy is DOM/accessibility first for structure,
provider download buttons for artifact bytes, and same-origin browser-session
HTTP only as an optimization after the UI has proved the same thread/account
state. The archive must store the UI-observed route and the faster route
receipt so a later run can detect provider drift.

### Claude

Start from `https://claude.ai/`. Capture the main conversation plus the artifact
panel. For each artifact, preserve the visible title, type, latest rendered text,
downloaded source if available, and any revision navigation the UI exposes.

Claude Artifacts can change independently from surrounding chat text. Hash and
upsert artifact bodies separately from message Markdown.

### Gemini

Start from `https://gemini.google.com/`. Capture chat text, generated files,
images, citations, canvas-style outputs, and Workspace-linked export/download
controls only when they are visible in the current account.

Do not assume Google account identity from the browser profile name. Use a
redacted account label observed in the provider UI or ask the user for a label.

#### Gemini HTTP API (proven, batchexecute RPC gateway)

Authenticated chat operations all ride one URL:

```text
POST /_/BardChatUi/data/batchexecute?rpcids=<id>&bl=<bl>&f.sid=<sid>&_reqid=<n>&rt=c
```

Three bootstrap params live in the `/app` HTML and must be scraped once per
session before any RPC:

- `at`  ← `"SNlM0e":"…"` (XSRF token, sent as the `at` form field)
- `bl`  ← `"cfb2h":"…"`  (build label)
- `sid` ← `"FdrFJe":"-?\d+"` (signed session id; **may be negative**)

Cookies: `__Secure-1PSID` + `SAPISID` on `.google.com` are the load-bearing
pair. Identity isn't extractable from the page bundle, so the provider derives
a label from a SAPISID prefix.

RPC ids in use:

- `MaZiqc` — paginated chat list. Request: `[<page_size>, <cursor|null>,
  [<flag1>, null, 1]]`. Response shape: `[null, "<next_cursor>", [<chats>...]]`.
  Each chat is `[c_<hex>, title, null, null, null, [unix, nanos],
  [[c_<hex>, r_<hex>], 0]?, ...]`.
- `hNvQHb` — full thread detail. Request: `[c_<chat_id>, 10, null, 1, [1], [4],
  null, 1]`. Response: `[<turns>, null, null, [...]]` where turns are
  newest-first and each is `[ids, _, user_block, assistant_block, [unix, nanos]]`.
  User text at `turn[2][0][0]`; assistant text at `turn[3][0][0][1][0]`.

Wire format:

```text
)]}'
<chunk_length>
<chunk_json>
<chunk_length>
<chunk_json>
...
```

Length prefixes are loose (sometimes code points, sometimes bytes, sometimes
include the trailing newline). The parser uses `json.JSONDecoder.raw_decode`
to consume one valid JSON value at a time and ignore the announced count.
Each `<chunk_json>` is a list of envelopes;
`["wrb.fr", "<rpc_id>", "<inner_json>", null, null, null, "generic"]` is the
shape of interest, with `<inner_json>` itself JSON-encoded (double-decode).

Image-generation turns put `http://googleusercontent.com/image_generation_content/<n>`
in the assistant text block; the provider lifts those into `artifact_refs`.
Deep-research turns embed many `http(s)://` references inline within the
assistant Markdown — those stay in `content` rather than being synthesized into
a structured citations list.

### Grok

Start from `https://grok.com/` and any account-linked Grok surface the user
explicitly asks to include. Keep Grok threads separate from unrelated X account
data unless the user requested that source.

Generated images, source links, reports, and downloads are artifacts. If a
thread bridges to X content, store external URLs as citations or source refs,
not as a separate social archive.

### Perplexity

Start from `https://www.perplexity.ai/`. Capture Library threads, Pages, Spaces
outputs, Deep Research reports, citations, source lists, uploads, and visible
export controls.

Perplexity outputs often depend on citation/source lists. Store citations as
structured records and keep source artifact snapshots in SQLite only when the
user requested source preservation and the UI exposes them.

#### Perplexity HTTP API (proven)

Cookies: `__Secure-next-auth.session-token` on `.perplexity.ai` is the only
required cookie for `/api/auth/session`. Library/detail endpoints may also
require `cf_clearance` — present in any browser-issued jar.

Endpoints:

- `GET /api/auth/session` → `{user: {email, name, ...}, expires}`. Standard
  NextAuth response.
- `POST /rest/thread/list_ask_threads?version=2.18&source=default` with body
  `{limit, offset}` → list of threads with `uuid`, `slug`, `title`,
  `last_query_datetime`, `query_str` preview. Discovered via Camoufox network
  capture (2026-05); was not exposed under any obvious `/api/` path.
- `GET /rest/thread/{uuid}` → full thread detail. Each `entry` has
  `query_str` (user text) and `text` (a JSON-encoded list of step objects).
- Decode `entry.text` once; the FINAL/PLAN_RESPONSE step's `content.answer`
  is itself a JSON envelope `{"answer": "<markdown>", ...}` — double-decode to
  recover the assistant Markdown. SEARCH_RESULTS steps carry `content.web_results`
  for citation extraction.

## Artifact Capture Rules

For each artifact:

- click or open the artifact in the browser before deciding how to save it
- prefer a provider download/export button over copying rendered text
- save downloaded bytes into SQLite `artifact_blobs` and compute SHA-256
- if no download exists, save rendered Markdown/HTML plus a screenshot receipt
- store source URL, visible title, type, byte hash or metadata hash, capture
  method, and failure gaps in SQLite
- link the artifact from the parent thread's rendered Markdown export only as a
  generated view

If an artifact is shown as a link to another provider or cloud storage system,
do not follow it unless the user included that system in scope.

## Refusal And Safety Boundaries

Stop and ask the user before:

- entering credentials, MFA codes, or account-selection choices
- changing sharing settings or publishing a thread/page
- downloading files from an organization, workspace, or third-party account the
  user did not explicitly include
- bypassing paywalls, access controls, retention limits, or provider export
  restrictions
- using extensions, cookies, HAR exports, or local browser databases directly

The archive workflow may use the logged-in browser session as the user sees it.
It must not extract raw session secrets to work around the UI.
