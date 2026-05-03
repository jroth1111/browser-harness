# eBay — Scraping & Data Extraction

Field-tested against ebay.com.au on 2026-05-02 using `uv run python` with `http_get`
and again on 2026-05-02 with `curl_cffi` + cookie extraction after Akamai WAF block.
Currency is AUD. Prices in search results show "AU $" prefix; JSON-LD returns `priceCurrency: "AUD"`.

## Source exploration

Follow the exploration order from `interaction-skills/data-source-exploration.md`:

1. **Exports**: eBay has no structured export/download for search results. Skip.
2. **APIs**: All public APIs are dead or require OAuth (see APIs section below). Skip.
3. **HTTP**: `http_get` with full Chrome UA works for ~5-10 requests before Akamai WAF block.
4. **Browser**: Not needed — HTTP with cookie fallback covers all use cases.

Backend capability is proven: `http_get` returns ~1.5MB HTML with full search results.
When blocked, cookie extraction + TLS impersonation via `interaction-skills/waf-bypass.md`
recovers access. No need to test capability per session — the pattern is stable.

**Backend selection**: Follow routing ladder from `interaction-skills/cross-domain-control-flow.md`.
eBay diverges at step 3: `http_get` is the cheapest backend that works, not CDP.

**Session management**: When cookie extraction is needed for WAF bypass, follow the
session continuity patterns from `interaction-skills/session-continuity.md`. Do not
commit cookie values — extract at runtime from the user's browser profile.

## Scripts

Executable scripts in `domain-skills/ebay/scripts/`:

| Script | Purpose |
|--------|---------|
| `search.py` | Full 4-layer search orchestrator: fetch, extract, dedup, classify, export. Uses `--synonyms`/`--modifiers` (unified with AliExpress vocabulary). |
| `generate_search_urls.py` | Generate eBay search URLs with 4-layer taxonomy and pagination. Uses `--synonyms`/`--modifiers`. |
| `classify_product_line.py` | Classify listing titles into product lines, form factors, RAM, storage |

### Quick start

```bash
# Full search with iterative discovery:
uv run python3 domain-skills/ebay/scripts/search.py search "Ryzen AI Max+ 395" --output results.csv

# Verify seller trust on existing CSV:
uv run python3 domain-skills/ebay/scripts/search.py verify results.csv --output verified.csv

# Generate URLs only (no fetching):
python3 domain-skills/ebay/scripts/search.py urls "RTX 5090" --products "RTX 5090"

# Classify titles from CSV:
python3 domain-skills/ebay/scripts/classify_product_line.py --csv results.csv --field title
```

### search.py workflow

```
Pass 1: L2 (chip refs) + L3 (category+architecture) + L4 (spec-level)
  → discover product types present on the platform
Pass 2: L1 queries for each discovered product name
  → catches listings that chip-level queries miss
Deduplicate by listing_id across all passes
Export to CSV with product_type, layer, query_source
```

The iterative discovery loop is mandatory — the Ryzen AI Max+ 395 search
proved that L1 adds 20+ listings that L2-4 miss entirely.

## Critical: Bot Detection ("Pardon Our Interruption" / "Access Denied")

eBay's Akamai WAF blocks after roughly **5–10 requests** from an unrecognised session.
The block page is ~400 bytes (`"Access Denied"`) or ~13 KB (`"Pardon Our Interruption..."`).

**Once triggered, the block is total and persistent** — every HTTP client (`curl`,
Python `requests`, `httpx`, `curl_cffi` without cookies) returns 403 for the entire
session. The documented 60–120s cooldown does **not** clear it after aggressive use.
Only cookie extraction + TLS impersonation recovers access (see below).

**Always check before parsing:**
```python
def is_blocked(html):
    return 'Pardon Our Interruption' in html or 'Access Denied' in html or len(html) < 20_000
```

### Primary method: `http_get` (fresh IP only)

```python
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
}

html = http_get("https://www.ebay.com.au/sch/i.html?_nkw=laptop&LH_BIN=1", headers=HEADERS)
if is_blocked(html):
    # Fall through to cookie extraction method below
```

A plain `"User-Agent": "Mozilla/5.0"` also works for the first few requests,
but the full Chrome UA lasts slightly longer before triggering the block.

### Fallback: cookie extraction + TLS impersonation

When `http_get` returns 403, use the universal WAF bypass from
`interaction-skills/waf-bypass.md`:

```python
import browser_cookie3
from curl_cffi import requests as cffi_requests

cj = browser_cookie3.chrome(domain_name="ebay.com.au")
cookies = {c.name: c.value for c in cj}

r = cffi_requests.get(
    "https://www.ebay.com.au/sch/i.html?_nkw=laptop&LH_BIN=1",
    headers=HEADERS,
    cookies=cookies,
    impersonate="chrome136",
    timeout=15,
)
# r.status_code == 200, len(r.text) ~ 1.5 MB
```

