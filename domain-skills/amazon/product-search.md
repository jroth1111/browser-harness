# Amazon — Product Search & Data Extraction

Field-tested against amazon.com.au on 2026-05-02 using a Chrome session.
No CAPTCHA or bot detection was triggered during any test run.
Currency is AUD. Amazon AU shows "RRP" where US shows "List Price".

## Strategic Principle

**Use Amazon to fulfill a decision, not to make the decision.**

Amazon's search page is partly a discovery engine, partly an ad marketplace, and
partly a conversion-optimization system. Sponsored Products appear in search
results and product pages; the first visible results are not necessarily the best
consumer matches. For anything above impulse-buy level, the optimal workflow is:

1. Define requirements and target price before searching Amazon
2. Research outside Amazon first (independent reviews, Reddit, brand sites)
3. Use Amazon search to find candidates matching those pre-defined requirements
4. Validate candidates against trust signals (seller, reviews, price history)
5. Buy only if Amazon wins on fit, trust, price, and fulfillment

This skill covers steps 3-4. Steps 1-2 are pre-search research; step 5 is
post-search decision-making. Both are documented below as context.

## Search Pathologies

Amazon's search engine (A10, current 2025-2026) is a revenue- and
conversion-optimized system. Amazon describes "Featured" sorting as factoring
in sales history, customer actions, item details, availability, and delivery
speed. The FTC has alleged that Amazon degraded search by replacing relevant
organic results with paid ads; Amazon Science publications describe separate
work on semantic product search, COSMO knowledge graphs, and recommendations,
confirming different systems contribute to different surfaces.

The pathologies are organized into four core categories plus three
super-categories. Each includes the mechanism and implication for the strategy.

### Core 1: Commercialized ranking, not neutral relevance

The default "Featured" ordering is a blended marketplace ranking mixing text
relevance, sales velocity, conversion probability, availability, ratings,
fulfillment, profitability, ad pressure, personalization, and Amazon's own
experiments. It is not a simple best-keyword-match.

**Default sort is commercial.** Sponsored products dominate top positions
regardless of query match. Organic results rank by sales velocity and conversion
rate, not keyword match. Irrelevant or substitute products appear above exact
matches. Field-tested: 2-12 of the first results are sponsored out of ~48 total.

**Sponsored-result dominance.** Ads occupy top, middle, and repeated positions.
The first screen is a paid marketplace, not a neutral result set. Creates "ad
crowd-out" where organically relevant items are pushed down, and "pay-to-play
visibility" where sellers must buy ads to remain visible.

**Organic buried under modules.** Search pages are no longer simple lists. Ads,
recommendation widgets, brand carousels, "Amazon's Choice," "Best Seller,"
"Highly rated," and other modules interrupt the result set.

**Label ambiguity.** "Sponsored," "Amazon's Choice," "Best Seller," "Overall
Pick," "Climate Pledge Friendly" badges are hard to interpret. Some are ads,
some algorithmic, some program labels. Shoppers treat them all as quality
endorsements.

**Self-preferencing.** Regulators have alleged Amazon biases results toward its
own products or preferred placements. Amazon disputes many allegations, but
self-preferencing is a recognized antitrust concern.

**Implication:** Treat the first screen as advertising. Scroll to find the first
organic cluster. Extract and mark `is_sponsored` for every result. Re-rank all
results client-side by relevance, not Amazon's commercial ordering.

### Core 2: Recall failure — relevant ASINs missing, suppressed, or buried

Relevant products fail to appear in keyword search but are visible through other
discovery surfaces (category pages, "Customers also bought," bestseller lists,
"Top rated" / "Most wished for").

**Search suppression.** Listings hidden for policy/compliance/image issues or
poor performance. Sellers report ASINs disappearing from search without notice.

**Cold-start invisibility.** New or specialized products lack behavioral data
(sales velocity, reviews, ad budget) needed to rank. Effectively invisible
despite being relevant.

**Feedback-loop ranking.** Products that get clicks, sales, and reviews receive
more exposure, creating more clicks, sales, and reviews. Favors incumbents,
high-ad-spend sellers, and viral products. Niche, new, or slower-moving but
higher-quality products disappear.

**Exact-match failure.** Searching for a precise brand/model can return
substitutes, competitors, bundles, sponsored rivals, or adjacent products. The
query is semantically over-expanded even when intent is specific.

**Availability and regionalization artifacts.** Results vary by location,
delivery promise, warehouse availability, seller eligibility, Prime status, and
shipping speed. A relevant product may exist but vanish under the current
fulfillment context.

**Pagination and result instability.** The same query produces different results
across refreshes, sessions, devices, or pages. Ranking experiments,
personalization, ad auctions, stock changes, and pagination cutoffs contribute.

**Implication:** Keyword search alone is insufficient for exhaustive discovery.
Use multiple discovery surfaces. Google `site:amazon.com.au` bypasses A10
entirely. Category browsing and related-product widgets use different retrieval.

### Core 3: Sort/filter systems operate on unstable candidate sets

Sort orders and filters don't operate on the full relevant set. Amazon builds a
restricted candidate set first, then sorts/filters that subset.

**Sort orders are not global sorts.** "Price: Low to High" and "Avg. Customer
Review" can drastically reduce result count (80-90% hidden), return products
violating the chosen sort, or mix in Featured-ranked results. Amazon applies
business rules before sorting.

**Facet/filter collapse.** Applying filters (brand, department, Prime, rating,
material, size, price) can radically change the result universe rather than
merely filtering the visible set. Feels like Amazon is hiding inventory.

**Misleading price comparisons.** Price sorting is undermined by pack sizes,
coupons, Subscribe & Save, shipping fees, third-party offers, used/open-box,
variant bait, and unit-price inconsistencies. The "lowest" result may not be
the cheapest comparable item.

**Variant/parent-child ASIN distortion.** Color, size, bundle, and model
variants are grouped or split in confusing ways. A product shows a low price
for one variant, strong reviews from another, or availability for only certain
options. This distorts search snippets and sorting.

**Implication:** Sort variants are useful for surface diversity (finding products
default sort buries) but not for accurate ordering. Always re-sort client-side.
Filter before sorting for more stable results. Verify price per unit and per
target variant on the detail page.

### Core 4: Search, browse, recommendations, and AI use different surfacing logic

