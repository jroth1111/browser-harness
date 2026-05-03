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

## Tri-state field semantics

Solve the ambiguity at the source. Every extracted field uses three states:

| JS value | CSV value | Meaning |
|----------|-----------|---------|
| `"value"` | `value` | Found and extracted |
| `null` | `(absent)` | Confirmed absent on this entity type |
| key omitted | `(not checked)` | Field not applicable to this entity type |

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

**Why this matters:** A `null` in a CSV tells the analyst "the extractor looked
and found nothing." An omitted column tells the analyst "this field doesn't apply."
An empty string tells the analyst nothing — it's ambiguous.

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
// Run via evaluate_script on a representative page
() => {
  const probes = {};
  // Check which classes exist and what they contain
  const classList = ['.title', '.price', '.seller', '.stock', '.delivery',
                     '.name', '.numberTxt', '.priceTxt', '.dayNumber'];
  for (const cls of classList) {
    const els = document.querySelectorAll(cls);
    probes[cls] = {
      count: els.length,
      samples: Array.from(els).slice(0, 3).map(e => e.textContent.trim())
    };
  }
  // Also check for entity-type containers
  const productLinks = document.querySelectorAll('a[href*="/product-"]');
  const itemLinks = document.querySelectorAll('a[href*="/items-"]');
  probes['_entity_types'] = {
    product_aggregations: productLinks.length,
    individual_offers: itemLinks.length
  };
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
other will always return `""`. The tri-state approach requires knowing which
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
count how many records have a real value vs `null` vs omitted.

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

The "all null" exception is important: if every record for an entity type shows
`null` for a field, that's correct — the field doesn't exist for that type.
The problem is when some records have values and most don't — that's a broken
selector.

**When to run triage:** After the first full extraction pass, before declaring
the extraction complete. Include the triage report in the merge output.

## Workflow summary

This document covers steps from two phases of domain skill creation. Steps
1-4 belong in Phase 1 (Explore). Steps 5-6 belong in Phase 3 (Test).

### During Phase 1 — Explore

1. **Navigate** to a representative page of each page type
2. **Discover selectors** — probe CSS classes via `evaluate_script`, don't rely
   only on a11y snapshots
3. **Identify entity types** — determine what distinct data records appear on
   each page type, and which fields belong to each
4. **Write extraction JS** — use tri-state semantics (`null` for confirmed
   absent, omit key for not applicable)

### During Phase 3 — Test

5. **Run coverage probe** — after extracting the first page of each type,
   compare extracted count against page-declared count
6. **Run field triage** — after a full pass, check fill rates per entity type;
   fix BROKEN selectors before declaring done

## Cross-references

- **Selector discovery** plugs into `data-source-exploration.md` exploration
  order after backend capability testing (step 4) and before authenticated
  source inventory (step 5).
- **Coverage probes** plug into `product-search.md` Step 5 (coverage
  verification) as a per-page check alongside the existing cross-query checks.
- **Field triage** plugs into `surface-map-pattern.md` Verification section as
  a per-extraction check alongside the existing structural checks.
- **Entity-type identification** is a domain-specific analysis step — document
  the results in each domain skill's `overview.md`.
