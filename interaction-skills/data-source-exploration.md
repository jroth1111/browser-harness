# Data Source Exploration

Use this before building a scraper, report, or data model for a site. The goal
is to discover available data primitives first, then compose them into workflows.

## What belongs here

Generalizable:

- public/private source discovery order
- cross-domain/source/backend control flow
- backend capability testing
- export-first collection
- field inventory and provenance
- network/API observation discipline
- primitive registry shape

Site-specific details belong in `domain-skills/<site>/`:

- URLs, route patterns, query parameters
- exact source names and UI navigation paths
- site-specific field labels and semantics
- observed backend compatibility for that site
- examples using real site pages

## Exploration order

1. Identify the decision or report the user wants.
2. Read the domain skill if one exists, then record the source context: domain,
   origin, auth state, account scope, date/filter/currency/device settings, and
   required fields.
3. Inventory public sources without authentication.
4. Test the cheapest backend first with `diagnose_url_capability()`.
5. Inventory authenticated/exportable sources in a persistent browser profile.
6. Prefer structured exports/downloads over UI text.
7. Inspect network requests only after UI/export behavior is understood.
8. Register primitives with source, scope, confidence, freshness, privacy class,
   and target schema.

## Source classification

Classify each target field before extraction. A page-level load is not enough;
the question is which source returns the field with the best completeness and
provenance.

### Export/download candidate

Use when the site offers CSV, iCal, JSON, PDF, report download, account export,
or another user-facing data file. Prefer exports when they contain the required
fields because they are usually more stable and complete than rendered UI.

### Network/API candidate

Use when the browser page is mainly a transport/auth shell for structured data.
Signals include:

- JSON bootstrap script tags
- GraphQL operation names
- persisted-query hashes
- `__typename` fields
- XHR/fetch responses containing target fields
- explicit pagination, cursors, totals, or stable IDs

If the API returns every required field with stable IDs and counts matching the
UI/export source, treat it as canonical for those fields. Use the authenticated
browser context only to supply the legitimate session, headers, and same-origin
environment; do not copy secrets into docs or committed code.

### Browser-rendered candidate

Use when the data is genuinely produced by client rendering or interaction:

- fields appear only after route transitions, clicks, lazy panels, modals, or
  virtualized scrolling
- the value depends on label text, visible ordering, screenshots, maps, photo
  position, or visual state
- structured payloads omit the field or disagree with the user-visible UI

Browser extraction should fill gaps left by exports/APIs, not duplicate all
fields by default.

## Field-level decision rule

For each target field:

1. Check exports/downloads.
2. Inspect bootstrap JSON and network calls.
3. If an API gives the field with stable IDs and reconciled counts, use the API.
4. If API/export coverage is missing or low confidence, extract only the missing
   fields from the browser UI.
5. Compare counts and required fields against the best available UI/export
   truth source.
6. Store a capability receipt with source, backend, fields found, fields missing,
   pagination/count evidence, and fallback reason.

Field-level parity decides the canonical source. Page-level success does not.

## Cross-domain routing

Use `interaction-skills/cross-domain-control-flow.md` when a workflow mixes
domains, auth states, public and private sources, iframes, or different browser
backends. Do not promote a backend across domains by analogy; prove capability
for the exact source context and record the fallback reason when it fails.

## Backend strategy

| Source type | Preferred backend | Reason |
|---|---|---|
| Static public docs | Direct HTTP or lightweight backend | Fast and low state |
| Public listing/search pages | Lightweight backend if capability test passes | Fast DOM/text extraction |
| Pages requiring visual confirmation | Headful browser | Screenshots and user-visible state |
| Authenticated private UI | Persistent headful profile | Login/MFA/device trust and full browser surface |
| Exports/downloads | Headful browser for download, parser afterward | More reliable than DOM scraping |
| Same-domain authenticated fetches | Browser-session HTTP after headful seed | Faster follow-up collection |

Lightweight backends are acceptable only when the expected fields are present and
stable for the exact URL context. If content is loaded-but-empty or blocked, stop
debugging selectors and switch backend or source.

## Primitive registry

For each primitive, record:

- `source_name`
- `public_or_private`
- `source_url_or_path`
- `capture_method`
- `backend_kind`
- `account_or_listing_scope`
- `date_scope`
- `observed_at`
- `field_names`
- `confidence`
- `freshness_target`
- `privacy_class`
- `target_schema`
- `example_decision`

## Network/API observation

Use this only after source discovery:

- capture endpoint path and request shape
- record response field names and pagination
- record auth/session requirements without secrets
- compare structured payload reliability against UI/export data
- never commit tokens, cookies, private payloads, guest data, or raw reports

## Output

The result of exploration should be a site-specific `data-inventory.md` or
equivalent domain skill file. It should contain the real source list and examples
for that site, while this file remains generic.