Keyword search, category browse, recommendation modules, bestseller pages,
related-product widgets, and Rufus use different retrieval and ranking systems.

**Category/browse vs keyword search.** Category pages, bestseller lists, and
"Customers also bought" surface better candidates than keyword search. Amazon
Science publications describe separate work on semantic search, query
attributes, recommendations, and COSMO knowledge graphs.

**Semantic drift from AI/query expansion.** Modern Amazon search over-expands
intent: "outdoor swing" pulls in patio accessories, hammocks, chairs, loosely
related substitutes. COSMO infers shopping intent/common sense; the same
strengths create fuzzy or surprising matches. Use exact phrases and exclusions
to counter drift.

**Rufus/AI-shopping pathologies.** Rufus is trained on the product catalog,
reviews, Q&A, and web information, and personalizes using browsing history,
wish lists, and purchases. Failure modes: opaque recommendations,
over-personalization, answer-style persuasion replacing comparison,
summarization errors, and less visibility into the actual candidate set.

**Mobile vs desktop divergence.** Mobile shows fewer organic products above the
fold and more modules per visible area. Ad load and ranking manipulation feel
stronger on mobile even when the underlying result set overlaps with desktop.

**Implication:** Don't stop at keyword search. Use category browsing,
best-seller lists, and related-product widgets to recover products keyword
search misses. Be aware that AI-assisted discovery (Rufus) over-broadens.

### Super-category: Trust-signal manipulation

**Fake reviews and rating manipulation.** Reviews/ratings influence trust and
likely ranking/conversion. Fake reviews distort search quality. The UK CMA
secured undertakings from Amazon in 2025 to strengthen anti-fake-review systems.

**Review hijacking/catalogue abuse.** A listing inherits reviews from an
unrelated product, making a low-quality or new item look established. This
contaminates ranking and trust signals simultaneously. Red flags: reviews
mentioning a different product, sudden review count jumps, photo mismatches.

**Keyword-stuffed junk.** Sellers stuff titles, bullets, backend keywords, and
attributes to catch more queries. Products match query text but not shopper
intent. Counter: specific queries with exact phrases and exclusions.

**Duplicate/clone/alphabet-soup brand flooding.** Visually identical products
under different brand names make search look larger than it is, fragment
reviews and prices, and make it hard to compare true manufacturers.

**Implication:** Don't trust review count or star rating alone. Check review
authenticity signals: review velocity, specificity, photo match, variant
consistency. Use minimum review count (50+) as a quality gate. Cross-reference
with external tools (Fakespot, ReviewMeta).

### Super-category: Personalization and session effects

**Personalization traps.** Search changes based on browsing history, purchase
history, location, Prime status, device, session behavior, and inferred
preferences. Traps users in repetitive brands, price bands, or product types.
Makes "objective" search hard to reproduce.

**Implication:** For exhaustive discovery, compare results across sessions or
use a fresh browser context. Fresh sessions reduce this but don't fix Core 1-3.

### Super-category: Marketplace integrity

**Counterfeits and unsafe goods.** Bad catalog entries are discoverable, ranked,
and badge-enhanced. Not purely a search issue but becomes one when search
surfaces them. Categories at highest risk: beauty, supplements, batteries,
safety gear, baby products, chargers, luxury goods.

**Implication:** For high-risk categories, prefer official brand storefronts,
"Sold by Amazon" listings, or buy direct from the manufacturer. Use the listing
validation checklist below.

## Search Strategy

### The core problem

Amazon search surfaces what makes Amazon money, not what matches the user's
intent. For any non-trivial search:
- ~25% of visible results are sponsored (paid placement)
- Organic results are ranked by commercial metrics, not relevance
- The search index doesn't cover the full catalog
- Sort orders are unreliable for ordering but useful for coverage diversity

No single query or surface produces a complete result set. The strategy must
combine multiple surfaces, scope the search index before querying, and re-rank
client-side.

### The key insight: scope before you search, then expand aggressively

The single highest-leverage move is narrowing the search index BEFORE querying,
not filtering results AFTER. Amazon's department-scoped search uses a narrower
index with category-specific ranking logic. This is why category pages and
"related products" sections feel superior to keyword search — they're operating
against a different, cleaner index.

Full-catalog keyword search (`/s?k=query`) pulls from everything with heavy A10
biases. Department-scoped search (`/s?k=query&i=department`) constrains the index
first, reducing the pool Amazon can game with sponsored placements and
velocity-boosted junk.

**Expansive search with post-hoc deduplication.** Overlap between departments,
synonyms, and surfaces is expected and desired. Each surface returns a different
slice of the catalog — maximize coverage by querying all relevant departments
and synonym variants, then deduplicate by ASIN afterward. For cross-category
products (keyboards in both electronics and computers, SSDs in both), run each
department scope separately and merge.

### URL parameter hacks (hidden filters)

Amazon supports URL query parameters that the UI doesn't always expose. These
act as advanced filters and sort controls. They work reliably on .com.au.

**Discount percentage filter** (`&pct-off=`):
- `&pct-off=50-` — only items 50%+ off
- `&pct-off=30-70` — 30-70% off range
- `&pct-off=25-` — 25%+ off
- Pulls deep-discount items (Lightning Deals, Warehouse, seller promotions) that
  don't appear in normal results
- Combine with department scope: `/s?k=headphones&i=electronics&pct-off=30-`
- Amazon rewrites the param internally: `&pct-off=30-` becomes `&rh=p_8%3A30-`
  in the URL bar. Both forms work as input.
- Reduces sponsored clutter significantly. E2e across 3 categories:
  headphones 27%→8%, keyboards 23%→4%, SSDs 27%→0%. More effective on
  higher-value products.

**Sort parameters** (unreliable for ordering, useful for coverage diversity):
- `&s=review-rank` — sort by customer review
- `&s=price-asc` — price low to high
- `&s=price-desc` — price high to low
- `&s=date-desc-rank` — newest arrivals
- `&s=exact-aware-popularity-rank` — best sellers
- **Do NOT trust these for actual ordering.** E2e across 3 categories:
  `&s=price-asc` produced 11-14 price-order violations per page. SSD test was
  extreme: `&s=price-asc` started at $144, then $14.99, then $12.99.
  `&s=price-desc` produced the *same first 5 prices* as `&s=price-asc` — both
  sort directions are decorative. Amazon accepts the param but A10 commercial
  ranking overrides it. Use these solely for coverage expansion (different result
  set), then re-sort client-side. They also reduce result count (33→26-27).

