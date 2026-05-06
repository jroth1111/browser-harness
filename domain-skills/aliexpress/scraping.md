# AliExpress — Product Search & Price Comparison

Field-tested against aliexpress.com on 2026-05-02 using Chrome DevTools MCP (CDP).
Tested across 10 GPU/workstation product categories with detail-page verification.
Browser CDP required. `http_get` returns error pages.

## Source exploration

Follow the exploration order from `interaction-skills/data-source-exploration.md`:

1. **Exports**: AliExpress has no structured export/download. Skip.
2. **APIs**: No public API. Internal API endpoints require browser session context.
   Embedded JSON (`_dida_config_`) provides structured data on search pages but
   requires CDP to access — not a standalone API. See `interaction-skills/data-source-exploration.md`
   embedded JSON extraction patterns.
3. **HTTP**: `http_get` returns error pages. Dead path — AliExpress blocks non-browser HTTP.
4. **Browser (CDP)**: Required. Returns 60 structured items per search page via
   embedded JSON. No anti-bot observed with CDP.

Backend capability is proven: CDP + embedded JSON extraction is the only viable path.
No need to re-test `http_get` — it has been confirmed blocked.

**Backend selection**: Follow routing ladder from `interaction-skills/cross-domain-control-flow.md`.
AliExpress diverges at step 2 — no API/HTTP option works, so CDP is mandatory.

## Search Strategy

### The core problem

AliExpress search returns 60 items per page. For any product category with
active gray-market or counterfeit risk:
- ~70% of results are completely unrelated (noise)
- Of the remaining ~30%, 60-80% are scams or variant traps
- Traps exist at **every price point**, not just cheap listings

No single filter solves this. A cascade of progressively tighter filters is
required, with detail-page verification as the final gate.

### Filter cascade

```
Step 1: Query specificity    — right query reduces noise at the source
Step 2: Price floor          — one number eliminates noise + most scams
Step 3: Title keywords       — catches remaining irrelevant results
Step 4: Detail-page verify   — the only reliable trap detector
```

### Step 1: Query specificity (most leverage)

The search query itself is the first and most powerful filter. More specific
queries dramatically reduce noise and traps.

| Query | Relevant results | Traps |
|-------|-----------------|-------|
| "RTX 3090" | 15+ | 6+ variant traps |
| "RTX 3090 24GB" | 8 | 2 variant traps |

Include distinguishing specs in the query: model number, memory size,
form factor. Don't rely on post-extraction filtering to compensate for a
vague query.

**SortType choice:**

| Goal | SortType | Why |
|------|----------|-----|
| Find legitimate sellers | `total_volume` | Established sellers with real orders surface first |
| Avoid scams on high-value goods | `price_desc` | Scams cluster at the bottom; expensive-first avoids them |
| Broad discovery | (none) | Default best match |
| Find cheapest (dangerous) | `price_asc` | Puts scams first — only use with aggressive price floor |

`price_asc` is almost never the right choice for GPUs. Scam listings are
always cheapest and promoted listings override the sort anyway.

### Step 2: Price floor (eliminates noise + scams)

Two ways to apply a price floor:

1. **Server-side (`pr=` URL param)** — preferred. AliExpress never serves
   items outside the range. Use `pr={min}-{max}` in the search URL.
   Example: `?pr=2000-30000` on RTX 4090 returned 3 items, all AU$2,330+.

2. **Client-side (`priceFloor` in extractor)** — fallback when `pr=` is
   unavailable or for fine-tuning after the page loads.

Set the floor to ~50-60% of known retail/used market price.

| Floor | Effect |
|-------|--------|
| 0 (none) | Full 60 items, ~70% noise |
| AU$50 | Removes stickers, cables, fans — still lots of traps |
| ~50% of retail | Removes noise AND most scam-priced listings |
| ~80% of retail | Aggressive — may remove legitimate used/refurbished |

Example: RTX 4090 used market ~AU$2,500. `pr=2000-30000` reduced 60 items
to 3 — all the AU$625-875 scam listings eliminated server-side.

### Step 3: Title keywords (catches remaining noise)

After price floor, some irrelevant items remain. The `keywords` param filters
by title relevance. Use model-identifying terms:

```javascript
keywords=["rtx", "4090", "gpu", "graphics", "geforce"]
```

Keep the list short (3-5 terms) and focused on product identity, not
descriptors.

### Step 4: Detail-page verification (required, not optional)

This is the only reliable trap detector. The JSON extractor cannot detect
traps because `maxPrice: null` is the norm even for multi-variant listings.
A RTX A6000 listing at AU$9,202 — well above any price floor — was still a
variant trap ("4GB-RTX A6000" variant).

Verify the top N cheapest results that survive Steps 1-3. For high-value
items, verify all of them. The detail page extractor returns `trapRisk`
and `trapFlags` for automated screening.

### When to stop searching

If Steps 1-3 return 0 results:
1. Broaden the query (remove spec details)
2. Lower the price floor
3. Try alternative query terms

After 3-4 attempts with 0 results, the product likely doesn't exist on
AliExpress. Data-center GPUs (L40S, A100, H100, RTX 6000 Ada) are in this
category. Recognize the absence rather than endlessly broadening.

