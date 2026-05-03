# G2G — Product Search & Data Extraction

Field-tested against g2g.com on 2026-05-03 using `http_get` against the public JSON API
at `sls.g2g.com`. AU region (`/au`), AUD currency. No browser required.

**Not to be confused with g2.com (B2B software reviews).** This is the digital goods
marketplace at g2g.com (gift cards, game accounts, in-game items, software subscriptions).

## Source exploration

Follow the exploration order from `interaction-skills/data-source-exploration.md`:

1. **Exports**: G2G has no structured export/download. Skip.
2. **APIs**: `sls.g2g.com` is a public JSON API with `Access-Control-Allow-Origin: *`.
   No auth, no cookies, no TLS impersonation required. Returns structured JSON.
   Primary transport for all data extraction. See API Reference below.
3. **HTTP**: `http_get` works directly for both the API and the search HTML page.
   No WAF on the API endpoint. No bot detection observed.
4. **Browser (CDP)**: Not needed for data extraction. Only as fallback for UI
   features not exposed through the API (e.g., checkout flow).

**Backend selection**: `http_get` is the cheapest working backend. No auth, no cookies,
no TLS impersonation. The API returns fully structured JSON — no HTML parsing needed
for offer data. Category discovery uses the `categories.json` static asset; the HTML
search page is a fallback when that asset fails or returns no matches.

## API Reference

Base URL: `https://sls.g2g.com`

All endpoints return `{"code": 2000, "payload": ...}` on success. The `code` field is
an integer — `2000` means success. Error responses have different codes.

### 1. Search offers

```
GET /offer/search
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `seo_term` | string | Category slug (e.g., "google-cloud-storage-subscription") |
| `service_id` | UUID | Service/delivery type |
| `brand_id` | UUID | Brand identifier |
| `region_id` | UUID | Geographic region. `0f76ac42-3267-4d77-9fba-f9d9d719dac9` = Global |
| `filter_attr` | string | Denomination filter. Format: `collection_id:dataset_id` |
| `page_size` | int | Results per page. Max 100 |
| `page` | int | Page number. 1-based |
| `sort` | string | `recommended_v2` (default) or `lowest_price` |
| `currency` | string | Display currency code (e.g., `AUD`) |
| `country` | string | Country code (e.g., `AU`) |
| `group` | int | `0` = individual offers, `1` = grouped by product variant |
| `include_out_of_stock` | int | `1` to include OOS offers |
| `include_inactive` | int | `1` to include inactive offers |
| `include_offline` | int | `1` to include offline sellers |
| `exclude_offers` | string | Comma-separated offer IDs to exclude |
| `seller` | string | Filter to specific seller username |

Returns:
```json
{
  "code": 2000,
  "payload": {
    "results": [offer, ...],
    "total_count": 42
  }
}
```

### 2. Search result count

```
GET /offer/search_result_count
```

Same params as search. Returns total count for pagination without fetching full offers.

Returns:
```json
{
  "code": 2000,
  "payload": {
    "count": 142
  }
}
```

### 3. Keyword info

```
GET /offer/keyword_info
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `seo_term` | string | Category slug |
| `include_relation_detail` | int | `1` to include related categories |

Returns category metadata: display name, brand image, marketing description,
related categories, and ancestor chain.

### 4. Service types

```
GET /offer/keyword_relation/service
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `include_settings` | int | `1` to include delivery display settings |
| `include_gc` | int | `1` to include gift card settings |

Returns all service/delivery types available for a category: delivery modes,
display settings, gift card configurations.

### 5. Collections / denominations

```
GET /offer/keyword_relation/collection/
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `brand_id` | UUID | Brand identifier |
| `region_id` | UUID | Region filter |
| `service_id` | UUID | Service type filter |
| `include_searchable_only` | int | `0` to include all, `1` for searchable only |

Returns denomination/variant entries for a category. Each entry has a
`collection_id` and `dataset_id` used as `filter_attr` in the search endpoint.

### 6. Offer detail

