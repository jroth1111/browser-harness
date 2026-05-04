# Amazon — Product Search & Data Extraction

Field-tested against amazon.com.au on 2026-05-04 across 4 product categories
(headphones, keyboards, SSDs, air fryers). No CAPTCHA or bot detection triggered.
Currency is AUD. Amazon AU shows "RRP" where US shows "List Price".

**Use Amazon to fulfill a decision, not to make the decision.** Define requirements
and target price before searching. Research outside Amazon first. This skill covers
finding candidates on Amazon and validating them.

## Multi-Surface Search Algorithm

Amazon search surfaces what makes Amazon money, not what matches user intent. No
single query or surface produces a complete result set. The strategy combines
multiple surfaces, scopes the search index before querying, and re-ranks client-side.

**Core tactics:** scope department before querying, search expansively across multiple
departments and synonyms, deduplicate by ASIN afterward, re-rank client-side.

```
Phase 0: Pre-search research (outside Amazon)
  0. Define requirements, target price, deal-breakers before searching
  1. Research independently: reviews, Reddit, brand sites, recall/defect checks
  2. Identify real brands and common failure modes

Phase 1: Department-scoped search (primary discovery)
  3. Select the most specific department for the product category
  4. Craft precise query: quoted phrase + distinguishing specs
  5. Navigate to department-scoped search URL
  6. Apply sidebar filters: rating, price range, Prime, review count
  7. THEN change sort from Featured to Avg. Customer Review or Price
  8. Extract all results, mark sponsored vs organic
  9. Paginate until convergence
  10. Collect ASINs into candidate set

Phase 2: Full-catalog + multi-department + synonyms (coverage expansion)
  11. Run same query without department scope (always returns 60)
  12. Run 2-3 synonym/variant queries (different vocabulary = different index slice)
  13. For cross-category products, try each relevant department separately
  14. Deduplicate new ASINs against candidate set

Phase 3: Curated category surfaces (gap fill — highest coverage delta)
  15. Use clear-search-bar trick on Phase 1 department → /b?node={id}
  16. Extract via link pattern a[href*="/dp/"] (different DOM from search)
  17. Fetch parent best-sellers page: /gp/bestsellers/{parent-slug}/
  18. Extract subcategory links via a[href*="bestsellers"] for {parent}/{node} URLs
  19. Fetch subcategory best-sellers page (30 ASINs, mostly new vs keyword)
  20. Fetch New Releases page (same DOM as best sellers, surfaces unranked items)
  21. Add new ASINs to candidate set

Phase 4: Related-product expansion (~10-32 new ASINs per page)
  22. For top-matching ASINs from Phases 1-3, visit product pages
  23. Extract [data-asin] on product page (captures all widgets)
  24. Add new ASINs to candidate set

Phase 5: Client-side ranking (override Amazon's commercial sort)
  25. Re-rank all candidates by: relevance > rating > review count > price
  26. Apply title relevance filter (must contain query core terms)
  27. Apply quality filter: 4+ stars AND 50+ reviews minimum
  28. Present ranked results with source surface tagged

Phase 6: Listing validation (trust verification)
  29. Verify seller, variant accuracy, review authenticity, price history
  30. Compare unit economics and outside-Amazon alternatives
  31. Buy only if Amazon wins on fit, trust, price, and fulfillment
```

### When to use which phase

| Search type | Phases needed |
|-------------|-------------|
| Specific product lookup | Phase 1 only |
| Price comparison | Phase 1 + Phase 5 |
| Category survey | Phase 1 + Phase 3 |
| Exhaustive discovery | All 6 phases |
| "Find alternatives to X" | Phase 1 + Phase 4 |
| Cross-category product | Phase 1 x 2-3 departments + Phase 3 |
| Deal hunting | Phase 1 + `&pct-off=` + Warehouse |
| High-risk/counterfeit concern | Phase 0 + Phase 1 + Phase 6 |

### Discovery surfaces (ordered by empirical coverage)

