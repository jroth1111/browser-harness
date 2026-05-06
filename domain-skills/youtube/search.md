# YouTube Search Surfaces

Search is a mixed renderer surface. Treat video, shorts, channels, playlists,
lockups, shelves, ads, empty states, chips, filters, and continuations as
first-class outputs.

## Search Surface Modes

The surface map treats these as distinct search modes:

- global search: `/youtubei/v1/search` with `{context, query}`.
- filtered global search: `/youtubei/v1/search` with `{context, query, params}`.
- continuation search: `/youtubei/v1/search` with `{context, continuation}`.
- chip search: chip continuation token or browser click plus captured request.
- filter dialog: `searchFilterRenderer` live state.
- channel-local search: `/@<handle>/search?query=<query>` in the browser.
- channel browse search: `/youtubei/v1/browse` with channel `browseId` and
  page-provided search-tab params.
- autocomplete: suggestqueries endpoint.

## Routes

```text
https://www.youtube.com/results?search_query=<query>
https://www.youtube.com/results?search_query=<query>&sp=<filter_state>
https://www.youtube.com/@<handle>/search?query=<query>
```

## URL Parameters

| Parameter | Required | Path | Meaning |
|---|---:|---|---|
| `search_query` | yes | global browser URL and direct HTML | User query text. |
| `sp` | no | browser URL and API `params` equivalent | YouTube-provided filter state. |
| `hl` | no | URL/context | Language/locale. |
| `gl` | no | URL/context | Geo market. |
| `persist_gl` | no | URL | Keep requested geo state when YouTube supplies it. |
| `query` | yes | channel-local search URL | Search text inside a channel route. |

## Innertube Search

Endpoint:

```text
POST https://www.youtube.com/youtubei/v1/search?prettyPrint=false&key=<PAGE_KEY>
```

Query parameters:

- `prettyPrint`: optional; use `false`.
- `key`: required by the Web endpoint, but it must be the page-provided
  Innertube key from `ytcfg`; it is not the official YouTube Data API key.

Initial body:

```json
{"context": "<ytcfg INNERTUBE_CONTEXT>", "query": "openai"}
```

Filtered body:

```json
{"context": "<ytcfg INNERTUBE_CONTEXT>", "query": "openai", "params": "<sp token>"}
```

Continuation/chip body:

```json
{"context": "<ytcfg INNERTUBE_CONTEXT>", "continuation": "<token>"}
```

Optional body fields such as `webSearchboxStatsUrl` may appear in browser
requests. Preserve page-generated shape when replaying a browser request.

## Continuation Primitive

`api_search_continuation` is a first-class primitive. It accepts a continuation
token captured from `continuationItemRenderer`, chip state, or a browser scroll
request and posts:

```json
{"context": "<ytcfg INNERTUBE_CONTEXT>", "continuation": "<token>"}
```

Return additional renderers, a next continuation, or a terminal `empty_result`.
Do not merge continuation results into an initial-search receipt without
recording the continuation source.

## Filters

`sp` is an opaque state token. A single filter can be passed as URL `sp` or
Innertube `params`. Combined filters are rewritten by YouTube after each
selection. Do not concatenate, decode, or manually compose tokens.

Required implementation behavior:

1. Open or request the live filter state.
2. Read `searchFilterRenderer.label`, `searchFilterRenderer.status`, and
   `navigationEndpoint.searchEndpoint.params`.
3. Skip `FILTER_STATUS_DISABLED`.
4. After applying a filter, re-read the returned live filter renderer before
   applying another filter.
5. Record selected and disabled filters in the receipt.

Single-filter tokens currently mapped in `surface-map.json`:

- Type: Videos, Shorts, Channels, Playlists, Movies.
- Duration: Under 3 minutes, 3-20 minutes, Over 20 minutes.
- Upload date: Last hour, Today, This week, This month, This year.
- Features: Live, 4K, HD, Subtitles/CC, Creative Commons, 360 deg, VR180, 3D,
  HDR, Location, Purchased.
- Sort: Relevance, Upload date, View count, Rating.

Combined-filter example from the test receipts:

- `sp=EgQIAhAB` selected `Type=Videos` and `Upload date=Today`.
- In that selected state YouTube returned rewritten compatible next-step tokens.

## Chips

Chips are continuation requests, not stable URL `sp` parameters. Mapped chips:
All, Shorts, Unwatched, Watched, Videos, Recently uploaded, Live.

Extract `continuationCommand.token` from `chipCloudChipRenderer`, or click the
chip in the browser and capture the `/youtubei/v1/search` request.

## Result Renderers

Do not write a video-only search parser.

| Renderer | Required fields |
|---|---|
| `videoRenderer` | `videoId`, title, watch URL, owner, channel ID, channel URL, publish time, duration, views, snippets, thumbnails, badges, menu, tracking params |
| `channelRenderer` | channel ID, title, handle, subscribers, video count, description snippet, avatar, subscribe state, browse endpoint |
| `shortsLockupViewModel` | entity/content ID, video ID, title, `/shorts/<id>` URL, thumbnail model, menu |
| `playlistRenderer` | playlist ID, title, owner, metadata rows, thumbnail, playlist URL, item count |
| `lockupViewModel` | content ID, content type, title, metadata rows, thumbnail, URL |
| ads/shelves | `searchPyvRenderer`, `adSlotRenderer`, `inFeedAdLayoutRenderer`, `shelfRenderer`, `gridShelfViewModel`, `verticalListRenderer` |
| `continuationItemRenderer` | continuation token |
| `backgroundPromoRenderer` | no-result or empty-state text |

## Optional yt-dlp Fallback

`ytdlp_ytsearch` is Tier 4 and degraded. It can return video-like results, but
it does not satisfy the mixed-renderer contract for channels, playlists, shorts,
chips, filters, shelves, ads, and empty states unless the caller explicitly
accepts degraded output.

## Channel-Local Search

Route:

```text
https://www.youtube.com/@<handle>/search?query=<query>
```

The visible SPA URL may drop `query` after load. The page can still keep an
input named `query` and a channel search tab. API replay uses channel browse
state, not global search. Re-extract `browseId` and search-tab params from the
channel page for each channel.
