# YouTube Workflows

Browser-harness YouTube work starts from surfaces, then chooses a bounded
workflow. The workflows below map user tasks to primitive chains without adding
the official YouTube Data API, official API keys, OAuth, silent cookies,
browser-cookie import, or media downloads.

## Single Video Metadata

- Goal: collect public title, owner, playability, microformat, live status, and
  storyboard/chapter hints for one public video.
- Primary chain: `local_video_id_extraction` -> `api_player_metadata` ->
  `api_watch_next_detail`.
- Optional probes: `api_video_live_status`, `api_storyboard_spec`,
  `api_chapters_key_moments`, `static_oembed_video_card`, `static_thumbnails`.
- Stop on: `login_required`, `members_only`, `age_restricted`.
- Expected output: normalized video ID, title/owner fields, playability status,
  renderer evidence, and optional live/storyboard/chapter fields.
- Unsafe paths: raw playback URL logging, `signatureCipher`, account-gated
  escalation, or page key leakage.
- Receipt: video ID, endpoint shape, playability status, renderer types,
  redaction check, and fallback attempts.

## Single Video Transcript Discovery

- Goal: determine whether the visible public transcript surface is available and
  normalize any already-captured transcript payload.
- Primary chain: `browser_transcript_panel` -> `timedtext_non_empty_body_probe`
  -> `unavailable_with_caption_metadata` -> `ytdlp_write_sub`.
- Terminal states: transcript button absent, captions disabled, empty timedtext
  body, age/member restriction, or unsupported renderer shape.
- Expected output: transcript segment list when available, or explicit terminal
  reason with caption metadata presence/absence.
- Unsafe paths: raw caption `baseUrl` logging, media download, ASR, silent
  cookies, or user browser-cookie import.
- Stop instead of retrying when: the video is account-gated, captions are absent,
  timedtext is empty, or the transcript UI is unavailable after bounded probing.
- Receipt: transcript panel route, segment count or terminal reason, language
  when known, and proof that caption `baseUrl` values were redacted.

## Search And Filtered Search

- Goal: map public search results, filters, chips, renderer shapes, and
  continuations.
- Primary chain: `api_global_search` -> `direct_search_html` ->
  `browser_search_dom` -> `screenshot_search_state` -> `ytdlp_ytsearch`.
- Continuation chain: `api_search_continuation` -> `direct_search_html` ->
  `browser_search_scroll` -> `screenshot_search_state` -> `ytdlp_ytsearch`.
- Degraded boundary: `ytdlp_ytsearch` is video-oriented and does not satisfy a
  mixed-renderer contract unless the caller accepts degraded output.
- Expected output: renderer buckets, result IDs by renderer type, filters/chips,
  continuation token state, and disabled/selected filter state when present.
- Unsafe paths: official search API, hand-composed opaque `sp` tokens, or
  dropping non-video renderers.
- Stop instead of retrying when: the page is blocked, the continuation returns a
  terminal empty state, or required filter tokens are unavailable in live state.
- Receipt: query, filter params source, renderer counts, continuations, and
  negative probe that non-video renderers were not dropped.

## Channel Resolution

- Goal: resolve handles, URLs, watch-owner links, and UC IDs to a public channel
  browseId before any tab workflow runs.
- Primary chain: `api_channel_resolution` -> `direct_channel_html` ->
  `api_browse_channel` -> `browser_channel_dom` -> `ytdlp_channel_dump`.
- Expected output: resolved UC browseId, canonical channel URL, handle when
  public, candidate list when ambiguous, or terminal state.
- Unsafe paths: treating search candidates as identity proof, using account
  cookies to resolve handles, or turning RSS failure into channel failure.
- Stop instead of retrying when: handle resolution is ambiguous, access state is
  terminal, or all public candidates fail identity checks.
- Batch note: channel resolution alone is not permission for broad collection;
  follow `batch-policy.md` before channel traversal.
- Receipt: input identifier, candidate evidence, selected browseId or terminal
  state, fallback attempts, and redaction check.

## Channel Tab Browsing

- Goal: inspect public channel tabs after channel resolution.
- Primary chain: `api_channel_about`, `api_channel_videos`,
  `api_channel_shorts`, `api_channel_playlists`, `api_channel_community`, or
  `api_channel_streams`.
- Params rule: read tab params from the live page or captured browse request;
  do not hand-compose opaque tab params.
