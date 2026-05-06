# YouTube - Browser-Harness Data Skill

This is the entrypoint for YouTube browser-harness work. The skill is a browser
surface map with task workflows layered on top; it is not a general transcript
archive tool and it does not replace the standalone `../youtube` runtime skill.

## When To Use

Use this domain skill when a task needs signed-out public YouTube browser/CDP
surface knowledge: search renderers, filters, watch-page metadata, transcript
panel state, comments/replies, channel tabs, playlist contents, trending/hashtag
routes, or safe fallback evidence.

## When Not To Use

Do not use this skill for uploads, likes, subscriptions, Studio, account
mutation, private/member/age-gated content, official YouTube Data API work,
OAuth, silent cookie reads, browser-cookie import, or full media downloads. Use
`../youtube` instead when the primary task is a portable transcript/search/batch
workflow outside browser-harness.

## Start Here

- `overview.md`: operating rules, scope, and the top-level decision tree.
- `workflows.md`: user-task workflows mapped to primitive chains.
- `workflow-map.json`: machine-readable workflow catalog for task-to-primitive
  routing.
- `surface-map.json`: machine-readable primitive registry, search parameters,
  result renderers, video-detail surfaces, fallback chains, and verification
  probes.
- `surface-map.schema.json`: schema for the machine-readable registry.
- `generated-surfaces.md`: generated tables from `surface-map.json`; regenerate
  with `scripts/render_docs.py`.
- `reports/latest-summary.json`: stable generated report with primitive count,
  live pass/conditional/fail counts, blocked surfaces, and drift notes; regenerate
  with `scripts/summarize_reports.py`.
- `primitives.md`: browser-harness helper primitives to use, split by
  `API/direct HTTP`, `Browser/CDP`, `Browser/API hybrid`, `static`, and `local`.
- `search.md`: global search, channel-local search, autocomplete, search filters,
  chips, result renderer fields, and pagination.
- `video-detail.md`: watch page URL parameters, `ytcfg`, `ytInitialPlayerResponse`,
  `ytInitialData`, Innertube endpoints, transcript, comments, chapters, related
  videos, share, save/report, embed, thumbnails, and RSS surfaces.
- `channel.md`: channel resolution, tabs, about metadata, tab params, sort tokens,
  and browse continuations.
- `playlist.md`: playlist contents, playlist RSS, Mix/generated playlist handling,
  and pagination.
- `trending-discovery.md`: trending feed, category state, hashtag pages, and
  signed-out terminal states.
- `innertube.md`: Web Innertube context, endpoint body rules, continuation rules,
  and redaction requirements.
- `fallback-chains.md`: canonical fallback chains, advance/terminate codes, and
  optional `yt-dlp` Tier 4 policy.
- `fallbacks-and-verification.md`: fallback DAGs, negative probes, and receipt
  requirements before claiming a path is robust.
- `failure-modes.md`: symptoms, advance/terminate codes, safe next fallback, and
  receipt evidence.
- `batch-policy.md`: required bounds, checkpoints, stop conditions, and cleanup
  before any broad collection.
- `crosswalk-youtube-skill.md`: mapping from the standalone `../youtube` method
  catalog to browser-harness primitives.
- `youtube_primitives.py`: thin callable parser/probe helpers that match
  primitive IDs. It does not own sessions or fallback routing.
- `caption_parsers.py`: local VTT, JSON3, and XML/TTML/SRV3 normalization helpers
  for already-captured caption payloads.
- `scripts/assert_no_forbidden_paths.py`: executable guard for unsafe API,
  cookie, playback URL, and unredacted field leakage.
- `fixtures/`: sanitized renderer fixtures for search, comments/replies,
  transcript, video detail, channel, playlist, and discovery shape tests.
- `receipts/`: versioned redacted live-test receipts.

## Default Procedure

1. Classify the request with `workflows.md`.
2. Read `surface-map.json` for the primitive, path type, availability, required
   inputs, and fallback chain.
3. Use API/direct HTTP first when the map marks the field as API-complete.
4. Use browser-harness when YouTube only exposes the field after hydration,
   interaction, or page-generated network requests.
5. Treat RSS, timedtext, and optional `yt-dlp` routes as conditional or degraded
   boundaries when the registry says so.
6. Record the selected primitive, fallback attempts, path type, command or CDP
   action, exit/status, redactions, terminal reason, and negative probe result.

## Recovery

Use `failure-modes.md` before changing parsers. Most failures should advance to a
declared fallback or terminate with an explicit status. Do not turn signed-out
redirects, disabled comments, missing transcript panels, RSS 404s, or empty
timedtext bodies into fabricated data.

## Verification

For local changes, run:

```bash
uv run --group dev pytest -q domain-skills/youtube/tests/test_primitives.py test_youtube_domain_skill.py
python3 domain-skills/youtube/scripts/render_docs.py
python3 domain-skills/youtube/scripts/summarize_reports.py
python3 domain-skills/youtube/scripts/assert_no_forbidden_paths.py
```

For live browser evidence, run from the repo root:

```bash
browser-harness < domain-skills/youtube/scripts/live_smoke.py
```

Do not commit, print, or paste cookies, visitor IDs, account payloads, raw
playback URLs, `signatureCipher`, caption `baseUrl`, or page-provided API keys.
Read-only public surfaces are in scope by default. Mutating account endpoints,
uploads, Studio, comments, subscriptions, likes, feedback, purchases, private
content, and age-gated content require an explicit user request and a separate
rollback/safety plan.