| Surface | ASINs | Extraction method |
|---------|-------|-------------------|
| Category landing page | 78-89 | `a[href*="/dp/"]` link extraction |
| Full-catalog `/s?k=` | 60 | Search result extractor |
| Dept-scoped `/s?k=&i=` | 22-33 | Search result extractor |
| Best Sellers `/gp/bestsellers/{parent}/{node}/` | 30 | Best sellers extractor |
| New Releases `/gp/new-releases/{slug}/` | 30 | Same as best sellers |
| Related products (per product page) | 10-32 | `[data-asin]` on product page |
| Synonym variant query | varies | Same as search extractor |
| URL-param enhanced (`&pct-off=`, `&s=`) | varies | Same as search extractor |

Full-catalog consistently returns 60. Category landing consistently 78-89. Best
sellers consistently 30. These are Amazon's page-size constants.

## Extractors

### Search results

```python
# Navigate (use new_tab for first visit)
tid = new_tab("https://www.amazon.com.au/s?k=%22noise+cancelling%22+headphones&i=electronics")
wait_for_content(min_text=200)

# Extract
results = js("""
  Array.from(document.querySelectorAll('[data-component-type="s-search-result"]')).map(el => {
    var asin = el.getAttribute('data-asin');
    return {
      asin: asin,
      title: el.querySelector('h2 span')?.innerText?.trim(),
      price: el.querySelector('.a-price .a-offscreen')?.innerText,
      list_price: el.querySelector('.a-text-price .a-offscreen')?.innerText,
      rating: el.querySelector('[aria-label*="out of 5 stars"]')?.getAttribute('aria-label')?.split(' ')[0],
      reviews: el.querySelector('[aria-label*="ratings"]')?.getAttribute('aria-label'),
      is_sponsored: !!el.querySelector('.puis-sponsored-label-text'),
      url: asin ? 'https://www.amazon.com.au/dp/' + asin : null
    };
  }).filter(r => r.asin)
""")
```

Field notes:
- `price`: `.a-price .a-offscreen` returns formatted string e.g. `"$69.99"`
- `list_price`: Only present when item is on sale (was/now pricing)
- `reviews`: Use `[aria-label*="ratings"]` — NOT `.a-size-base.s-underline-text` (shows wrong text on sponsored)
- `is_sponsored`: `.puis-sponsored-label-text` — typically 6-12 first results
- `url`: Construct from ASIN — `h2 a` does NOT exist on AU search cards

**Sponsored results:** Do NOT auto-discard. They're often genuinely relevant products
that sellers paid to promote. Extract `is_sponsored`, re-rank all results (sponsored +
organic) by relevance client-side, disclose sponsored status in output.

**Result count:**
```python
count_text = js("document.querySelector('[data-component-type=\"s-result-info-bar\"] h1')?.innerText?.trim()")
# Returns e.g.: '1-16 of over 40,000 results for "wireless mouse"\nSort by:\n...'
```

### Product detail page

```python
goto_url("https://www.amazon.com.au/dp/B08Z6X4NK3")
wait_for_content(min_text=200)

detail = js("""
  ({
    title: document.querySelector('#productTitle')?.innerText?.trim(),
    price: (function() {
      var whole = document.querySelector('.a-price-whole')?.innerText?.replace(/[\\n.]/g,'');
      var frac  = document.querySelector('.a-price-fraction')?.innerText;
      return (whole && frac) ? '$' + whole + '.' + frac
           : document.querySelector('.a-price .a-offscreen')?.innerText || null;
    })(),
    list_price: document.querySelector('.basisPrice .a-offscreen')?.innerText,
    rating: document.querySelector('#acrPopover')?.getAttribute('title'),
    review_count: document.querySelector('#acrCustomerReviewText')?.innerText,
    availability: document.querySelector('#availability span')?.innerText?.trim(),
    brand: document.querySelector('#bylineInfo')?.innerText?.trim(),
    asin: document.querySelector('input[name="ASIN"]')?.value,
    bullet_points: Array.from(document.querySelectorAll('#feature-bullets li span.a-list-item'))
                       .map(e => e.innerText?.trim()).filter(t => t)
  })
""")
```