The user must have visited ebay.com.au in Chrome at least once for cookies to exist.
See `interaction-skills/waf-bypass.md` for full details and prerequisites.

## Search URL Structure

```
https://www.ebay.com.au/sch/i.html?_nkw={query}&{filters}
```

Confirmed working URL examples:
```python
# Buy It Now only, sorted by lowest price
"https://www.ebay.com.au/sch/i.html?_nkw=mechanical+keyboard&LH_BIN=1&_sop=15"

# Auctions only
"https://www.ebay.com.au/sch/i.html?_nkw=vintage+camera&LH_Auction=1"

# New condition only, page 2
"https://www.ebay.com.au/sch/i.html?_nkw=laptop&LH_ItemCondition=1000&_pgn=2"
```

### Filter Parameters (all confirmed working)

| Parameter | Value | Effect |
|-----------|-------|--------|
| `LH_BIN` | `1` | Buy It Now only |
| `LH_Auction` | `1` | Auctions only |
| `LH_ItemCondition` | see below | Filter by condition |
| `LH_PrefLoc` | see below | Item location filter |
| `_sop` | see below | Sort order |
| `_pgn` | `2`, `3`, … | Page number (confirmed: returns ~65–88 items/page) |
| `_ipg` | `25`, `50`, `100`, `200` | Items per page (unconfirmed, standard eBay param) |

### Location Codes for `LH_PrefLoc`

| Code | Label | Notes |
|------|-------|-------|
| *(absent)* | Default (worldwide) | **Includes international sellers only — 0 AU results in testing.** Do not use for AU price comparison. |
| `1` | Australia only | Located in Australia. Returns domestic sellers + items warehoused in AU. |
| `2` | North America | Located in US/Canada/Mexico. |
| `99` | Worldwide | Explicit worldwide (same as default). |

**Critical**: ebay.com.au default search surfaces **international sellers only** for many
product categories. Confirmed on RTX 5090 search: 60 items, all from China (33), South Korea
(11), US (4), Japan (3), Taiwan (1), UK (1) — zero from Australia. With `LH_PrefLoc=1`:
132 items, 77 domestic (shown without "from" label) plus 55 international items warehoused in AU.

For any AU-local price comparison, always add `LH_PrefLoc=1`. Without it, you get
international bulk/resale listings at prices that don't reflect the AU market.

### Condition Codes for `LH_ItemCondition`

| Code | Label |
|------|-------|
| `1000` | New |
| `1500` | New Other (open box, no original packaging) |
| `2000` | Manufacturer Refurbished |
| `2500` | Seller Refurbished |
| `2750` | Like New |
| `3000` | Used |
| `4000` | Very Good |
| `5000` | Good |
| `6000` | Acceptable |
| `7000` | For parts or not working |

### Sort Codes for `_sop`

| Code | Sort Order |
|------|-----------|
| `1` | Best Match (default) |
| `10` | Ending Soonest |
| `12` | Newly Listed |
| `15` | Lowest Price + Shipping |
| `16` | Highest Price |

### Item Detail URL

```
https://www.ebay.com.au/itm/{listing_id}
```

The listing ID is a plain integer (e.g. `167040158614`). Always strip query parameters
from extracted URLs — tracking params bloat the URL and are not needed for navigation.

## Search Results: HTML Structure (No JSON-LD)

**JSON-LD is absent on search results pages.** The listing data is embedded in HTML
with eBay-specific class names. The response is large (~1.5–1.8 MB uncompressed).

### Card Structure

Each result is an `<li>` element with `data-listingid="<id>"`. Key elements within each card:

| Data | Pattern |
|------|---------|
| Listing ID | `data-listingid="?(\d+)"?` on the `<li>` |
| Item URL | `href="?(https://(?:www\.)?ebay\.com\.au/itm/(\d+))"?` |
| Title | `s-card__title` > `su-styled-text primary` > text |
| Current price | `class="[^"]*price[^"]*">[^<]*\$([0-9,\.]+)<` (AU pages prefix "AU ") |
| Original/list price | `strikethrough[^>]*>[^$]*\$([0-9,\.]+)` |
| Image | `class="s-card__image"[^>]*src="([^"]+)"` |
| Alt title | `img[alt]` in the card (same as product title) |

### Confirmed Extractor (field-tested, 60 items from a single search)

