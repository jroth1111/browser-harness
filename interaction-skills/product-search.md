---
name: product-search
description: Search for products across marketplace domain skills (AliExpress, eBay, Walmart, Amazon) with maximum coverage using composable layered queries and platform-specific transport.
---

# Product Search — Cross-Platform Marketplace Search Prompt

Use this when the user wants to find products on one or more marketplace platforms.
Handles both single-platform and cross-platform searches.

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

**Extraction gotchas:**
- CSS classes are obfuscated — extraction uses `a[class*="search-card-item"]`
- Price via innerText regex (`AU$X,XXX.XX`), not CSS selectors
- `evaluate_script` requires plain arrow functions `() => {...}`, NOT IIFE
- Accumulation uses `localStorage` (not window variables — those die on navigation)

**Merge:**
```bash
python3 domain-skills/aliexpress/scripts/search.py merge results.json \
  --require {KEYWORDS} --exclude {NOISE} --min-price {FLOOR}
```

### eBay

```bash
python3 domain-skills/ebay/scripts/search.py search "{QUERY}" \
  --base-terms {SYNONYMS} --form-factors {MODIFIERS} --output results.csv
```

**Transport:** `http_get` via `curl_cffi` + browser cookies. No browser needed for search.

**Workflow:** Single command fetches all pages, extracts, deduplicates, classifies.

**Extraction gotchas:**
- eBay rate-limits at ~5-10 requests per IP — backoff is built into the script
- Uses `browser_cookie3` for authenticated cookies (better results with login)
- `LH_BIN=1` filter excludes auctions (usually what you want for price comparison)

**Note:** eBay's `generate_search_urls.py` still uses chip-centric flags (`--base-terms`,
`--form-factors`). If the AliExpress generalized flags (`--synonyms`, `--specs`,
`--modifiers`) have been adopted, adapt the eBay flags accordingly.

### Walmart

**Transport:** `http_get` with bare `Mozilla/5.0` UA. No browser needed.

**Workflow:** Manual — no batch scripts yet. Use the patterns from `domain-skills/walmart/scraping.md`:

1. Build search URL: `https://www.walmart.com/search?q={query}&sort=best_seller`
2. Fetch with bare UA: `headers={"User-Agent": "Mozilla/5.0"}`
3. Extract from `__NEXT_DATA__` JSON embedded in HTML
4. Filter results by title relevance and price

**Extraction gotchas:**
- MUST use bare `Mozilla/5.0` UA — full Chrome UA triggers PerimeterX bot challenge
- All product data is in `window.__NEXT_DATA__.props.pageProps.initialProps.searchResult.itemStacks[0].items`
- Price range filter: `min_price=X&max_price=Y` in URL params

### Amazon

**Transport:** CDP (browser). Amazon requires browser session.

**Workflow:** Manual — no batch scripts yet. Use patterns from `domain-skills/amazon/product-search.md`:

1. Navigate to search URL: `https://www.amazon.com.au/s?k={query}`
2. Wait 2s for dynamic content
3. Extract from search result cards
4. Handle pagination if needed

**Extraction gotchas:**
- Amazon AU uses AUD, shows "RRP" where US shows "List Price"
- Session cookies matter — logged-in results may differ
- No CAPTCHA observed in testing, but rate-limit if too many page loads

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

All platforms return noise. Apply this cascade:

1. **Price floor** — set to ~50-60% of known retail to eliminate cheap accessories and scams
2. **`--require` keywords** — title must contain at least one relevant term
3. **`--exclude` keywords** — filter known noise categories

Common noise by product type:

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

## Key constraints by platform

| Platform | Items/page | Sort options | Price filter | Bot detection |
|----------|-----------|-------------|-------------|---------------|
| AliExpress | 60 | total_volume, price_desc | `pr=min-max` URL param | None observed |
| eBay | ~48/page | _sop=15 (price), 16 (date) | LH_BIN=1 (Buy It Now) | Rate limit ~5-10 req |
| Walmart | ~40 | sort=best_seller, price_low | min_price/max_price params | PerimeterX (use bare UA) |
| Amazon | ~48 | (default relevance) | (via sidebar filters) | None observed |

## When to stop searching

- After 3-4 queries with 0 new unique products, the product likely doesn't exist on that platform
- Data-center GPUs (L40S, A100, H100) are genuinely scarce on consumer marketplaces
- Recognize absence rather than endlessly broadening queries