**Other parameters**:
- `&prime=true` — force Prime-only results
- `&rh=n%3A<node>` — category node filter (alternative to `&i=`)

**Workflow**: After applying filters in the UI, copy the full URL, append or
tweak parameters, and reload. This bypasses some A10 performance biases that
the UI enforces. Bookmark tuned URLs for one-click reuse.

```python
# Example: department-scoped + discount filter + review sort
goto_url("https://www.amazon.com.au/s?k=%22noise+cancelling%22+headphones&i=electronics&pct-off=30-&s=review-rank")
wait_for_content(min_text=200)
```

### Query syntax

Amazon supports structured query syntax that reduces noise at the source:

| Syntax | Effect | Example |
|--------|--------|---------|
| `"exact phrase"` | Requires exact match, disables fuzzy | `"noise cancelling headphones"` |
| `-term` | Excludes results containing term | `headphones -kids -gaming -earbuds` |
| Combined | Precision + exclusion | `"wireless ANC" headphones -kids -gaming` |

Always use quotes for the primary product concept. Add exclusions for known
noise categories. This is more efficient than post-extraction filtering because
it reduces the result set Amazon returns, which in turn reduces sponsored
insertion opportunities.

**Limitation:** `-term` exclusions are unreliable and query-dependent. E2e tests
produced conflicting results:
- Headphones `-kids -gaming`: filtered organic results but not sponsored
- Keyboards `-gaming -rgb`: failed entirely — 30/33 results still contained
  "gaming" or "rgb" in titles (21 organic + 9 sponsored)

Amazon appears to honor exclusion syntax inconsistently depending on query and
category. Treat `-term` as a hint that may reduce noise but does not reliably
eliminate it. Always combine with `is_sponsored` extraction and client-side
title filtering for complete noise control.

### Discovery surfaces (ordered by empirical coverage, e2e-tested)

| Surface | ASINs found | New vs prev | Extraction |
|---------|------------|-------------|------------|
| Category landing page (clear search bar) | 89 | highest single surface | Link extraction `a[href*="/dp/"]` — different DOM |
| Full-catalog search `/s?k=` | 60 | +25 over dept-scoped | Search result extractor below |
| Dept-scoped search `/s?k=&i=` | 33 | baseline | Search result extractor below |
| Best Sellers `/gp/bestsellers/{parent}/{node}/` | 30 | +29 (1 overlap with keyword) | Best sellers extractor below |
| Related products (per product page) | 18 | +11 avg per page | `[data-asin]` on product page |
| Synonym variant query | 33 | +18 over primary query | Same as search extractor |
| URL-param enhanced (`&pct-off=`, `&s=`) | 26 | different set, not more | Same as search extractor |
| Google `site:amazon.com.au` | varies | surfaces suppressed items | ASIN extraction from Google results |
| Amazon Warehouse / Renewed | varies | 40-60% cheaper variants | Same site structure |
| New Releases `/gp/new-releases/{slug}/` | 30 | surfaces unranked items | Same DOM as best sellers — identical extractor |

**Key insight from e2e:** The category landing page (89 ASINs) and best sellers
(30 ASINs, 29 new) produce the highest coverage delta per page load. A single
keyword search page (33 ASINs) misses most popular products — only 1 of the top
30 best-seller headphones appeared in keyword search results.

### Clear-search-bar trick

To access the pure category page (Best Sellers, Top Rated, Most Wished For)
without constructing a URL:

```python
# Navigate to department search first
goto_url("https://www.amazon.com.au/s?k=headphones&i=electronics")
wait_for_content(min_text=200)

# Clear the search bar and submit — loads curated category view
js("document.querySelector('#twotabsearchtextbox').value = ''")
js("document.querySelector('#nav-search-submit-text').closest('form').submit()")
wait_for_content(min_text=200)
```

This navigates to `/b?node={id}` — the department landing page. It does NOT use
the search result DOM structure. Products lack `[data-component-type]` and
`[data-asin]` attributes. Extract via product links instead:

```python
# Category landing page extraction (different from search results)
category_asins = js("""
  Array.from(new Set(
    Array.from(document.querySelectorAll('a[href*="/dp/"]')).map(a => {
      var match = a.href.match(/\\/dp\\/([A-Z0-9]{10})/);
      return match ? match[1] : null;
    }).filter(Boolean)
  ))
""")
```

Yields 89 unique ASINs for Electronics — high-coverage discovery surface
requiring no category slug or node ID knowledge.

### Multi-surface search algorithm

```
Phase 0: Pre-search research (outside Amazon)
  0. Define requirements, target price, deal-breakers before searching
  1. Research independently: reviews, Reddit, brand sites, recall/defect checks
  2. Identify real brands and common failure modes

Phase 1: Department-scoped search (primary discovery — highest leverage)
  3. Select the most specific department for the product category
  4. Craft precise query: quoted phrase + exclusions + distinguishing specs
  5. Navigate to department-scoped search URL
  6. Apply aggressive sidebar filters: rating, price range, Prime, review count
  7. THEN change sort from Featured to Avg. Customer Review or Price
  8. Extract all results, mark sponsored vs organic
  9. Paginate until convergence (zero-streak per product-search.md)
  10. Collect ASINs into candidate set

Phase 2: Full-catalog search (coverage expansion)
  11. Run same query without department scope
  12. Run 2-3 synonym/variant queries (different vocabulary = different index slice)
  13. Deduplicate new ASINs against candidate set
  14. For hybrid products that span departments, try 2-3 departments separately

Phase 3: Curated category probe (gap fill — highest coverage delta)
  15. Use clear-search-bar trick on Phase 1 department → /b?node={id}
  16. Extract via link pattern a[href*="/dp/"] (NOT search result DOM — different page)
  17. Fetch parent best-sellers page: /gp/bestsellers/{parent-slug}/
  18. Extract subcategory links via a[href*="bestsellers"] for {parent}/{node} URLs
  19. Fetch subcategory best-sellers page (e2e: 30 ASINs, 29 new vs keyword)
  20. Add new ASINs to candidate set

Phase 4: Related-product expansion (deep discovery — ~11 new ASINs per page)
  21. For top-matching ASINs from Phases 1-3, visit product pages
  22. Extract [data-asin] on product page (broad selector captures all widgets)
  23. Add new ASINs to candidate set (~11 new ASINs per product page on average)
  24. Optionally visit those product pages for full metadata

Phase 5: Client-side ranking (override Amazon's commercial sort)
  25. Re-rank all candidates by: relevance to query > rating > review count > price
  26. Apply title relevance filter (must contain query core terms)
  27. Apply quality filter: 4+ stars AND minimum review count (50+ to exclude
      fake-inflated new listings)
  28. Present ranked results with source surface tagged

Phase 6: Listing validation (trust verification)
  29. For serious candidates, run listing validation checklist
  30. Verify seller, variant accuracy, review authenticity, price history
  31. Compare unit economics and outside-Amazon alternatives
  32. Buy only if Amazon wins on fit, trust, price, and fulfillment
```

