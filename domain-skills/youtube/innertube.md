# YouTube Innertube Reference

This skill uses page-provided Web Innertube state. It does not use the official
YouTube Data API and does not require OAuth.

## Context Sources

Read from a hydrated YouTube page or static HTML:

- `ytcfg.data_.INNERTUBE_CONTEXT`
- `ytcfg.data_.INNERTUBE_API_KEY`
- `ytcfg.data_.INNERTUBE_CLIENT_NAME`
- `ytcfg.data_.INNERTUBE_CLIENT_VERSION`
- `ytcfg.data_.HL`
- `ytcfg.data_.GL`

The page key is required for Web Innertube requests but must be redacted from
fixtures, receipts, and copied snippets.

## Endpoints

| Endpoint | Use |
|---|---|
| `/youtubei/v1/search` | search, filters, chips, continuation |
| `/youtubei/v1/player` | player metadata, playability, storyboard, live status |
| `/youtubei/v1/next` | watch detail, comments, related videos |
| `/youtubei/v1/browse` | channels, channel tabs, playlist contents, hashtags, trending |
| `/youtubei/v1/get_transcript` | UI-generated transcript requests |
| `/youtubei/v1/share/get_share_panel` | UI-generated share dialog metadata |

## Body Rules

Initial search uses `{context, query}` and optional `params`. Search
continuation uses `{context, continuation}`.

Browse tabs use `{context, browseId, params}` only when `params` came from a live
page, fixture, or captured request. Browse continuation uses
`{context, continuation}`.

Transcript and share requests are browser/API hybrid paths. Preserve the
page-generated body shape and redact sensitive fields.

## Redaction

Never commit or print:

- cookies or authorization headers
- `INNERTUBE_API_KEY`
- `VISITOR_DATA` or visitor headers
- playback URLs or `signatureCipher`
- caption `baseUrl`
- account payloads or mutation request bodies

Receipts should keep endpoint shape, status, renderer types, fallback attempts,
and redaction-check status.