- Fallbacks: direct channel HTML, browser DOM, then degraded `ytdlp_flat_playlist`
  only for upload-like video listings.
- Expected output: tab ID, params source, renderer counts, continuation state,
  and tab-specific item list or terminal state.
- Unsafe paths: invented tab params, account cookies to fill signed-out gaps, or
  treating a single empty tab as whole-channel failure.
- Stop instead of retrying when: a tab is unavailable signed-out, access state is
  terminal, or renderer shape is unsupported after bounded fallback.
- Batch note: broad channel traversal must follow `batch-policy.md` before any
  live collection beyond the bounded tab inspection.
- Receipt: input identifier, resolved browseId or terminal state, tab route,
  params source, renderer types, continuation token presence.

## Playlist Enumeration

- Goal: enumerate public playlist metadata and videos without treating Mix/radio
  pages as ordinary user playlists.
- Primary chain: `api_playlist_contents` -> direct playlist HTML -> browser DOM
  -> degraded `ytdlp_flat_playlist`.
- Static probe: `static_playlist_rss` is opportunistic and independent of browse
  availability.
- Expected output: playlist metadata, playlist kind, public video entries,
  continuation state, or explicit terminal state.
- Unsafe paths: treating Mix/radio as an ordinary user playlist, unbounded
  continuation paging, or media download.
- Stop instead of retrying when: the playlist is private/login-gated, generated
  semantics are unsupported, or item/page bounds are reached.
- Batch note: broad playlist traversal must follow `batch-policy.md` before any
  live collection beyond the requested page/item bounds.
- Receipt: playlist ID, playlist kind, video count or terminal state, continuation
  presence, and Mix/generated degradation label when applicable.

## Comments And Replies

- Goal: capture public top-level comment threads and bounded reply expansion.
- Primary chain: `api_comments` -> `browser_comments_dom` -> `ytdlp_comments`.
- Bounds: expand replies only for a configured top-N thread subset.
- Expected output: top-level thread list, reply continuation tokens, bounded
  expanded replies, or disabled-comments terminal state.
- Unsafe paths: comment-write endpoints, account identity reads, or unbounded
  reply expansion.
- Stop instead of retrying when: comments are disabled, reply shape is
  unsupported, or configured expansion bounds are reached.
- Receipt: thread count, reply continuation count, expanded reply count, sort
  mode when known, and terminal reason for disabled comments.

## Storyboards And Live Status

- Goal: extract public storyboard template metadata and live/premiere status from
  player response fields.
- Primary chain: `api_storyboard_spec` and `api_video_live_status`, both after
  `api_player_metadata`.
- Expected output: redacted storyboard template shape, level count, live/upcoming
  flags, scheduled/actual timestamps when public, and playability status.
- Unsafe paths: raw storyboard/playback URL leakage or inferring unavailable
  livestream details from private/account surfaces.
- Stop instead of retrying when: player response lacks the field or video access
  is terminal.
- Receipt: storyboard level count, redacted URL template shape, live/upcoming/end
  status fields, and playability status.

## Trending And Hashtags

- Goal: record public discovery route behavior for signed-out profiles.
- Primary chain: `api_trending` or `api_hashtag` -> direct HTML -> browser DOM.
- Signed-out rule: redirects, empty feeds, or blocked states are terminal
  evidence, not parser failures.
- Expected output: route state, landed URL, renderer counts, category/tag, item
  list when public, or terminal signed-out state.
- Unsafe paths: forcing account cookies, pretending redirect home is trending
  content, or widening to personalized feeds.
- Stop instead of retrying when: signed-out redirect, block, or empty result is
  observed and recorded.
- Receipt: route, landed URL, renderer counts, category/tag, and terminal state.

## Safe yt-dlp Tier 4

- Goal: use `yt-dlp` only as an optional degraded final fallback for selected
  surfaces.
- Allowed shapes: `--skip-download` plus metadata, flat playlist, comments, or
  subtitle flags.
- Forbidden shapes: browser-cookie import, media download, raw playback URL
  logging.
- Expected output: availability, command shape, degraded status, and bounded
  result metadata if the command is actually executed by a caller.
- Unsafe paths: browser-cookie import, media extraction, broad unbounded
  playlist/search commands, or raw URL dumps.
- Stop instead of retrying when: `yt-dlp` is absent, the route would require
  cookies/account access, or the caller needs full mixed-renderer browser data.
- Receipt: availability check, command shape, exit code when executed, no-media
  proof, and redaction check.