### Filter-then-sort sequence (critical ordering)

Amazon's sort behaves differently on a pre-filtered pool vs the full result set.
The correct sequence is:

1. **Apply filters first** (sidebar): star rating, price range, Prime/delivery,
   review count minimum, brand
2. **Then change sort** from Featured to your preferred order

Why: Post-filter sorts are more stable because the pool is already cleaned of
low-quality and irrelevant items. Amazon's business rules (which corrupt sort
order) are applied to a smaller, higher-quality set. Featured sort always mixes
in sponsored/velocity-boosted results regardless of filters — changing sort
AFTER filtering minimizes this contamination.

If switching sort causes result count to plummet, note the top items from the
filtered Featured view first, then apply the sort. The sort may hide items but
the Featured snapshot captures them.

### Query construction rules

1. **Scope the department first.** Select the most specific department before
   querying. For "noise cancelling headphones" → Electronics > Headphones, not
   site-wide search.
2. **Use exact phrases in quotes.** `"noise cancelling headphones"` not
   `noise cancelling headphones`. Quotes disable fuzzy matching.
3. **Add exclusions for known noise (unreliable).** `headphones -kids -gaming -earbuds`
   — may reduce noise but is query-dependent and not guaranteed to filter. Always
   combine with client-side title filtering.
4. **Include distinguishing specs.** `"wireless ANC" headphones battery 30 hours`
   — long-tail intent signals push relevant results higher.
5. **Run multiple query variants.** Amazon's index partitions by vocabulary.
   `"noise cancelling"` and `"ANC"` return partially disjoint sets. Dedup by ASIN.
6. **Use URL sort params with caution.** `&s=review-rank`, `&s=price-asc` etc. work
   but may reduce result count. Most effective on pre-filtered pools. Always
   re-sort client-side as the authoritative ranking.
7. **Try multiple departments for cross-category products.** Keyboards appear in
   both `&i=electronics` (31 ASINs) and `&i=computers` (33 ASINs) — overlapping
   but distinct sets. Products that straddle categories benefit from multiple
   department scopes.

### Sponsored result handling

Sponsored results are not useless — they're often genuinely relevant products
that sellers have paid to promote. The correct strategy is:
1. Extract and mark `is_sponsored` for every result
2. Do NOT discard sponsored results automatically
3. Re-rank all results (sponsored + organic) by relevance client-side
4. Disclose sponsored status in output

The only case to exclude sponsored results: when counting "organic popularity"
or calculating market position. For product discovery, sponsored results are
valid data points.

### Quality filters (applied in Phase 5)

| Filter | Threshold | Purpose |
|--------|-----------|---------|
| Star rating | 4+ stars minimum | Eliminates low-quality products |
| Review count | 50+ reviews | Excludes fake-inflated new listings with few reviews |
| Price range | Context-dependent | Eliminates accessories mislabeled as main products |
| Prime / Fulfilled | Optional, per user preference | Shipping reliability (especially on AU) |
| Brand filter | Use sidebar for known brands | Reduces no-name keyword-stuffed junk |

Review count minimum is critical: a 4.8-star product with 3 reviews is less
trustworthy than a 4.2-star product with 2,000 reviews. The review count filter
catches fake-inflated new listings that star rating alone misses.

### Listing validation checklist (Phase 6)

For each serious candidate, verify before buying:

**Seller and fulfillment:**
- Prefer "Sold by [official brand]" or "Sold by Amazon" for high-counterfeit
  categories
- Fulfilled by Amazon helps logistics but does not prove authenticity
- Be cautious with unknown third-party sellers, especially auto-generated names

**Variant accuracy:**
- Confirm reviews, price, size, color, and pack count refer to the exact
  variant being purchased
- Variant/parent-child ASINs can show a low price for one variant, strong
  reviews from another, or availability for only certain options

**Review authenticity:**
- Sort reviews by most recent — a product good 3 years ago may differ now
- Read 2-4 star reviews: they reveal real defects better than 5-star or 1-star
- Check customer images/videos for real-world scale, build quality, failures
- Red flags: many reviews in a short window, vague praise, reviews mentioning
  a different product, sudden 5-star flood after negative reviews
- Use Fakespot / ReviewMeta for automated authenticity analysis

**Price verification:**
- Don't trust the crossed-out "List Price" / "RRP" alone — often inflated
- Check Keepa / CamelCamelCamel for actual historical price
- A deal is real only if current price is low relative to historical price AND
  external alternatives, not merely low relative to Amazon's list price
- Compare unit price (per ounce, per item, per count) not just list price
- Account for coupons, Subscribe & Save, and shipping costs

**Q&A check:**
- Search within Q&A for must-have specs
- Q&A often reveals incompatibilities not mentioned in product description

### Category slug discovery

Amazon category slugs don't follow a predictable pattern. Discover them from
search results:

```python
# Extract category breadcrumbs from search results
categories = js("""
  Array.from(document.querySelectorAll('#departments a.a-link-normal')).map(a => ({
    name: a.innerText?.trim(),
    href: a.href
  }))
""")
```

Use the `href` from breadcrumbs to construct best-seller and category-browse URLs.

### Department search URL construction

```python
# Department-scoped search (preferred — highest relevance)
goto_url("https://www.amazon.com.au/s?k=noise+cancelling+headphones&i=electronics")
wait_for_content(min_text=200)

# With exclusions
goto_url("https://www.amazon.com.au/s?k=%22noise+cancelling%22+headphones+-kids+-gaming&i=electronics")
wait_for_content(min_text=200)
```

