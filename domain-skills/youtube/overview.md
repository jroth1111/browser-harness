# YouTube Overview

Field-tested against `youtube.com` on 2026-04-28 with a clean signed-out
browser-harness Chrome profile, Web client `WEB 2.20260427.01.00`, `hl=en-GB`,
and `gl=US`.

This domain skill maps YouTube data surfaces for browser-harness. It is not a
transcript-only recipe and it is not a wrapper around the official YouTube Data
API. It distinguishes API/direct HTTP surfaces from browser-only and hybrid
browser/API surfaces.

## Source exploration

Follow the exploration order from `interaction-skills/data-source-exploration.md`:

1. **APIs**: YouTube's InnerTube API (`/youtubei/v1/*`) provides structured data
   for search, player metadata, channel tabs, playlists, and comments. Requires
   a valid `INNERTUBE_CONTEXT` but no authentication — works with a fresh signed-out
   browser session. See `innertube.md` for endpoint details.
2. **Static HTTP**: oEmbed endpoint provides title, author, thumbnail for public videos.
3. **Embedded JSON**: `ytInitialData` and `ytInitialPlayerResponse` on watch/search
   pages. See `interaction-skills/data-source-exploration.md` embedded JSON extraction patterns.
4. **Browser (CDP)**: Required for transcript capture, filter chip rendering, and
   any field requiring user interaction (expanding descriptions, loading more comments).

Backend selection follows the routing ladder from
`interaction-skills/cross-domain-control-flow.md`. YouTube converges on the
InnerTube API for most data — CDP is only needed when the API doesn't cover the
requested fields or when browser interaction is required.

**Auth boundaries**: Follow `interaction-skills/session-continuity.md` for session
management. YouTube works signed-out for public content. Do not reuse authenticated
sessions for public observations.

## Operating Rules

- Prefer the primitive in `surface-map.json` whose `outputs` exactly cover the
  requested fields.
- Use API/direct HTTP first when the primitive is marked `api` or `static`.
- Use Browser/CDP when a field requires hydration, a visible UI action, or a
  page-generated network request.
- Record path type, selected primitive, fallback attempts, status/exit code,
  renderer types, and redactions in receipts.
- Never commit or paste cookies, visitor IDs, account payloads, raw playback
  URLs, `signatureCipher`, caption `baseUrl`, or page-provided API keys.
- Treat likes, subscriptions, comments, feedback, uploads, Studio, account
  settings, purchases, private content, and age-gated content as out of scope
  unless the user explicitly requests that mutating or account-bound action.

## Decision Tree

| Need | First path | Fallback |
|---|---|---|
| title, author, thumbnail, embed HTML | static oEmbed | embed page, player metadata, DOM |
| search results | `/youtubei/v1/search` with page context | continuation, direct HTML, browser DOM, screenshot |
| search filters/chips | live filter/chip renderers | browser click and capture page request |
| player metadata/playability | `/youtubei/v1/player` | watch global, oEmbed, DOM |
| watch detail, panels, related, comments root | `/youtubei/v1/next` | watch `ytInitialData`, hydrated DOM |
| comments and reply threads | `/youtubei/v1/next` continuations | hydrated DOM, raw entity keys, optional `yt-dlp` |
| transcript | browser Show transcript request capture | DOM panel, non-empty timedtext probe, optional `yt-dlp` |
| video storyboard/live status | `/youtubei/v1/player` | watch global, DOM, optional `yt-dlp` |
| channel resolution and tabs | `/youtubei/v1/browse` with live tab params | direct HTML, browser DOM, optional `yt-dlp` for supported lists |
| channel uploads | RSS by channel ID | browse API, channel DOM, optional `yt-dlp` |
| playlist contents | `/youtubei/v1/browse` or playlist initial data | playlist RSS, browser DOM, optional `yt-dlp` |
| trending and hashtags | `/youtubei/v1/browse` or direct route HTML | browser DOM with terminal signed-out state |
| thumbnails | `maxresdefault` | `hqdefault`, `mqdefault`, `default` |

The machine-readable registry is the acceptance source for this skill:
`surface-map.json`.

Use `scripts/README.md` before running any YouTube helper script. It classifies
each script as a runner, probe, guard, or exporter and records the expected
outputs and refusal boundaries.

Use `scripts/render_docs.py` after editing `surface-map.json`; it regenerates
the summary tables in `generated-surfaces.md`. Use `scripts/live_smoke.py`
through `browser-harness` to create a redacted receipt when re-checking live
YouTube surfaces. Optional `yt-dlp` fallbacks are Tier 4 degraded paths and must
not download media, import browser cookies, or log raw playback URLs.
