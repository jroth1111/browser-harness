# AliExpress — Product Search & Price Comparison

Field-tested against aliexpress.com on 2026-05-02 using Chrome DevTools MCP (CDP).
Extractors tested across 7+ product categories: consumer GPUs, pro GPUs, data-center
GPUs, workstations, CPUs, keyboards, shoes, and zero-result queries.

## Architecture

AliExpress search pages embed **structured JSON** in `window._dida_config_._init_data_`
(~357 KB). This JSON contains all product data — prices, titles, images, URLs — as
clean typed fields. **No DOM scraping or regex needed for search results.**

Detail pages have no equivalent embedded JSON. Use DOM selectors for those.

| Page | Primary method | Data source |
|------|---------------|-------------|
| Search | `window._dida_config_._init_data_` | SSR-embedded JSON |
| Product detail | DOM selectors | CSS partial-match on class names |

## Fastest Path

```
navigate → /search?SearchText={query}&SortType=price_asc → extract JSON via JS → done
```

Browser CDP is required. `http_get` returns error pages. No JSON-LD or `__NEXT_DATA__`.

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
| `price_asc` | Cheapest roughly first | Not strict ascending; promoted listings may override |
| `total_volume` | Most orders | Confirmed working |

### Result counts

60 items per page from the embedded JSON (indexed "0" through "59").

## Embedded JSON Data Source (Primary)

### JSON path

```
window._dida_config_._init_data_.data.data.root.fields.mods.itemList.content
```

Returns an object with numeric string keys. Each value is a product object with
fully structured data — no regex, no DOM, no currency parsing.

### Item structure (confirmed fields)

```
{
  "productId":            "1005011964111724",        // string, product ID
  "title": {
    "displayTitle":       "FRESH IN Gaming GeForce RTX 4090 24GB..."
  },
  "prices": {
    "salePrice": {
      "minPrice":         625.99,                     // number (already parsed)
      "maxPrice":         2849.27,                    // number, highest variant price
      "formattedPrice":   "AU $625.99",               // string with currency prefix
      "currencyCode":     "AUD",                      // adapts to user region
      "cent":             62599                        // price in cents
    },
    "originalPrice": {                                // only present when on sale
      "minPrice":         834.65,
      "formattedPrice":   "AU $834.65"
    },
    "salePrice": {
      "discount":         "21% off"                   // only present when on sale
    }
  },
  "productType":          "natural",                  // "natural" = organic; other = promoted
  "image": {
    "imgUrl":             "//ae-pic-a1.aliexpress-media.com/kf/..."
  },
  "productDetailUrl":     "/item/1005011964111724.html?...",  // needs domain prepended
}
```

### Variant-trap detection in JSON

The `minPrice` is always the cheapest variant. A GPU listing with an accessory
variant shows `minPrice` of the accessory, not the GPU. Detect this with the
**spread ratio**:

```
spread = maxPrice / minPrice
```

| Spread | Meaning | Action |
|--------|---------|--------|
| `null` (no maxPrice) | Single variant | Clean listing |
| 1.0–1.5 | Discount only (sale vs original) | `minPrice` is the real price |
| 1.5–3 | Minor variants (different capacities) | Use title + product knowledge |
| 3–10 | Variant trap likely (accessory vs product) | `maxPrice` is closer to real price |
| 10+ | Obvious trap (cable vs GPU) | Discard or use `maxPrice` |

### JSON Search Extractor (Field-Tested)

Run via CDP `evaluate_script` after page load. Returns clean structured data
directly from the embedded JSON — no DOM parsing, no regex, no currency guessing.

```javascript
() => {
  const cfg = window._dida_config_?._init_data_;
  if (!cfg) return { error: "_dida_config_._init_data_ not found" };
  const content = cfg.data?.data?.root?.fields?.mods?.itemList?.content;
  if (!content) return { error: "itemList.content not found" };

  const items = [];
  for (const [idx, item] of Object.entries(content)) {
    const sale = item.prices?.salePrice || {};
    const orig = item.prices?.originalPrice;
    const low = sale.minPrice ?? null;
    const high = sale.maxPrice ?? null;
    const spread = (low && high && low > 0) ? +(high / low).toFixed(1) : null;
    const img = item.image || {};

    items.push({
      productId:       item.productId,
      title:           item.title?.displayTitle?.substring(0, 150),
      salePrice:       low,                            // number, cheapest variant
      maxPrice:        high,                           // number, most expensive variant
      originalPrice:   orig?.minPrice ?? null,         // number, was-price (null if not on sale)
      discount:        sale.discount || null,          // string "21% off" or null
      currency:        sale.currencyCode || null,      // "AUD", "USD", etc.
      spread,
      productType:     item.productType,               // "natural" = organic
      thumbnailUrl:    img.imgUrl ? "https:" + img.imgUrl : null,
      url:             "https://www.aliexpress.com" + (item.productDetailUrl || "").split("?")[0],
    });
  }
  return { count: items.length, items };
}
```

### Why JSON over DOM

| Aspect | JSON extractor | DOM extractor |
|--------|---------------|---------------|
| Price data | Numeric `minPrice: 625.99` | Regex on `AU$` text — fragile |
| Currency | `currencyCode: "AUD"` — explicit | Hardcoded `AU$` regex — region-dependent |
| Variant spread | `minPrice` + `maxPrice` — clean ratio | Multiple regex matches — error-prone |
| Item count | 60 per page (all items) | Variable (12–24), misses items |
| Free shipping | Not available in JSON — check detail page DOM | `allText.includes('Free shipping')` |
| Organic vs promoted | `productType: "natural"` | No distinction possible |
| Discount info | `discount: "21% off"` + `originalPrice` | Regex `-(\d+)%` on text |
| Maintenance risk | Low — JSON structure is stable | High — CSS classes change on deploy |

