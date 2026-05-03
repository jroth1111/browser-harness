# YouTube Browser-Harness Primitives

Use browser-harness directly. Do not add a YouTube-specific manager layer.

## API / Direct HTTP

- `http_get(url)`: public oEmbed, thumbnails, RSS, embed pages, static watch or
  search HTML.
- `http_get_browser_session(url)`: same-domain reads after a real profile has
  established usable YouTube page state. Seed first with `seed_browser_session()`
  if cookies may be stale. Do not print cookie headers.
- `/youtubei/v1/search`: global search, filters, chips, and continuations using
  page-derived context.
- `/youtubei/v1/player`: player metadata and playability.
- `/youtubei/v1/next`: watch detail, comments roots, related videos, and
  continuations.
- `/youtubei/v1/browse`: channel tabs, channel-local search, hashtags, and
  browse continuations, playlist contents, and discovery surfaces.
- Playlist RSS:
  `https://www.youtube.com/feeds/videos.xml?playlist_id=<playlist_id>`.

## Browser / CDP

- `new_tab(url)`: first navigation. Avoid `goto_url()` for first navigation so
  the user's active tab is not overwritten.
- `goto_url(url)`: same-tab navigation only after the agent owns the active
  YouTube tab.
- `wait_for_load()` then a hydration wait before watch-page DOM reads.
- `wait_for_load_js()` and `wait(seconds)`: fallback load/hydration gates.
- `wait_for_content()`: distinguish a usable YouTube page from blank/challenge
  shells.
- `capture_screenshot()`: verify visible state before clicks, panels, filter
  dialogs, comments, transcript controls, and sign-in walls.
- `capture_screenshot_trace()`: debug transient filter menus, panels, and
  hydration changes.
- `click_at_xy()`, `type_text()`, `press_key()`, and `scroll()`: operate visible
  UI controls.
- `dispatch_key()`: selector-targeted keyboard fallback.
- `js(expression)`: read `ytcfg.data_`, `ytInitialPlayerResponse`,
  `ytInitialData`, and DOM state.
- `cdp("Network.enable")` plus `drain_events()`: capture page-generated
  `/youtubei/v1/*` requests. Redact keys, cookies, visitor IDs, and raw media
  URLs before writing receipts.
- `ax_snapshot()`: fallback when visible controls are clearer in the
  accessibility tree than the DOM.

## Hybrid Paths

Hybrid paths use the browser to produce a valid request, then parse structured
API data:

- transcript: click Show transcript and capture
  `/youtubei/v1/get_transcript`.
- share panel: click Share and capture `/youtubei/v1/share/get_share_panel`.
- search chips: click chip or parse `chipCloudChipRenderer` continuation.
- comments: use continuations emitted by `/youtubei/v1/next` or the page.
- channel tabs, playlist contents, trending, and hashtags: use browser or direct
  HTML only to capture page-provided browse IDs, params, renderer types, and
  continuations before replaying structured requests.

## Local Safety

- `endpoint_info()`, `browser_backend_info()`, and
  `diagnose_url_capability(url)` belong in receipts before debugging selectors.
- `detect_block_page()` is the local classifier for fetched HTML/text when a
  page may be blank, denied, or challenged.
- `discover_local_cdp_endpoints()` is setup/debug only when the browser endpoint
  is unknown.
- `ensure_real_tab()`, `list_tabs()`, `current_tab()`, `switch_tab()`,
  `close_tab()`, and `close_tabs()` keep YouTube work in agent-owned tabs and
  cleanup bounded tab batches.
- `page_info()`, `page_info_js()`, and `page_content_status()` belong in
  receipts after major navigation.
- `browser_cookies()` and `browser_cookie_header()` are local-only helpers for
  same-domain browser-session HTTP; never include their output in shared docs,
  test fixtures, or committed logs.
- `http_get_browser_session_response()` records status/header shape for
  same-domain browser-session reads.
- `iframe_target()` is only for YouTube embeds that expose a real iframe target.
- `login_session_manifest()` and `prompt_user_login()` are only for explicit
  auth-wall tasks where the user performs login themselves.
- `upload_file()` is out of the mapped extraction surface; YouTube upload/Studio
  requires a separate explicit mutating task.

## Optional Local Fallbacks

`yt-dlp` is a Tier 4 degraded fallback for selected read-only surfaces only.
Check `shutil.which("yt-dlp")`; if absent, return `not_available`. Allowed
invocations must be no-media shapes such as `--skip-download`, `--dump-single-json`,
or `--flat-playlist`. Do not import browser cookies or log playback URLs.

Thin callable helpers may parse fixtures and expose primitive-shaped functions,
but they must not become a YouTube-specific manager layer, retry framework, or
session abstraction.
