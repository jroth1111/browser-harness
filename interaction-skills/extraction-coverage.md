# Extraction Coverage — Preventing Silent Data Loss

Use this when building or debugging a browser-based extractor for any site. The
core problem: extraction code can return empty values when the data actually
exists on the page, and nothing in the pipeline catches this.

## The problem

Web extraction returns fields by querying the DOM. When a field comes back empty,
there are two possible explanations:

1. The data doesn't exist on this page (correct empty result)
2. The data exists but the extractor failed to find it (silent failure)

If the extractor uses empty string `""` for both cases, downstream consumers
cannot tell them apart. This is the **open-world assumption (OWA) coverage gap**:
absence of evidence is treated as evidence of absence.

**When it happens:** Any site where a single page contains multiple entity types
with different field sets. Example: a marketplace category page shows both
product aggregations (title, price, offer count) and individual seller offers
(title, price, seller name, stock, delivery time). An extractor written for one
entity type silently returns `""` for fields that belong to the other type — and
also returns `""` for fields it genuinely failed to extract from the correct type.

**What it looks like in practice:** You write extraction JS, run it, get results.
Some fields show values, some show `""`. You assume the `""` fields just aren't
present on those pages. Later you discover the data was there all along — your
selector was wrong, your regex didn't match the text format, or you were querying
the wrong parent element.

## Four-state field semantics

Solve the ambiguity at the source. Every extracted field uses four states:

| JS value | CSV value | Meaning |
|----------|-----------|---------|
| `"value"` | `value` | Found and extracted |
| `null` | `(absent)` | Confirmed absent on this entity type |
| `"__UNOBSERVABLE__"` | `(unobservable)` | Page blocked or broken — could not inspect |
| key omitted | `(not checked)` | Field not applicable to this entity type |

For Python-side parser or fixture checks, use
`extraction_contracts.validate_extraction_record(...)` and
`extraction_contracts.summarize_extraction_coverage(...)` to enforce these
states before treating a result set as usable.

Implementation in extraction JS:

```javascript
// Instead of:
seller: parentText.match(/Seller:\s*(.+)/)?.[1] || ''

// Write:
// For entity types where seller is structurally present:
seller: parentText.match(/Seller:\s*(.+)/)?.[1] ?? null
// For entity types where seller never appears:
// Omit the key entirely
```

The `?? null` (nullish coalescing) returns `null` when the match fails, which
means "I checked, it's not here." Omitting the key means "I didn't check because
this entity type never has this field."

### Unobservable state

Use `"__UNOBSERVABLE__"` when the page could not be inspected at all. This is
different from `null` — `null` means the extractor looked and found nothing,
while `"__UNOBSERVABLE__"` means the extractor could not look.

Triggers:

- WAF or anti-bot block (Cloudflare, Kasada, PerimeterX, etc.)
- Auth gate or login redirect
- Geo-fence or region lock
- Page failed to render (blank content, JavaScript crash)
- Connection timeout or DNS failure

Implementation pattern:

```javascript
// Check page accessibility before extraction
() => {
  // Use wait_for_content() or detect_block_page() before running this
  // If the page is blocked, return unobservable for every field
  const blocked = document.querySelector('.challenge-platform')
    || document.title.includes('Just a moment')
    || document.body.innerText.trim().length < 50;

  if (blocked) {
    return {
      product_name: '__UNOBSERVABLE__',
      price: '__UNOBSERVABLE__',
      seller: '__UNOBSERVABLE__',
      // ... all expected fields marked unobservable
      _block_reason: 'WAF challenge page detected'
    };
  }

  // Normal extraction with four-state semantics
  return {
    product_name: document.querySelector('.title')?.textContent?.trim() ?? null,
    price: document.querySelector('.price')?.textContent?.trim() ?? null,
    // ...
  };
}
```

**Why four states matter:** A `null` in a CSV tells the analyst "the extractor
looked and found nothing." An omitted column tells the analyst "this field
doesn't apply." An `"__UNOBSERVABLE__"` tells the analyst "the extractor
couldn't reach the data — retry may work with a different session, proxy, or
wait." An empty string tells the analyst nothing — it's ambiguous.

## Selector discovery: a11y snapshots are not enough

