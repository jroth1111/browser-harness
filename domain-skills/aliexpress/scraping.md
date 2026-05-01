# AliExpress — Product Search & Price Comparison

Field-tested against aliexpress.com on 2026-05-02 using Chrome DevTools MCP (CDP).
Tested across 10 GPU/workstation product categories with detail-page verification.
Browser CDP required. `http_get` returns error pages.

## Complete Workflow

```
1. Search  →  extract JSON, filter by title + price floor
2. Verify  →  open top N detail pages, check variants for traps
3. Report  →  only include verified clean listings
```

Every product needs Step 2. Across 10 GPU categories, 60-80% of search results
were scams or variant traps that only the detail page extractor could detect.

## Search URLs

| URL | Status | Notes |
|-----|--------|-------|
| `/search?SearchText={query}` | Works | Redirects to `/w/wholesale-{query}.html` |
| `/search?SearchText={query}&SortType=price_asc` | Works | Loose sort, cheapest roughly first |
| `/search?SearchText={query}&SortType=total_volume` | Works | Sort by orders |
| `/search?SearchText={query}&page=2` | Works | Pagination |
| `/w/wholesale/{query}.html` | **Dead (404)** | Old pattern |
| `/item/{product_id}.html` | Works | Product detail page |

### SortType values

| Value | Effect | Note |
|-------|--------|------|
| (none) | Best match | Default |
| `price_asc` | Cheapest roughly first | Promoted listings may override |
| `total_volume` | Most orders | Confirmed working |

60 items per page from the embedded JSON.

## Step 1: Search Extractor

### JSON path

```
window._dida_config_._init_data_.data.data.root.fields.mods.itemList.content
```

Object with numeric string keys ("0" through "59"), each a product with fully
structured data — no regex, no DOM parsing, no currency guessing.

### Combined extractor with filtering

