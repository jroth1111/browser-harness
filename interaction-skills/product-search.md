---
name: product-search
description: Search for products across marketplace domain skills (AliExpress, eBay, Walmart, Amazon) with maximum coverage using composable layered queries and platform-specific transport.
---

# Product Search — Cross-Platform Marketplace Search Prompt

Use this when the user wants to find products on one or more marketplace platforms.
Handles both single-platform and cross-platform searches.

## Entry Map

| Task | Section |
|---|---|
| Run a known product search on one platform | Steps 1-2 (platform scripts below) |
| Run cross-platform search | Steps 1-5 |
| Filter noise and verify coverage | Steps 4-5 |
| Search for all products containing a chip/component | Marketplace Search Strategy → Maximum-coverage search |
| Search for a product category (not a specific model) | Marketplace Search Strategy → Product search vs category search |
| Deal with marketplace fraud/scams | Marketplace Trust and Fraud |
| Compare prices across platforms | Marketplace Trust and Fraud → Cross-platform comparison |
| Understand why search price ≠ detail price | Marketplace Trust and Fraud → Search-level price vs detail-level price |

## Step 1: Determine platforms and query parameters

From the user's request, extract:

| Parameter | Source | Example |
|-----------|--------|---------|
| Query | Main product name | "RTX 4090", "Ryzen AI Max+ 395" |
| Synonyms | Alternative names | "Strix Halo", "GeForce RTX 4090" |
| Specs | Distinguishing specs that change results | "24GB", "48GB", "128GB" |
| Modifiers | Category/context words | "graphics card", "mini PC", "laptop", "gaming PC" |
| Platforms | Which marketplaces | eBay, Walmart, Amazon, AliExpress |

If the user doesn't specify platforms, search all available platforms where
domain skills exist. Check `domain-skills/<platform>/` for availability.

## Step 2: For each platform, run the search plan

### AliExpress

```bash
python3 domain-skills/aliexpress/scripts/search.py plan "{QUERY}" \
  --synonyms {SYNONYMS} --specs {SPECS} --modifiers {MODIFIERS}
```

**Transport:** CDP (browser). AliExpress requires browser session.

**Workflow:**
1. Run `search.py extract-js --reset` → execute reset JS via CDP
2. Navigate to each URL from the plan
3. After each page load, run extraction JS via CDP `evaluate_script`
4. After all URLs, run dump JS → save JSON

**Extraction details:** See `domain-skills/aliexpress/scraping.md` for selectors,
accumulation strategy, and platform-specific gotchas.

**Merge:**
```bash
python3 domain-skills/aliexpress/scripts/search.py merge results.json \
  --require {KEYWORDS} --exclude {NOISE} --min-price {FLOOR}
```

### eBay

```bash
python3 domain-skills/ebay/scripts/search.py search "{QUERY}" \
  --synonyms {SYNONYMS} --modifiers {MODIFIERS} --output results.csv
```

**Transport:** `http_get` via `curl_cffi` + browser cookies. No browser needed for search.

**Workflow:** Single command fetches all pages, extracts, deduplicates, classifies.

**Extraction details:** See `domain-skills/ebay/scraping.md` for rate limits,
cookie handling, URL params, and platform-specific gotchas.

### Walmart

**Transport:** `http_get` with bare `Mozilla/5.0` UA. No browser needed.

**Workflow:** Manual — no batch scripts yet. Use the patterns from `domain-skills/walmart/scraping.md`:

1. Build search URL with query and sort params
2. Fetch with appropriate UA (see domain skill for required UA)
3. Extract from embedded JSON
4. Filter results by title relevance and price

**Extraction details:** See `domain-skills/walmart/scraping.md` for URL patterns,
JSON paths, UA requirements, and platform-specific gotchas.

### Amazon

**Transport:** CDP (browser). Amazon requires browser session.

**Workflow:** Manual — no batch scripts yet. Use patterns from `domain-skills/amazon/product-search.md`:

1. Navigate to search URL with query
2. Wait for dynamic content
3. Extract from search result cards
4. Handle pagination if needed