### Complete pipeline

```
1. Navigate to search URL with specific query + SortType=total_volume + pr={min}-{max}
2. Extract JSON with keywords filter (priceFloor optional if pr= already applied)
3. If 0 results → broaden query or lower pr= floor, retry (max 3 attempts)
4. Open top N detail pages, run trap assessment
5. Discard trapRisk="trap", flag "suspicious"
6. Report only trapRisk="clean" (or "suspicious" with caveats)
```

### Strategic filter combinations

| Goal | URL params | Why |
|------|------------|-----|
| Find legitimate seller | `SortType=total_volume` + `filterCode:4StarRating` + `pr={floor}-{max}` | Established sellers, quality floor, eliminates scam pricing |
| Find fastest delivery | `shpf_co=AU` + `filterCode:freeshipping` | Local stock, no shipping surprises |
| Find verified deal | `filterCode:choice_atm` + `filterCode:bigsale` + `pr={floor}-{max}` | Platform-verified items on promotion, scam pricing excluded |
| Maximum scam elimination | `SortType=price_desc` + `pr={floor}-{max}` + `filterCode:PremiumQuality` | Expensive-first + price floor + quality badge — may return 0 |

Filters intersect (AND logic). Start with fewer filters and add more if results
are still noisy. `PremiumQuality` is very aggressive — only 6 items for RTX 4090.

### Discovering new parameters

The embedded JSON contains metadata about all available filters and sort options.
Extract them to discover parameters AliExpress adds over time:

```javascript
() => {
  const cfg = window._dida_config_?._init_data_;
  const fields = cfg?.data?.data?.root?.fields || {};
  return {
    sortBar: fields.sortBar?.map(s => ({ code: s.code, text: s.text })),
    refineFilters: fields.searchRefineFilters?.map(f => ({
      code: f.code, text: f.text, type: f.type, values: f.values?.slice(0, 5),
    })),
  };
}
```

Run this on any search page to get the full list of available `SortType` values
and `selectedSwitches` filter codes. If AliExpress adds new filters, they'll
appear here without needing to reverse-engineer the UI.

## Search URLs

| URL | Status | Notes |
|-----|--------|-------|
| `/w/wholesale-{query}.html` | Works | Canonical search URL |
| `/search?SearchText={query}` | Works | Redirects to `/w/wholesale-{query}.html` |
| `/w/wholesale/{query}.html` | **Dead (404)** | Old pattern — do not use |
| `/item/{product_id}.html` | Works | Product detail page |

60 items per page from the embedded JSON.

### SortType values

| Value | Effect | Tested | Use when |
|-------|--------|--------|----------|
| (none) | Best match | Yes | Default — good for broad discovery |
| `price_asc` | Cheapest roughly first | Yes | **Dangerous for GPUs** — puts scams first |
| `price_desc` | Most expensive first | Yes | Find high-end models; avoids scam noise |
| `total_volume` | Most orders | Yes | Surface established sellers |

### Filter switches (`selectedSwitches`)

All set via `selectedSwitches=filterCode:{code}`. Combine multiple with commas
(intersection — all must match).

| Code | Effect | Tested | Items (RTX 4090) | Use when |
|------|--------|--------|-------------------|----------|
| `freeshipping` | Free shipping only | Yes | 60 | Eliminate hidden shipping costs |
| `bigsale` | Sale/discounted items | Yes | 60 | Find active promotions (all have discounts) |
| `choice_atm` | AliExpress "Choice" verified | Yes | 39 | Trust signal — platform-verified quality |
| `4StarRating` | 4+ star rated | Yes | 26 | Quality filter — removes low-rated items |
| `PremiumQuality` | Premium quality badge | Yes | 6 | Very strict — may return 0 for niche products |

**Multi-select works** — comma-separate the filter codes:
```
?selectedSwitches=filterCode:freeshipping,filterCode:4StarRating
```
Free shipping + 4+ stars: 20 items (intersection of 60 and 26).

### Price range (`pr`)

Server-side price filter. Much more efficient than client-side `priceFloor`
in the extractor — irrelevant items never arrive.

```
?pr=2000-30000
```

| Format | Example | Effect |
|--------|---------|--------|
| `pr={min}-{max}` | `pr=2000-30000` | Both bounds (tested: all 60 items AU$2,330-13,035) |
| `pr=-{max}` | `pr=-5000` | Upper bound only (untested) |
| `pr={min}-` | `pr=1000-` | Lower bound only (untested) |

**Combines with other filters:**
```
?selectedSwitches=filterCode:freeshipping&pr=2000-30000
```
Free shipping + AU$2,000-30,000: 3 items, all AU$3,438-8,917.

### Shipping origin (`shpf_co`)

Filter by country the item ships from.

| Code | Effect | Tested | Items (RTX 4090) | Use when |
|------|--------|--------|-------------------|----------|
| `CN` | Ships from China | Yes | 60 | Default — most listings |
| `AU` | Ships from Australia | Yes | 32 | Faster delivery, local stock |
| `TR` | Ships from Turkey | Yes | 32 | Alternative origin |

### View style

| Value | Effect | Note |
|--------|--------|------|
| `style=gallery` | Grid layout | Default |
| `style=list` | List layout | Same 60 items in JSON — visual only |