```python
import re

def extract_search_results(html):
    """
    Parse eBay search results HTML into a list of dicts.
    Returns [] if blocked or no results.
    """
    if 'Pardon Our Interruption' in html or len(html) < 20_000:
        return []

    cards = re.split(r'(?=<li[^>]+data-listingid=)', html)
    results = []
    seen_ids = set()

    for card in cards[1:]:  # skip preamble before first card
        # Listing ID (dedup)
        lid_m = re.search(r'data-listingid="?(\d+)"?', card)
        if not lid_m:
            continue
        listing_id = lid_m.group(1)
        if listing_id in seen_ids:
            continue
        seen_ids.add(listing_id)

        # Item URL (clean, no tracking params)
        url_m = re.search(r'href="?(https://(?:www\.)?ebay\.com\.au/itm/(\d+))"?', card)
        item_url = url_m.group(1).split('?')[0] if url_m else None

        # Title from s-card__title
        title_m = re.search(r's-card__title[^>]*>.*?primary[^>]*>([^<]+)', card, re.DOTALL)
        title = title_m.group(1).strip() if title_m else None

        # Skip placeholder "Shop on eBay" stub cards
        if not title or title == 'Shop on eBay':
            continue

        # Current price — AU pages show "AU $" prefix, US shows just "$"
        price_m = re.search(r'class="[^"]*price[^"]*">[^<]*\$([0-9,\.]+)<', card)
        if not price_m:
            price_m = re.search(r'price">[^<]*\$([0-9,\.]+)<', card)
        price = '$' + price_m.group(1) if price_m else None

        # Original / list price (strikethrough — present when discounted)
        orig_m = re.search(r'strikethrough[^>]*>[^$]*\$([0-9,\.]+)', card)
        original_price = '$' + orig_m.group(1) if orig_m else None

        # Thumbnail image URL
        img_m = re.search(r'class="?s-card__image"?[^>]*src="?([^"\s>]+)"?', card)
        image = img_m.group(1) if img_m else None

        results.append({
            'listing_id': listing_id,
            'url': item_url,
            'title': title,
            'price': price,
            'original_price': original_price,  # None if not on sale
            'image': image,
        })

    return results
```

**Usage:**
```python
from helpers import http_get
import re

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

html = http_get("https://www.ebay.com.au/sch/i.html?_nkw=mechanical+keyboard&LH_BIN=1&_sop=15", headers=HEADERS)
items = extract_search_results(html)
print(f"{len(items)} items")
for item in items[:5]:
    print(f"  {item['listing_id']} | {item['title'][:50]} | {item['price']}")
# Output (confirmed on AU): 62 items
# 366284747321 | LED Keyboard Switches Tester Mechanical Keyboa... | $15.88
# 358156371070 | LED Keyboard Switches Tester Mechanical Keyboa... | $14.85
# 397354083626 | Mechanical Keyboard MX Switch Tester Lightless... | $15.86
```

## Item Detail Pages: JSON-LD (Reliable)

Item detail pages at `/itm/{id}` serve **two JSON-LD blocks**: `BreadcrumbList` and `Product`.
The `Product` schema is the most useful — it contains price, condition, availability, brand, images, and return policy.

```python
import re, json

def extract_item_detail(html):
    """
    Extract structured data from an eBay item page.
    Returns dict or None if blocked.
    """
    if 'Pardon Our Interruption' in html:
        return None

    ld_blocks = re.findall(r'application/ld\+json[^>]*>(.*?)</script>', html, re.DOTALL)
    product = None
    breadcrumbs = []

    for ld_str in ld_blocks:
        try:
            d = json.loads(ld_str.strip())
        except Exception:
            continue

        if d.get('@type') == 'Product':
            product = d
        elif d.get('@type') == 'BreadcrumbList':
            breadcrumbs = [i.get('name') for i in d.get('itemListElement', [])]

    if not product:
        return None

    offers = product.get('offers', {})
    if isinstance(offers, list):
        offers = offers[0]

    # Schema.org condition URL -> human label
    CONDITION_MAP = {
        'NewCondition':          'New',
        'UsedCondition':         'Used',
        'RefurbishedCondition':  'Refurbished',
        'DamagedCondition':      'For Parts / Not Working',
        'LikeNewCondition':      'Like New',
        'VeryGoodCondition':     'Very Good',
        'GoodCondition':         'Good',
        'AcceptableCondition':   'Acceptable',
    }
    cond_url = offers.get('itemCondition', '')
    cond_key = cond_url.split('/')[-1]  # e.g. "RefurbishedCondition"
    condition = CONDITION_MAP.get(cond_key, cond_key)

    # List price from priceSpecification (only present when there's a "was" price)
    price_spec = offers.get('priceSpecification', {})
    list_price = price_spec.get('price') if price_spec.get('name') == 'List Price' else None

    # Shipping (first destination)
    shipping_details = offers.get('shippingDetails', [])
    if shipping_details:
        shipping_val = shipping_details[0].get('shippingRate', {}).get('value', '')
        shipping = 'Free' if str(shipping_val) in ('0', '0.0') else f"${shipping_val}"
    else:
        shipping = None

    # Return policy
    return_policies = offers.get('hasMerchantReturnPolicy', [])
    return_days = return_policies[0].get('merchantReturnDays') if return_policies else None

    return {
        'listing_id': offers.get('url', '').split('/itm/')[-1],
        'name': product.get('name'),
        'brand': product.get('brand', {}).get('name') if isinstance(product.get('brand'), dict) else product.get('brand'),
        'price': offers.get('price'),
        'list_price': list_price,     # was-price, None if no discount shown
        'currency': offers.get('priceCurrency'),
        'availability': offers.get('availability', '').split('/')[-1],  # e.g. "InStock"
        'condition': condition,
        'condition_url': cond_url,
        'shipping': shipping,
        'return_days': return_days,
        'images': product.get('image', []),
        'gtin13': product.get('gtin13'),
        'mpn': product.get('mpn'),
        'color': product.get('color'),
        'breadcrumbs': breadcrumbs,
    }
```