```
GET /offer/{offer_id}
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `currency` | string | Display currency |
| `country` | string | Country code |
| `include_out_of_stock` | int | `1` to include OOS |
| `is_precheckout_page` | int | `1` for precheckout details |

Returns full offer details including extended description, delivery instructions,
and seller contact info.

### 7. Seller info

```
GET /user/{user_id}/info
```

Returns seller profile: username, avatar, join date, description, verification status.

### 8. Seller rating

```
GET /rating/user/{user_id}?user_type=all
```

Returns seller rating breakdown: positive/neutral/negative counts, rating percentage,
recent rating trends.

### 9. Seller completion rate

```
GET /order/seller/{user_id}/completion_rate
```

Returns order completion statistics: completion rate, cancellation rate, total orders.

### Offer data structure

```json
{
  "offer_id": "G1775488463122SX",
  "title": "Google Cloud Storage Subscription 2 TB (Global)",
  "description": "18-month subscription with 5TB storage...",
  "offer_currency": "USD",
  "unit_price": 7,
  "unit_price_in_usd": 7.00,
  "converted_unit_price": 10.01,
  "display_currency": "AUD",
  "display_price": "10.01",
  "formatted_unit_price": "7.00",
  "delivery_speed": "instant",
  "delivery_mode": ["instant_inventory"],
  "delivery_method_ids": ["instant_inventory"],
  "available_qty": 4,
  "reserved_qty": 1,
  "min_qty": 1,
  "wholesale_details": [
    {
      "min": 5,
      "max": 2147483647,
      "discount": 0.2,
      "unit_price": 5.6,
      "converted_unit_price": 8.0111,
      "formatted_unit_price": "5.60"
    }
  ],
  "satisfaction_rate": 1,
  "total_rating": 140,
  "total_success_order": 162,
  "seller_id": "4459048",
  "username": "NeoGaGa",
  "user_level": 99,
  "seller_ranking": "4",
  "user_avatar": "https://assets.g2g.com/user/avatar/...",
  "is_official": false,
  "is_online": true,
  "service_id": "8f88b6fd-93df-4a07-b8b0-7d90b152b81f",
  "brand_id": "67071d4a-b301-46d1-b385-092526f8a80f",
  "region_id": "0f76ac42-3267-4d77-9fba-f9d9d719dac9",
  "cat_id": "f8e8ebec-39a8-4fcb-8792-0f7d7474d6e4",
  "ancestor_id": "f6bb038d-9fe8-459c-a4df-a63e06f67e32",
  "offer_attributes": [
    {"collection_id": "b7d1999b", "dataset_id": "ade25ccd"}
  ],
  "filter_attributes": {"b7d1999b": ["ade25ccd"]},
  "offer_group": "/ade25ccd",
  "sales_territory_settings": {"settings_type": "global", "countries": []},
  "status": "live",
  "is_bundle": false
}
```

**Key fields for price comparison:**
- `converted_unit_price`: price in the requested currency (AUD). Use this for all comparisons.
- `unit_price`: price in the seller's listing currency (often USD). Do not use for AUD comparisons.
- `display_price`: string-formatted `converted_unit_price`. Redundant with `converted_unit_price`.
- `wholesale_details`: volume discount tiers. The base price is single-unit only.
- `satisfaction_rate`: float 0-1 (e.g., `0.9877` = 98.77%). Not a percentage.
- `total_success_order`: seller's all-time completed orders for this specific offer, not platform-wide.
- `seller_ranking`: string (`"4"`), not numeric. Parse with `int()` before sorting.
- `available_qty`: current stock minus reserved. `0` means out of stock.
- `sales_territory_settings.settings_type`: `"global"` means worldwide availability.

## Category Discovery

### Primary: categories.json index

```
https://assets.g2g.com/offer/categories.json
```

G2G preloads a static JSON index of all categories on every page. This is the primary
source for category discovery — faster and more reliable than parsing rendered HTML.

The JSON object has two types of entries:
- **Slug-keyed entries** (key starts with a letter, contains hyphens): full category
  data with `marketing_title`, `service_id`, `brand_id`.
- **UUID-keyed entries** (compound UUIDs like `8f88b6fd-..._67071d4a-...`): redirect
  pointers with just `{seo_term: "slug-name"}`.

**Match logic:** Check if the query appears in `marketing_title.en` or the slug key
itself (case-insensitive substring match).

**Parser pattern:**
```python
from helpers import http_get
import json

