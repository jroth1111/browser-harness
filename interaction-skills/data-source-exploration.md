# Data Source Exploration

Use this before building a scraper, report, or data model for a site. The goal
is to discover available data primitives first, then compose them into workflows.

## What belongs here

Generalizable:

- public/private source discovery order
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
2. Inventory public sources without authentication.
3. Test the cheapest backend first with `diagnose_url_capability()`.
4. Inventory authenticated/exportable sources in a persistent browser profile.
5. Prefer structured exports/downloads over UI text.
6. Inspect network requests only after UI/export behavior is understood.
7. Register primitives with source, scope, confidence, freshness, privacy class,
   and target schema.

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
