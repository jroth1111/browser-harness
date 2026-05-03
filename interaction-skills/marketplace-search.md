# Marketplace Search — Cross-Platform Product & Component Search

Use this when the query searches for products across multiple e-commerce
platforms — either a known product ("find RTX 5090 prices everywhere") or a
component-containment search ("find desktops/laptops containing GB10").

Field-tested on 2026-05-02 with GB10 (Blackwell) → RTX 5070 laptop/desktop
searches across eBay (79 results), Walmart (60/374 total), and AliExpress
(60 per query).

## What belongs here

Generalizable:

- component-to-product mapping
- cross-platform orchestration pattern
- common result schema
- form-factor filtering heuristics
- query construction strategy

Platform-specific extractors, URLs, and transport details belong in
`domain-skills/<platform>/`. This skill orchestrates across them; it does not
duplicate their extractors.

## Component-to-product mapping

Translate technical chip/component names to consumer-facing product names that
sellers actually list. Searches for "GB10" return nothing; searches for
"RTX 5070 laptop" return real results.

These mappings are shared across all marketplace domain skills. They are
component-vendor knowledge (NVIDIA/AMD product naming), not site-specific
knowledge — they apply regardless of which marketplace is being searched.

### NVIDIA GPUs

| Component | Architecture | Consumer products | Form factors |
|-----------|-------------|-------------------|--------------|
| GB10 | Blackwell | RTX 5060, RTX 5070, RTX 5070 Ti, RTX 5080, RTX 5090 | desktop, laptop |
| GB202 | Blackwell | RTX 5090 | desktop only |
| GB203 | Blackwell | RTX 5070, RTX 5070 Ti | desktop, laptop |
| GB205 | Blackwell | RTX 5060 Ti | desktop, laptop |
| GB206 | Blackwell | RTX 5060 | desktop, laptop |
| AD102 | Ada Lovelace | RTX 4090 | desktop only |
| AD103 | Ada Lovelace | RTX 4080, RTX 4080 SUPER | desktop, laptop |
| AD104 | Ada Lovelace | RTX 4070, RTX 4070 Ti, RTX 4070 SUPER | desktop, laptop |
| AD106 | Ada Lovelace | RTX 4060 Ti | desktop, laptop |
| AD107 | Ada Lovelace | RTX 4060 | desktop, laptop |
| GA102 | Ampere | RTX 3090, RTX 3090 Ti, RTX 3080 Ti | desktop only |
| GA103 | Ampere | RTX 3080 | desktop, laptop |
| GA104 | Ampere | RTX 3070, RTX 3070 Ti, RTX 3060 Ti | desktop, laptop |
| GA106 | Ampere | RTX 3060 | desktop, laptop |
| GA107 | Ampere | RTX 3050 | desktop, laptop |

### NVIDIA Data Center / Workstation

| Component | Architecture | Consumer products | Form factors |
|-----------|-------------|-------------------|--------------|
| GB100 | Blackwell | B200, B100, GB200 | data center |
| GH100 | Hopper | H100, H200 | data center |
| AD102 (pro) | Ada | RTX 6000 Ada | workstation |
| GA100 | Ampere | A100 | data center |
| GA102GL | Ampere | RTX A6000, RTX A5000 | workstation |

### AMD GPUs

| Component | Architecture | Consumer products | Form factors |
|-----------|-------------|-------------------|--------------|
| Navi 48 | RDNA 4 | RX 9070, RX 9070 XT | desktop |
| Navi 44 | RDNA 4 | RX 9060, RX 9060 XT | desktop |
| Navi 31 | RDNA 3 | RX 7900 XTX, RX 7900 XT | desktop |
| Navi 32 | RDNA 3 | RX 7800 XT, RX 7700 XT | desktop |
| Navi 33 | RDNA 3 | RX 7600, RX 7600 XT | desktop |

### Adding new entries

When a user searches for a component not in the table:
1. Identify the architecture and product family
2. List all consumer-facing product names (the names sellers use in listings)
3. Note available form factors
4. Add to the table

## Query construction

For each product name from the mapping, construct platform-specific queries.
The form factor constrains the query:

```
Desktop:  "{product} desktop", "{product} PC", "{product} gaming PC",
          "{product} workstation", "{product} prebuilt"
Laptop:   "{product} laptop", "{product} notebook"
```

Not all variations are needed for every platform. Use 1-2 per form factor:

| Platform | Query style | Why |
|----------|------------|-----|
| eBay | `"{product} laptop"` + `LH_BIN=1` | eBay respects quotes and BIN filter works well |
| Walmart | `"{product} laptop"` | Walmart's search handles multi-word queries well |
| Amazon | `"{product} laptop"` | Same — Amazon search handles it naturally |
| AliExpress | `"{product} laptop"` + `pr={min}-{max}` | Price floor essential to eliminate scams |

### Deduplication across queries

Multiple queries (e.g., "RTX 5070 laptop" and "RTX 5070 notebook") will
return overlapping results. Deduplicate by platform-specific product ID:
- eBay: `listing_id`
- Walmart: `usItemId`
- Amazon: ASIN
- AliExpress: `productId`

## Orchestration pattern

Each platform has a different transport. Parallelize where possible.

### Platform transport (from domain skills)