## Step 1: Search Extractor

### JSON path

```
window._dida_config_._init_data_.data.data.root.fields.mods.itemList.content
```

Object with numeric string keys ("0" through "59"), each a product with fully
structured data — no regex, no DOM parsing, no currency guessing.

### Combined extractor with filtering

Run via `js()` after page load. Accepts `keywords` for title
relevance filtering and `priceFloor` to discard cheap accessories. Returns
only relevant, adequately-priced items.

```javascript
(keywords, priceFloor) => {
  const cfg = window._dida_config_?._init_data_;
  if (!cfg) return { error: "_dida_config_._init_data_ not found" };
  const content = cfg.data?.data?.root?.fields?.mods?.itemList?.content;
  if (!content) return { error: "itemList.content not found — no results" };

  const kw = keywords || [];
  const pf = priceFloor || 0;
  const items = [];

  for (const item of Object.values(content)) {
    const sale = item.prices?.salePrice || {};
    const orig = item.prices?.originalPrice;
    const low = sale.minPrice ?? null;
    const high = sale.maxPrice ?? null;
    const spread = (low && high && low > 0) ? +(high / low).toFixed(1) : null;
    const img = item.image || {};
    const title = item.title?.displayTitle ?? null;
    const tlc = (title || '').toLowerCase();

    // Price floor: discard cheap accessories
    if (low !== null && low < pf) continue;

    // Title relevance: at least one keyword must match (if keywords provided)
    if (kw.length > 0 && !kw.some(k => tlc.includes(k.toLowerCase()))) continue;

    items.push({
      productId:       item.productId,
      title:           title ? title.substring(0, 150) : null,
      salePrice:       low,
      maxPrice:        high,
      originalPrice:   orig?.minPrice ?? null,
      discount:        sale.discount ?? null,
      currency:        sale.currencyCode ?? null,
      spread,
      productType:     item.productType ?? null,
      thumbnailUrl:    img.imgUrl ? "https:" + img.imgUrl : null,
      url:             item.productDetailUrl ? "https://www.aliexpress.com" + item.productDetailUrl.split("?")[0] : null,
      _extracted_from: location.href,
      _extracted_at:   new Date().toISOString(),
    });
  }
  return { count: items.length, items };
}
```

**Usage examples:**

```javascript
// GPU search with title filter and price floor
(keywords, priceFloor) => { /* ... */ }
// Call with: keywords=["rtx","4090","gpu","graphics","geforce"], priceFloor=500

// Broad search, no filtering
(keywords, priceFloor) => { /* ... */ }
// Call with: keywords=[], priceFloor=0
```

### Search-level price is not authoritative

`salePrice` (minPrice) from the search JSON can differ from the detail page
price. Observed: search showed AU$13,453 but detail page showed AU$6,957 for
the same product ID. The search price may reflect a stale variant, a different
default selection, or a cached value. **Detail page price is always canonical.**

Use search-level prices only for initial filtering and ordering. Do not report
them as final prices without detail-page verification.

### When `itemList.content` is missing

The `mods` object will contain `searchTips` instead of `itemList` when the
search returns zero results. This is distinct from nonsense queries, which
return recommended products ( itemList present but titles are unrelated).

## Step 2: Detail Page Verification (Required)

No embedded JSON on detail pages. Use DOM selectors. **Always verify before
trusting a search result** — variant traps and scams are the norm, not the
exception, for GPU listings.

### Detail page extractor with trap and seller assessment

