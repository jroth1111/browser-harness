# Domain Skill Surface Map Pattern

Use this pattern when a domain skill grows beyond a single simple recipe.

## Contract First

Create a `surface-map.json` before writing detailed prose. The map is the
machine-readable contract; Markdown files are operator-facing views over it.
Validate the shared shape against `domain-skills/surface-map.schema.json`, then
add domain-specific checks for surfaces such as search, product detail, checkout,
or profile pages.

Required top-level fields:

- `schema_version`
- `domain`
- `path_types`
- `forbidden`
- `execution_policy`
- `primitives`
- `fallback_nodes`
- `fallback_dags`
- `verification_probes`

Recommended fields for browser-heavy domains:

- `browser_harness_primitives`
- `field_tested`
- `fixtures`
- `receipts`

Naming rules:

- Primitive IDs should be stable snake_case and begin with the dominant path
  type when useful, for example `api_global_search` or
  `browser_transcript_panel`.
- Fallback node IDs should describe the route or state being tested, not the
  implementation accident that found it.
- Each primitive must declare `inputs`, `outputs`, and evidence that proves the
  output was reached.

## Path Types

Use the same path vocabulary across domain skills:

- `api`: direct HTTP or page API call that can be executed without visible UI.
- `browser`: visible browser/CDP interaction, DOM state, screenshots, or user
  session state.
- `hybrid`: browser-derived request, token, or session state used by an API
  call.
- `static`: stable public static URL such as images, RSS, oEmbed, or public
  files.
- `local`: local-only classification, unavailable state, or verification helper.

Do not silently change path type during fallback. Record the selected primitive,
the path type, and the reason the fallback was allowed.

## Execution Policy

Every map must say:

- when to stop (`stop_on`)
- when fallback is allowed (`fallback_on`)
- what paths must never be used (`never_fallback_to`)
- which receipt fields are required (`receipt_required`)

Common receipt fields are `primitive_id`, `path_type`,
`source_url_or_endpoint_shape`, `status_or_exit_code`, `fallback_attempts`,
`renderer_types`, `redaction_check`, and `negative_probe`.

## Redaction

Never commit cookies, visitor IDs, account payloads, raw playback URLs,
signature fields, private API keys, bearer tokens, session headers, or raw HTML
and text dumps from an authenticated page. Receipts should capture shape and
status, not sensitive values.

## Live Smoke Scripts

If a domain skill includes a live-smoke script, keep it small and local:

- Load `surface-map.json` and record which primitive contract is being checked.
- Write a redacted receipt under the domain skill's `receipts/` directory.
- Do not dump cookies, raw HTML, raw text, playback URLs, or token values.
- Close any tab the script opens.
- Fail loudly if run from the wrong working directory.
- Keep browser-harness calls direct; do not introduce a manager layer.

## Field Readiness

For browser-only or hybrid surfaces, document a readiness signal rather than a
bare sleep when practical. Prefer API/static paths first. Use browser paths when
the field requires hydration, a visible UI action, or a page-generated network
request. If a fixed wait is the only reliable finding, record the field-tested
browser/date and the fields that are unavailable before the wait.

## Refactor Ledger

At the start of replacement work, record the exact target path and source of
truth. If the target changes, restore accidental edits first, then continue in
the authorized path.

## Verification

Every surface map should have tests that prove:

- primitive IDs are unique
- path types are known
- every fallback reference is either a primitive ID or a typed fallback node
- declared browser-harness helper names exist in `helpers.py`
- forbidden paths are explicit
- receipt fields exist
- optional search filter groups have `label`, `token`, and `status`
- entrypoint docs reference the map and focused docs

Run tests through the repo environment first when available, then use host
Python only as a secondary check.