When building an extractor for a new site, the typical workflow is:

1. Navigate to the page
2. Take an a11y snapshot (`take_snapshot`)
3. Identify fields from the snapshot text
4. Write extraction JS using the snapshot structure

**This misses critical information.** A11y snapshots show the text content and
semantic structure, but not which CSS classes contain which data. When a page has
structured data in specific DOM elements (product cards, seller info, pricing),
you need to know the CSS selectors, not just the visible text.

**The discovery step** — run this between "page loads" and "write extraction":

```javascript
// Probe for CSS classes that hold structured data
// Run via js() on a representative page
() => {
  const probes = {};
  // Replace these with candidate class names from your site's DOM.
  // Use browser DevTools or a11y snapshot to find likely class names first.
  const classList = ['.title', '.price', '.seller', '.stock', '.delivery'];
  for (const cls of classList) {
    const els = document.querySelectorAll(cls);
    probes[cls] = {
      count: els.length,
      samples: Array.from(els).slice(0, 3).map(e => e.textContent.trim())
    };
  }
  // Also check for entity-type containers — adapt the URL pattern to your site
  probes['_entity_types'] = {};
  // Example: document.querySelectorAll('a[href*="/product-"]').length
  return probes;
}
```

Adapt the class list to the site. The point is to **probe for the actual CSS
classes** rather than guessing from snapshot text. This step catches the case
where "seller info is in a `div.name` element inside the card, not in the card's
text content" — which is exactly the case that produces silent `""` failures.

**When to do this:** Always, for any site where the page contains structured data
beyond plain text. Skip only for sites where the a11y tree directly maps to the
data you need (simple article text, form fields, etc.).

## Entity-type identification

Before writing extraction JS, identify how many distinct entity types appear on
each page type. A "page type" is a URL pattern (search results, category listing,
product detail). An "entity type" is a distinct kind of data record on that page.

Example from a marketplace:

| Page type | Entity types |
|-----------|-------------|
| Search results | Category cards |
| Category listing | Product aggregations + Individual seller offers |
| Product detail | Product info + Seller list |

Each entity type has a different field set. Product aggregations have offer
counts but no seller name. Individual offers have seller name, stock, and
delivery time but no offer count.

**Why this matters for extraction:** If you write one extraction function that
handles all entity types uniformly, fields that belong to one type but not the
other will always return `""`. The four-state approach requires knowing which
fields belong to which entity type so you can return `null` (checked, absent)
for the right fields and omit keys for the wrong entity type entirely.

Document entity types in the domain skill's `overview.md` with a table showing
which fields are expected for each type.

## Coverage probes

After running extraction on a page, verify that the extractor actually found
everything on the page. Compare extracted counts against page-declared counts.

For multi-stage crawl coverage accounting (0/0 edge cases, additive counts, dedup
statistics), see `coverage-accounting.md`.

### Worked example

On a marketplace category page, the page text shows "21 Product Contain 14
Offers". After running the extraction JS, check:

```javascript
// Coverage probe — adapted for a specific site
() => {
  const bodyText = document.body.innerText;
  // Adapt this regex to match the site's specific count format
  const totalMatch = bodyText.match(/(\d+)\s+Product\s+Contain/);
  const offerMatch = bodyText.match(/(\d+)\s+Offers/);

  // Read your extraction key from localStorage
  const stored = JSON.parse(localStorage.getItem('__z2u_products') || '[]');
  // Count how many were extracted from this specific page
  const currentUrl = location.href.split('?')[0]; // strip pagination params
  const extractedThisPage = stored.filter(r => r.url && r.url.startsWith(currentUrl));

  return {
    page_declared_total: totalMatch ? parseInt(totalMatch[1]) : null,
    page_declared_offers: offerMatch ? parseInt(offerMatch[1]) : null,
    extracted: extractedThisPage.length,
    coverage_ratio: totalMatch
      ? extractedThisPage.length / parseInt(totalMatch[1])
      : null
  };
}
```

Running this on a z2u category page returned:

```json
{
  "page_declared_total": 21,
  "extracted": 21,
  "coverage_ratio": 1.0
}
```

Full coverage — the extractor found all 21 products the page declared.