Field notes:
- `#priceblock_ourprice` and `#priceblock_dealprice` are **legacy** — return `null`
- Price: construct from `.a-price-whole` + `.a-price-fraction` (strip `\n` and `.`)
- `brand`: format varies — "Brand: Philips" (kitchen) vs "Visit the SanDisk Store" (tech)
- `#productOverview_feature_div table` has structured specs if bullets are sparse

### Best Sellers page

```python
goto_url("https://www.amazon.com.au/gp/bestsellers/electronics/7058119051/")
wait_for_content(min_text=200)

items = js("""
  Array.from(document.querySelectorAll('[data-asin]')).map(el => {
    var container = el.closest('[id="gridItemRoot"]') || el;
    return {
      asin: el.getAttribute('data-asin'),
      rank: container.querySelector('[class*="zg-bdg-text"]')?.innerText,
      title: container.querySelector('img[alt]')?.getAttribute('alt'),
      price: container.querySelector('.p13n-sc-price, .a-size-base.a-color-price')?.innerText,
      url: 'https://www.amazon.com.au/dp/' + el.getAttribute('data-asin')
    }
  }).filter(r => r.rank)
""")
```

**URL format (AU-specific):**
- Top-level: `/gp/bestsellers/{slug}/` e.g. `/gp/bestsellers/electronics/`
- Subcategory: `/gp/bestsellers/{parent-slug}/{node-id}/` e.g. `/gp/bestsellers/electronics/7058119051/`
- New Releases uses same format: `/gp/new-releases/{slug}/{node}/` — identical DOM

Discover subcategory links from parent page:
```python
subcategories = js("""
  Array.from(document.querySelectorAll('a[href*="bestsellers"]')).map(a => ({
    text: a.innerText?.trim(),
    href: a.href
  })).filter(l => l.text && l.href.includes('/gp/bestsellers/'))
""")
```

### Category landing page (clear-search-bar trick)

```python
# Navigate to department search first
goto_url("https://www.amazon.com.au/s?k=headphones&i=electronics")
wait_for_content(min_text=200)

# Clear search bar and submit — loads curated category view
js("document.querySelector('#twotabsearchtextbox').value = ''")
js("document.querySelector('#nav-search-submit-text').closest('form').submit()")
wait_for_content(min_text=200)

# Extract — different DOM, no [data-component-type] or [data-asin]
category_asins = js("""
  Array.from(new Set(
    Array.from(document.querySelectorAll('a[href*="/dp/"]')).map(a => {
      var match = a.href.match(/\\/dp\\/([A-Z0-9]{10})/);
      return match ? match[1] : null;
    }).filter(Boolean)
  ))
""")
```

### Related products (from product detail page)

```python
related = js("""
  Array.from(document.querySelectorAll(
    '[data-asin]:not([data-asin=""])'
  )).map(el => el.getAttribute('data-asin'))
  .filter((v, i, a) => a.indexOf(v) === i)
""")
```

### Pagination

```python
next_url = js("document.querySelector('.s-pagination-next')?.href")
if next_url:
    goto_url(next_url)
    wait_for_content(min_text=200)
```

### Category breadcrumbs

```python
categories = js("""
  Array.from(document.querySelectorAll('#departments a.a-link-normal')).map(a => ({
    name: a.innerText?.trim(),
    href: a.href
  }))
""")
```

### Alternative navigation patterns

```python
# Search box typing (when you need category filtering via UI)
goto_url("https://www.amazon.com.au")
wait_for_content()
js("document.querySelector('#twotabsearchtextbox').focus()")
js("document.querySelector('#twotabsearchtextbox').click()")
wait(0.3)
type_text("wireless mouse")
wait(0.3)
press_key("Enter")
wait_for_content(min_text=200)

# Direct product page
goto_url("https://www.amazon.com.au/dp/B08Z6X4NK3")
wait_for_content(min_text=200)
```

### Parallel tab workflow (exhaustive searches)

For exhaustive searches, use multiple surfaces in separate tabs. Each tab uses
a different combination to capture items any single view misses. With CDP, implement
as sequential tab switches (browser is single-session):

```
Tab 1: Department + keyword + 4+ stars + Prime
Tab 2: Same query + &pct-off=30- + &s=price-asc (deep-discount view)
Tab 3: Category landing page (clear-search-bar trick)
Tab 4: Best Sellers + New Releases
```

