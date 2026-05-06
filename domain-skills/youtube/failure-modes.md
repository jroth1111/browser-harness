# YouTube Failure Modes

Each failure mode maps to an advance or terminate reason from
`youtube_primitives.py` and `surface-map.json`.

| Symptom | Likely Cause | Code | Safe Next Step | Receipt Evidence |
| --- | --- | --- | --- | --- |
| Search HTML loads but expected renderers are absent | Layout drift, localization, or signed-out experiment | `unsupported_shape` | Capture renderer types and try browser DOM/screenshot fallback | URL, renderer counts, ytcfg context presence |
| Search ranking changes | YouTube ranking drift | `empty_result` or `not_found` | Record timestamp/query and avoid claiming stable rank | Query, gl/hl, result IDs |
| Filter token fails | Token expired or copied from another locale/client | `not_available` | Capture filters from the live UI again | Params source and HTTP status |
| Channel handle resolves ambiguously | Search result is a candidate, not the channel identity | `not_found` | Use owner link, UC ID, or page browseId | Input, candidates, selected browseId |
| Channel tab has no items | Empty tab, blocked tab, or unsupported renderer | `empty_result` | Record terminal state; do not mark the whole channel unavailable | Tab URL, params source, renderer counts |
| RSS returns 404 | Public RSS unavailable for that fixture/date | `not_available` | Continue with browse/HTML path | Feed URL shape, status code |
| Playlist is a Mix or radio | Generated playlist semantics differ from user playlist | `unsupported_shape` | Label as degraded and avoid ordinary playlist claims | Playlist kind and renderer types |
| Trending redirects to Home | Signed-out discovery route unavailable in region/profile | `empty_result` | Record redirect as terminal evidence | Requested URL, landed URL |
| Hashtag grid empty | Low-volume tag or signed-out experiment | `empty_result` | Try browser DOM, then stop with tag-specific terminal state | Tag, route, renderer counts |
| Transcript button is absent | Captions disabled or UI surface hidden | `not_available` | Probe caption metadata/timedtext, then stop or Tier 4 | Button/panel evidence and caption metadata |
| Timedtext body is empty | Track unavailable or invalid caption params | `empty_result` | Do not treat as transcript text | Status, byte count, redacted URL shape |
| Comments are disabled | Creator/video disabled comments | `not_available` | Stop or record ytdlp fallback if allowed | Thread count, continuation absence |
| Reply continuation changes shape | Renderer drift | `unsupported_shape` | Capture sanitized fixture and update parser | Reply token presence, renderer path |
| Storyboard spec parse fails | Spec format changed or field absent | `parse_error` | Record spec presence/absence, keep metadata path usable | Field path and redacted template |
| Video is private, members-only, or age-gated | Access requires account or authorization | `login_required`, `members_only`, `age_restricted` | Terminate; do not escalate to cookies/OAuth | Playability status and public reason |
| CDP/browser unavailable | Browser-harness backend issue | `timeout` or `blocked` | Diagnose backend before changing parser | backend kind, endpoint info |
| `yt-dlp` is missing | Optional Tier 4 unavailable | `not_available` | Advance chain or stop with degraded unavailable status | `shutil.which` result |
| Fixture contains unredacted sensitive fields | Redaction failure | `blocked` | Do not commit; regenerate sanitized fixture | Guard output file/line/class |

No recovery path may use the official YouTube Data API, OAuth, silent browser
cookie reads, browser-cookie import, account mutation, or media download unless a
separate user-approved task explicitly changes scope.