The `&i=` parameter is the department scope. Common values:
- `electronics`, `computers`, `office`, `sporting-goods`, `home`, `kitchen`
- Not exhaustive — discover from breadcrumbs or the "All" dropdown

### Related-products extraction (Phase 4)

On a product detail page, extract related-product ASINs:

```python
related = js("""
  Array.from(document.querySelectorAll(
    '[data-asin]:not([data-asin=""])'
  )).map(el => el.getAttribute('data-asin'))
  .filter((v, i, a) => a.indexOf(v) === i)
""")
```

This is a broad selector — it captures all ASIN-bearing elements including
"Customers also bought", "Products related to", and comparison widgets. Filter
for uniqueness by ASIN, then visit selectively for metadata.

### Personalization workaround

Search results are session-dependent. For exhaustive discovery across
multiple sessions, consider:
- Running queries in a fresh browser context to reset personalization bias
- Comparing results across sessions to identify personalized vs universal results
- The pathologies are algorithmic, not personalization-only — fresh sessions
  reduce personalization but don't fix Core 1-3

### When to use which phase

| Search type | Phases needed | Why |
|-------------|-------------|-----|
| Specific product lookup | Phase 1 only | Department-scoped search usually finds it |
| Price comparison for known product | Phase 1 + Phase 5 | Need all sellers, re-rank by price |
| Category survey | Phase 1 + Phase 3 | Curated category views fill search gaps |
| Exhaustive discovery | All 6 phases | Every surface adds products others miss |
| "Find alternatives to X" | Phase 1 + Phase 4 focus | Department scope + related products is the most direct path |
| Hybrid product (spans categories) | Phase 1 x 2-3 departments + Phase 3 | Try each relevant department separately |
| Deal hunting | Phase 1 + `&pct-off=` + Warehouse | Discount filter surfaces hidden deals |
| Best value (price + quality) | Phase 1 + Google `site:` + Warehouse | Cross-surface comparison finds cheapest legitimate option |
| High-risk product (counterfeit concern) | Phase 0 + Phase 1 + Phase 6 | Pre-search research + strict listing validation |

### Parallel tab workflow (maximum coverage)

For exhaustive searches, run multiple surfaces simultaneously in separate tabs.
Each tab uses a different combination of filters/sort/surface to capture items
that any single view misses:

```
Tab 1: Department + keyword + Top Brands + 4+ stars + Prime
Tab 2: Same query + &pct-off=30- + &s=price-asc (deep-discount view)
Tab 3: Google site:amazon.com.au "exact product name" (bypasses A10)
Tab 4: Category Best Sellers + Warehouse/Renewed (separate inventory)
```

Compare side-by-side. Main search misses what Warehouse or Google surfaces.
The parallel approach reveals the full product picture in one pass.

When using CDP (browser automation), implement this as sequential tab switches
rather than true parallelism — the browser is single-session. Use `new_tab()`
for each surface and switch between them to extract.

### Google site search (bypasses A10 entirely)

Google indexes Amazon product pages independently. Searching Google with
`site:amazon.com.au "product name"` uses Google's relevance algorithm, not
Amazon's commercial ranking. This surfaces:
- Products suppressed in Amazon's search index
- Products buried deep in Amazon's pagination
- Products with low sales velocity that A10 deprioritizes
- Products from small sellers Amazon doesn't promote

```python
# Not a CDP operation — use web search tool
# site:amazon.com.au "Sony WH-1000XM5"
```

Extract ASINs from Google results (match `/dp/([A-Z0-9]{10})` in URLs), then
visit those product pages directly on Amazon for full metadata. This is a
supplementary discovery surface, not a replacement for Amazon-native search.

### Amazon Warehouse / Renewed

Amazon Warehouse (returns, open-box) and Amazon Renewed (refurbished) are
separate inventory surfaces with their own pricing. Items often 40-60% cheaper
than new. Access points:
- Warehouse storefront: `/b/?node=170NNNN1011` (node ID varies by region)
- Renewed storefront: `/ref=nav_cs_renewed`
- Individual product pages show "Buy it renewed" or "Used – Like New" options
  below the main price
- Filter by condition: Like New, Very Good, Good, Acceptable

Warehouse items share the same ASIN as new items but have separate buybox
entries. The product detail page extractor works the same way — check
availability text for condition indicators.

### External verification tools

For high-value purchases, verify Amazon's data against external sources:

| Tool | Purpose | What it catches |
|------|---------|-----------------|
| Keepa / CamelCamelCamel | Price history tracking | Fake "was" prices, price manipulation, best time to buy |
| Fakespot / ReviewMeta | Review authenticity analysis | Fake/inflated reviews, review merging across variants |
| `site:amazon.com.au` via Google | Independent relevance check | Products Amazon suppresses or buries |

Keepa is especially valuable for detecting fake "List Price / RRP" claims —
Amazon's "was" price is frequently inflated. The `list_price` field in the
extractor captures this, but Keepa confirms whether the item was ever actually
sold at that price.

### Buying channel risk matrix

Not everything should be bought on Amazon. Match the channel to the risk:

**Safe on Amazon:** low-risk commodities, known brands with official storefronts,
items where returns are easy, products where authenticity is not safety-critical.

**Consider buying direct or specialist retailer:** beauty/skincare, supplements,
baby products, batteries/chargers, safety gear, car parts, medical-adjacent
products, high-end electronics, luxury goods, anything frequently counterfeited.

Amazon's own brand-protection materials emphasize ongoing anti-counterfeit
efforts — a reminder that counterfeits are a real marketplace problem, not just
buyer paranoia.

## Navigation

### Direct search URL (fastest, always use this)
```python
goto_url("https://www.amazon.com.au/s?k=mechanical+keyboard")
wait_for_content(min_text=200)  # polls for content + detects CAPTCHA/blocks
```

### Search box typing (use when you need category filtering)
```python
goto_url("https://www.amazon.com.au")
wait_for_content()
js("document.querySelector('#twotabsearchtextbox').focus()")
js("document.querySelector('#twotabsearchtextbox').click()")
wait(0.3)
type_text("wireless mouse")
wait(0.3)
press_key("Enter")
wait_for_content(min_text=200)
```