raw = http_get("https://assets.g2g.com/offer/categories.json", timeout=30.0)
index = json.loads(raw)

query_lower = query.lower()
# Process slug-keyed entries (rich data) — skip UUID redirect entries
slug_entries = {k: v for k, v in index.items()
                if isinstance(v, dict) and k and k[0].isalpha() and "-" in k}

for seo_term, entry in slug_entries.items():
    title_obj = entry.get("marketing_title", {})
    name = title_obj.get("en", "") if isinstance(title_obj, dict) else str(title_obj)
    if query_lower in f"{name} {seo_term}".lower():
        # entry has service_id, brand_id for Wave 2
        print(f"Found: {name} -> {seo_term}")
```

### Fallback: Search page HTML

```
https://www.g2g.com/au/search?q={query}
```

If `categories.json` fails or returns no matches, extract `seo_term` values from
`/categories/{seo_term}` href patterns in the HTML. This finds category slugs but
does not provide `service_id` or `brand_id` — those must be resolved via the
`keyword_info` API in Wave 2.

### Category page structure

```
https://www.g2g.com/au/categories/{seo_term}
```

Category pages contain:
- **Product type tabs**: different service/delivery modes (e.g., "Instant Delivery",
  "Email Delivery", "Account Access")
- **Sort options**: `recommended_v2` (default), `lowest_price`
- **Region filter**: dropdown with region UUIDs
- **Product cards**: offer groups representing each denomination/variant

The category page HTML is useful for interactive browsing but the API provides
all the same data more efficiently. Use the API for exhaustive data extraction.

### Category page to offer group

```
https://www.g2g.com/au/categories/{seo_term}/offer/group?fa={filter_attr}&region_id={region_id}
```

Shows all sellers for a specific product variant. Contains:
- Featured seller (top result)
- Other sellers section
- Product info panel
- Delivery details
- Other denominations sidebar
- Volume discount tiers

Again, the API endpoint `/offer/search` with `filter_attr` and `group=0` returns
all this data as structured JSON. Prefer the API.

## Product Detail Page

The offer group page at `/categories/{seo_term}/offer/group?fa=...&region_id=...`
is the buyer-facing product detail. It aggregates all sellers for a denomination.

For data extraction, use the API instead:
- `/offer/search` with `filter_attr` and `group=0` — all sellers for a denomination
- `/offer/{offer_id}` — full details for a single offer
- `/user/{user_id}/info` — seller profile
- `/rating/user/{user_id}` — seller rating breakdown
- `/order/seller/{user_id}/completion_rate` — seller reliability metrics

JSON-LD on offer pages contains only basic schema.org Offer/Product data — not the
full seller details. The API is the authoritative source for all data extraction.

## Pagination

API uses `page` (1-based) and `page_size` (max 100).

```python
from helpers import http_get
import json, time

def paginate_all_offers(seo_term, service_id=None, brand_id=None,
                        region_id=None, filter_attr=None, sort="recommended_v2"):
    """Fetch all offers for a category/denomination, paginating automatically."""
    all_offers = []
    page = 1

    while True:
        params = {
            "seo_term": seo_term,
            "page_size": 100,
            "page": page,
            "sort": sort,
            "currency": "AUD",
            "country": "AU",
            "group": 0,
        }
        if service_id:
            params["service_id"] = service_id
        if brand_id:
            params["brand_id"] = brand_id
        if region_id:
            params["region_id"] = region_id
        if filter_attr:
            params["filter_attr"] = filter_attr

        qs = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"https://sls.g2g.com/offer/search?{qs}"
        resp = json.loads(http_get(url))

        if resp.get("code") != 2000:
            break

        results = resp.get("payload", {}).get("results", [])
        if not results:
            break

        new_count = 0
        seen_ids = {o["offer_id"] for o in all_offers}
        for offer in results:
            if offer["offer_id"] not in seen_ids:
                all_offers.append(offer)
                seen_ids.add(offer["offer_id"])
                new_count += 1

        print(f"Page {page}: {len(results)} results, {new_count} new")

        # Convergence: stop when page returns 0 new offers
        if new_count == 0:
            break

        page += 1
        time.sleep(1)  # polite delay

    return all_offers
