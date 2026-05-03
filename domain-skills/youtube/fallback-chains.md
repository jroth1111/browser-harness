# YouTube Fallback Chains

The canonical chains live in `surface-map.json`. This file is the operator view.

## Advance And Terminate

Advance on:

- `not_available`
- `not_found`
- `empty_result`
- `parse_error`
- `blocked`
- `timeout`
- `unsupported_shape`

Terminate on:

- `login_required`
- `members_only`
- `age_restricted`

## Tier 4: yt-dlp

`yt-dlp` is optional. Check `shutil.which("yt-dlp")`; when absent, return
`not_available` and advance where the chain allows it.

Allowed command shapes must include no-media behavior such as `--skip-download`,
`--dump-single-json`, or `--flat-playlist`. Do not import browser cookies, log
raw playback URLs, or download media.

Some `yt-dlp` outputs are degraded:

- `ytdlp_ytsearch`: video-only search, not mixed renderer search.
- `ytdlp_flat_playlist`: flat items, metadata may be incomplete.
- `ytdlp_comments`: comment shapes can differ from Innertube renderers.
- `ytdlp_write_sub`: subtitle files only with `--skip-download`.

## Canonical Chains

| Capability | Chain |
|---|---|
| Search results | `api_global_search` -> `api_search_continuation` -> direct HTML -> browser DOM -> browser scroll -> screenshot -> optional `yt-dlp` |
| Search continuation | `api_search_continuation` -> browser scroll -> screenshot |
| Channel resolution | `api_channel_resolution` -> direct HTML -> browse API -> browser DOM -> optional `yt-dlp` |
| Channel videos | `api_channel_videos` -> RSS -> direct HTML -> browser DOM -> optional `yt-dlp` |
| Channel shorts | `api_channel_shorts` -> direct HTML -> browser DOM |
| Channel playlists | `api_channel_playlists` -> direct HTML -> browser DOM -> optional `yt-dlp` |
| Channel community | `api_channel_community` -> direct HTML -> browser DOM |
| Channel streams | `api_channel_streams` -> direct HTML -> browser DOM -> optional `yt-dlp` |
| Playlist contents | `api_playlist_contents` -> RSS -> direct HTML -> browser DOM -> optional `yt-dlp` |
| Trending | `api_trending` -> direct HTML -> browser DOM |
| Hashtag | `api_hashtag` -> direct HTML -> browser DOM |
| Comments | `api_comments` -> browser DOM -> raw entity keys -> optional `yt-dlp` |
| Transcript | browser transcript request -> DOM -> non-empty timedtext -> optional `yt-dlp` -> unavailable with metadata |
| Storyboard | `api_storyboard_spec` -> player metadata/watch global -> browser DOM -> optional `yt-dlp` |
| Live status | `api_video_live_status` -> player metadata/watch global -> browser DOM -> optional `yt-dlp` |
| Video ID extraction | `local_video_id_extraction` |
