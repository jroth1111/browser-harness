# YouTube Overview

Field-tested against `youtube.com` on 2026-04-28 with a clean signed-out
browser-harness Chrome profile, Web client `WEB 2.20260427.01.00`, `hl=en-GB`,
and `gl=US`.

This domain skill maps YouTube data surfaces for browser-harness. It is not a
transcript-only recipe and it is not a wrapper around the official YouTube Data
API. It distinguishes API/direct HTTP surfaces from browser-only and hybrid
browser/API surfaces.

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

Use `scripts/render_docs.py` after editing `surface-map.json`; it regenerates
the summary tables in `generated-surfaces.md`. Use `scripts/live_smoke.py`
through `browser-harness` to create a redacted receipt when re-checking live
YouTube surfaces. Optional `yt-dlp` fallbacks are Tier 4 degraded paths and must
not download media, import browser cookies, or log raw playback URLs.