## Gotchas

- **Use `new_tab()` for first Amazon visit** — `goto_url()` can silently fail on first navigation
- **`.zg-item-immersion` is gone** — Best Sellers uses `[data-asin]` + `[id="gridItemRoot"]` + `img[alt]`
- **`.a-size-base.s-underline-text` is unreliable for review count** — shows unrelated text on sponsored. Use `[aria-label*="ratings"]`
- **`#priceblock_ourprice` is legacy** — construct from `.a-price-whole` + `.a-price-fraction`
- **Sponsored appear first** — 6-12 of first results are typically sponsored. Mark with `is_sponsored`, re-rank client-side
- **`data-asin` can be empty string** — filter with `.filter(r => r.asin)`
- **`.a-price-whole` has trailing `\n.`** — strip with `.replace(/[\n.]/g,'')`
- **Amazon appends `?th=1`** — normal redirect, `input[name="ASIN"]` has the clean ASIN
- **Use `wait_for_content()` not `wait_for_load()`** — search results load async
- **AU product pages render slowly** — if `#productTitle` is null, page hasn't finished
- **System titles are brand-only** — for desktops/laptops, `h2 span` returns just brand name, need `#productTitle` from detail page
- **List Price / RRP is often inflated** — verify with Keepa
- **`#bylineInfo` format varies by category** — "Brand: Philips" vs "Visit the SanDisk Store"
- **Best sellers AU: must use `{parent-slug}/{node-id}`** — bare node IDs 404, bare slugs return empty
- **Check page title for "undefined"** — signals invalid best-seller URL
- **Not all products have best-seller subcategories** — keyboards, SSDs, air fryers don't on AU

## Query Construction

### URL parameters

**Discount filter** (`&pct-off=`, highly effective):
- `&pct-off=50-` — 50%+ off, `&pct-off=30-70` — 30-70% off range
- Amazon rewrites internally: `&pct-off=30-` → `&rh=p_8%3A30-` (both work as input)
- **Reduces sponsored to 0-8%** across all tested categories. More effective on higher-value products.
- Combine: `/s?k=headphones&i=electronics&pct-off=30-`

**Sort params** (decorative — do NOT trust for ordering):
- `&s=price-asc`, `&s=price-desc`, `&s=review-rank`, `&s=date-desc-rank`
- `&s=exact-aware-popularity-rank` — best sellers sort
- Both `price-asc` and `price-desc` can produce identical ordering — Amazon ignores sort direction
- 11-14 price-order violations per page across all categories
- Use solely for coverage expansion (different result set), re-sort client-side
- Reduce result count by 13-25%

**Other params:**
- `&i={department}` — department scope: `electronics`, `computers`, `kitchen`, `home`, `office`
- `&prime=true` — Prime-only results
- `&rh=n%3A<node>` — category node filter
- `&page=N` — pagination

### Query syntax

| Syntax | Effect | Example |
|--------|--------|---------|
| `"exact phrase"` | Requires exact match, disables fuzzy | `"noise cancelling headphones"` |
| `-term` | Excludes results (unreliable) | `headphones -kids -gaming` |

`-term` exclusions are unreliable and query-dependent. E2e showed they failed entirely
for keyboards (30/33 results still contained excluded terms). Always combine with
client-side title filtering.

### Construction rules

1. **Scope department first** — `&i=electronics` not site-wide
2. **Use exact phrases in quotes** — disables fuzzy matching
3. **Run multiple departments** — keyboards appear in both `&i=electronics` and `&i=computers`
4. **Run synonym variants** — "noise cancelling" and "ANC" return disjoint sets
5. **Expansive search, dedupe post-hoc** — overlap between departments is expected and desired

### Filter-then-sort sequence

Apply sidebar filters first (rating, price, Prime, review count), THEN change sort.
Post-filter sorts are more stable because the pool is already cleaned. If switching
sort causes result count to plummet, note top items from Featured view first.

## Quality Filters (Phase 5)

