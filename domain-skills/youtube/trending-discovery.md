# YouTube Trending And Discovery Surfaces

Discovery surfaces are read-only and signed-out by default. Empty or unavailable
states are valid terminal evidence when YouTube withholds a surface.

## Trending

Route:

```text
https://www.youtube.com/feed/trending
```

Primitive: `api_trending`.

Use the page context and browse state when the page exposes a trending browse ID.
When the route uses a `bp` category parameter, record the category or `bp` token
as opaque state. Do not hand-compose category tokens.

Expected outputs:

- category or terminal state
- renderer types
- video IDs and titles when available
- signed-out availability evidence

## Hashtags

Route:

```text
https://www.youtube.com/hashtag/<tag>
```

Primitive: `api_hashtag`.

Use `/youtubei/v1/browse` with page-provided hashtag state or parse direct
hashtag HTML. Continuations use `{context, continuation}`.

Expected outputs:

- tag
- renderer types
- video IDs and titles
- continuation tokens
- terminal state

## Negative Probes

- A signed-out empty trending page is `empty_result`, not parser failure.
- A signed-out `/feed/trending` redirect to `/` is `redirected` terminal
  route evidence, not proof that trending browse data exists.
- Hashtag tags are URL-encoded and treated as inputs, not interpolated into API
  params other than the route or page-provided request.
- Browser DOM fallback must not depend on account cookies.

## 2026-04-28 Smoke

In the clean signed-out browser-harness smoke, search, channel about, and
playlist routes landed on their requested paths with `INNERTUBE_CONTEXT`.
`/feed/trending` landed on `https://www.youtube.com/`; treat that as redirect
evidence for the signed-out profile.