If `coverage_ratio` came back as `0.3` (6 extracted out of 21 declared), that
means 15 products were silently missed — selectors are wrong or the page has
entity types the extraction JS doesn't handle.

### Generic template

Adapt the worked example to any site by changing three things:

1. **Count regex** — match how this site displays totals (e.g., `"Showing 1-40 of 2,340"`, `"234 results"`, `"21 Product Contain"`)
2. **localStorage key** — use whatever key your extraction JS accumulates into
3. **Page URL filter** — strip or match pagination params so you count only
   items from this specific page, not accumulated totals

### Interpreting coverage ratio

- `1.0` — full coverage (extracted count matches declared count)
- `0.5-0.9` — partial coverage (some items missed, likely pagination or selector issue)
- `0.0-0.4` — extraction failure (selectors wrong or page structure different than expected)

Run the probe after extraction on the first page of each new page type. If
coverage is below 1.0, investigate before proceeding with bulk extraction.

## Per-entity-type field triage

After collecting data, run a fill-rate analysis per entity type. For each field,
count how many records have a real value vs `null` vs `"__UNOBSERVABLE__"` vs
omitted.

```
Field triage for entity type: product_aggregation (42 records)
  title:         42/42 (100%) OK
  price:         40/42 ( 95%) OK
  seller:        0/42  (  0%) — all null (confirmed absent for this type)
  offer_count:   42/42 (100%) OK

Field triage for entity type: individual_offer (28 records)
  title:         28/28 (100%) OK
  price:         28/28 (100%) OK
  seller:        5/28  ( 18%) LOW — extraction likely broken
  stock:         3/28  ( 11%) LOW — extraction likely broken
  delivery:      27/28 ( 96%) OK
```

**Status thresholds:**

| Fill rate | Status | Action |
|-----------|--------|--------|
| 100% or all `null` | OK | No action |
| 50-99% | LOW | Check if page structure varies across pages |
| 0-49% (not all null) | BROKEN | Selector is wrong — redo discovery step |
| Any `"__UNOBSERVABLE__"` | BLOCKED | Page was inaccessible — retry with different session or wait |

The "all null" exception is important: if every record for an entity type shows
`null` for a field, that's correct — the field doesn't exist for that type.
The problem is when some records have values and most don't — that's a broken
selector. `"__UNOBSERVABLE__"` records should be excluded from fill-rate
calculations since they represent pages that were never inspected, not extraction
failures.

**When to run triage:** After the first full extraction pass, before declaring
the extraction complete. Include the triage report in the merge output.

## Closure certificates

Use when a crawl needs to make a formal ABSENT_PROVEN claim — the statement
"this data does not exist within scope" rather than "we did not find it."

A closure certificate is a structured evidence package that authorizes the
system to treat missing values as confirmed absence. Without it, missing values
must remain `UNKNOWN_NOT_OBSERVED` (i.e. `null` in extraction JS).

### Prerequisites

All three conditions must be true before emitting a certificate:

| Condition | Evidence | Source |
|-----------|----------|--------|
| Pagination exhausted | No next-page element or final page reached | Extraction readiness sequence step 9 |
| Coverage ratio == 1.0 | Extracted count == page-declared count | Coverage probe |
| No unresolved required unknowns | Zero `__UNOBSERVABLE__` fields in required field set | Field triage (BLOCKED status) |

If any category has `coverage_rating: UNKNOWN` per `coverage-accounting.md`, the
certificate cannot be emitted — UNKNOWN blocks absence claims.

### Certificate template

```json
{
  "closure_certificate": true,
  "scope": "site/page_type/session_id",
  "basis": {
    "pagination_exhausted": true,
    "coverage_ratio": 1.0,
    "unobservable_required_count": 0
  },
  "coverage": {
    "declared": 21,
    "extracted": 21,
    "deduped": 0
  },
  "unobservable_count": 0,
  "field_triage_summary": {
    "product_aggregation": "OK",
    "individual_offer": "OK"
  },
  "valid_until": "site content changes or session expires"
}
```

### When NOT to emit

- Any entity type has BROKEN or LOW field triage status (selectors are wrong)
- Coverage rating is UNKNOWN per `coverage-accounting.md`
- Pages were blocked during the crawl (`unobservable_count > 0` for required fields)
- The site uses infinite scroll or cursor-based pagination with no total count