```javascript
() => {
  const current = document.querySelector('[class*="price-default--current--"]')?.innerText?.trim();
  const extraEl = document.querySelector('[class*="price-default--priceExtra--"]');
  const extraText = extraEl?.innerText?.trim() ?? '';
  const extraPrices = [];
  const extraRx = /AU\$\s*([\d,]+\.?\d*)/g;
  let em;
  while ((em = extraRx.exec(extraText)) !== null) {
    const before = extraText.substring(Math.max(0, em.index - 6), em.index);
    if (before.match(/Save\s*$/i)) continue;
    extraPrices.push(em[1]);
  }
  const wasPrice = extraPrices.length > 0 ? extraPrices[extraPrices.length - 1] : null;
  const saveMatch = extraText.match(/Save\s+AU\$\s*([\d,]+\.?\d*)/);

  const skus = Array.from(document.querySelectorAll('[class*="sku-item--box"]'))
    .map(el => el.innerText?.trim()).filter(Boolean);
  const skuProps = Array.from(document.querySelectorAll('[class*="sku-item--title--"]'))
    .map(el => el.innerText?.trim()).filter(Boolean);
  const ordersMatch = document.body.innerText.match(/(\d[\d,]+)\s*(?:orders|sold|bought)/i);
  const orders = ordersMatch?.[1] || null;

  // Seller feedback extraction
  const storeName = document.querySelector('[class*="store-header--storeName"]')?.innerText?.trim();
  const storeText = [];
  document.querySelectorAll('[class*="store"]').forEach(el => {
    const t = el.innerText?.trim();
    if (t && t.length < 150 && t.includes('Feedback') && !storeText.includes(t))
      storeText.push(t);
  });
  const fbMatch = storeText.join(' ').match(/([\d.]+)%\s*Positive\s*Feedback/);
  const followersMatch = storeText.join(' ').match(/([\d,]+)\s*Followers/);
  const sellerFeedback = fbMatch ? parseFloat(fbMatch[1]) : null;
  const sellerFollowers = followersMatch ? parseInt(followersMatch[1].replace(/,/g, '')) : null;

  // Trap assessment
  const allVariants = skus.join(' ').toLowerCase();
  const hasAccessory = /cable|fan|heatsink|sticker|cover|gasket|bracket|sled|thermal|dedicated line|cascade|power cord/.test(allVariants);
  const hasMultiGpu = (skus.join('\n').match(/\bRTX\s*\d{3,4}/gi) || []).length > 1
    || (skus.join('\n').match(/\bA\d{4}\b/g) || []).length > 1;
  const hasObfuscated = /describe|option\s*\d|package\s*\d/i.test(allVariants);
  const hasFakeSpec = /4gb.*a6000|4gb.*a5000|intel.*high.*def/i.test(allVariants);
  const is338Orders = orders === '338';

  // Seller trust assessment
  const lowFeedback = sellerFeedback !== null && sellerFeedback < 95;
  const lowFollowers = sellerFollowers !== null && sellerFollowers < 50;

  let trapRisk = 'clean';
  const flags = [];
  if (hasAccessory) { trapRisk = 'trap'; flags.push('accessory variant'); }
  if (hasMultiGpu) { trapRisk = 'trap'; flags.push('multi-GPU variant — price is for cheapest model'); }
  if (hasObfuscated) { trapRisk = 'suspicious'; flags.push('obfuscated variant name'); }
  if (hasFakeSpec) { trapRisk = 'trap'; flags.push('fake spec in variant — e.g. "4GB-RTX A6000"'); }
  if (is338Orders) { flags.push('338 orders — fabricated count'); }
  if (lowFeedback) { flags.push(`low seller feedback: ${sellerFeedback}%`); }
  if (lowFollowers) { flags.push(`low follower count: ${sellerFollowers}`); }

  return {
    currentPrice: current,
    wasPrice,
    saveAmount: saveMatch?.[1] ?? null,
    variants: skus,
    variantProperties: skuProps,
    orders,
    seller: {
      name: storeName,
      feedbackPercent: sellerFeedback,
      followers: sellerFollowers,
    },
    trapRisk,          // "clean" | "suspicious" | "trap"
    trapFlags: flags,  // array of detected issues
    _extracted_from: location.href,
    _extracted_at:   new Date().toISOString(),
  };
}
```

### `trapRisk` output guide

| Risk | Meaning | Action |
|------|---------|--------|
| `clean` | No variant trap, no seller flags | Include in results |
| `suspicious` | Obfuscated variants, low feedback, low followers, or 338 orders | Investigate or exclude |
| `trap` | Accessory variant, multi-GPU, or fake spec | **Discard** |

Check `trapFlags` for the specific reasons. A listing can be `clean` on variant
analysis but still have seller flags in `trapFlags` (e.g., `"low seller feedback: 87.5%"`).

### Detail page selectors

| Data | Selector pattern | Notes |
|------|-----------------|-------|
| Current price | `[class*="price-default--current--"]` | Always present on listings with a price |
| Was/original price | `[class*="price-default--priceExtra--"]` | Filter "Save" prefix from matches |
| Variant options | `[class*="sku-item--box"]` | Reveals what each variant actually is |
| Variant property names | `[class*="sku-item--title--"]` | e.g., "Color", "Plug Type" |
| Store name | `[class*="store-header--storeName"]` | Seller display name |
| Feedback + followers | `[class*="store"]` (contains "Feedback") | Parse `X% Positive Feedback \| Y Followers` |

### Seller trust thresholds

| Metric | Trust | Caution | Avoid |
|--------|-------|---------|-------|
| Feedback % | ≥ 95% | 90-95% | < 90% |
| Followers | ≥ 500 | 50-500 | < 50 (likely fresh or burner store) |

A low-feedback seller with obfuscated variants is a strong scam signal. A
100% feedback score with < 50 followers is a fresh store with insufficient
track record — treat same as suspicious. Seller trust is assessed alongside
variant trap detection, not instead of it.

## Fraud Patterns

### Type 1: Accessory variant trap

Listing has the target product + cheap accessory as variants. Search shows the
accessory price, not the product price. This applies to any product category,
not just GPUs — a laptop listing with "cooling pad" as a variant is the same trap.

**Rule: if any variant is a non-comparable item (accessory, part, replacement
component), the entire listing is a trap.** The listed price is for the cheapest
variant, which is never the product you want.

| Example | searchPrice | Detail variant | Real price |
|---------|-------------|----------------|------------|
| DGX Spark AU$80 | AU$80 | "Only Cascade Cable" | AU$7,200+ |
| DGX Spark AU$100 | AU$100 | "dedicated line" (Color variant) | AU$7,000+ |
| RTX 4090 AU$80 | AU$80 | "describe 4" (obfuscated) | AU$2,000+ |
| RTX 5070 Desktop AU$1,146 | AU$1,146 | Obfuscated A/B/C/D variants | Unknown — likely bare case |