### Direct product page
```python
# URL pattern: /dp/{ASIN}  or  /dp/{ASIN}?th=1 (Amazon may redirect to add ?th=1)
goto_url("https://www.amazon.com.au/dp/B08Z6X4NK3")
wait_for_content(min_text=200)
```

## Session Gotcha

**Always use `new_tab()` when opening Amazon for the first time in a harness session.**
`goto_url()` can silently fail to navigate if the current tab resists the navigation
(observed when the daemon attached to a different real tab). The safe pattern:

```python
tid = new_tab("https://www.amazon.com.au/s?k=mechanical+keyboard")
wait_for_content(min_text=200)
```

After that, `goto_url()` works fine within the same Amazon session.

## Search Results Extraction

### Container selector
`[data-component-type="s-search-result"]` — confirmed working, yields ~60 results per page.

### Full extraction (field-tested)
```python
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

### Field notes
- **`asin`**: `data-asin` attribute on the container div — always present, matches the `/dp/{ASIN}` URL.
- **`title`**: `h2 span` works consistently. `h2 a.a-link-normal span` also works.
- **`price`**: `.a-price .a-offscreen` returns the formatted string e.g. `"$69.99"`. Use this, not `.a-price-whole`.
- **`list_price`**: `.a-text-price .a-offscreen` — only present when item is on sale (was/now pricing).
- **`rating`**: Use `aria-label` on `[aria-label*="out of 5 stars"]` — gives `"4.5 out of 5 stars, rating details"`, split on space for the number.
- **`reviews`**: Use `[aria-label*="ratings"]` attribute — gives `"1,514 ratings"`. Do NOT use `.a-size-base.s-underline-text` — that element exists on sponsored results and shows "Xbox" (a cross-sell widget text).
- **`is_sponsored`**: `.puis-sponsored-label-text` is present on sponsored listings; first 12 results are usually sponsored.
- **`url`**: Construct from ASIN — `h2 a` does NOT exist on AU search cards. Sponsored cards have zero links; organic cards link via image/swatches but not title. `'https://www.amazon.com.au/dp/' + asin` is the only reliable method.

## Product Detail Page Extraction

### Confirmed selectors (field-tested on B0D3F69XSP)
```python
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

### Price field notes
- `#priceblock_ourprice` and `#priceblock_dealprice` are **legacy** — they return `null` on modern product pages.
- Construct price from `.a-price-whole` + `.a-price-fraction` (both stripped of `\n` and `.`).
- As a fallback: first `.a-price .a-offscreen` on the page also works (confirmed `$69.99`).
- `list_price` from `.basisPrice .a-offscreen` shows the crossed-out "was" price when a discount exists.

## Best Sellers Page

### URL format (AU-specific)

Top-level: `https://www.amazon.com.au/gp/bestsellers/{slug}/`
e.g. `https://www.amazon.com.au/gp/bestsellers/electronics/`

Subcategory: `https://www.amazon.com.au/gp/bestsellers/{parent-slug}/{node-id}/`
e.g. `https://www.amazon.com.au/gp/bestsellers/electronics/7058119051/` (Headphones)

**Critical AU gotchas:**
- The US format `/Best-Sellers-{Category}/zgbs/{slug}/` returns 404 on AU
- Node-only URLs like `/gp/bestsellers/7058119051/` also return 404 on AU — you MUST
  include the parent slug: `/gp/bestsellers/electronics/7058119051/`
- Bare slug URLs like `/gp/bestsellers/headphones/` load but return empty results
  (title shows "undefined") — use the `{parent}/{node}` format instead
- Invalid node IDs also show "undefined" in the title — check the page title for
  "undefined" as a signal that the URL is wrong
- **Not all products have a dedicated best-sellers subcategory.** Keyboards on AU
  don't appear as a subcategory under either Electronics or Computers — they're
  buried under "Computer Accessories" which contains cables, chargers, etc. If no
  dedicated subcategory exists, the category landing page (Phase 3 clear-search-bar)
  is a better discovery surface.
- Discover correct subcategory URLs from the parent best-sellers page's navigation
  links, not from search breadcrumbs

### DOM structure (2025, e2e-verified)
`.zg-item-immersion` **does not exist** — Amazon migrated to CSS modules. Use `[data-asin]` anchored on `[id="gridItemRoot"]`:

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

### Subcategory link discovery

Find correct best-seller subcategory URLs by scraping navigation links on the
parent page:

```python
# From the parent best-sellers page, extract subcategory links
subcategories = js("""
  Array.from(document.querySelectorAll('a[href*="bestsellers"]')).map(a => ({
    text: a.innerText?.trim(),
    href: a.href
  })).filter(l => l.text && l.href.includes('/gp/bestsellers/'))
""")
```

This returns URLs with the correct `{parent}/{node}` format for AU.

### Coverage impact (e2e-verified 2026-05-04)

Field test: `"noise cancelling" headphones` in Electronics department.
- Keyword search returned 32 ASINs
- Best sellers (headphones subcategory) returned 30 ASINs
- **Overlap: 1 ASIN** — keyword search and best sellers share almost zero results
- Best sellers found Apple AirPods, EarPods, AirPods Pro 3 — top-selling items
  that keyword search completely missed
- **Phase 3 (best sellers) increased unique product coverage from 32 to 61 ASINs**

This confirms Core 2 (recall failure): keyword search alone misses the most
popular products. The multi-surface strategy is not theoretical — it nearly
doubles coverage.

Note: Title comes from the product image `alt` attribute — the text title
elements use obfuscated CSS module class names that change between deployments.

## Pagination

```python
# Get next page URL directly
next_url = js("document.querySelector('.s-pagination-next')?.href")
if next_url:
    goto_url(next_url)
    wait_for_content(min_text=200)

# Or construct by page number
goto_url("https://www.amazon.com.au/s?k=wireless+mouse&page=2")
```

## Result Count

```python
count_text = js("document.querySelector('[data-component-type=\"s-result-info-bar\"] h1')?.innerText?.trim()")
# Returns e.g.: '1-16 of over 40,000 results for "wireless mouse"\nSort by:\n...'
# Extract just the count: count_text.split('\n')[0]
```

## CAPTCHA Detection

No CAPTCHA was encountered during testing with a logged-in Chrome session. To detect defensively:

```python
def check_captcha():
    text = js("document.body.innerText.slice(0,500)") or ""
    url  = page_info()["url"]
    return (
        "captcha" in text.lower()
        or "enter the characters" in text.lower()
        or "sorry, we just need to make sure" in text.lower()
        or "captcha" in url.lower()
        or "validateCaptcha" in url
    )

if check_captcha():
    raise RuntimeError("Amazon CAPTCHA hit — stop and notify user")
```

Amazon may serve a CAPTCHA on fresh/anonymous sessions. Using the browser's existing logged-in session avoids this in practice.

## Gotchas

- **`goto_url()` silent failure**: On first visit, use `new_tab(url)` instead. After the tab is on Amazon, `goto_url()` works.
- **`.zg-item-immersion` is gone**: Best Sellers page uses CSS module classes (obfuscated). Use `[data-asin]` + `img[alt]` for title.
- **`.a-size-base.s-underline-text` is unreliable for review count**: On sponsored results it shows unrelated text (e.g. "Xbox"). Use `[aria-label*="ratings"]` instead.
- **`#priceblock_ourprice` is legacy**: Returns `null` on modern pages. Construct from `.a-price-whole` + `.a-price-fraction`.
- **Sponsored results appear first**: Up to 12 of the first results can be sponsored (varies by query — see Core 1 in Search Pathologies). Mark with `is_sponsored` and re-rank client-side rather than discarding.
- **`data-asin` can be empty string on non-product rows**: Filter with `.filter(r => r.asin)`.
- **Price split DOM**: `.a-price-whole` innerText includes a trailing `\n.` — strip it: `.replace(/[\n.]/g,'')`.
- **ASIN from URL**: Use `/dp/([A-Z0-9]{10})/` regex on the product URL. `data-asin` on search results is always the canonical ASIN.
- **`?th=1` redirect**: Amazon appends `?th=1` (and sometimes `?psc=1`) to product URLs after redirect. This is normal — `input[name="ASIN"]` always has the clean ASIN.
- **Use `wait_for_content()` after navigation**: Amazon search results load listing cards asynchronously. `wait_for_load()` fires before cards render. `wait_for_content(min_text=200)` polls until content appears AND detects CAPTCHA/block pages.
- **Product pages need longer on AU**: Product detail pages can take 4-5s to fully render on AU. If `#productTitle` is null, the page hasn't finished loading. Use `new_tab()` for the first product page visit.
- **Product overview specs**: `#productOverview_feature_div table` provides structured key/value specs (brand, connectivity, etc.) — useful when bullet points are sparse.
- **Search result titles are brand-only for computers/systems**: For desktops, laptops, and computer systems, `h2 span` returns just the brand name ("ASUS", "MSI") instead of the full product name. This doesn't affect GPUs, peripherals, or accessories — only system-level products. For these categories, search extraction can identify ASINs and prices, but `#productTitle` from the product detail page is required for the actual product name.
- **List Price / RRP is often inflated**: Don't trust the crossed-out "was" price. Verify with Keepa. Amazon's reference prices are frequently higher than the item was ever sold for.
- **Variant reviews can be misleading**: Reviews from one variant (color, size) may appear on all variants. Check if review content matches the specific variant being purchased.

## E2E Test Results (2026-05-04)

Field-tested against amazon.com.au with query `"noise cancelling" headphones` in
Electronics department. All phases of the multi-surface strategy tested.

### Phase 1: Department-scoped search (PASS)
- 33 results, 9 sponsored, 24 organic
- Field coverage: 32/33 prices, 33/33 ratings, 33/33 reviews, 33/33 titles
- All selectors work as documented

### Phase 2: Full-catalog + synonym variants (PASS — high yield)
- Full-catalog (no `&i=`): 60 results, 25 new ASINs not in dept-scoped search
- Synonym variant "ANC headphones" in electronics: 33 results, 18 new ASINs
- Synonym surfaced Sennheiser Accentum, Momentum 4, Nothing Headphone(1),
  Soundcore Space One — products that "noise cancelling" didn't find
- Total from Phase 1+2: ~75 unique ASINs from 3 queries

### Phase 3: Best sellers + category probe (PASS — highest coverage delta)

**Best sellers extractor:**
- Top-level `/gp/bestsellers/electronics/`: 30 items, 100% field coverage
- Subcategory `/gp/bestsellers/electronics/7058119051/` (headphones): 30 items
- **Coverage: 29 of 30 best-seller ASINs were NOT in keyword search**
- Best sellers found Apple AirPods, EarPods, AirPods Pro 3 — top-selling items
  keyword search completely missed
- Keyword search and best sellers share only 1 of 62 combined ASINs

**Best sellers URL format (AU gotcha):**
- Must use `{parent-slug}/{node-id}`: `/gp/bestsellers/electronics/7058119051/`
- Bare node IDs `/gp/bestsellers/7058119051/` → 404
- Bare slugs `/gp/bestsellers/headphones/` → loads but empty ("undefined" category)

**Category landing page (clear-search-bar trick):**
- Navigates to `/b?node={id}` — different DOM structure entirely
- No `[data-component-type]` or `[data-asin]` attributes on products
- Extractable via `a[href*="/dp/"]` link pattern: yielded 89 unique ASINs
- Highest single-surface ASIN count of any method tested

**Subcategory link discovery:**
- `a[href*="bestsellers"]` on parent page returns correct `{parent}/{node}` URLs

### Phase 4: Related-product expansion (PASS)
- Product page (B0G51SYYH6, BlueAnt Pump X): 18 related ASINs
- Product page (B0C3HCD34R, Soundcore Q20i): 18 related ASINs, 11 new
- Section IDs confirm "sp_detail_*" widgets (sponsored related products)
- Each product page adds ~11 new ASINs on average

### Phase 5: Client-side ranking (verified)

**URL sort params (confirmed Core 3):**
- `&s=price-asc` returned results starting at $349, then $69.99, $52.99 — completely
  unsorted. 11 price-order violations (headphones) and 14 violations (keyboards) on
  page 1. Reduced result count by 13-15%.
- `&s=review-rank` accepted but NOT truly sorted by rating
- Both confirm Core 3: sort params work as surface-diversity tools, not reliable sorts