## DOM Fallback Search Extractor

Use only if `_dida_config_` is unavailable (page structure changed, A/B test, etc.).
This extractor parses visible DOM text with regex.

```javascript
() => {
  const items = [];
  document.querySelectorAll('a[href*="/item/"]').forEach(link => {
    const h3 = link.querySelector('h3');
    if (!h3) return;
    const title = h3.innerText.trim();
    const url = link.href.split('?')[0];
    const idMatch = url.match(/\/item\/(\d+)\.html/);
    const allText = link.innerText;
    const prices = [];
    const rx = /AU\$\s*([\d,]+\.?\d*)/g;
    let m;
    while ((m = rx.exec(allText)) !== null) {
      const before = allText.substring(Math.max(0, m.index - 15), m.index);
      const after = allText.substring(m.index + m[0].length).trimStart();
      if (before.match(/[×x]\s*$/) || before.match(/Save\s*$/i) || after.startsWith('off')) continue;
      prices.push(parseFloat(m[1].replace(/,/g, '')));
    }
    prices.sort((a, b) => a - b);
    const low = prices[0] || null;
    const high = prices.length > 1 ? prices[prices.length - 1] : null;
    const spread = (low && high && low > 0) ? Math.round(high / low) : null;
    items.push({
      itemId: idMatch?.[1],
      title: title.substring(0, 150),
      lowPrice: low,
      highPrice: high,
      spread,
      priceCount: prices.length,
      freeShipping: allText.includes('Free shipping'),
      discount: (allText.match(/-(\d+)%/) || [])[1] || null,
      url
    });
  });
  return items;
}
```

### DOM filter rules

The DOM regex extractor must exclude three patterns that contain price-like text:

| Pattern | Example | Why filter |
|---------|---------|------------|
| Installments | `6 × AU$130.94` | Not a product price |
| Coupon amounts | `AU$3 off on AU$23` | Discount, not price |
| Savings | `Save AU$3.23` | Savings, not price |

### Currency note (DOM only)

The `AU$` prefix is hardcoded in the DOM regex. For other regions, adjust to match
the local currency prefix (e.g., `US$`, `€`, `£`). The JSON extractor has no
region dependency — `currencyCode` is explicit.

## Product Detail Page Extractor (DOM)

No embedded JSON on detail pages. Use DOM selectors with CSS partial-match.

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
  return {
    currentPrice: current,
    wasPrice,
    saveAmount: saveMatch?.[1] || null,
    variants: skus,
    variantProperties: skuProps,
    orders: ordersMatch?.[1] || null
  };
}
```

### Detail page selectors

| Data | Selector pattern | Notes |
|------|-----------------|-------|
| Current price | `[class*="price-default--current--"]` | Always present on listings with a price |
| Was/original price | `[class*="price-default--priceExtra--"]` | Contains save amount + was price; filter "Save" prefix |
| Variant options | `[class*="sku-item--box"]` | Reveals what each variant actually is |
| Variant property names | `[class*="sku-item--title--"]` | e.g., "Color", "Plug Type" |

### Variant detection on detail pages

The `variants` array reveals what each SKU option actually is:

| Variant text | Meaning |
|-------------|---------|
| `"GRAPHICS-CARD"` | Single-variant listing (the real product) |
| `"Only Cascade Cable"` | Variant trap — cable, not the workstation |
| `"4GB-RTX A6000"` | Variant trap — 4GB card labeled as RTX A6000 |
| `"describe 4"` | Obfuscated variant — seller hiding actual product names |

## Empty / No-Match Results

Two behaviors observed:

| Query type | Behavior | Extractor result |
|------------|----------|-----------------|
| Specific, no matches (e.g., "NVIDIA L40S 48GB GPU") | "Sorry, your search did not match" page | JSON extractor returns `{ count: 0, items: [] }` |
| Nonsense query (e.g., "xyznonexistent12345") | Falls back to recommended products | Returns ~8 unrelated items — **check titles for relevance** |

## Anti-Bot

- `http_get` via browser-harness: **returns error page**. Dead path.
- Chrome DevTools MCP (CDP): **works without issues**. No CAPTCHA observed.
- No rate-limiting observed across 10+ sequential searches.

## Gotchas

- **`/w/wholesale/{query}.html` is dead** — use `/search?SearchText={query}`
- **`SortType=price_asc` is a loose sort** — promoted listings override ordering
- **CSS module hashes change** — always use `[class*="prefix--"]` partial match for detail pages
- **`minPrice` is cheapest variant** — a GPU listing with an AU$5 cable variant shows minPrice: 5, not the GPU price. Use `spread` to detect this.
- **Product URLs have tracking params** — always `.split('?')[0]`
- **`thumbnailUrl` lacks protocol** — prepend `https:` to `//ae-pic-a1...` URLs
- **`productType: "natural"`** identifies organic listings; promoted/sponsored have different values
- **Single-price variant traps** — if `spread: null` and the price seems too low for the product, visit the detail page to check variants
- **Obfuscated variant names** — sellers may use "describe 4" instead of the real product name
- **"Modified" cards** — "V100 Modified for RTX 4090" is a flashed card, not a real 4090
- **"BUY 2 GET 1 FREE"** on GPU listings is a scam pattern
- **"For [GPU]..." titles** — replacement parts (fans, coolers), not the GPU itself
- **Nonsense queries return recommendations** — empty results only for specific no-match queries