```

**Total page calculation:** Use `/offer/search_result_count` first to estimate:
```python
count_resp = json.loads(http_get(f"https://sls.g2g.com/offer/search_result_count?seo_term={seo_term}&..."))
total = count_resp["payload"]["count"]
max_pages = (total + 99) // 100
```

**Termination:** Stop when a page returns 0 results, or when 2 consecutive pages
return 0 new offers (after dedup). The latter catches pagination drift where the
same offers appear across pages.

## Sort Modes

| Sort | Value | Use when |
|------|-------|----------|
| Recommended (default) | `recommended_v2` | General browsing — surfaces high-rated sellers |
| Lowest price | `lowest_price` | Price comparison — finds cheapest offers first |

Different sorts may surface different offers. For coverage verification, run both
sorts and merge results:

```python
recommended = paginate_all_offers(seo_term, sort="recommended_v2")
cheapest = paginate_all_offers(seo_term, sort="lowest_price")

all_ids = {o["offer_id"] for o in recommended}
coverage_gap = [o for o in cheapest if o["offer_id"] not in all_ids]
print(f"Coverage gap: {len(coverage_gap)} offers found only by lowest_price sort")
```

If the coverage gap is small (< 3% of total), single-sort is sufficient.

## Scripts

Executable scripts in `domain-skills/g2g/scripts/`:

| Script | Purpose |
|--------|---------|
| `search.py` | Full exhaustive crawl: search, discover categories/service types/denominations, paginate all offers, dedup, CSV export, coverage report |

### Quick start

```bash
# Full exhaustive search:
python3 domain-skills/g2g/scripts/search.py search "google" --output results.csv

# With target keywords:
python3 domain-skills/g2g/scripts/search.py search "netflix" --output netflix.csv --target-keywords "premium" "family" "4k"

# Discover categories only:
python3 domain-skills/g2g/scripts/search.py categories "spotify"

# Enrich with detailed seller info:
python3 domain-skills/g2g/scripts/search.py seller results.csv --output seller-results.csv

# Generate coverage report from existing CSV:
python3 domain-skills/g2g/scripts/search.py coverage results.csv
```

## Workflow Algorithm

The exhaustive crawl uses a 4-wave BFS approach to discover every offer:

### Wave 1: Search query -> categories

```
Input:  free-text query (e.g., "google cloud")
Fetch:  https://assets.g2g.com/offer/categories.json
Parse:  JSON index -> match marketing_title or slug -> [{name, seo_term, service_id, brand_id}, ...]
Fallback: HTML search page -> extract /categories/{slug} hrefs
Output: set of seo_terms (with service_id, brand_id if available) for Wave 2
```

Primary source is the `categories.json` static asset. Falls back to the HTML search
page only if the JSON index fails or returns no matches.

### Wave 2: Category -> service types

```
Input:  seo_term from Wave 1
Fetch:  GET /offer/keyword_info?seo_term={seo_term}&include_relation_detail=1
        GET /offer/keyword_relation/service?include_settings=1&include_gc=1