**Discount filter:**
- `&pct-off=30-` works (Amazon rewrites to `&rh=p_8%3A30-`)
- Headphones: 27%→8%, keyboards: 23%→4%, SSDs: 27%→**0%** sponsored
- Effectiveness scales with product price point — higher-value = cleaner results
- 3-10 results per page have discount prices

### Query exclusion syntax (FAIL — unreliable)
- Headphones `-kids -gaming`: appeared to filter organic but not sponsored
- Keyboards `-gaming -rgb`: failed entirely — 30/33 organic results still had excluded terms
- Exclusion syntax is query-dependent and cannot be relied upon for noise control
- Always combine with client-side title filtering

### Mobile viewport (PASS — extractors work identically)
- 375x812 mobile emulation: same 33 results, 9 sponsored
- Amazon served a wider layout (1000px) than the viewport — mobile detection
  is server-side based on UA, not viewport alone
- All selectors work on both layouts

### Pagination (PASS)
- Page 2: 33 results, 26 new ASINs, 5 overlap with page 1
- Over 2,000 total results available for the test query
- `.s-pagination-next` selector works for finding next page URL

### Full multi-surface coverage summary

| Surface | ASINs found | New (cumulative) |
|---------|------------|-----------------|
| Phase 1: Dept-scoped search | 33 | 33 |
| Phase 2: Full-catalog search | 60 | +25 = 58 |
| Phase 2: Synonym "ANC" | 33 | +18 = 76 |
| Phase 3: Best sellers (headphones) | 30 | +29 = 105 |
| Phase 3: Category landing page | 89 | high (not fully cross-ref'd) |
| Phase 4: Related products (2 pages) | 36 | +29 = ~134 |

Phase 1 alone found 33 ASINs. The full strategy found 134+ unique ASINs across
6 surfaces — a 4x coverage increase. Each surface adds products that all other
surfaces miss.

### Strategy validation summary

| Strategy element | Status | Evidence |
|-----------------|--------|----------|
| Department-scoped search is higher quality | PASS | 33 results vs 60 but more relevant |
| Sort orders are decorative | PASS | 11-14 violations per page; price-desc = same ordering as price-asc |
| Best sellers fills keyword gaps | PASS* | 29/30 new ASINs for headphones; SSDs/keyboards lack dedicated subcategory |
| Synonym variants find different products | PASS | "ANC" +18, "mech keyboard" 28, "external SSD" different first results |
| Discount filter reduces noise | PASS | Sponsored 0-8% across categories (strongest on high-value products) |
| Query exclusions are unreliable | FAIL | `-gaming -rgb` failed on 30/33 organic results for keyboards |
| Related products expand discovery | PASS | 16-32 ASINs per page, scales with product popularity |
| Pagination adds significant coverage | PASS | Page 2 added 26-33 new ASINs |
| Category landing page is highest-yield surface | PASS | 78-89 ASINs from single page load |
| Multi-department coverage expands results | PASS | Overlap is expected — search expansively, dedupe by ASIN post-hoc |
| New Releases surfaces different products | PASS | 30 items, same DOM as best sellers, unranked items |

\* Best sellers effectiveness depends on subcategory availability on AU. See
Best Sellers Page section for AU gotchas.

### Cross-validation: keyboards (2026-05-04)

Tested `"mechanical keyboard"` to validate strategy across categories:

| Surface | ASINs | Sponsored | Notes |
|---------|-------|-----------|-------|
| Dept-scoped `&i=electronics` | 31 | 7 | Baseline |
| Dept-scoped `&i=computers` | 33 | 9 | Overlapping but distinct from electronics |
| Full-catalog (no `&i=`) | 60 | 12 | 57 unique (3 dupes on page) |
| Synonym "mech keyboard" | 28 | 4 | Different vocabulary, different results |
| Category landing page | 89 | N/A | Consistent yield across categories |
| Best sellers (keyboards) | N/A | N/A | No dedicated subcategory on AU |
| Related products (EPOMAKER F75) | 16 | N/A | Includes self-ASIN |
| `&s=price-asc` | 27 | 3 | 14 sort violations, count dropped from 31 |
| `&pct-off=30-` | 25 | 1 | 8 discounted items, sponsored 4% |
| `-gaming -rgb` exclusion | 33 | 9 | No filtering effect, 30/33 titles contained excluded terms |

Key finding: exclusion syntax is unreliable, not just for sponsored results.
Previously documented as "sponsored-only override" but keyboard test showed
organic results also unaffected. Updated query syntax limitation section.

### Cross-validation: portable SSD (2026-05-04)

Tested `"portable SSD"` — high-value product ($67-$836 range), department overlap
(computers/electronics), counterfeit risk. Stress-tested sort accuracy and
discount filter effectiveness.

| Surface | ASINs | Sponsored | Notes |
|---------|-------|-----------|-------|
| Dept-scoped `&i=computers` | 33 | 9 | Baseline, price range $67-$836 |
| Dept-scoped `&i=electronics` | 33 | 9 | Near-identical ASINs to computers |
| Full-catalog (no `&i=`) | 60 | 12 | Standard expansion |
| Synonym "external SSD" | 33 | 9 | Different first results from "portable SSD" |
| Category landing page (computers) | 78 | N/A | Different from electronics (89) |
| Best sellers (data storage) | 30 | N/A | Mostly SD cards/USB — SSDs buried |
| New releases (data storage) | 30 | N/A | Same DOM as best sellers, distinct products |
| Related products (SanDisk Extreme) | 32 | N/A | Highest related count seen |
| `&s=price-asc` | 26 | 3 | 11 violations, started at $144 then $14.99 |
| `&s=price-desc` | 26 | 3 | Same first 5 prices as price-asc! Sort is decorative |
| `&pct-off=30-` | 24 | **0** | Zero sponsored — strongest noise reduction seen |

Key findings:
- `&s=price-desc` produces the *same ordering* as `&s=price-asc` — Amazon ignores
  sort direction entirely on this query
- Discount filter eliminated 100% of sponsored results on SSDs (vs 92% on keyboards,
  78% on headphones) — effectiveness scales with product price point
- Category landing page yield varies by department: Computers 78 vs Electronics 89
- Related products scale with product popularity: 32 for SanDisk (78K reviews) vs
  16 for EPOMAKER keyboard (3.4K reviews)
- New Releases page uses identical DOM to Best Sellers — same extractor works
