# YouTube Video Detail Surfaces

## Watch Routes

```text
https://www.youtube.com/watch?v=<videoId>
https://youtu.be/<videoId>
https://www.youtube.com/shorts/<videoId>
https://www.youtube.com/embed/<videoId>
```

URL parameters:

| Parameter | Required | Meaning |
|---|---:|---|
| `v` | yes on watch URL | Video ID. |
| `t` | no | Start time. |
| `list` | no | Playlist ID. |
| `index` | no | Playlist position. |
| `pp` | no | YouTube-provided navigation/state token. |
| `start_radio` | no | Radio/playlist flow flag. |

## Browser Globals

Read with `js()` after load and hydration:

- `ytcfg.data_`: Innertube context, page-provided Web key, client name/version,
  `hl`, `gl`, login state, visitor data. Redact key and visitor fields.
- `ytInitialPlayerResponse`: player metadata, playability, captions, streaming
  shape, microformat.
- `ytInitialData`: watch UI sections, comments root, related videos, panels, and
  actions.

## Innertube Endpoints

| Endpoint | Path type | Body | Use |
|---|---|---|---|
| `/youtubei/v1/player` | API | `{context, videoId}` | player metadata and playability |
| `/youtubei/v1/next` | API | `{context, videoId}` or `{context, continuation}` | watch detail, related videos, comments |
| `/youtubei/v1/search` | API | `{context, query, params}` or `{context, continuation}` | search, filters, chips |
| `/youtubei/v1/browse` | API | `{context, browseId, params}` | channels, tabs, hashtags |
| `/youtubei/v1/get_transcript` | Browser/API hybrid | UI-generated `{context, params, languageCode, externalVideoId}` | transcript |
| `/youtubei/v1/share/get_share_panel` | Browser/API hybrid | page-generated body | share dialog |

Mutating/account endpoints are out of scope unless explicitly requested:
subscription, like, feedback, account, upload, Studio, comment create/delete,
playlist mutation, survey, purchase, and settings endpoints.

## Player Response Fields

Use `/youtubei/v1/player` first. Fall back to `ytInitialPlayerResponse` if the
API path fails or exact page state is required.

Required field inventory:

- `playabilityStatus`: status, reason, playable-in-embed, miniplayer data.
- `videoDetails`: video ID, title, author, channel ID, length seconds, view
  count, keywords, thumbnails, short description, live/private/crawlable flags.
- `streamingData`: formats and adaptive formats shape only. Redact raw URLs and
  signature fields.
- `captions`: caption tracks, language codes, `kind`, `vssId`, baseUrl presence,
  translation language count.
- `microformat.playerMicroformatRenderer`: title, category, upload date, publish
  date, owner channel name, external channel ID, available countries,
  family-safe flag, view count, owner profile URL.
- `storyboards`, `cards`, `endscreen`, `playbackTracking`, `playerConfig`, and
  ad metadata.
- `storyboards.playerStoryboardSpecRenderer.spec`: storyboard URL template and
  tile/level metadata. Redact URL query secrets when writing fixtures.
- live status: `videoDetails.isLiveContent`, playability fields, and
  `microformat.playerMicroformatRenderer.liveBroadcastDetails` when present.

## Watch Initial Data Fields

Required field inventory:

- `videoPrimaryInfoRenderer`: title, view count, date, buttons, menu.
- `videoSecondaryInfoRenderer`: owner/channel, subscribers, subscribe/join
  controls, description, show-more state.
- Engagement panels: comments, ads, "In this video", search preview, key
  moments, chapters, structured description, searchable transcript.
- Comments: header count, create box, sort menu, thread refs, continuations.
  Preserve raw entity keys when text is not directly present. Reply continuation
  tokens expand `commentRepliesRenderer` for a bounded number of top-level
  threads.
- Related videos: support `lockupViewModel`; do not require
  `compactVideoRenderer`.
- Chapters/key moments: `macroMarkersListItemRenderer` title, time, URL, start
  seconds. Heat markers may be absent.

## Transcript

Transcript is browser-primary.

Reliable path:

1. Open `/watch?v=<videoId>` in browser-harness.
2. Wait for load and hydration.
3. Enable Network events with CDP.
4. Open the description/transcript UI and click Show transcript.
5. Capture the page-generated `/youtubei/v1/get_transcript` request/response.
6. Parse `transcriptRenderer`, `transcriptSearchPanelRenderer`, and
   `transcriptSegmentListRenderer`.

Do not treat a direct minimal JSON call returning HTTP 400 as transcript
absence. The tested direct call returned "Precondition check failed"; the
UI-triggered request returned segments.

Timedtext `captionTracks[].baseUrl` is a last fallback only after a same-session
fetch returns a non-empty body.

## Comments And Replies

`api_comments` covers paginated top-level comments and bounded reply expansion.
Each top-level thread can expose a reply continuation under
`commentRepliesRenderer`. Expand replies only for the configured first N threads
and record that bound in the receipt. Reply renderers use the same normalized
fields as top-level comments plus `parent_comment_id` when available.

## Storyboards

`api_storyboard_spec` parses `playerStoryboardSpecRenderer.spec` from
`/youtubei/v1/player` or `ytInitialPlayerResponse`. Normalize the spec into
levels, redacted URL templates, thumbnail dimensions, and tile counts. Do not log
raw media or signed URL material.

## Live And Premiere Status

`api_video_live_status` reads player and microformat fields and returns
`is_live_content`, `is_live_now`, `is_upcoming`, `premiere_state`,
`start_timestamp`, and `end_timestamp` when present. Age-restricted,
members-only, and login-required player states terminate rather than falling
through to account-bound paths.

## Static and Ancillary Surfaces

- oEmbed: title, author, thumbnail, iframe HTML.
- Embed page: embeddability and iframe route.
- Thumbnails: `maxresdefault`, `hqdefault`, `mqdefault`, `default`.
- RSS: recent uploads by channel ID, with legacy `user=` route as fallback.
- Playlist RSS: recent playlist entries by playlist ID.
- Share: click Share and capture `share/get_share_panel`.
- Save/report/actions: browser-only availability and auth-wall state. Do not
  execute mutating endpoints without explicit user request.