**Field-tested on item 167040158614:**
```python
html = http_get("https://www.ebay.com.au/itm/167040158614", headers=HEADERS)
detail = extract_item_detail(html)
# {
#   'listing_id':   '167040158614',
#   'name':         'Logitech - PRO X TKL LIGHTSPEED Wireless Mechanical Gaming Keyboard - 920-012118',
#   'brand':        'Logitech',
#   'price':        74.99,
#   'list_price':   '219.99',
#   'currency':     'AUD',
#   'availability': 'InStock',
#   'condition':    'Refurbished',
#   'shipping':     'Free',
#   'return_days':  30,
#   'images':       ['https://i.ebayimg.com/images/g/vwsAAeSwEcFpw~hW/s-l1600.jpg', ...],  # 5 images
#   'gtin13':       '097855189066',
#   'mpn':          '920-012118',
#   'color':        'Black',
#   'breadcrumbs':  ['eBay', 'Electronics', 'Computers/Tablets & Networking', ...],
# }
```

### Seller Trust Data from `ux-textspans` (mandatory for price comparison)

The `ux-textspans` elements contain seller reputation data not available in JSON-LD.
**Always extract seller feedback when comparing prices or reporting results.**
A low price from a seller with <95% positive feedback or <100 feedback count
is not a valid data point — it's a scam or mislisting signal.

**Field-tested finding:** sellers with 0 feedback never have a feedback percentage
shown on the page. The regex must handle `feedback_pct = None` for these sellers.
0-feedback sellers with auto-generated names (`sunny_4539`, `tvbux-89`, `tho-875314`)
are a confirmed scam pattern on eBay AU for high-value electronics.

```python
import re

def extract_seller_trust(html):
    """Extract seller name, feedback count, and feedback % from an item page.
    Returns dict with seller, feedback_count, feedback_pct, and flag."""
    spans = [m.group(1) for m in re.finditer(r'ux-textspans[^>]*>([^<]+)</span>', html)]

    seller_name = None
    feedback_pct = None
    feedback_count = None

    for s in spans:
        if 'positive' in s.lower() and '%' in s:
            feedback_pct = s  # e.g. "99.6% positive"
        if s.startswith('(') and s.endswith(')'):
            inner = s[1:-1].replace(',', '').replace(' ', '')
            if inner.isdigit():
                feedback_count = int(inner)  # e.g. "(20742)" or "(0)"

    # Seller name is the span right before the feedback count
    for i, s in enumerate(spans):
        if feedback_count is not None and s == f"({feedback_count})" and i > 0:
            seller_name = spans[i - 1]
            break

    # Parse percentage — eBay returns "99.8% positive feedback" or "100% positive"
    pct_val = None
    if feedback_pct:
        m = re.search(r'(\d+\.?\d*)%', feedback_pct)
        if m:
            pct_val = float(m.group(1))

    # Trust scoring — handles None pct_val (0-feedback sellers)
    count_val = feedback_count if feedback_count is not None else 0
    if count_val < 100 or pct_val is None or pct_val < 95:
        flag = 'HIGH_RISK'
    elif pct_val < 98 or count_val < 500:
        flag = 'MODERATE_RISK'
    else:
        flag = 'OK'

    return {
        'seller': seller_name or 'UNKNOWN',
        'feedback_count': count_val,
        'feedback_pct': feedback_pct,
        'pct_val': pct_val,
        'flag': flag,
    }
```

**Thresholds (field-tested against GB10 GPU listings, 2 May 2026):**
- `OK`: ≥98% positive and ≥500 feedback — established seller, price is credible
  Example: JW Computers (14,881 feedback, 99.8%), GSPACE (4,598 feedback, 100%)
- `MODERATE_RISK`: 95-98% or 100-500 feedback — verify listing details carefully
- `HIGH_RISK`: <95% or <100 feedback or no feedback data — price is not a valid comparison point
  Example: sunny_4539 (0 feedback), tvbux-89 (0 feedback) — all turned out to be scams
- **0 feedback is the strongest scam signal.** No legitimate seller of $2,000+ electronics
  has zero transaction history. Always flag these as HIGH_RISK regardless of price.

**Usage in pipeline:**
```python
for item in items:
    detail_html = http_get(item['url'], headers=HEADERS)
    trust = extract_seller_trust(detail_html)
    if trust['flag'] == 'HIGH_RISK':
        print(f"  SKIPPING {item['listing_id']}: {trust['seller']} "
              f"({trust['feedback_pct'] or 'no data'}, {trust['feedback_count']} feedback)")
        continue
    # ... proceed with price comparison
```