**Extraction details:** See `domain-skills/amazon/product-search.md` for URL patterns,
currency handling, and platform-specific gotchas.

## Step 3: Cross-platform orchestration

When searching multiple platforms in parallel:

1. **Group by transport:**
   - `http_get` group (eBay, Walmart) → run in parallel via `ThreadPoolExecutor`
   - CDP group (AliExpress, Amazon) → run sequentially (single browser session)

2. **Normalize results** to common schema:

```python
{
    "platform":     str,    # "ebay" | "walmart" | "amazon" | "aliexpress"
    "product_id":   str,    # platform-specific ID
    "title":        str,
    "price":        float,  # numeric, currency-normalized to AUD
    "currency":     str,    # "AUD" | "USD"
    "url":          str,    # cleaned product URL
    "match_term":   str,    # which search term matched
    "condition":    str,    # "new" | "used" | "refurbished" | None
}
```

3. **Deduplicate across queries** by platform-specific product ID
4. **Present** sorted by price or grouped by platform

## Step 4: Noise filtering (universal)

All platforms return noise. Apply this cascade **in this order**:

1. **Dedup by product ID** — remove duplicates across queries first, so subsequent
   filters produce accurate counts.
2. **Price floor** — set to ~50-60% of known retail to eliminate cheap accessories and scams
3. **`--require` keywords** — title must contain at least one relevant term
4. **`--exclude` keywords** — filter known noise categories

The ordering matters: dedup before filtering gives accurate stats per stage; price
floor before keyword filter gives separate counts for price-filtered vs keyword-filtered.

**Exclusion matching must use word boundaries.** Plain substring matching produces
false positives — excluding "model" matches "3D Modeling", excluding "case" matches
"carrying case statement". Use `\b` + `re.escape()` for all exclusion terms:

```python
import re
exclude_patterns = [re.compile(r'\b' + re.escape(term) + r'\b', re.IGNORECASE)
                    for term in exclude_terms]
```

**Ambiguous identifier disambiguation.** When a search target shares a numeric ID
with other products (e.g., "6000" = RTX A6000 vs RTX 6000 Ada vs RTX PRO 6000),
the relevance filter must require an adjacent qualifier:

```python
# For "RTX PRO 6000" — require "pro" adjacent to "6000" in title
pattern = re.compile(r'pro\s*6000')
if not pattern.search(title_lower):
    return False
```

This prevents cross-family noise without requiring exact product name matches.

Common noise by product type (table structure is reusable; specific keywords are
domain-specific examples — adjust for the target product category):

| Searching for | Common noise | Exclude keywords |
|---------------|-------------|-----------------|
| GPUs | Water blocks, NVLink bridges, cables, coolers | "water block" "bridge" "cable" "cooler" "fan" |
| Systems | Standalone components, bare motherboards | "graphics card" "GPU only" "motherboard" |
| Laptops | Cases, sleeves, chargers, batteries | "case" "sleeve" "charger" "battery" "adapter" |
| Monitors | Mounts, cables, screen protectors | "mount" "stand" "cable" "protector" |

For ambiguous product names (e.g., "A5000" = Sony cameras, "L40S" = vacuum cleaners):
- Always use the full product name with brand prefix ("RTX A5000", "NVIDIA L40S")
- Add `--exclude` for the noise category

## Step 5: Coverage verification

After initial search, verify coverage:

1. Did Layer 2 find all expected product types/models?
2. If not, run Layer 3 queries for underperforming terms
3. For hot products, add specificity variants via `--specs` — these nearly double coverage
4. Check if any known products are missing from results

## Component-to-product mapping

When the user searches by technical component name (e.g., "GB10", "AD102"),
expand to consumer product names using the mapping in
`interaction-skills/marketplace-search.md`.

Example: "GB10" → search for "RTX 5060", "RTX 5070", "RTX 5070 Ti", "RTX 5080", "RTX 5090"

## Product classification framework

When search results contain multiple product categories (standalone GPUs, prebuilt
systems, laptops, accessories), classify each result for grouping and filtering.
Use an ordered specificity list with first-match-wins:

1. Define classification patterns from most specific to least specific.
2. Test each pattern against the title in order. First match wins.
3. Fall back to "Unknown" if no pattern matches.

```python
# Framework — patterns go from most specific to least specific
PRODUCT_PATTERNS = [
    (r"\bRTX\s*PRO\s*6000\b", "RTX PRO 6000", "standalone_gpu"),
    (r"\bRTX\s*6000\s+Ada\b", "RTX 6000 Ada", "standalone_gpu"),
    (r"\bRTX\s*4090\b",       "RTX 4090",     "standalone_gpu"),
    # ... more specific patterns ...
    # Generic patterns last
    (r"\bGPU\b",              "Unknown GPU",   "standalone_gpu"),
]
```

The framework (ordered patterns, first-match, fallback) is generic. The actual
regex patterns and product names are domain-specific and live in each domain
skill's `classify_product_line.py`. When adding a new marketplace domain skill,
implement classification using this framework with site-specific patterns.

## Key constraints by platform

Domain-specific filter parameters, URL patterns, and extraction details live in
each `domain-skills/<platform>/` skill. The table below summarizes constraints
for quick reference during cross-platform orchestration.

| Platform | Items/page | Has URL sort | Has URL price filter | Bot detection |
|----------|-----------|-------------|---------------------|---------------|
| AliExpress | 60 | Yes | Yes | None observed |
| eBay | ~48 | Yes | Yes (condition filter) | Rate limit ~5-10 req |
| Walmart | ~40 | Yes | Yes | PerimeterX (see domain skill) |
| Amazon | ~48 | No (relevance only) | No (sidebar only) | None observed |

## Pagination algorithm

For any paginated search endpoint, use convergence-based pagination rather than
a fixed page count:

1. **Zero-streak convergence**: Track consecutive full pages that return 0 new
   items (after dedup by product ID). When the streak reaches N (typically 2),
   stop. A "full page" is one that returns the platform's max items per page
   (~48-60 depending on platform).
2. **Short-page termination**: If a page returns fewer items than the platform
   maximum, it's the last page — stop immediately.
3. **Loop detection**: If two consecutive pages return the same number of new
   items (and that number > 0), probe the next page. If it also returns the
   same count, the platform is repeating results — stop.
4. **Hard cap**: Always set `max_pages` (typically 50) as a safety limit.
5. **Backoff after blocks**: If a page returns empty after retries (likely WAF
   or rate limit), increment a separate block counter. Apply exponential
   backoff between blocked attempts.

The convergence algorithm replaces fixed "fetch N pages" approaches because the
right depth varies per query — hot products need 5-10 pages, niche products
converge after 1-2.

## Coverage verification

After a maximum-coverage search, run verification probes to measure how
complete the results are. Use the gap-ratio model rather than absolute counts:

1. **Sort-variant probes**: Re-run the primary query with different sort orders
   (cheapest-first, most-expensive-first) as separate paginated searches. These
   surface items that default sort buries deep in pagination.
