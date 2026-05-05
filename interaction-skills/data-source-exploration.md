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
- extraction coverage and four-state field semantics (see `extraction-coverage.md`)

Site-specific details belong in `agent-workspace/domain-skills/<site>/`:

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
5. If using browser extraction: probe CSS selectors via `js()`
   before writing extraction JS. See `extraction-coverage.md` for selector
   discovery, entity-type identification, and four-state field semantics.
6. Inventory authenticated/exportable sources in a persistent browser profile.
7. Prefer structured exports/downloads over UI text.
8. Inspect network requests only after UI/export behavior is understood.
9. Register primitives with source, scope, confidence, freshness, privacy class,
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
   pagination/count evidence, and fallback reason. Use
   `source_receipts.build_source_receipt(...)` for the shared source-selection
   shape.

Field-level parity decides the canonical source. Page-level success does not.

For multi-stage API crawls, see `api-schema-audit.md` for data threading between
waves, heterogeneous dict classification, and schema comparison against actual API
responses.

## Embedded JSON extraction

Many sites embed structured data in `<script>` tags within the HTML. This is
often more complete and stable than DOM scraping, and doesn't require API
reverse-engineering. Check for embedded JSON before building DOM extractors.

### Common patterns by framework

| Framework | Script tag / variable | Contains |
|-----------|----------------------|----------|
| Next.js | `#__NEXT_DATA__` | Page props, pagination, facets, product data |
| React bootstrap | `#data-deferred-state-0`, `#data-initializer-bootstrap` | Initial state, API keys, operation hashes |
| Site-specific config | varies by site | Sort options, filter metadata, search refinement config |
| Global variable | varies by site | Search results, video metadata, player config |
| Generic | `window.__APOLLO_STATE__` | GraphQL cache with normalized entities |

Site-specific variable names belong in `agent-workspace/domain-skills/<site>/`. This table shows the
pattern categories; actual variable names are discovered per site during exploration.

### Discovery workflow

1. Load the target page in a browser.
2. Inspect `<script>` tags for JSON blobs: `document.querySelectorAll('script[type="application/json"]')`
   and `document.querySelectorAll('script#__NEXT_DATA__')`.
3. Check `window` for large JSON objects: `Object.keys(window).filter(k => k.startsWith('yt') || k.startsWith('__'))`.
4. Parse and explore the structure to find target fields.

### Standard extraction JS

```javascript
// Next.js
() => JSON.parse(document.querySelector('#__NEXT_DATA__')?.textContent || '{}')

// React bootstrap JSON
() => JSON.parse(document.querySelector('#data-deferred-state-0')?.textContent || '{}')

// Global variable on window
() => window.YOUR_SITE_DATA_VAR

// Config object embedded in script tag
() => JSON.parse(document.querySelector('script')?.textContent.match(/CONFIG_VAR\s*=\s*({.*?});/)?.[1] || '{}')
```

Embedded JSON is a second-tier source (after exports/APIs, before DOM scraping).
It's particularly valuable for discovering URL parameters, filter options, and
sort metadata without reverse-engineering the UI.

### Python extraction via `fetch()` Response

When using `fetch()` (returns a `Response` object), extraction helpers are available:

```python
r = fetch("https://example.com/page")

# Next.js
data = r.next_data()                    # -> dict or None

# JSON-LD structured data
products = r.json_ld("Product")          # -> list of dicts matching @type
all_schemas = r.json_ld()                # -> list of all ld+json blocks

# window.VAR_NAME = {...} assignments
config = r.embedded_json("SITE_CONFIG")  # -> dict or None
```

## Filtering strategy

Push filtering to the server whenever possible. The hierarchy:

1. **URL parameters** — the server never sends irrelevant items. Most efficient.
2. **Embedded JSON filtering** — extract then filter in the extractor script.
3. **DOM filtering** — last resort, least reliable, most token-expensive.

Always check for URL-level filters before falling back to client-side extraction.
Platform-specific filter parameters (AliExpress `pr=`, Walmart `min_price/max_price`,
eBay `LH_ItemCondition`) are domain-specific and documented in `product-search.md`
and individual domain skills. The examples illustrate the concept; actual parameters
vary by platform and change over time.

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

## Cross-domain routing

Use `cross-domain-control-flow.md` when a workflow mixes domains, auth states,
public and private sources, iframes, or different browser backends. Do not
promote a backend across domains by analogy; prove capability for the exact
source context and record the fallback reason when it fails.

Use `product-search.md` for marketplace search strategy, fraud avoidance, and
cross-platform comparison rules.

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
