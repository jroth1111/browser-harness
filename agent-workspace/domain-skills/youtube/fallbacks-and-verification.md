# YouTube Fallbacks and Verification

The fallback DAGs are defined in `surface-map.json`. A primitive is robust only
when its positive path and forbidden shortcut are both probed.

## Execution Policy

Stop on `success`. Fall back only on `not_available`, `not_found`,
`empty_result`, `parse_error`, `blocked`, `timeout`, or `unsupported_shape`.
Terminate on `login_required`, `members_only`, or `age_restricted`.
Never fall back to the official YouTube Data API, OAuth, silent browser cookie
reads, account mutations, or media downloads unless the user explicitly requests
that separate task.

`yt-dlp` is optional Tier 4 for selected read-only surfaces. It must run in
no-media mode, skip browser-cookie import, and be labelled degraded when it
cannot preserve the mapped renderer contract.

## Fallback DAGs

| Capability | Chain |
|---|---|
| Search results | API search, API continuation, direct search HTML, browser DOM, screenshot state |
| Search filters | live filter renderer, browser filter dialog, direct HTML filter renderers |
| Search chips | chip renderer continuation, browser click and captured request |
| Video metadata | oEmbed, player endpoint, watch player global, browser DOM |
| Watch detail | next endpoint, watch initial data, browser DOM, screenshot state |
| Comments | next continuations, browser comments DOM, raw entity-key capture |
| Transcript | UI-triggered get_transcript, DOM transcript panel, non-empty timedtext probe, unavailable-with-metadata |
| Channel uploads | channel RSS, legacy user RSS, browse API, channel DOM |
| Channel tabs | browse API with live tab params, direct channel HTML, browser DOM, optional `yt-dlp` where supported |
| Playlist contents | browse API, playlist RSS, direct playlist HTML, browser DOM, optional `yt-dlp` |
| Trending | browse API or direct `/feed/trending` HTML, browser DOM |
| Hashtag | browse API or direct `/hashtag/<tag>` HTML, browser DOM |
| Storyboard | player endpoint, watch player global, browser DOM, optional `yt-dlp` |
| Live status | player endpoint, watch player global, browser DOM, optional `yt-dlp` |
| Thumbnails | thumbnail_maxresdefault, thumbnail_hqdefault, thumbnail_mqdefault, thumbnail_default |

## Required Receipts

For each run record:

- primitive ID and path type (`api`, `browser`, `hybrid`, `static`, or `local`)
- URL or endpoint shape, with sensitive values redacted
- browser-harness primitive or HTTP method used
- status code, exit code, or CDP action result
- renderer types observed
- fallback attempts and stop condition
- redaction check for cookies, visitor IDs, keys, playback URLs, signatures, and
  caption base URLs

## Search Probes

Positive:

- `/youtubei/v1/search` returns 200 for `{context, query}`.
- At least one `params` token from each filter group required by the task
  returns 200.
- Continuation tokens return additional items or a terminal empty state.

Negative:

- The parser reports non-video renderers instead of dropping them silently.
- Combined filters are read from live filter renderers, not composed manually.

## Watch Probes

Positive:

- `/youtubei/v1/player` returns `playabilityStatus.status` and
  `videoDetails.videoId`.
- `/youtubei/v1/next` or `ytInitialData` exposes primary info, secondary info,
  panels, and related/comment entry points.

Negative:

- Raw playback URLs, signature ciphers, cookies, API keys, and visitor IDs are
  redacted.
- Related-video parsing supports `lockupViewModel`, not only
  `compactVideoRenderer`.

## Transcript Probes

Positive:

- Opening Show transcript triggers a page-generated `/youtubei/v1/get_transcript`
  request and returns transcript segment renderers.
- DOM fallback yields visible transcript segments when response-body capture is
  unavailable.

Negative:

- Direct minimal `get_transcript` JSON returning 400 is not treated as transcript
  absence.
- Timedtext is accepted only when body length is non-zero.

## Static Probes

Positive:

- oEmbed returns 200 for a public video.
- Thumbnail fallback reaches at least `hqdefault`.
- RSS succeeds or fails independently of channel browse state.
- Playlist RSS succeeds or fails independently of playlist browse state.

Negative:

- RSS 404 does not mark a channel unavailable.
- Playlist RSS 404 does not mark playlist browse unavailable.

## Channel And Playlist Probes

Positive:

- Channel resolution returns a UC browse ID or explicit terminal state.
- Channel tab params are captured from live page state and record renderer types
  or terminal state.
- Playlist contents expose metadata plus video entries or terminal state.

Negative:

- Channel tab params are not hand-composed.
- RSS failure does not mark browse surfaces unavailable.
- Mix/radio playlists are labelled degraded or terminal, not ordinary playlists.

## Discovery Probes

Positive:

- Trending and hashtag routes expose renderers or signed-out terminal state.

Negative:

- Empty signed-out trending is `empty_result`, not parser failure.
- Hashtag routes do not depend on account cookies.

## yt-dlp Probes

Positive:

- Missing `yt-dlp` returns `not_available`.
- Present `yt-dlp` command shapes include no-media flags.

Negative:

- `yt-dlp` fallbacks do not import browser cookies, download media, or emit raw
  playback URLs.

## 2026-04-28 Receipts Preserved

- Signed-out Web client: `clientName=WEB`, `clientVersion=2.20260427.01.00`,
  `hl=en-GB`, `gl=US`.
- Global search returned `responseContext`, `estimatedResults`, `contents`,
  `trackingParams`, `header`, `topbar`, `onResponseReceivedCommands`, and
  `targetId`.
- Search filters returned 200 for mapped single-filter tokens; combined filters
  were rewritten by live filter state.
- Chips observed: All, Shorts, Unwatched, Watched, Videos, Recently uploaded,
  Live.
- Channel-local `/@YouTube/search?query=openai` used browse state and returned
  mixed video and playlist renderers.
- Public watch player returned `OK`, captions metadata, streamingData shape,
  microformat, cards, endscreen, and playback tracking metadata.
- UI-triggered transcript request returned segment renderers; direct minimal
  request returned HTTP 400.
- Share panel request returned 200 and rendered Embed, Copy, Start at, and
  social options.
- Signed-out Save opened sign-in modal. No account mutation endpoint was
  executed.