| Filter | Threshold | Purpose |
|--------|-----------|---------|
| Star rating | 4+ stars | Eliminates low-quality products |
| Review count | 50+ reviews | Excludes fake-inflated new listings |
| Price range | Context-dependent | Eliminates accessories mislabeled as main products |
| Title relevance | Must contain query core terms | Removes semantic drift matches |

## Listing Validation (Phase 6)

For serious candidates, verify:
- **Seller:** prefer "Sold by [official brand]" or "Sold by Amazon" for high-counterfeit categories
- **Reviews:** sort by most recent, read 2-4 star, check for review hijacking (reviews mentioning different product)
- **Price:** verify "was" price with Keepa/CamelCamelCamel — frequently inflated
- **Variants:** confirm reviews/price/size refer to the exact variant being purchased
- **Q&A:** search for must-have specs, reveals incompatibilities

### Buying channel risk matrix

**Safe on Amazon:** low-risk commodities, known brands with official storefronts.
**Consider buying direct:** beauty, supplements, baby products, batteries, safety gear,
high-end electronics, anything frequently counterfeited.

### External verification tools

| Tool | What it catches |
|------|-----------------|
| Keepa / CamelCamelCamel | Fake "was" prices, price history, best time to buy |
| Fakespot / ReviewMeta | Fake/inflated reviews, review merging across variants |
| `site:amazon.com.au` via Google | Products Amazon suppresses or buries |

## Supplementary Surfaces

### Amazon Warehouse / Renewed

Warehouse (returns/open-box) and Renewed (refurbished) are separate inventory, often
40-60% cheaper. Access: product pages show "Buy it renewed" or "Used – Like New"
below main price. Same ASINs as new items, separate buybox entries.

### Google site search

`site:amazon.com.au "product name"` bypasses A10 entirely, uses Google's relevance
algorithm. Surfaces suppressed products. Extract ASINs via `/dp/([A-Z0-9]{10})` regex
on Google result URLs. Supplementary, not replacement for Amazon-native search.

## CAPTCHA Detection

No CAPTCHA encountered during 4-category e2e testing with a logged-in Chrome session.
Defensive check:

```python
text = js("document.body.innerText.slice(0,500)") or ""
url = page_info()["url"]
captcha = ("captcha" in text.lower() or "enter the characters" in text.lower()
           or "captcha" in url.lower() or "validateCaptcha" in url)
```

## Appendix A: Search Pathologies

Amazon's search engine (A10, current 2025-2026) is a revenue- and conversion-optimized
system. The pathologies below explain *why* the multi-surface strategy is necessary.
They are reference material — the algorithm above is the actionable strategy.

### Core 1: Commercialized ranking, not neutral relevance

Default "Featured" ordering blends text relevance, sales velocity, conversion
probability, availability, ratings, fulfillment, profitability, ad pressure,
personalization, and experiments. Sponsored products dominate top positions.
Organic results rank by commercial metrics, not keyword match. The first screen
is a paid marketplace, not a neutral result set.

**Strategy implication:** Extract `is_sponsored`, re-rank client-side.

### Core 2: Recall failure — relevant ASINs missing

Relevant products fail to appear in keyword search but surface through category
pages, "Customers also bought," bestseller lists, and other discovery surfaces.
Causes: search suppression, cold-start invisibility, feedback-loop ranking,
exact-match failure, availability artifacts, pagination instability.

**Strategy implication:** Keyword search alone insufficient. Use multiple surfaces.
E2e: keyword search found 1 of top 30 best-seller headphones.

### Core 3: Sort/filter systems are decorative

Sort orders don't operate on the full relevant set. Amazon builds a restricted
candidate set first, then "sorts" that subset. Both `price-asc` and `price-desc`
can produce the same ordering. Applying filters can radically change the result
universe, not just filter the visible set.

**Strategy implication:** Sort for coverage diversity only. Always re-sort client-side.
Filter before sorting for more stable results.

### Core 4: Different surfaces use different retrieval

Keyword search, category browse, recommendation modules, bestseller pages, and
related-product widgets use different retrieval and ranking systems. Category pages
and bestseller lists surface better candidates than keyword search.