| Platform | Transport | Rate limit | Extractor doc |
|----------|-----------|------------|---------------|
| eBay | `http_get` | ~5-10 req/IP then block | `domain-skills/ebay/scraping.md` |
| Walmart | `http_get` (bare UA) | No observed limit | `domain-skills/walmart/scraping.md` |
| Amazon | CDP (browser) | No observed limit | `domain-skills/amazon/product-search.md` |
| AliExpress | CDP (browser) | No observed limit | `domain-skills/aliexpress/scraping.md` |

### Execution order

```
1. Expand component → product names using mapping
2. Generate queries per product per form factor
3. Group queries by transport:
   - http_get group (eBay, Walmart) → ThreadPoolExecutor
   - CDP group (Amazon, AliExpress) → sequential (browser is single-session)
4. For each query:
   a. Build platform URL with query + filters
   b. Fetch page using platform's transport
   c. Run platform's search extractor
   d. Apply form-factor filter (title heuristics)
   e. Normalize to common schema
5. Deduplicate across queries by platform product ID
6. Optionally: fetch detail pages for top candidates
7. Present sorted by price or grouped by platform
```

### Parallel pattern (http_get platforms)

Following `domain-skills/news-aggregation/multi-source.md`:

```python
from concurrent.futures import ThreadPoolExecutor

def search_platform(args):
    platform, query, filters = args
    url = build_url(platform, query, filters)
    html = http_get(url, headers=HEADERS.get(platform, {}))
    if is_blocked(html, platform):
        return platform, []
    results = extract(html, platform)
    filtered = [r for r in results if is_system(r['title'])]
    return platform, [normalize(r, platform) for r in filtered]

tasks = [
    ("ebay", "RTX 5070 laptop", {"LH_BIN": 1, "_sop": 15}),
    ("walmart", "RTX 5070 laptop", {"sort": "price_low"}),
    # ...
]

with ThreadPoolExecutor(max_workers=len(tasks)) as ex:
    all_results = dict(ex.map(search_platform, tasks))
```

CDP platforms (Amazon, AliExpress) must run sequentially — the browser is a
single session. Run them after the http_get batch completes.

## Common result schema

Normalize all platform results to this shape for cross-platform comparison:

```python
{
    "platform":        str,       # "ebay" | "walmart" | "amazon" | "aliexpress"
    "product_id":      str,       # platform-specific ID
    "title":           str,       # full title from search results
    "price":           float,     # numeric price
    "currency":        str,       # "AUD" | "USD"
    "url":             str,       # cleaned product URL
    "form_factor":     str,       # "desktop" | "laptop" | "unknown"
    "match_term":      str,       # which search term matched (e.g. "RTX 5070")
    "is_system":       bool,      # True = system, False = standalone component
    "condition":       str,       # "new" | "used" | "refurbished" | None
    "image":           str,       # thumbnail URL (or None)
}
```

Platform-specific fields (rating, seller, orders, trap flags) are preserved
for detail-page analysis but not in the common schema.

## Form-factor filtering

Title-based heuristics to distinguish systems from standalone components.
Applied after extraction, before normalization.

### Is a system (keep)

Title contains:
- "laptop", "notebook", "desktop", "PC", "workstation"
- "prebuilt", "gaming PC", "all-in-one", "AIO"
- Both a GPU model AND a CPU brand ("Intel", "AMD Ryzen", "Threadripper")
- "DGX", "system", "server" (for data center products)

### Is a standalone component (exclude)

Title contains:
- "graphics card", "GPU", "video card", "videocard"
- Without also containing a system keyword

Title is just the GPU model name with no system context.

### Uncertain (flag for review)

Title mentions the GPU but has no clear system or component indicator.
Include with `is_system: None` — detail-page verification can resolve.

### Limitations

Title heuristics are approximate. Sellers use inconsistent naming. A listing
titled "RTX 5070 16GB GDDR7" could be a standalone GPU or a system where the
seller only listed the GPU spec. Detail-page verification resolves ambiguity
for high-value results.

### Field-tested accuracy (2026-05-02, AliExpress "RTX 5070 desktop")

| Classification | Count | Examples |
|---------------|-------|---------|
| System (keep) | 50 | "Desktops Gamer Core I9-14900K RTX 5070 Gaming Pc", "Mini ITX Gaming PC RTX 5070 Desktop Computer" |
| Standalone GPU (exclude) | 10 | "MSI NVIDIA RTX 5070 12GB placa de vídeo", "GIGABYTE GeForce RTX 5070 EAGLE OC ICE Video Card" |

~83% accuracy on the "desktop" query. The 10 GPU-only results slipped through
because the word "desktop" appears in the search query itself, pulling in
desktop GPU listings. Query-specific filtering ("desktop" in the query inflates
the "is_system" count) is a known limitation — the heuristic works better for
"laptop" queries where the form factor word is less ambiguous.

## Cross-references

- `domain-skills/ebay/scraping.md` — eBay extractors, URL params, rate limits
- `domain-skills/walmart/scraping.md` — Walmart extractors, `__NEXT_DATA__` pattern
- `domain-skills/amazon/product-search.md` — Amazon CDP extraction
- `domain-skills/aliexpress/scraping.md` — AliExpress CDP extraction, trap detection
- `interaction-skills/product-search.md` — filtering strategy, marketplace fraud avoidance, product-vs-category search
- `interaction-skills/cross-domain-control-flow.md` — backend routing, auth boundaries
- `domain-skills/news-aggregation/multi-source.md` — ThreadPoolExecutor parallel fetch pattern
