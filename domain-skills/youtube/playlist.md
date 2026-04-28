# YouTube Playlist Surfaces

Playlist enumeration is mapped by `api_playlist_contents` with
`static_playlist_rss` as an independent static surface.

## Routes

```text
https://www.youtube.com/playlist?list=<playlist_id>
https://www.youtube.com/watch?v=<video_id>&list=<playlist_id>
https://www.youtube.com/feeds/videos.xml?playlist_id=<playlist_id>
```

## Contents

Primary path:

```text
POST /youtubei/v1/browse
```

Use `VL<playlist_id>` as the browse ID only when YouTube accepts it. Otherwise
use the page-provided browse ID, continuation, or initial data from the playlist
HTML. Capture `playlistVideoListRenderer`, `playlistVideoRenderer`,
`lockupViewModel`, and continuation renderers as first-class shapes.

Required normalized fields:

- playlist title
- description when visible
- owner
- video count
- total duration text when present
- last-updated text when present
- privacy or terminal state
- playlist kind: `user_playlist`, `mix_or_radio`, or `generated_playlist`
- video entries and continuations

## RSS

`static_playlist_rss` uses:

```text
GET https://www.youtube.com/feeds/videos.xml?playlist_id=<playlist_id>
```

RSS success or failure is independent evidence. RSS 404 does not prove that the
playlist browse surface is unavailable.

## Mixes And Generated Playlists

Mix/radio/generated playlists can expose a watch queue rather than an ordinary
playlist. Label those as degraded or terminal instead of normalizing away the
difference.

## Fallbacks

`api_playlist_contents` falls back to playlist RSS, direct playlist HTML,
browser DOM, then optional `yt-dlp --flat-playlist`. `yt-dlp` output is degraded
when it cannot preserve playlist metadata or renderer type evidence.