### Scam Detection Pipeline

Combine three independent signals to classify listings. Any single HIGH_RISK signal
is sufficient to exclude the listing — no need for multiple signals.

```python
def classify_listing(item, trust, reference_price=None):
    """Classify a listing as TRUSTED, SUSPICIOUS, or SCAM.
    reference_price: cross-platform anchor price (e.g. Amazon price for same product)."""

    # Signal 1: Seller trust
    if trust['flag'] == 'HIGH_RISK':
        return 'SCAM', f"seller {trust['seller']} has {trust['feedback_count']} feedback"

    # Signal 2: Price vs reference (50% threshold)
    if reference_price and item['price'] < reference_price * 0.5:
        return 'SCAM', f"${item['price']} is <50% of reference ${reference_price}"

    # Signal 3: Title-based variant exclusion (accessories, parts, multi-unit)
    title_lower = item['title'].lower()
    PARTS = ['parts', 'for parts', 'broken', 'no core', 'no power', 'board only',
             'cable', 'shroud', 'water block', 'heatsink', 'fan adapter', 'no gpu']
    for kw in PARTS:
        if kw in title_lower:
            return 'EXCLUDED', f"title contains '{kw}'"

    if trust['flag'] == 'MODERATE_RISK':
        return 'SUSPICIOUS', f"seller has {trust['feedback_count']} feedback, {trust['feedback_pct']}"

    return 'TRUSTED', 'all signals clear'
```

**Field-tested results (GB10 Grace Blackwell devices, eBay AU):**
- 7 listings classified SCAM via seller trust (all 0 feedback, auto-generated names)
- Price range of SCAM listings: $1,650–$4,860 (31–61% of Amazon reference price)
- Price range of TRUSTED listings: $6,942–$11,354 (87–142% of Amazon reference price)
- No TRUSTED listing was priced below 87% of the Amazon reference

### Full `ux-textspans` Reference

Additional data available from the same elements:

```python
def extract_ux_textspans(html):
    """Return list of all ux-textspans text values from an item page."""
    return [m.group(1) for m in re.finditer(r'ux-textspans[^>]*>([^<]+)</span>', html)]

# From item 167040158614 (confirmed):
# Index [3]  -> item title
# Index [4]  -> subtitle / seller tagline
# Index [5]  -> seller name ("Logitech")
# Index [6]  -> seller feedback count ("(20742)")
# Index [7]  -> seller feedback % ("99.6% positive")
# Index [10] -> current price ("AU $74.99")
# Index [12] -> list price ("AU $219.99")
# Index [33] -> condition label ("Excellent - Refurbished")
# Index [36] -> quantity sold ("45 sold")
# Pairs from [105] onward: item specifics as label/value pairs
```

## Pagination

Use `_pgn=N` (confirmed working, returns ~65–88 items per page):
```python
for page in range(1, 4):
    url = f"https://www.ebay.com.au/sch/i.html?_nkw=laptop&LH_BIN=1&_sop=15&_pgn={page}"
    html = http_get(url, headers=HEADERS)
    if is_blocked(html):
        break
    items = extract_search_results(html)
    print(f"Page {page}: {len(items)} items")
    # IMPORTANT: add delay between pages to avoid bot detection
    time.sleep(3)
```

**Rate-limit safe pattern**: 3–5 second delay between requests. Beyond ~10 rapid requests
in a session, eBay returns "Pardon Our Interruption" for all subsequent requests from that IP.

## APIs (All Require Auth or Are Dead)

| API | Status | Notes |
|-----|--------|-------|
| Finding API (svcs.ebay.com) | **Dead** — HTTP 500 | Was free/JSONP, no longer works |
| Browse API (api.ebay.com) | **Requires OAuth** — HTTP 400 | Needs eBay developer account + token |
| Shopping API (open.api.ebay.com) | **Requires token** | Returns `"Token not available"` error |
| RSS feed (`_rss=1`) | **Blocked same as HTML** | Returns "Pardon Our Interruption" when rate-limited |

**Bottom line**: There is no public unauthenticated eBay API in 2026. Use HTML scraping.

## Practical Workflow

### Scrape a search and follow top items

```python
import re, json, time
from helpers import http_get

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

def is_blocked(html):
    return 'Pardon Our Interruption' in html or len(html) < 20_000

# Step 1: Search
html = http_get(
    "https://www.ebay.com.au/sch/i.html?_nkw=mechanical+keyboard&LH_BIN=1&_sop=15&LH_ItemCondition=1000",
    headers=HEADERS
)
if is_blocked(html):
    raise RuntimeError("Rate limited — wait 60-120s and retry")

items = extract_search_results(html)
print(f"Found {len(items)} items")

# Step 2: Fetch details for top results (with delay)
details = []
for item in items[:5]:
    time.sleep(3)
    detail_html = http_get(item['url'], headers=HEADERS)
    if is_blocked(detail_html):
        print(f"Blocked on item {item['listing_id']}, stopping")
        break
    detail = extract_item_detail(detail_html)
    if detail:
        details.append(detail)
        print(f"  {detail['name'][:50]} | {detail['price']} {detail['currency']} | {detail['condition']}")
```