**Strategy implication:** Don't stop at keyword search. Use category browsing and
related-product widgets to recover missed products.

### Trust-signal manipulation

Fake reviews, review hijacking (listing inherits reviews from unrelated product),
keyword-stuffed titles, and duplicate/clone brand flooding distort trust signals.

**Strategy implication:** 50+ review count minimum. Check review authenticity signals.

### Personalization

Search changes based on browsing history, purchase history, location, Prime status,
device, and session. Fresh browser contexts reduce personalization but don't fix
Core 1-3.

### Marketplace integrity

Counterfeits surface in search with badges. High-risk categories: beauty, supplements,
batteries, safety gear, baby products, chargers, luxury goods.

## Appendix B: E2E Test Results (2026-05-04)

Field-tested against amazon.com.au across 4 product categories and 11 surfaces.

### Phase 1: Department-scoped search (PASS)

| Category | Dept | Results | Sponsored | Price range |
|----------|------|---------|-----------|-------------|
| Headphones | electronics | 33 | 9 | $50-$350 |
| Keyboards | electronics | 31 | 7 | $9-$370 |
| Keyboards | computers | 33 | 9 | overlapping |
| SSDs | computers | 33 | 9 | $67-$836 |
| Air fryers | kitchen | 22 | 6 | $50-$429 |

100% field coverage for prices, ratings, reviews, titles across all categories.

### Phase 2: Full-catalog + synonyms (PASS — high yield)

- Full-catalog always returns 60 results, 12 sponsored
- Synonyms find different products: "ANC" +18 new, "mech keyboard" 28, "external SSD" different top results
- "airfryer" ≈ "air fryer" — less useful for appliances

### Phase 3: Curated category surfaces (PASS — highest coverage delta)

- Category landing page: 78-89 ASINs consistently, different DOM from search
- Best sellers: 30 items when subcategory exists, 29/30 new vs keyword (headphones)
- Keyboards, SSDs, air fryers lack dedicated best-seller subcategories on AU
- New Releases: 30 items, identical DOM to best sellers
- Best sellers AU format: `/gp/bestsellers/{parent-slug}/{node-id}/` required

### Phase 4: Related products (PASS)

Related ASINs scale with product popularity:
- SanDisk SSD (78K reviews): 32 related
- EPOMAKER keyboard (3.4K reviews): 16 related
- Philips air fryer (350 reviews): 10 related

### Sort params (decorative across all categories)

| Category | `&s=price-asc` violations | Result count change |
|----------|--------------------------|-------------------|
| Headphones | 11 | 33→27 |
| Keyboards | 14 | 31→27 |
| SSDs | 11 | 33→26 |
| Air fryers | 8 | 22→18 |

SSD test: `&s=price-desc` produced same first-5 prices as `&s=price-asc`.

### Discount filter (consistently effective)

| Category | Baseline sponsored | With `&pct-off=30-` | Discount items |
|----------|-------------------|---------------------|---------------|
| Headphones | 27% | 8% | 10/26 |
| Keyboards | 23% | 4% | 8/25 |
| SSDs | 27% | **0%** | 3/24 |
| Air fryers | 27% | **0%** | 12/16 |

### Query exclusion syntax (FAIL — unreliable)

- Headphones `-kids -gaming`: appeared to filter organic but not sponsored
- Keyboards `-gaming -rgb`: failed entirely — 30/33 organic results still had excluded terms
- Cannot be relied upon for noise control

### Cross-category consistency summary

| Metric | Headphones | Keyboards | SSDs | Air fryers |
|--------|-----------|-----------|------|------------|
| Dept-scoped count | 33 | 31-33 | 33 | 22 |
| Full-catalog count | 60 | 60 | 60 | 60 |
| Sponsored baseline | 27% | 22-27% | 27% | 27% |
| Sponsored with `&pct-off=30-` | 8% | 4% | 0% | 0% |
| Category landing ASINs | 89 | 89 | 78-89 | 83 |
| Best sellers ASINs | 30 | N/A | 30 | 30 |

Strategy validated: multi-surface search increases coverage 4x over single keyword
search (134+ vs 33 unique ASINs for headphones).
