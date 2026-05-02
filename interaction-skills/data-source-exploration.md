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

## Filtering strategy

Push filtering to the server whenever possible. The hierarchy:

1. **URL parameters** — the server never sends irrelevant items. Most efficient.
2. **Embedded JSON filtering** — extract then filter in the extractor script.
3. **DOM filtering** — last resort, least reliable, most token-expensive.

Server-side price ranges, sort orders, and category filters exist on most
marketplace platforms (AliExpress `pr=`, Walmart `min_price/max_price`, eBay
`LH_ItemCondition`). Always check for URL-level filters before falling back to
client-side extraction and filtering.

**Location/sourcing defaults vary by platform.** Many marketplaces default to
showing international sellers on regional sites (eBay AU returns zero domestic
results without `LH_PrefLoc=1`). Before running any price comparison, test
whether the default search includes local sellers or only international ones.
If the default is worldwide, add the location filter to every search URL for
that platform. This is a server-side filter — it removes irrelevant items
before they reach the extractor, and is strictly better than post-filtering.

## Embedded JSON metadata discovery

Many platforms embed filter and sort metadata in their page JSON. Extract this
to discover all available URL parameters without reverse-engineering the UI:

- AliExpress: `_dida_config_` contains `sortBar` and `searchRefineFilters`
- Walmart: `__NEXT_DATA__` contains pagination, sort options, and facet metadata
- eBay: HTML class patterns reveal available `_sop` and `LH_*` parameters

Run a metadata extraction pass on any new marketplace to build the URL parameter
reference before building extractors. If the platform adds new filters, they'll
appear in the metadata without re-probing.

## Product search vs category search

Product search ("find price of RTX 5090") and category search ("find all
desktops containing GB10") are different operations requiring different
extraction workflows.

**Product search**: You know the target. Search → extract → done. The domain
skill extractors are designed for this. One query returns mostly relevant
results, and the search-level data (title, price, URL) is usually sufficient.

**Category search**: You don't know the model names. Search → discover
candidates → filter by title keywords → hit detail pages for confirmation →
deduplicate across multiple queries. This requires a discover-then-verify loop:

```
1. Broad search (multiple keyword variations)
2. Deduplicate results across queries by ID (ASIN, listing_id, etc.)
3. Filter by title keywords matching the target category
4. Fetch detail pages for surviving candidates
5. Confirm category membership from detail-level fields
6. Report confirmed results with full metadata
```

Category searches produce far more noise. eBay returns accessories, parts,
and unrelated items sharing keywords. Amazon AU returns every product from the
brand matching any keyword. Post-filtering on title text is mandatory.

No domain skill documents this pattern yet. When building a category search,
extend the product search extractors with a filter+verify layer rather than
writing a separate pipeline.

## Cross-platform comparison requires detail pages

Search result data is insufficient for like-for-like comparison across
platforms. Search result titles are truncated (Amazon AU returns brand names
only for systems), abbreviated (eBay truncates at ~80 chars), or misleading
(both platforms show accessories alongside real products).

For meaningful comparison, the workflow is:

1. Search each platform with the same query.
2. Extract candidate IDs and prices from search results.
3. Fetch the product detail page for each candidate.
4. Normalize fields from detail-level data (full title, specs, configuration,
   condition, seller location).
5. Match across platforms on normalized fields, not search result titles.

Price without configuration context is meaningless for systems. A "DGX Spark"
at $1,933 and one at $8,053 may differ in storage (1TB vs 4TB), condition,
or seller legitimacy. Always extract and compare configuration metadata
(storage, RAM, edition) alongside price.

## Search-level price vs detail-level price

Search result prices are preliminary estimates, not final. On marketplaces with
multi-variant listings, the search-level price can differ significantly from the
detail page price for the same product ID. Observed: AliExpress search JSON
showed AU$13,453 but the detail page showed AU$6,957 for the same listing.

This applies across platforms — any site with variant-based pricing (eBay
multi-variation listings, Amazon configurations, AliExpress SKU variants) can
show a different price at search level. The detail page is always canonical.

Use search-level prices only for initial filtering and ordering. Never report
them as final prices without detail-page verification.

## When to stop searching for niche products

After 3 query variations with 0 results for a specific product, the product
likely isn't on the platform. Continue broadening after this point returns
unrelated items, not missed products. Document the absence as a finding — "not
available on this platform" is a valid and useful result.

Example: ASUS Ascent GX10 and MSI EdgeXpert returned 0 results across 3 query
variations each on AliExpress. The correct conclusion is that these products are
not sold on AliExpress, not that the search needs more refinement.

## Marketplace fraud avoidance

For platforms with gray-market or counterfeit risk (AliExpress, eBay, etc.):

1. **Seller trust is the primary filter.** Always extract seller reputation
   data (feedback %, feedback count, account age) alongside listing data.
   A price from a seller below the platform's trust threshold is not a valid
   data point — exclude it before comparison. Typical thresholds: <95%
   positive feedback or <100 transactions = exclude. Domain skills define
   the exact extraction method and thresholds for their platform.
2. **Sort order is a fraud filter.** Cheapest-first sort surfaces scams.
   Use `total_volume` (most orders) or `price_desc` (expensive-first) to
   surface legitimate sellers.
3. **Server-side price floors eliminate most scams.** Scam listings are
   always priced below market. A URL-level price range (`pr=2000-30000`,
   `min_price=200`) removes them before they reach the extractor.
4. **Detail-page verification is mandatory for high-value goods.** The
   search-level data cannot detect variant traps (accessory listed as GPU
   variant, multi-model listings priced at the cheapest variant). Always
   verify surviving results on their detail pages.
5. **Two independent signals justify exclusion.** A listing should be
   excluded if either: (a) seller trust is below threshold, or (b) price
   is below 50% of a cross-platform reference price. Both signals are
   independently sufficient — you don't need both to flag.
6. **Platform-specific order count artifacts indicate fabrication.** Some
   platforms show a suspiciously consistent order count across unrelated
   listings (e.g., AliExpress "338 orders"). When the same count appears
   on listings from different sellers at wildly different prices, it's a
   platform or seller fabrication — not real transaction data. Do not use
   fabricated counts as a trust signal.

## Cross-domain routing

Use `interaction-skills/cross-domain-control-flow.md` when a workflow mixes
domains, auth states, public and private sources, iframes, or different browser
backends. Do not promote a backend across domains by analogy; prove capability
for the exact source context and record the fallback reason when it fails.

Use `interaction-skills/marketplace-search.md` when searching for products or
components across multiple e-commerce platforms. It provides component-to-product
mapping, cross-platform orchestration, form-factor filtering, and a common
result schema.

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