Run via CDP `evaluate_script` after page load. Accepts `keywords` for title
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
    const title = item.title?.displayTitle || '';
    const tlc = title.toLowerCase();

    // Price floor: discard cheap accessories
    if (low !== null && low < pf) continue;

    // Title relevance: at least one keyword must match (if keywords provided)
    if (kw.length > 0 && !kw.some(k => tlc.includes(k.toLowerCase()))) continue;

    items.push({
      productId:       item.productId,
      title:           title.substring(0, 150),
      salePrice:       low,
      maxPrice:        high,
      originalPrice:   orig?.minPrice ?? null,
      discount:        sale.discount || null,
      currency:        sale.currencyCode || null,
      spread,
      productType:     item.productType,
      thumbnailUrl:    img.imgUrl ? "https:" + img.imgUrl : null,
      url:             "https://www.aliexpress.com" + (item.productDetailUrl || "").split("?")[0],
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

### When `itemList.content` is missing

The `mods` object will contain `searchTips` instead of `itemList` when the
search returns zero results. This is distinct from nonsense queries, which
return recommended products ( itemList present but titles are unrelated).

## Step 2: Detail Page Verification (Required)

No embedded JSON on detail pages. Use DOM selectors. **Always verify before
trusting a search result** — variant traps and scams are the norm, not the
exception, for GPU listings.

### Detail page extractor with trap assessment

```javascript
() => {
  const current = document.querySelector('[class*="price-default--current--"]')?.innerText?.trim();
  const extraEl = document.querySelector('[class*="price-default--priceExtra--"]');
  const extraText = extraEl?.innerText?.trim() || '';
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

  // Trap assessment
  const allVariants = skus.join(' ').toLowerCase();
  const hasAccessory = /cable|fan|heatsink|sticker|cover|gasket|bracket|sled|sled|thermal/.test(allVariants);
  const hasMultiGpu = (skus.join('\n').match(/\bRTX\s*\d{3,4}/gi) || []).length > 1
    || (skus.join('\n').match(/\bA\d{4}\b/g) || []).length > 1;
  const hasObfuscated = /describe|option\s*\d|package\s*\d/i.test(allVariants);
  const hasFakeSpec = /4gb.*a6000|4gb.*a5000|intel.*high.*def/i.test(allVariants);
  const is338Orders = orders === '338';

  let trapRisk = 'clean';
  const flags = [];
  if (hasAccessory) { trapRisk = 'trap'; flags.push('accessory variant'); }
  if (hasMultiGpu) { trapRisk = 'trap'; flags.push('multi-GPU variant — price is for cheapest model'); }
  if (hasObfuscated) { trapRisk = 'suspicious'; flags.push('obfuscated variant name'); }
  if (hasFakeSpec) { trapRisk = 'trap'; flags.push('fake spec in variant — e.g. "4GB-RTX A6000"'); }
  if (is338Orders) { flags.push('338 orders — fabricated count'); }

  return {
    currentPrice: current,
    wasPrice,
    saveAmount: saveMatch?.[1] || null,
    variants: skus,
    variantProperties: skuProps,
    orders,
    trapRisk,          // "clean" | "suspicious" | "trap"
    trapFlags: flags,  // array of detected issues
  };
}
```

### `trapRisk` output guide

| Risk | Meaning | Action |
|------|---------|--------|
| `clean` | No variant trap detected, no 338 flag | Include in results |
| `suspicious` | Obfuscated variant names or 338 orders | Investigate further or exclude |
| `trap` | Accessory variant, multi-GPU, or fake spec | **Discard** |

### Detail page selectors

| Data | Selector pattern | Notes |
|------|-----------------|-------|
| Current price | `[class*="price-default--current--"]` | Always present on listings with a price |
| Was/original price | `[class*="price-default--priceExtra--"]` | Filter "Save" prefix from matches |
| Variant options | `[class*="sku-item--box"]` | Reveals what each variant actually is |
| Variant property names | `[class*="sku-item--title--"]` | e.g., "Color", "Plug Type" |

## Fraud Patterns

### Type 1: Accessory variant trap

Listing has GPU + cheap accessory as variants. Search shows accessory price.

| Example | searchPrice | Detail variant | Real price |
|---------|-------------|----------------|------------|
| DGX Spark AU$80 | AU$80 | "Only Cascade Cable" | AU$7,200+ |
| RTX 4090 AU$80 | AU$80 | "describe 4" (obfuscated) | AU$2,000+ |

### Type 2: Multi-variant price gaming

Multiple GPU models as variants. Search shows cheapest model price. `maxPrice: null`
in JSON — variant-level pricing not always exposed.

| Example | searchPrice | Cheapest variant | Target variant |
|---------|-------------|------------------|----------------|
| "RTX 3090 24GB" AU$476 | AU$476 | RTX 3060 12G | RTX 3090 24G = AU$2,084+ |
| "RTX A4000 A3000 A5000" AU$434 | AU$434 | A3000 6GB | A5000 24GB = AU$3,639+ |

### Type 3: Outright scam (no variants)

Single price with no variants, 50-80% below market. 338 fabricated orders.

| Example | Listed price | Market price |
|---------|-------------|-------------|
| RTX PRO 6000 Blackwell | AU$2,173 | ~AU$10,000-15,000 |
| RTX 4090 "FRESH IN" | AU$625 | ~AU$2,500 used |

### The "338 orders" red flag

The number **338** appears on virtually every GPU listing regardless of seller,
price, or product. Fabricated by sellers or a platform artifact. Verified order
counts that differed: L40S 48GB = 193, RTX PRO 6000 AU$33K = 249, RTX 3090
AU$2,084 = 127.

Rule: 338 orders + below-market price = scam. 338 orders + at-market price =
possibly legitimate with inflated count.

## Enterprise GPU Availability

| Category | Expected results | Notes |
|----------|-----------------|-------|
| Consumer GPUs (RTX 30/40/50 series) | 10-30 per search | High scam/trap rate |
| Pro GPUs (RTX A5000/A6000) | 5-15 per search | Most are variant traps below AU$10K |
| Data-center GPUs (L40S, A100, H100) | 0-2 per search | Near-zero AliExpress presence |
| Workstation flagship (RTX 6000 Ada) | **0** | Not available on AliExpress |
| New-release pro (RTX PRO 6000 Blackwell) | 1-4 | Only 1 verified non-scam listing |

For data-center GPUs, AliExpress is not viable. Use eBay, used-equipment
resellers, or authorized distributors.

## Empty / No-Match Results

| Query type | Behavior | Extractor result |
|------------|----------|-----------------|
| Specific, no matches (e.g., "NVIDIA L40S 48GB GPU") | "Sorry, your search did not match" | `{ count: 0, items: [] }` (mods has `searchTips` not `itemList`) |
| Nonsense query (e.g., "xyznonexistent12345") | Falls back to recommended products | Returns ~8 unrelated items — check titles |

## Anti-Bot

- `http_get` via browser-harness: **returns error page**. Dead path.
- Chrome DevTools MCP (CDP): **works without issues**. No CAPTCHA observed.
- No rate-limiting observed across 10+ sequential searches.

## Gotchas

- **`/w/wholesale/{query}.html` is dead** — use `/search?SearchText={query}`
- **`SortType=price_asc` is a loose sort** — promoted listings override ordering
- **`minPrice` is cheapest variant** — a GPU with an AU$5 cable variant shows minPrice: 5
- **`maxPrice: null` does NOT mean safe** — multi-variant listings with similar prices show null
- **Product URLs have tracking params** — always `.split('?')[0]`
- **`thumbnailUrl` lacks protocol** — prepend `https:` to `//ae-pic-a1...` URLs
- **Every listing needs detail-page verification** — 60-80% of search results are scams or traps
- **"Modified" cards** — "V100 Modified for RTX 4090" is a flashed card, not a real 4090
- **"BUY 2 GET 1 FREE"** on GPU listings is a scam pattern
- **"For [GPU]..." titles** — replacement parts (fans, coolers), not the GPU itself
- **CSS module hashes change** — always use `[class*="prefix--"]` partial match for detail pages