### Type 2: Multi-variant price gaming

Multiple GPU models as variants. Search shows cheapest model price. `maxPrice: null`
in JSON — variant-level pricing not always exposed.

| Example | searchPrice | Cheapest variant | Target variant |
|---------|-------------|------------------|----------------|
| "RTX 3090 24GB" AU$476 | AU$476 | RTX 3060 12G | RTX 3090 24G = AU$2,084+ |
| "RTX A4000 A3000 A5000" AU$434 | AU$434 | A3000 6GB | A5000 24GB = AU$3,639+ |

### Type 2b: Multi-config variant pricing (configurable systems)

Distinct from multi-GPU price gaming. Configurable systems (mini PCs, laptops,
desktops) have legitimate RAM and storage variants. The search price always
reflects the cheapest configuration (lowest RAM, no SSD). This is not fraud —
the listing is real — but the search price is useless for comparison unless you
specify the exact configuration.

| Example | searchPrice | Cheapest config | Target config |
|---------|-------------|-----------------|---------------|
| GMKtec EVO-X2 AU$3,011 | AU$3,011 | 64GB / 2TB | 128GB / 2TB = higher |
| OneXPlayer Super X AU$3,353 | AU$3,353 | 48GB / 1TB | 128GB / 2TB = higher |
| Bosgame M5 AU$3,725 | AU$3,725 | 128GB / no SSD | 128GB / 2TB = higher |

Rule: for configurable systems, always check the variant list for the target
configuration. Never report search-level prices as 128GB prices without
confirming which variant they correspond to.

### Type 3: Outright scam (no variants)

Single price with no variants, 50-80% below market. 338 fabricated orders.

| Example | Listed price | Market price |
|---------|-------------|-------------|
| RTX PRO 6000 Blackwell | AU$2,173 | ~AU$10,000-15,000 |
| RTX 4090 "FRESH IN" | AU$625 | ~AU$2,500 used |

### The "338 orders" red flag

The number **338** appears on virtually every high-value listing regardless of
product category — observed on GPUs, AI systems (DGX Spark), and workstations.
Fabricated by sellers or a platform artifact. Verified order counts that
differed: L40S 48GB = 193, RTX PRO 6000 AU$33K = 249, RTX 3090 AU$2,084 = 127,
DGX Spark bundle = 454, Dell Pro Max = 428.

Rule: 338 orders + below-market price = scam. 338 orders + at-market price =
possibly legitimate with inflated count.

### Type 4: Bundle variant pricing