Parse:  service types (delivery modes), brand_id, region_id
Output: set of (service_id, brand_id, region_id) tuples for Wave 3
```

Each category can have multiple service types (e.g., "Instant Delivery" vs
"Email Delivery" for gift cards). Each service type is a separate offer space.

### Wave 3: Service type -> collections/denominations

```
Input:  (brand_id, region_id, service_id) from Wave 2
Fetch:  GET /offer/keyword_relation/collection/?brand_id={brand_id}&region_id={region_id}&service_id={service_id}&include_searchable_only=0
Parse:  denomination entries -> [{collection_id, dataset_id, name}, ...]
Output: set of filter_attr strings ("collection_id:dataset_id") for Wave 4
```

Denominations represent product variants (e.g., "2 TB", "5 TB" for storage, or
"$50", "$100" for gift cards). Each denomination is a separate offer group.

### Wave 4: Denomination -> paginated offers

```
Input:  seo_term, service_id, filter_attr from Waves 2-3
Fetch:  GET /offer/search?seo_term={seo_term}&service_id={service_id}&filter_attr={filter_attr}&group=0&page_size=100&page=1&sort=recommended_v2&currency=AUD&country=AU
Parse:  offer objects from paginated results
Repeat: page=2, page=3, ... until convergence
Output: all offers for this denomination
```

### Coverage verification

After Wave 4 completes for all denominations, re-probe with `sort=lowest_price`
for a sample of denominations. Any offer IDs not in the existing set represent
a coverage gap. If gap < 3%, coverage is sufficient.

### Termination

Stop when all three conditions are met:
1. All frontier items (categories, service types, denominations) have been processed
2. Pagination has converged (0 new offers on a page, or 2 consecutive zero-new-offer pages)
3. Coverage verification gap < 3%

## Anti-Bot / Rate Limits

- No CAPTCHA observed on the API (`sls.g2g.com`).
- No WAF or bot detection on the API.
- No rate limiting observed during testing (20+ sequential requests).
- The main site (`www.g2g.com`) may have Cloudflare or similar, but the API is unrestricted.

**Safe pattern:** 1-2 second delay between requests. No special headers, cookies,
or TLS configuration required.

If blocked (unlikely), the API will return a non-2000 code or an HTTP error.
Report clearly and preserve partial results — do not retry aggressively.

## Gotchas

- **`seo_term` is a URL slug, not a search query.** Must resolve via the `categories.json`
  index first (or the HTML search page as fallback). The `keyword_info` API requires a
  known `seo_term` — it cannot do free-text search. Example: searching "google cloud"
  in the index returns `seo_term = "google-cloud-storage-subscription"`.

- **`filter_attributes` are collection/dataset IDs representing denominations.** Must
  discover per category via the `/offer/keyword_relation/collection/` API. The IDs
  are opaque hex strings (e.g., `"b7d1999b"`, `"ade25ccd"`) — there is no way to
  guess them without querying the collection endpoint first.

- **`group=0` returns individual offers; `group=1` groups by product variant.** Use
  `group=0` for exhaustive research to see every seller's listing. Use `group=1` for
  a quick overview of available variants.

- **`unit_price` is in the seller's currency (often USD).** `converted_unit_price`
  is in the requested currency (AUD when `currency=AUD`). Always use
  `converted_unit_price` for price comparisons. The two can differ significantly
  for sellers listing in non-USD currencies.

- **`wholesale_details` is a list of tier objects, not a single dict.** Each tier has
  `min`, `max`, `discount` (float, e.g., `0.2` = 20% off), `unit_price`, and
  `converted_unit_price`. Multiple tiers represent increasing volume discounts.
  The listed base price is single-unit only.

- **`sales_territory_settings` determines geographic availability.**
  `settings_type: "global"` means worldwide. Any other value may restrict to
  specific countries listed in the `countries` array.

- **`seller_ranking` is a string, not numeric.** The API returns `"4"` (string), not
  `4` (int). Parse with `int()` before sorting or comparing.

- **API paginates with `page` (1-based), `page_size` max 100.** Off-by-one is easy
  here — page 1 is the first page, not page 0.

- **`categories.json` is the primary source for category discovery.** The HTML search
  page is a fallback when the JSON index fails or returns no matches. The `keyword_info`
  API requires a known `seo_term` — it cannot do free-text search.

- **`offer_attributes` arrays define the denomination via `collection_id:dataset_id`.**
  Multiple attributes mean the offer belongs to multiple filter groups. When querying
  with a specific `filter_attr`, an offer may appear in multiple denomination results
  if it has multiple `offer_attributes`.

- **`satisfaction_rate` is a float 0-1, not a percentage.** `0.9877` means 98.77%.
  Multiply by 100 for display. Do not confuse with a 0-100 scale.

- **`total_success_order` is the seller's all-time completed orders for this specific
  offer, not platform-wide.** A seller with `total_success_order: 162` on one offer
  may have thousands of orders across all their listings.

- **JSON-LD on offer pages contains only basic schema.org Offer/Product data.** It
  does not include full seller details, rating breakdowns, or volume discounts.
  Use the API for complete data extraction.

- **Region ID `0f76ac42-3267-4d77-9fba-f9d9d719dac9` is the "Global" region.** Other
  regions (US, EU, etc.) have different UUIDs. Discover available regions via the
  collection API or from the category page HTML.