## Gotchas

- **"Pardon Our Interruption" is not a CAPTCHA** — it's eBay's bot-detection interstitial. It doesn't require solving — just wait and back off. `'captcha'` does NOT appear in the blocked page.

- **No JSON-LD on search results** — The `application/ld+json` blocks that Amazon and other sites embed are absent from eBay search pages. Parse the HTML using regex on `s-card` class names.

- **JSON-LD IS on item pages** — Two blocks: `BreadcrumbList` and `Product`. The `Product` block is authoritative. Use the regex `r'application/ld\+json[^>]*>(.*?)</script>'` (note the `[^>]*` before `>` — eBay doesn't use `type="..."` quote style consistently in all contexts).

- **Duplicate listing IDs in the HTML** — Each card's listing ID appears 2–3 times (image link, title link, watch button). Always deduplicate using a `seen_ids` set when splitting on `data-listingid`.

- **Placeholder cards ("Shop on eBay")** — The first card slot may be a promoted/placeholder card with title `"Shop on eBay"` and listing ID `"123456"`. Filter these out.

- **Item URLs have tracking params** — Raw extracted URLs look like `https://www.ebay.com.au/itm/167040158614?_skw=...&epid=...&hash=...&itmprp=...`. Always strip to `itm/{id}` with `.split('?')[0]`.

- **`www.ebay.com.au` vs `ebay.com.au`** — Some item URLs in search results omit `www.`. Normalize with `url.replace('//ebay.com.au/', '//www.ebay.com.au/')`.

- **Search response is large** — Uncompressed HTML is 1.5–1.8 MB per page. The `http_get` helper handles gzip transparently, so the actual transfer is much smaller, but parsing a 1.8 MB string is slow. Use `re.split` on card boundaries rather than an HTML parser for speed.

- **`_sop` sort and `LH_ItemCondition` require full browser-like UA** — Requests with just `"Mozilla/5.0"` (minimal UA) return empty results for these parameters more quickly than full Chrome UA. Always use the full UA string.

- **Condition in JSON-LD is a schema.org URL** — `offers.itemCondition` returns `"https://schema.org/RefurbishedCondition"`, not a human label. Split on `/` and map the last segment using `CONDITION_MAP` (see `extract_item_detail` above).

- **`list_price` only present when discounted** — `offers.priceSpecification` only appears in JSON-LD when eBay shows a "List Price" comparison. Check `price_spec.get('name') == 'List Price'` before using.

- **Seller data is NOT in JSON-LD** — `d.get('seller')` returns `None` on item pages. The seller name, feedback %, and items sold count are only in `ux-textspans` elements in the HTML body.

- **AU prices include "AU " prefix in HTML** — Price markup on ebay.com.au shows `AU $15.88`, not just `$15.88`. The regex patterns use `[^$]*\$` to skip the prefix. The extractor returns plain `$15.88` (strips the "AU ").

- **Bot detection is session-level, not IP-level** — eBay's Akamai WAF fingerprints the browser/TLS session, not just the IP. A fresh browser context with updated UA can bypass an existing block on the same IP. With `http_get`, wait 60–120s for the block to clear. If the block persists, use the cookie extraction fallback documented above.

- **Lowest-price sort (`_sop=15`) surfaces parts and accessories** — eBay search is keyword-loose. Sorting by lowest price returns fan shrouds, water blocks, cables, broken boards, and replacement parts ahead of actual GPUs. Filter results before comparing prices:
  ```python
  PARTS_KEYWORDS = ['parts', 'for parts', 'broken', 'no core', 'no power',
                    'board only', 'fan adapter', 'water block', 'heatsink',
                    'cooler', 'cable', 'shroud', 'no gpu', 'read description']

  def is_real_item(title):
      t = title.lower()
      return not any(kw in t for kw in PARTS_KEYWORDS)

  real_items = [i for i in extract_search_results(html) if is_real_item(i['title'])]
  ```
  Apply this filter before selecting the "best 3 prices" for any product.

- **Discard non-comparative variants** — A listing for an accessory (cable, bracket,
  adapter) that matches the search keyword but is not the main product must be excluded
  from price comparisons. Similarly, multi-unit listings ("2 X Nvidia DGX Sparks")
  cannot be compared per-unit against single listings without normalizing. Always verify
  the title describes the full product, not a component or variant that shares the keyword.

- **Always run the scam detection pipeline before reporting prices** — Use `classify_listing()` from the "Scam Detection Pipeline" section above. Three independent signals: seller trust, price vs reference, and title-based variant exclusion. Any single HIGH_RISK signal is sufficient to exclude. The `extract_search_results` function returns raw data; the pipeline must filter it before any comparison or reporting.

- **0-feedback sellers are the strongest scam signal** — Confirmed pattern: auto-generated seller names (`sunny_4539`, `tvbux-89`, `tho-875314`) with 0 feedback listing high-value electronics at 30-60% of retail. No legitimate seller of $2,000+ goods has zero transaction history. Always flag these as HIGH_RISK.

- **Default search is worldwide, not AU-local** — ebay.com.au without `LH_PrefLoc` returns international sellers only. Confirmed: RTX 5090 search returned 60 items from China/Korea/US/Japan with zero Australian sellers. Add `LH_PrefLoc=1` for any AU market price comparison. Without it, prices reflect international bulk/resale markets, not local retail.

- **Condition is a major price axis for configurable hardware** — Used ROG Flow Z13 units sell for $2.5-3.8K vs $3.8-4K new on the same search page. For meaningful price comparison, always extract condition from detail pages (JSON-LD `itemCondition`) and group results by condition before comparing. Search-level HTML does not include condition.

- **Defect-in-title is transparency, not fraud** — eBay sellers include defects directly in titles: "FRAME SPLIT", "ODOR ISSUE", "Cracked Screen". These are legitimate used-item disclosures. Don't exclude these from results (they're real products), but do flag the condition as defective for price comparison purposes.

