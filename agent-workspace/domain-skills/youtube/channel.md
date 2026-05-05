# YouTube Channel Surfaces

Channel work starts with `api_channel_resolution`, then uses page-provided tab
params for `/youtubei/v1/browse`. Do not invent browse params from examples.

## Resolution

Accepted inputs:

- `@handle`
- `/channel/UC...`
- channel URL from a watch owner link
- raw UC channel ID

Resolution outputs are `browseId`, `channel_id`, `canonical_handle`, `title`,
and `resolution_source`. If a handle cannot be resolved without auth or cookies,
return `not_found`, `login_required`, or `unsupported_shape` rather than trying
an account-bound route.

## Routes

```text
https://www.youtube.com/@<handle>
https://www.youtube.com/@<handle>/videos
https://www.youtube.com/@<handle>/shorts
https://www.youtube.com/@<handle>/playlists
https://www.youtube.com/@<handle>/community
https://www.youtube.com/@<handle>/streams
https://www.youtube.com/@<handle>/about
https://www.youtube.com/channel/<UC...>
```

## Tab Primitives

| Tab | Primitive | Expected shapes |
|---|---|---|
| about | `api_channel_about` | `channelAboutFullMetadataRenderer`, metadata rows |
| videos | `api_channel_videos` | `richGridRenderer`, `videoRenderer`, `richItemRenderer` |
| shorts | `api_channel_shorts` | `shortsLockupViewModel`, `richItemRenderer` |
| playlists | `api_channel_playlists` | `playlistRenderer`, `gridPlaylistRenderer`, `lockupViewModel` |
| community | `api_channel_community` | `backstagePostThreadRenderer`, polls, image/video attachments |
| streams | `api_channel_streams` | videos with live, upcoming, or past-stream state |

## Params And Continuations

Use `ytcfg.data_.INNERTUBE_CONTEXT` plus a channel `browseId` and the tab
`params` captured from the live channel page. Continuations post back to the same
`/youtubei/v1/browse` endpoint with `{context, continuation}`.

Sort tokens for channel videos are opaque. Capture newest/popular/oldest tokens
from the live tab state and record the selected sort in the receipt.

## Terminal States

Signed-out availability varies by channel and region. Valid terminal states are
`empty_result`, `not_found`, `login_required`, `blocked`, and
`unsupported_shape`. A missing community tab is not a parser failure.

## Receipts

Record `browseId`, tab route, params source, renderer types, continuation
presence, fallback attempts, and a redaction check for visitor data, page keys,
cookies, playback URLs, caption base URLs, and signature fields.