Listings with bundle variants (e.g., "DGX Spark (2 units)") show a single price
that looks expensive per unit but is actually a multi-unit price. The trap risk
is low (it's a real product), but the per-unit price requires division.

| Example | Listed price | Actual per-unit | Variant text |
|---------|-------------|-----------------|--------------|
| DGX Spark bundle | AU$16,451 | ~AU$8,226 | "Bundle: DGX Spark (2 units)" |

Extract the variant text to detect bundles. If a variant contains "2 units",
"pair", or a quantity > 1, divide the price accordingly before comparison.

### Fresh stores on hot products

Newly-released, in-demand products (Ryzen AI Max+ 395, new GPU launches)
attract fresh stores with 100% feedback but < 25 followers. These sellers
opened stores specifically to sell the hot product. The standard trust
threshold (< 50 followers = avoid) would reject all of them.

For hot products, lower the follower threshold to < 10 (not < 50) and
weight feedback percentage more heavily. A 100% feedback seller with 11–24
followers selling a hot product is more trustworthy than a 66% feedback
seller with thousands of followers. Context matters — seller trust thresholds
should adapt to product lifecycle stage.

### Accessory traps are category-specific

Accessory variant traps (cable at AU$80 for a AU$7,000 system) appear in
categories where accessories can co-list as variants: GPUs (cables, fans),
laptops (cooling pads), phones (cases). Mini PCs, handhelds, and tablets do
not have accessory traps — the product is the whole system with no cheap
accessory to hide as a variant.

For non-accessory categories, the fraud patterns shift to: multi-config price
gaming (Type 2b), fresh stores with no track record, and outright scams with
0% feedback. Adjust the trap detection strategy by category.

## Triage: Price-to-Market Ratio

The fastest way to distinguish clean data from garbage is the **ratio of listing
price to known market price**. This catches traps, scams, and accessory variants
before you even open the detail page.

| Price vs market | What it means | Action |
|----------------|---------------|--------|
| < 5% of market | Accessory variant or outright scam | Discard without verification |
| 5-50% of market | Likely scam or variant trap | Detail-page verify required |
| 50-80% of market | Possible legitimate used/refurbished | Verify seller + variants |
| 80-120% of market | Plausible retail/used pricing | Standard verification |
| > 120% of market | Overpriced or different configuration | Check specs match intent |

**Examples from GB10 verification (DGX Spark market price ~AU$8,000):**

| Listing price | % of market | Verdict | Why |
|--------------|-------------|---------|-----|
| AU$80 | 1% | **Discard** | "Only Cascade Cable" accessory variant |
| AU$83 | 1% | **Discard** | Same cable trap, 338 fabricated orders |
| AU$100 | 1.3% | **Discard** | "dedicated line" — cable, not system |
| AU$7,226 | 90% | **Clean** | 96.2% feedback, 3,669 followers, single variant |
| AU$7,443 | 93% | **Clean** | 95.7% feedback, 7,804 followers, single variant |
| AU$7,913 | 99% | **Avoid** | Clean variant but 66.7% feedback, 28 followers |
| AU$12,325 | 154% | **Avoid** | 75% feedback — overpriced for the seller quality |
| AU$12,407 | 155% | **Clean** | Dell Pro Max, 100% feedback, different config (2TB vs 4TB) |

### Combined triage model

Three signals, evaluated in order:

```
1. Price-to-market ratio
   < 50% → discard (variant trap or scam)
   ≥ 50% → proceed to step 2

2. Seller trust
   feedback < 90% or followers < 50 → avoid
   feedback 90-95% or followers 50-500 → caution
   feedback ≥ 95% and followers ≥ 500 → trusted

3. Variant analysis (detail page)
   accessory variant → discard regardless of price or seller
   multi-model variant → discard (price is cheapest model)
   obfuscated variant → suspicious
   single clean variant → clean
```

A result is only "clean" when all three pass. A plausible price from a bad
seller is not a valid result. A good seller with a variant trap is not a valid
result. All three must align.

## Enterprise GPU Availability

| Category | Expected results | Notes |
|----------|-----------------|-------|
| Consumer GPUs (RTX 30/40/50 series) | 10-30 per search | High scam/trap rate |
| Pro GPUs (RTX A5000/A6000) | 5-15 per search | Most are variant traps below AU$10K |
| Data-center GPUs (L40S, A100, H100) | 0-2 per search | Near-zero AliExpress presence |
| Workstation flagship (RTX 6000 Ada) | **0** | Not available on AliExpress |
| New-release pro (RTX PRO 6000 Blackwell) | 1-4 | Only 1 verified non-scam listing |
| GB10 AI systems (DGX Spark) | 14 unique across 8 queries | 11 DGX Spark + 1 Dell Pro Max + 3 traps. Max-coverage requires multi-query strategy (see below). |
| GB10 AI systems (Dell Pro Max) | 1 per search | Single verified clean listing |
| GB10 AI systems (ASUS Ascent GX10) | **0** | Not available on AliExpress |
| GB10 AI systems (MSI EdgeXpert) | **0** | Only charger/accessories found, not the system |
| Ryzen AI Max+ 395 systems | 86 unique across 8 queries | 18 product lines: GMKtec EVO-X2, Bosgame M5, FEVM FAEX1, FEVM FAEX9, Beelink GTR9 Pro, OpenClaw, Minisforum MS-S1 MAX, SZBOX, Z2 Mini G1a, GPD WIN 5, OneXPlayer Apex MAX+, OneXPlayer Super X, Onexfly Apex, AYANEO NEXT 2 + generic mini PCs and motherboards. Hot product — form-factor synonyms required for coverage. |

For data-center GPUs, AliExpress is not viable. Use eBay, used-equipment
resellers, or authorized distributors.

### Homonym noise from common English words

When a product name contains common English words, the search returns massive
noise. "DGX Spark" returns 60 results — 3 are the actual DGX Spark, 3 are
cable traps, 54 are spark plugs and car parts matching "spark". "GB10" returns
air purifier filters and guitar strings.

Title relevance filtering is mandatory for any product name containing common
English words. Add product-identifying terms to the `keywords` filter to
discard noise: for DGX Spark use `["dgx", "nvidia", "blackwell", "grace"]`.

### Spec-level queries discover related products

Queries targeting exact hardware specs (e.g., "128GB LPDDR5X Blackwell")
surface products from different product lines that share those specs. This
found 8 Jetson AGX Thor listings (Blackwell GPU + 128GB LPDDR5X) that no
product-name query would surface.

Spec-level queries are a fourth layer beyond product names, chip references,
and category terms. Use them when the component has distinguishing specs that
are uncommon in combination. The results won't be the target product, but they
may be relevant to the user's underlying intent.

### Form-factor keywords are non-overlapping query spaces

AliExpress search treats different form-factor keywords as separate result
sets with minimal overlap. For configurable systems, each of these must be a
separate Layer 3 query:

- "mini PC"
- "desktop"
- "workstation"
- "host"
- "gaming computer"
- "server"

Observed: "Ryzen AI Max workstation" found the Z2 Mini G1a (AU$4,960.69) that
"Ryzen AI Max mini PC" and "Ryzen AI Max desktop" did not return at all. The
search engine does not treat these as synonyms — each keyword reaches a
different slice of the product index.

For maximum coverage, enumerate all plausible form-factor synonyms as
separate queries. Do not assume the search engine equates them.

### Product convergence scales with market density

**Niche products** (few listings, small seller pool): all listings converge to
a small number of actual products quickly. GB10: 14 listings across 8 queries
→ 2 products (DGX Spark, Dell Pro Max). 3 queries with 0 new product lines =
confirmed coverage.

**Hot products** (many listings, large seller pool): convergence is slower but
still happens. Ryzen AI Max+ 395: 86 listings across 8 queries → 18 product
lines. 6 verification queries added only 1 new product line. The stopping
rule scales: after 3 queries with 0 new product lines, coverage is confirmed
regardless of market density.

Once you've identified the actual product lines, future searches can skip
discovery and search directly by product name.

## Empty / No-Match Results

| Query type | Behavior | Extractor result |
|------------|----------|-----------------|
| Specific, no matches (e.g., "NVIDIA L40S 48GB GPU") | "Sorry, your search did not match" | `{ count: 0, items: [] }` (mods has `searchTips` not `itemList`) |
| Nonsense query (e.g., "xyznonexistent12345") | Falls back to recommended products | Returns ~8 unrelated items — check titles |
| Homonym query (e.g., "DGX Spark") | Returns 60 items matching "spark" | 90%+ are spark plugs — title filter required |

## Anti-Bot

- `http_get` via browser-harness: **returns error page**. Dead path.
- Chrome DevTools MCP (CDP): **works without issues**. No CAPTCHA observed.
- No rate-limiting observed across 10+ sequential searches.

## Gotchas

- **`/w/wholesale/{query}.html` is dead** — use `/search?SearchText={query}`
- **`[class*="price"]` doesn't work for search-level prices** — AliExpress uses obfuscated CSS classes with no "price" substring. Use `innerText` regex (`/AU\$([\d,]+\.?\d*)/`) on the card element instead. The `extract-js` command in search.py has the correct snippet.
- **`SortType=price_asc` is a loose sort** — promoted listings override ordering
- **`minPrice` is cheapest variant** — a GPU with an AU$5 cable variant shows minPrice: 5
- **Search price ≠ detail price** — search JSON can show AU$13K while detail shows AU$7K for the same ID. Detail page is authoritative.
- **`maxPrice: null` does NOT mean safe** — multi-variant listings with similar prices show null
- **Product URLs have tracking params** — always `.split('?')[0]`
- **`thumbnailUrl` lacks protocol** — prepend `https:` to `//ae-pic-a1...` URLs
- **Every listing needs detail-page verification** — 60-80% of search results are scams or traps
- **"Modified" cards** — "V100 Modified for RTX 4090" is a flashed card, not a real 4090
- **"BUY 2 GET 1 FREE"** on GPU listings is a scam pattern
- **"For [GPU]..." titles** — replacement parts (fans, coolers), not the GPU itself
- **CSS module hashes change** — always use `[class*="prefix--"]` partial match for detail pages
- **"dedicated line" and "cascade cable" are DGX Spark accessory traps** — listings at $80-$100 with these variant names are cables, not the DGX Spark system. The accessory regex must include `dedicated line|cascade|power cord` to catch these. Confirmed on product IDs 1005010734242172, 1005010734240196, 1005011659350058.
- **Max-coverage category search requires multiple query strategies** — "GB10" alone returns 60 items but only 4 are relevant. Combining "GB10 Grace Blackwell" (8 results, 5 relevant), "DGX Spark" (60 results, 12 relevant), "Grace Blackwell workstation" (60 results, 7 relevant), and "Blackwell AI desktop computer" (60 results, 16 relevant) found 14 unique GB10 system listings after deduplication. Single-query coverage misses 40-60% of available listings.

## Batch search scripts

Scripts in `domain-skills/aliexpress/scripts/` automate maximum-coverage searches
for any product type:

- **`search.py plan <query>`** — generates layered search URLs with early
  termination. Composable flags: `--synonyms`, `--specs`, `--modifiers`.
- **`search.py extract-js`** — prints extraction JS that accumulates across
  navigations via localStorage. Use `--dump` to retrieve, `--reset` to clear.
- **`search.py merge <results.json>`** — deduplicates, price-filters, keyword-
  filters, excludes noise, classifies product lines. Supports `--require`,
  `--exclude`, `--min-price`, `--max-price`.
- **`generate_search_urls.py`** — URL generator used by search.py; also works
  standalone for custom query sets
- **`dedup_listings.py`** — compares extracted results against an existing CSV,
  outputs only new listings; supports `--require` and `--exclude`
- **`classify_product_line.py`** — auto-classifies titles into product lines

### Composable query expansion

The layer system adapts to any search type through composable flags:

| Flag | Purpose | Example |
|------|---------|---------|
| `query` (positional) | Main search term | "RTX 4090" |
| `--synonyms` | Alternative names | "Strix Halo" |
| `--specs` | Specificity tokens that change results | "24GB" "48GB" |
| `--modifiers` | Category/context words appended to queries | "graphics card" "GPU" |

**Layer 2** (base coverage): bare terms + term×spec combos.
**Layer 3** (breadth): term×modifier combos.
**Layer 4** (deep): full spec queries via `--spec-terms`.

Why `--specs` matters: AliExpress treats "RTX 4090" and "RTX 4090 24GB" as
orthogonal queries. Adding specificity tokens nearly doubles coverage for
consumer products.

### Search patterns by type

```bash
# Standalone GPUs:
plan "RTX 4090" --specs "24GB" "48GB" --modifiers "graphics card" "GPU" "gaming PC"

# Systems containing a chip:
plan "Ryzen AI Max+ 395" --synonyms "Strix Halo" --modifiers "mini PC" "desktop" "workstation" "server"

# Ambiguous terms that need disambiguation:
plan "RTX A5000" --specs "24GB" --modifiers "professional" "workstation"

# Simple product (no expansion):
plan "mechanical keyboard"

# Category browsing:
plan "4K monitor" --modifiers "gaming" "IPS" "32 inch"
```

### Accumulating extraction via localStorage

Extraction JS uses `localStorage` (key `__ae_results`) to persist results across
page navigations. `window.__aeResults` does NOT work — page navigation creates a
new JS context that wipes window-scoped variables. localStorage persists because
all AliExpress search pages share the same origin.

```bash
# Print the JS snippets:
python3 search.py extract-js          # extract current page, accumulate
python3 search.py extract-js --dump   # dump all accumulated results
python3 search.py extract-js --reset  # clear before starting a new batch
```

### Search-level extraction JS

The extraction JS uses `a[class*="search-card-item"]` (not `a[href*="/item/"]`)
and text-based price extraction (not `[class*="price"]` CSS selectors) because
AliExpress uses obfuscated CSS classes that don't contain the word "price".
Get the latest snippet: `python3 search.py extract-js`

### Noise filtering

Search results contain significant noise. Three filter types work as a cascade:

1. **`--require`** (OR-match) — title must contain at least one keyword
2. **`--exclude`** (word-boundary match) — title must NOT contain any of these
   keywords as whole words (not substrings)
3. **`--min-price` / `--max-price`** — filter by AUD price range

Exclusion uses word-boundary matching: `--exclude "model"` won't match
"modeling" or "rendering". `--exclude "ram"` won't match "framing". This
prevents false positives on legitimate GPU titles.

Common noise patterns per query type:

| Query type | Noise | Fix |
|------------|-------|-----|
| Ambiguous names ("L40S", "A5000") | Vacuums, cameras, phones | Use full name ("RTX A5000"), `--exclude "dreame" "sony"` |
| GPU searches | Water blocks, cables, coolers, accessories | `--exclude "water block" "cable" "cooler" "heatsink" "bracket"` |
| Component searches | Building blocks, toys, cases | `--min-price` to cut below real-product threshold |
| Generic terms ("A5000") | 100% noise | Always prefix with brand ("RTX A5000") |

GPU search safe exclusion keywords (won't kill legitimate listings):
```
--exclude "dreame" "vacuum" "robot" "water block" "cooler" "heatsink" \
  "cable" "riser" "bracket" "backplate" "filter" "brush" "mop" \
  "dust bag" "spare parts" "earphone" "earbuds" "motorcycle" \
  "watercolor" "sketchbook" "podofo" "amplifier"
```

**Do NOT exclude** these common words that appear in legitimate GPU listings:
"model" (appears in "3D Modeling"), "ram"/"ssd" (system specs),
"laptop" (gaming laptops), "bridge" (NVLink), "water" (water-cooled GPUs).

```bash
python3 search.py merge results.json --existing data.csv \
  --require "rtx" "gpu" "graphics card" \
  --exclude "dreame" "vacuum" "water block" "cooler" "cable" \
  --min-price 100
```

### Layer efficiency

Not all queries need all layers. Use early stopping based on product type:

| Type | L2 expected | L3 gain | Recommendation |
|------|-------------|---------|----------------|
| Consumer GPU (3090/4090/5090) | 20-30 | +5-15 | Run L3 |
| Professional GPU (A6000/6000 Ada/A5000) | 10-15 | +0-3 | Skip L3 |
| Enterprise GPU (L40S/H100) | 2-5 | +0-2 | Skip L3 |
| System containing GPU | 5-15 | +3-10 | Run L3 |

### Rapid search workflow

```bash
# 1. Generate layered URLs with early termination guidance
python3 domain-skills/aliexpress/scripts/search.py plan "RTX 4090" \
  --specs "24GB" "48GB" --modifiers "graphics card" "GPU" "gaming PC"

# 2. Reset accumulation, then navigate to each URL and run extraction JS
#    (extraction accumulates across navigations automatically via localStorage)

# 3. Dump all accumulated results from browser, save to file

# 4. Merge, dedup, filter noise, classify
python3 domain-skills/aliexpress/scripts/search.py merge results.json \
  --require "rtx" "gpu" "graphics card" \
  --exclude "water block" "bridge" "cooler" --min-price 100
```

When new product lines are discovered, add them to the classifier's
`PRODUCT_PATTERNS` list in `classify_product_line.py`.

### Query ambiguity warning

Some product names collide with consumer products on AliExpress:

| Query | Noise source | Fix |
|-------|-------------|-----|
| "L40S" | Dreame L40s vacuum cleaners | Use `--exclude "dreame" "vacuum"` |
| "A5000" | Sony A5000 cameras, OnePlus phones | Use "RTX A5000" as query |
| "RTX 6000 Ada" | Water blocks, NVLink bridges | `--exclude "water block" "bridge"` |
| "RTX PRO 6000" | Cooling accessories | `--exclude "cooler" "water block"` |

Always check what a bare query returns before trusting results. Ambiguous
terms need either a more specific query or aggressive `--exclude` filtering.