2. **Query-variant probes**: Re-run with/without brand prefixes (e.g., "Ryzen AI
   Max+ 395" vs "AI Max+ 395") to catch listings that omit the brand.
3. **Known-product probes**: If the search targets specific known products, check
   whether each was found. For any missing product, run a targeted query.
4. **Calculate gap ratio**: `gap_ratio = new_from_probes / total_listings_found`
5. **Rate coverage**:
   - `new_from_probes == 0` → **HIGH** — gap probes found nothing new
   - `gap_ratio ≤ 0.03` or `new_from_probes ≤ 5` → **MEDIUM**
   - otherwise → **LOW** — re-run recommended

Coverage verification is mandatory for exhaustive/category searches and optional
for single-product lookups.

## When to stop searching

- After 3-4 queries with 0 new unique products, the product likely doesn't exist on that platform
- Enterprise/data-center products are genuinely scarce on consumer marketplaces
- Recognize absence rather than endlessly broadening queries

---

## Marketplace Search Strategy

### Product search vs category search

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

### Maximum-coverage search strategy for component-containment queries

When searching for all products containing a specific component or chip,
use a 4-layer query taxonomy ordered by specificity:

1. **Known product names** — "DGX Spark", "Ascent GX10", "EdgeXpert"
2. **Chip/component references** — "GB10", "Grace Blackwell", "GB10 Grace"
3. **Category + architecture** — "Blackwell AI server", "Blackwell supercomputer",
   "Blackwell workstation", "Blackwell mini PC"
   Each form-factor synonym must be a **separate query**. Marketplace search
   engines do not treat "mini PC", "desktop", "workstation", "host", "server"
   as equivalent — they reach different slices of the product index. Enumerate
   all plausible synonyms rather than assuming the engine equates them.
4. **Spec-level** — "128GB LPDDR5X Blackwell", "arm cortex x925 blackwell"

Layers 1-2 find products you already know about. Layer 3 catches products
described generically. Layer 4 catches products that share hardware specs but
are from different product lines (e.g., Jetson AGX Thor shares Blackwell GPU +
128GB LPDDR5X with GB10 systems).

**All 4 layers are mandatory.** Skipping any layer leaves coverage gaps.
Field testing confirmed that skipping Layer 1 (product names) missed 40% of
total listings that chip-level queries didn't surface. The same product listing
appears under different query result sets depending on whether the query matches
the product name, the chip name, or the category.

Run all queries without price floor. Deduplicate by product ID across all
queries. Filter by title relevance. Verify survivors on detail pages.

**Iterative discovery loop.** Run layers 2-3 first to discover product names
present on the platform. Then immediately run layer 1 queries for every product
found. This two-pass approach ensures layer 1 uses actual product names from
the platform rather than assumed names that may not exist there.

```
Pass 1: layers 2-4 → discover products → extract unique product names
Pass 2: layer 1 queries for each discovered product name → new listings
Deduplicate across all passes by product ID
```

**Pagination is mandatory for hot products.** If a query returns ≥50 results
on page 1, run at least pages 1-3. Single-page results are incomplete — hot
products can return 80+ items on page 1 with more on subsequent pages. For
niche products (<50 results), page 1 is sufficient.

**Exact chip ID in the relevance filter.** When the target is a specific chip
model (e.g., "Ryzen AI Max+ 395"), the relevance filter must require that
exact identifier ("395") in the title. Do not accept "max" + product name
alone — the same product family ships with multiple chip tiers (380, 385, 390,
395, plus PRO variants). Filtering on "max" + "ZBook" returns all five chip
tiers, not just the 395.

```python
# Wrong — accepts 380, 385, 390, PRO 380, PRO 385, PRO 390, 395
'395' not required, just 'max' + product name

# Right — only 395 listings
target_chip = '395'
relevant = [i for i in items if target_chip in i['title']]
```

**Chip families have multiple tiers.** Modern chips ship in families (Ryzen
AI Max 380/385/390/395, PRO variants). The same product chassis (HP ZBook
Ultra G1a, HP Z2 G1a Mini) is available with every tier. When searching for
one tier, the relevance filter must exclude the others explicitly.

**Homonym noise**: when the product name contains common English words ("spark",
"grace", "edge"), searches return massive noise (spark plugs, baby names,
etc.). Title relevance filtering is mandatory — include at least one
domain-specific term in the filter.

**Negative results are findings**: 3 query variations × 0 results = confirmed
absence. "Not available on this platform" is a first-class result alongside
positive findings. Record it in the output.

**Accessory noise scales with product popularity.** Hot products attract
accessory listings (cases, bags, stickers, rack mounts, cables, screen
protectors) that contain the product name but cost $10-50 vs $3,000+ for the
actual product. A price floor filter (e.g., `price > $200` for systems) or
an accessory keyword blocklist eliminates these at the filter stage.

### Embedded JSON metadata discovery

Many platforms embed filter and sort metadata in their page JSON. Extract this
to discover all available URL parameters without reverse-engineering the UI. See
`interaction-skills/data-source-exploration.md` for the generic discovery
workflow and common framework patterns. Platform-specific variable names and
JSON paths belong in each `domain-skills/<platform>/` skill.

Run a metadata extraction pass on any new marketplace to build the URL parameter
reference before building extractors. If the platform adds new filters, they'll
appear in the metadata without re-probing.

### Location/sourcing defaults vary by platform

Many marketplaces default to showing international sellers on regional sites.
Before running any price comparison, test whether the default search includes
local sellers or only international ones. If the default is worldwide, add the
location filter to every search URL for that platform. This is a server-side
filter — it removes irrelevant items before they reach the extractor, and is
strictly better than post-filtering. Platform-specific location filters are
documented in each domain skill.

### Convergence rate scales with market density

Niche products converge after 2-3 queries (GB10: 14 listings → 2 products).
Hot products converge more slowly but still converge — 6 verification queries
on a hot product (Ryzen AI Max+ 395: 86 listings → 18 product lines) found
only 1 additional product line. The gap is usually vocabulary (missing
form-factor synonyms), not depth (missing pagination). Verification queries
should test synonym coverage rather than deeper pagination.

---

## Marketplace Trust and Fraud

### Marketplace fraud avoidance

For platforms with gray-market or counterfeit risk (AliExpress, eBay, etc.):

1. **Seller trust is the primary filter.** Always extract seller reputation
   data (feedback %, feedback count, account age) alongside listing data.
   A price from a seller below the platform's trust threshold is not a valid
   data point — exclude it before comparison. Typical thresholds: <95%
   positive feedback or <100 transactions = exclude. Domain skills define
   the exact extraction method and thresholds for their platform.
2. **Sort order is a fraud filter.** Cheapest-first sort surfaces scams.
   Use most-popular or most-expensive sort to surface legitimate sellers.
   Sort param names are platform-specific — see domain skills.
3. **Server-side price floors eliminate most scams.** Scam listings are
   always priced below market. A URL-level price range removes them before
   they reach the extractor. Price filter param names are platform-specific.
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
   listings. When the same count appears on listings from different sellers
   at wildly different prices, it's a platform or seller fabrication — not
   real transaction data. Do not use fabricated counts as a trust signal.
   Domain skills should document observed fabrication patterns for their
   platform.
7. **Auto-generated seller names + zero feedback = fabrication.** The
   combination of an auto-generated seller name pattern (random letters/digits)
   and 0 feedback is a stronger fabrication signal than either alone. "Low
   feedback" is not sufficient — it's the name pattern that distinguishes
   newly-created scam stores from legitimate new sellers.
8. **Cross-listing order count parity = platform fabrication.** When unrelated
   listings from different sellers share the same order count, the platform is
   fabricating the numbers. This is distinct from seller-level fabrication —
   it's a platform-level artifact that affects all listings equally. Do not
   rely on order counts from platforms exhibiting this pattern.
9. **Title truncation is a platform-wide data quality issue.** Platforms that
   truncate titles at ~80 chars lose configuration data (RAM, storage, GPU
   tier) for listings with long SKU numbers. This is not a seller error — it's
   a platform limitation. When title truncation is known for a platform, always
   verify specs on the detail page rather than extracting from the search title.
   Domain skills should document truncation behavior.
10. **Condition is a mandatory grouping axis for price comparison.** On any
    marketplace with used goods, item condition (new/used/refurbished/for parts)
    must be treated as a first-class grouping dimension alongside configuration.
    Mixing conditions in a single price range produces misleading comparisons.

### Fraud patterns are category-specific

| Category | Dominant fraud pattern | Why |
|----------|----------------------|-----|
| GPUs | Accessory variant traps (cables as variants) | Small accessories can co-list |
| Configurable systems | Multi-config price gaming (search shows cheapest config) | RAM/storage variants are legitimate |
| Enterprise/niche systems | Seller quality variance (few listings, variable trust) | Small seller pool, no scale |
| Hot consumer products | Fresh stores with no track record | New sellers flood in to capitalize |

Fraud avoidance strategy should be category-aware. Domain skills should add
category-specific detection (e.g., GPUs check for accessory variants, mini
PCs check for config-level price gaming).

### Market density predicts seller quality distribution

Niche products (few listings, small seller pool) have more established sellers
but fewer choices. Hot products (many listings, flooded market) attract both
legitimate new entrants and scammers. Adjust seller trust thresholds by market
density:

- **Niche (< 20 listings)**: use standard thresholds (≥95% feedback, ≥500 followers)
- **Hot (> 50 listings)**: lower follower threshold (≥10 acceptable if feedback ≥95%),
  but increase scrutiny on 0% feedback sellers

For hot products, seller verification matters more than product verification
(the product is real, but is the seller?). For niche products, product
existence verification matters more (does the product even exist on this
platform?).

### When to stop searching for niche products

After 3 query variations with 0 results for a specific product, the product
likely isn't on the platform. Continue broadening after this point returns
unrelated items, not missed products. Document the absence as a finding — "not
available on this platform" is a valid and useful result.

For maximum-coverage searches, expand this to 3 query variations × 4 query
layers before concluding absence.

### Verified-sample trust is sufficient for hot products

For product categories with 50+ listings, verifying cheapest/most-expensive/median
listing per product type (a ~30% sample) catches all HIGH_RISK sellers. Risk
concentrates at price extremes: the cheapest listing in a category is most likely to
be a scam, and the most expensive is most likely to be mislabeled. Full verification
of every listing is unnecessary for hot products.

### Condition is a price axis for configurable hardware

On marketplace platforms with used goods (eBay, Facebook Marketplace, Gumtree), item
condition (New/Used/Refurbished/Open Box/For Parts) is as important as configuration
(RAM/storage) for price comparison. A used ROG Flow Z13 sells for $2,520–$3,800; the
same system new is $3,800–$4,000. Without condition, a $2,520 price looks like a great
deal when it's actually a defective unit ("FRAME SPLIT", "Cracked Screen").

Condition is rarely available at search level. It requires detail-page extraction.
Group results by condition before comparing prices. Never mix conditions in a single
price range without labeling.

Some sellers include defects directly in titles — "FRAME SPLIT", "ODOR ISSUE",
"Cracked Screen". These are transparency disclosures, not fraud. Flag them as
defective for price comparison but don't exclude them from results.

### Sellers misname products on marketplace platforms

Marketplace sellers frequently use incorrect product names. Confirmed: "ROG Flow X13"
listings (which is not a real ASUS product — it's the ROG Flow Z13) at premium prices.
For category searches, exact product name matching misses mislabeled listings. Use
fuzzy matching that accounts for close variant names and common seller errors.

### Title truncation loses config on marketplace platforms

Marketplace platforms truncate titles at ~80 characters on some sites. Business/OEM
listings with long SKU numbers lose the RAM/storage config in truncation. Title-based
RAM extraction returns "?" for these. Must hit detail pages for spec extraction on
listings with SKU-based titles. Domain skills should document truncation behavior.

### Cross-platform comparison requires detail pages

Search result data is insufficient for like-for-like comparison across
platforms. Search result titles are truncated, abbreviated, or misleading
(platforms show accessories alongside real products).

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

### Search-level price vs detail-level price

Search result prices are preliminary estimates, not final. On marketplaces with
multi-variant listings, the search-level price can differ significantly from the
detail page price for the same product ID. Observed: search JSON showed
AU$13,453 but the detail page showed AU$6,957 for the same listing.

This applies across platforms — any site with variant-based pricing can show a
different price at search level. The detail page is always canonical.

**For configurable hardware (mini PCs, laptops, desktops, servers), the search
price is guaranteed to be the cheapest configuration, not the one you want.** A
listing with 64GB/96GB/128GB RAM variants will always show the 64GB price in
search results. This is a different problem than price drift — it's systematic
misrepresentation by configuration. Comparison must happen at the variant level:
navigate to the detail page, identify the target configuration in the variant
list, and use that variant's price.

Use search-level prices only for initial filtering and ordering. Never report
them as final prices without detail-page verification.