### Integration with field triage

The prerequisite "no unresolved required unknowns" means all entity types must
have OK status (100% fill or all `null`) from the field triage table. BROKEN,
LOW, or BLOCKED statuses prevent certificate emission.

For saturation-based stopping (0 new items for K pages but no page-declared
count), see `coverage-accounting.md`. Saturation is an efficiency signal — it
does NOT authorize a closure certificate.

## Extraction readiness sequence

Every page extraction must follow this sequence. Skipping steps produces silent
data loss — blocked pages return empty results that look identical to real
absence.

```
1. navigate: new_tab(url) or goto_url(url)
2. wait for content: wait_for_content(min_text=200)
3. check block: if result.block or result.ok is False → emit __UNOBSERVABLE__
4. extract: js(extraction_snippet)
5. check js result: if {"_js_undefined": True} → check tab state, may be detached; if {"_js_error": ...} → extraction crashed; if {"_quota_error": true} → dump now
6. check suspect: if result.suspect → wait 2s, retry once; if still suspect → try embedded JSON fallback
7. validate first page: check primary key field has non-null values
8. check containers each page: if containers_found drops to 0 unexpectedly → investigate
9. paginate or continue
```

### Why wait_for_content() instead of wait_for_load() + fixed delay

`wait_for_load()` fires on the browser load event — it proves the browser saw
a page, not that the site served content. Many sites return a WAF challenge
shell with `document.readyState == "complete"` and <200 characters of text.
A fixed `wait(3.0)` doesn't detect this either.

`wait_for_content(min_text=200)` polls until the page has meaningful text OR
detects a block. It returns `{ok, reason, url, title, text, textLength, html, htmlLength, readyState, block}` so you can
distinguish three outcomes:

| `ok` | `block` | Meaning | Action |
|------|---------|---------|--------|
| true | false | Content rendered | Run extraction JS |
| false | false | Timeout, empty content | Emit `__UNOBSERVABLE__` |
| false | true | Hard block or WAF challenge (403, access denied) | Emit `__UNOBSERVABLE__` |

**When timeout occurs with no block (`ok: false, block: false`):** This means
`wait_for_content()` waited the full timeout and the page never reached the
minimum text threshold. Three likely causes:

1. **SPA with slow async rendering** — the page loads but content fetches
   slowly. Try `wait_for_content(min_text=200, timeout=30.0)` with a longer
   timeout, or check `readyState` via `js("document.readyState")` — if
   `"interactive"` the page is still loading.
2. **Empty results page** — the page loaded but genuinely has no content (zero
   results for this query). Take a screenshot to confirm. These are correct
   empty pages, not failures.
3. **Geo-fence or region restriction** — the page loaded but shows a region
   error instead of expected content. Check `result.text` for messages like
   "not available in your region" — these should be treated as `__UNOBSERVABLE__`.

Use `wait_for_content()` as the default after navigation for any page where
extraction will run. Reserve `wait_for_load()` for pages where you only need
the load event (clicking buttons, checking URL redirects).

### Handling js() return values

`js()` can return four problematic outcomes after extraction:

| Return | Meaning | Action |
|--------|---------|--------|
| `{"_js_undefined": True}` | JS returned `undefined` | Extraction function has no return statement, tab may be detached — check `current_tab()` then fix snippet |
| `{"_js_error": msg}` | JS threw an exception | Syntax error, null dereference, etc. — read `msg` and fix |
| `{"added": 0, "suspect": true}` | Containers exist but extraction found nothing | Wait 2s and retry once; if still 0, try embedded JSON fallback |
| `{"_quota_error": true}` | localStorage quota exceeded | Dump accumulated results immediately before continuing |

Always check `"_js_undefined" not in result` and `"_js_error" not in result`
before treating the extraction output as valid data. A `_js_undefined` return
means either the extraction snippet returned nothing or the tab was destroyed
mid-evaluation — check tab state before retrying.

### First-page validation

After extracting the first page of each page type, verify the extraction works
before committing to a full crawl. Check that the primary key field (title,
product_name, or equivalent) has non-null values on at least one record:

```python
# After first-page extraction
results = js(extraction_snippet)
if results:
    primary_values = [r.get('title') or r.get('product_name') for r in results
                      if r.get('title') is not None and r.get('title') != '__UNOBSERVABLE__']
    if not primary_values:
        print("BROKEN: primary key field is null/empty on all records — selectors wrong")
        # Stop and redo selector discovery before continuing
```

This catches broken selectors after one page instead of after the entire crawl.

### Handling partial blockage during crawls

When some pages in a crawl are blocked and others aren't:

1. **Record blocked URLs** — accumulate them in a separate set, don't silently
   skip them.
2. **Mark results as `__UNOBSERVABLE__`** — not null or empty string.
3. **Continue the crawl** — one blocked page doesn't mean all pages are blocked.
4. **Retry with backoff** — if blocks increase in frequency, apply exponential
   backoff between requests (see `product-search.md` pagination algorithm for
   the block counter pattern).
5. **Report unobservable fraction** — after the crawl, report what percentage
   of pages were blocked alongside the coverage ratio. A crawl with 95% coverage
   but 30% unobservable pages has a different reliability profile than one with
   95% coverage and 0% unobservable.

### Zero-result disambiguation

When extraction returns `added: 0`, three explanations are possible:

1. **Page is genuinely empty** — no items for this query. Correct, move on.
2. **Items exist but haven't rendered** — SPA with async loading. Wait and retry.
3. **Items exist but selectors are wrong** — structural change or wrong selectors.

All three produce the same output unless the extraction JS includes a **container
diagnostic**. Every extraction snippet should check for expected container elements
and report their count:

```javascript
// At the end of extraction JS, before returning
const containers = document.querySelectorAll('a[href*="/product-"]');
return {
  total: results.length,
  added: added,
  url: location.href,
  containers_found: containers.length,
  suspect: (added === 0 && containers.length > 0)
};
```

**Interpreting the `suspect` flag:**

| `added` | `containers_found` | `suspect` | Meaning | Action |
|---------|--------------------|-----------|---------|--------|
| 0 | 0 | false | Page is empty | Continue to next page |
| >0 | >0 | false | Normal extraction | Continue |
| 0 | >0 | true | Containers exist but extraction missed them | Wait 2s and retry once; if still 0, selectors may be broken |

The `suspect` flag catches the most dangerous failure mode: a page that looks
like it has 0 results but actually has items the selectors can't find. Without
it, the agent silently converges to incomplete data.

### Embedded JSON fallback

When DOM extraction returns 0 items on a page that should have items (`suspect`
is true after retry), try embedded JSON extraction before giving up. Many sites
embed the same data in `<script>` tags that DOM extraction misses — especially
when content renders asynchronously.

```javascript
// Fallback: try embedded JSON when DOM extraction fails
if (added === 0 && containers.length > 0) {
  // Check common embedded JSON sources
  const nextData = document.querySelector('#__NEXT_DATA__');
  if (nextData) {
    try {
      const data = JSON.parse(nextData.textContent);
      // Navigate the JSON structure to find items
      // Adapt this path to the specific site's JSON structure
      const items = data?.props?.pageProps?.items || [];
      return { total: items.length, added: 0, fallback_items: items.length,
               fallback_source: 'NEXT_DATA', suspect: false };
    } catch (e) {}
  }
  // Check window variables
  const windowKeys = Object.keys(window).filter(k => k.startsWith('__'));
  if (windowKeys.length > 0) {
    return { total: 0, added: 0, fallback_items: 0,
             fallback_source: 'none', window_keys: windowKeys, suspect: true };
  }
}
```

See `data-source-exploration.md` for the full embedded JSON discovery workflow
and common framework patterns. The fallback is a per-page safety net, not a
replacement for primary DOM extraction.

### Container fingerprinting across pages

First-page validation catches broken selectors on the first page. But if a site
changes page layout between categories (different product types with different
DOM structures), selectors that work on page 1 may silently fail on page 20.

Check container element counts on every page, not just the first. If the count
drops to 0 on a page that should have items, the page structure changed:

```python
# During crawl loop, after each extraction
result = js(extraction_snippet)
if result.get('containers_found', 0) == 0 and expected_items > 0:
    print(f"WARNING: no containers on {url} — page structure may have changed")
    # Don't assume convergence — investigate before continuing
```

This is lightweight (one extra property in the return value) and catches
structural changes that convergence detection alone would miss.

## Workflow summary

This document covers steps from two phases of domain skill creation. Steps
1-5 belong in Phase 1 (Explore). Steps 6-9 belong in Phase 3 (Test).

### During Phase 1 — Explore

1. **Navigate** to a representative page of each page type
2. **Wait for content** — use `wait_for_content()`, not `wait_for_load()` + delay
3. **Discover selectors** — probe CSS classes via `js()`, don't rely
   only on a11y snapshots
4. **Identify entity types** — determine what distinct data records appear on
   each page type, and which fields belong to each
5. **Write extraction JS** — use four-state semantics (`null` for confirmed
   absent, `"__UNOBSERVABLE__"` for blocked pages, omit key for not applicable)

### During Phase 3 — Test

6. **Run first-page validation** — after extracting the first page of each type,
   verify primary key fields have non-null values; stop and fix selectors if not
7. **Run coverage probe** — compare extracted count against page-declared count
8. **Run field triage** — after a full pass, check fill rates per entity type;
   fix BROKEN selectors before declaring done
9. **Report unobservable fraction** — count blocked pages and report alongside
   coverage ratio
10. **Emit closure certificate** (optional) — if all entity types pass field triage
    as OK, coverage ratio is 1.0, and no required fields are unobservable, emit a
    closure certificate to formalize the ABSENT_PROVEN claim. See "Closure
    certificates" section.

## Cross-references

- **Selector discovery** plugs into `data-source-exploration.md` exploration
  order after backend capability testing (step 4) and before authenticated
  source inventory (step 6).
- **Coverage probes** plug into `product-search.md` Step 5 (coverage
  verification) as a per-page check alongside the existing cross-query checks.
- **Field triage** plugs into `../agent-workspace/domain-skills/surface-map-pattern.md` Verification
  section as a per-extraction check alongside the existing structural checks.
- **Entity-type identification** is a domain-specific analysis step — document
  the results in each domain skill's `overview.md`.
- **Block handling during pagination** is documented in `product-search.md`
  pagination algorithm (backoff after blocks, block counter).
- **Closure certificates** cross-reference `coverage-accounting.md` UNKNOWN rating
  — UNKNOWN blocks absence claims, preventing certificate emission.
- **Saturation-based stopping** in `coverage-accounting.md` provides an efficiency
  signal for when to stop exploring; saturation is distinct from closure.
- **Failure-mode table** below maps each failure mode to its detection, mitigation,
  and residual risk.

## Failure-mode coverage

| Failure mode | Detection | Mitigation | Residual risk |
|---|---|---|---|
| Missed dynamic content | `wait_for_content()` timeout with no block flag | Scroll/click exploration, longer timeout, `wait_for_content(min_text=200, timeout=30)` | Anti-bot, auth gates, session-specific content |
| Missed list items | Coverage probe < 1.0, `suspect` flag true | Embedded JSON fallback, selector rediscovery | Irregular templates, hidden pagination, personalization |
| Missed fields | `field_triage()` LOW/BROKEN status | Selector discovery via `js()` probes, local retry | Ambiguous labels, fields only visible after interaction |
| Hallucinated values | Schema validation, grounding checks | `?? null` semantics (no `|| ''` fallbacks) | Model may infer values under pressure |
| False absence | No closure certificate emitted | Four-state semantics, closure certificates | Global absence unprovable without scope definition |
| Blocked pages | `detect_block_page()`, `wait_for_content()` block=true | `__UNOBSERVABLE__` state, session retry with `seed_browser_session()`, backoff | Persistent blocks, geo-fences |
| Overconfident stopping | No saturation or coverage check | `CrawlState.saturation_reached()`, marginal discovery curve | Sites with burst discovery patterns |
| Duplicate records | `CrawlState.add()` returns False | Dedup by key field, `summary()["deduped"]` count | Weak entity resolution across different key formats |
| Silent pagination end | `containers_found` drops to 0 | Container fingerprinting on every page | Structural changes mid-crawl |