- **Sellers misname products** — "ROG Flow X13" is not a real ASUS product (it's the ROG Flow Z13). For category searches, exact product name matching misses mislabeled listings. Use fuzzy matching that accounts for close variant names.

- **Title truncation at ~80 chars loses config** — HP ZBook Ultra G1a listings with long SKU numbers (e.g., "B34KWES#ABD", "CW0H2ES") get truncated before the RAM config. 6 of 15 HP ZBook Ultra listings showed "?" RAM in title-based extraction. Must hit detail pages for spec extraction on business/OEM listings with SKU-based titles.

- **Verified-sample trust is sufficient for hot products** — For categories with 50+ listings, verifying cheapest/most-expensive/median per product type (29% sample) catches all HIGH_RISK sellers. Risk is concentrated at price extremes. Full verification of every listing is unnecessary.

- **GPU chip IDs are ambiguous across generations** — "6000" appears in RTX A6000, RTX 6000 Ada, and RTX PRO 6000. The relevance filter must check for the distinguishing qualifier (A/Ada/PRO) adjacent to the number, not just the number itself. Without this, a search for "RTX 6000 Ada" returns RTX A6000 and Quadro RTX 6000 (Turing) listings too.

- **Bare chip names match non-GPU products** — "L40S" matches robot vacuums (Dreame L40S Pro) and industrial parts (Yanmar starters, SICK sensors). Always provide known product names via `--products` for ambiguous chip IDs.

- **eBay results are non-deterministic per session** — The same search URL can return different listings on consecutive requests. This makes perfect convergence impossible for high-volume queries. The coverage rating uses gap-ratio (new_from_probes / total_listings) to account for this: <=3% = MEDIUM, >3% = LOW.

- **20s+ delay between GPU searches prevents WAF** — Running 8 GPU searches in a batch script with 15s delays causes WAF blocks on GPUs 7-8. 20s delays with the Session class (auto cookie refresh + backoff) is more reliable.

- **Pagination convergence requires 2 consecutive zero-new pages** — A single zero-new page can be coincidence on high-volume queries (60+ items/page, high dedup rate). Requiring 2 consecutive zero-new pages eliminates false convergence without significantly increasing request count.

## Category Search: Ryzen AI Max+ 395 (Field-Tested)

**119 listings** across 10 queries (5 AU-only, 5 worldwide), 2 May 2026.

### Product Landscape

| Product | Count | Price Range (AUD) |
|---------|-------|-------------------|
| ASUS ROG Flow Z13 | 22 | $2,520–$12,381 |
| GPD WIN 5 | 17 | $3,247–$4,683 |
| HP ZBook Ultra G1a | 15 | $3,590–$13,875 |
| ASUS ROG Flow X13 (mislabeled Z13) | 13 | $5,970–$7,273 |
| OneXPlayer Super X | 9 | $3,777–$4,721 |
| OneXPlayer Apex | 8 | $3,191–$5,101 |
| OneXPlayer ONEXStation i1 | 7 | $5,276–$7,690 |
| HP Z2 G1a Mini | 6 | $5,700–$12,129 |
| HP ZBook Studio 99 | 5 | $7,617–$8,289 |
| MinisForum MS-S1 Max | 5 | $6,109–$6,843 |
| MINIX ER939-AI | 2 | $4,836–$5,060 |
| NIMO Mini PC | 2 | $1,526–$3,819 |
| EVO-X2 Mini PC | 1 | $3,512 |

### Seller Trust (35 verified)

- 28 OK, 4 MODERATE_RISK, 3 HIGH_RISK
- HIGH_RISK: ari334 (90.5%, 29 fb) × 2, UNKNOWN seller (0 fb) selling NIMO at $1,526
- MODERATE_RISK: diy-fans (97.8%, 32,805 fb), SEVEN-Leo (97.9%, 139 fb), brand_mini_pc_official_store (99.0%, 391 fb), Direct Sale Factory (99.2%, 122 fb)

### Key Sellers

| Seller | Feedback | Trust | Products Sold |
|--------|----------|-------|---------------|
| Antonline | 349,673 (99.5%) | OK | ASUS ROG Flow Z13 |
| ItsWorthMore | 149,262 (99.5%) | OK | ASUS ROG Flow Z13 (used) |
| diy-fans | 32,805 (97.8%) | MODERATE | OneXStation i1 |
| Sinobright | 21,837 (99.6%) | OK | HP ZBook Studio 99, ROG Flow X13 |
| digi-techx | 16,865 (100.0%) | OK | HP ZBook Ultra G1a, HP Z2 G1a Mini |
| FutureGear | 12,973 (98.6%) | OK | MINIX ER939-AI |
| Free Shipping Tech | 12,098 (98.4%) | OK | MINIX ER939-AI |
| ErsaZZa | 4,792 (99.7%) | OK | HP Z2 G1a Mini |
| avantgardemm | 2,148 (99.1%) | OK | GPD WIN 5 |
| Professional Mini Pc Store | 729 (99.8%) | OK | MinisForum, OneXPlayer |

### Queries Used

```
# AU-only
_nkw="Ryzen AI Max+ 395"&LH_PrefLoc=1&LH_BIN=1
_nkw="Ryzen AI Max 395"&LH_PrefLoc=1&LH_BIN=1
_nkw="AI Max+ 395 laptop"&LH_PrefLoc=1&LH_BIN=1
_nkw="AI Max+ 395 mini PC"&LH_PrefLoc=1&LH_BIN=1
_nkw="AI Max+ 395 workstation"&LH_PrefLoc=1&LH_BIN=1

# Worldwide
_nkw="Ryzen AI Max+ 395"&LH_BIN=1
_nkw="Ryzen AI Max 395"&LH_BIN=1
_nkw="AI Max+ 395 laptop"&LH_BIN=1
_nkw="AI Max+ 395 mini PC"&LH_BIN=1
_nkw="AI Max+ 395 handheld"&LH_BIN=1
```

AU-only queries returned 0 results (confirmed: no Australian sellers for this chip yet).
All 119 listings from worldwide search.

## GPU Search (Field-Tested, 2 May 2026)

8-GPU search across consumer and enterprise GPUs. All searches use `--mode gpu`
which filters for GPU-related keywords in titles.

### Results

| GPU | Listings | Coverage | Category |
|-----|----------|----------|----------|
| RTX 5090 | 688 | MEDIUM | Consumer |
| RTX 4090 | 597 | MEDIUM | Consumer |
| RTX 3090 | 347 | HIGH | Consumer |
| RTX PRO 6000 Blackwell | 92 | MEDIUM | Enterprise |
| RTX A5000 | 92 | HIGH | Enterprise |
| L40S | 94 | MEDIUM | Enterprise |
| RTX A6000 | 60 | HIGH | Enterprise |
| RTX 6000 Ada | 56 | HIGH | Enterprise |

### GPU-Specific Learnings

**Chip ID disambiguation.** "6000" is shared by three GPU generations:
RTX A6000 (Ampere), RTX 6000 Ada (Ada Lovelace), RTX PRO 6000 (Blackwell).
The relevance filter must match the distinguishing qualifier adjacent to the number:
- "RTX A6000" → requires "a6000" or "a 6000" in title
- "RTX 6000 Ada" → requires "6000 ada" or "6000ada" in title
- "RTX PRO 6000" → requires "pro 6000" or "pro6000" in title
Without this, cross-contamination is severe (RTX 6000 Ada search pulled in 54 non-Ada listings).

**L40S needs product name hints.** Bare "L40S" matches robot vacuums, starters, and
industrial sensors. Must pass `--products 'NVIDIA L40S' 'HPE NVIDIA L40S'` to seed the
search with known product names. The L1 pre-population then catches GPU listings.

**Enterprise GPUs exist on eBay AU but are rare.** L40S at 94 listings was surprising —
they're datacenter GPUs sold by international sellers on ebay.com.au. All enterprise GPUs
ship from EU/US/UK, not AU.

**Consumer GPU coverage plateaus.** RTX 5090 with ~700 listings can't reach HIGH coverage
because eBay returns non-deterministic results per request — each page fetch returns a
slightly different set of listings. The gap-ratio coverage threshold (<=3% = MEDIUM)
accounts for this. For consumer GPUs, MEDIUM coverage with 600+ listings is the practical limit.

**Batch execution triggers WAF.** Running 8 GPUs sequentially within one shell script
causes the last 2-3 GPUs to get WAF-blocked. The Session class handles this with
automatic cookie refresh and exponential backoff, but individual GPU runs with 20s+
delays between them are more reliable than batch execution.
