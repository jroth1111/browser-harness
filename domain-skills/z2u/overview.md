# z2u.com — Exhaustive Product Search

Field-tested against z2u.com on 2026-05-02 using a Chrome CDP session.
No Cloudflare Turnstile was triggered during testing with a standard browser session.

## Field Semantics (OWA-correct four-state)

Every extracted field uses four-state semantics to distinguish "not found" from "confirmed absent" from "could not check":

| JS value | CSV value | Meaning |
|----------|-----------|---------|
| `"value"` | `value` | Found and extracted |
| `null` | `(absent)` | Confirmed absent on this page/entity type |
| `"__UNOBSERVABLE__"` | `(unobservable)` | Page blocked or broken — could not inspect |
| key omitted | `(not checked)` | Field not applicable to this entity type |
| `""` | `(absent)` | Legacy: treated as confirmed absent |

This avoids the CWA/OWA coverage gap: downstream consumers can distinguish "no seller on this page type" from "seller exists but extraction failed."

## Source Classification

| Source | Available | Notes |
|--------|-----------|-------|
| Exports | None | No CSV/API export |
| Public API | None | No documented API |
| HTTP scraping | Blocked | Cloudflare Turnstile on some routes |
| CDP (browser) | Required | Full rendered pages with structured data |

## URL Patterns

```
# Global search (returns category cards with offer counts)
/searchAllGame?search={query}              # page 1
/searchAllGame?search={query}&page={N}     # pagination

# Category listing (paginated product/seller offers)
/{game-slug}/{type}-{ids}                  # page 1
/{game-slug}/{type}-{ids}?page={N}         # pagination

# Product detail page
/product-{id}/{slug}.html

# Individual seller offer page
/items-{id}/{slug}.html
```

**Type IDs**: 1=Currency, 2=Top-Up, 3=Items, 4=Boosting, 5=Accounts, 9=Video Games, 10=Gift Cards, 11=Coupons, 12=Subscriptions, 15=Game DLC, 16=CD Keys

**Pagination note**: Category pagination links in the DOM omit the `search=` parameter. Always construct pagination URLs manually as `?search={query}&page={N}` for search results.

## Items Per Page

z2u.com supports up to 400 items per page. Always set this to minimize pagination passes.

```javascript
// Set items per page to 400
const select = document.querySelector('select');
if (select) {
  select.value = '400';
  select.dispatchEvent(new Event('change', { bubbles: true }));
  document.querySelectorAll('button').forEach(b => {
    if (b.textContent.trim() === 'Confirm') b.click();
  });
}
```

Wait for page reload after clicking Confirm.

## Search Results Page Extraction

### Category cards

Each category is a `<a>` containing an `<h3>` heading and offer count text.

```javascript
// Returns { total, added, url, containers_found, suspect } — categories in localStorage
() => {
  const stored = localStorage.getItem('__z2u_categories');
  const results = stored ? JSON.parse(stored) : [];
  const existing = new Set(results.map(r => r.url));
  const links = document.querySelectorAll('a[href]');
  let added = 0;
  for (const link of links) {
    const h3 = link.querySelector('h3');
    if (!h3) continue;
    const text = link.textContent || '';
    const offerMatch = text.match(/(\d+)\s*Offers/);
    if (!offerMatch) continue;
    const url = link.href;
    if (existing.has(url)) continue;
    existing.add(url);
    results.push({
      name: h3.textContent.trim(),
      url: url,
      offer_count: parseInt(offerMatch[1]),
      _extracted_from: location.href,
      _extracted_at: new Date().toISOString()
    });
    added++;
  }
  localStorage.setItem('__z2u_categories', JSON.stringify(results));
  const containers = document.querySelectorAll('a[href] h3');
  const pageHasContainers = containers.length > 0;
  return {
    total: results.length,
    added: added,
    url: location.href,
    containers_found: containers.length,
    suspect: (added === 0 && pageHasContainers)
  };
}
```

### Pagination detection

```javascript
() => {
  const pageText = document.body.innerText;
  const totalMatch = pageText.match(/(\d+)\s*records?\s*in\s*total/i);
  const lastPageLink = document.querySelector('a[href*="page="]:last-of-type');
  // Construct next page URL manually — DOM links omit search param
  const currentUrl = new URL(location.href);
  const currentPage = parseInt(currentUrl.searchParams.get('page') || '1');
  return {
    total_records: totalMatch ? parseInt(totalMatch[1]) : null,
    current_page: currentPage,
    has_more: true // check by comparing categories extracted vs total
  };
}
```

## Category Listing Page Extraction

Category pages show two types of listings mixed together:

1. **Product aggregations** — link to `/product-{id}/`, show "X Offers", have aggregated pricing
2. **Individual seller offers** — link to `/items-{id}/`, show stock count, delivery time, seller name, direct price

### Confirmed CSS selectors

**Product aggregation cards** (inside `a[href*="/product-"]`):
| Field | Selector | Example |
|-------|----------|---------|
| Title | `.title` | "ChatGPT Plus 1-Month Top up （For All User）" |
| Region | `.fromCountry` | "Global" |
| Attribute | `.fromAttr` | "Manual Top Up" |
| Offer count | `.numberTxt` | "2 Offers" |
| Price | `.priceTxt` | "$17.6" |
| Original price | `del` | "$20" |
| Discount | `.discountNumber` | "-12%" |

**Individual seller offer cards** (inside `a[href*="/items-"]` parent):
| Field | Selector | Example |
|-------|----------|---------|
| Title | `a.productName .title` | "plus,gpt5,chatgpt plus,1 month" |
| Stock | `.dayNumber` | "30" |
| Delivery | `.deliveryTimeLabel` | "48H" |
| Seller | `div.name` | "chatgpt996" |
| Price | `.priceTxt` | "$22" |

```javascript
(categoryName) => {
  const stored = localStorage.getItem('__z2u_products');
  const results = stored ? JSON.parse(stored) : [];
  const existing = new Set(results.map(r => r.url));
  let added = 0;

  // Product aggregations: /product-{id}/
  document.querySelectorAll('a[href*="/product-"]').forEach(link => {
    const url = link.href.split('?')[0];
    if (existing.has(url)) return;
    existing.add(url);
    const urlMatch = link.href.match(/\/product-(\d+)\//);
    const titleEl = link.querySelector('.title') || link.querySelector('h3');
    const title = titleEl ? titleEl.textContent.trim() : '';
    const countryEl = link.querySelector('.fromCountry');
    const attrEl = link.querySelector('.fromAttr');
    const region = countryEl ? countryEl.textContent.trim() : null;
    const attr = attrEl ? attrEl.textContent.trim() : null;
    const numberEl = link.querySelector('.numberTxt');
    const offerCountMatch = numberEl ? numberEl.textContent.match(/(\d+)/) : null;
    const priceEl = link.querySelector('.priceTxt');
    const price = priceEl ? priceEl.textContent.trim() : null;
    const text = (link.textContent || '');
    const soldOut = text.includes('sold out');
    results.push({
      type: 'product',
      product_id: urlMatch ? urlMatch[1] : null,
      url: url,
      title: title || null,
      category: categoryName,
      region: region,
      attribute: attr,
      price: price,
      offer_count: offerCountMatch ? parseInt(offerCountMatch[1]) : (soldOut ? 0 : null),
      sold_out: soldOut,
      seller: null,
      stock: null,
      delivery: null,
      _extracted_from: location.href,
      _extracted_at: new Date().toISOString()
    });
    added++;
  });

  // Individual seller offers: /items-{id}/
  document.querySelectorAll('a[href*="/items-"]').forEach(link => {
    const url = link.href.split('?')[0];
    if (!/\/items-\d+\//.test(url)) return;
    if (existing.has(url)) return;
    existing.add(url);
    const title = link.textContent.trim();
    if (!title || title.length < 3) return;
    const parent = link.closest('div, li, tr') || link.parentElement;
    const stockEl = parent ? parent.querySelector('.dayNumber') : null;
    const deliveryEl = parent ? parent.querySelector('.deliveryTimeLabel') : null;
    const sellerEl = parent ? parent.querySelector('.name') : null;
    const priceEl = parent ? parent.querySelector('.priceTxt') : null;
    results.push({
      type: 'offer',
      item_id: (url.match(/\/items-(\d+)\//) || [])[1] || null,
      url: url,
      title: title,
      category: categoryName,
      price: priceEl ? priceEl.textContent.trim() : null,
      seller: sellerEl ? sellerEl.textContent.trim() : null,
      stock: stockEl ? stockEl.textContent.trim() : null,
      delivery: deliveryEl ? deliveryEl.textContent.trim() : null,
      sold_out: false,
      offer_count: 1,
      _extracted_from: location.href,
      _extracted_at: new Date().toISOString()
    });
    added++;
  });

  localStorage.setItem('__z2u_products', JSON.stringify(results));
  const productContainers = document.querySelectorAll('a[href*="/product-"]');
  const offerContainers = document.querySelectorAll('a[href*="/items-"]');
  const pageHasContainers = productContainers.length > 0 || offerContainers.length > 0;
  return {
    total: results.length,
    added: added,
    url: location.href,
    containers_found: productContainers.length + offerContainers.length,
    suspect: (added === 0 && pageHasContainers)
  };
}
```

## Product Detail Page Extraction

Product detail pages show full info plus all sellers for a product.

```javascript
(categoryName) => {
  const h1 = document.querySelector('h1');
  const title = h1 ? h1.textContent.trim() : null;
  const bodyText = document.body.innerText;

  // Extract key fields from the page text
  const region = (bodyText.match(/(Global|United States|Europe|Turkey|Argentina)/) || [])[1] || null;
  const platform = (bodyText.match(/Activate\/redeem\/trade on (.+)/) || [])[1] || null;
  const deliveryMatch = bodyText.match(/Delivery Time:\s*([^\n]+)/);
  const durationMatch = bodyText.match(/Subscription duration:\s*([^\n]+)/);

  // Primary seller info
  const sellerLink = document.querySelector('a[href*="/shop/"]');
  const sellerName = sellerLink ? sellerLink.textContent.trim() : null;
  const ratingMatch = bodyText.match(/(\d+\.\d+)%/);
  const stockText = bodyText.match(/Stock:\s*([^\n]+)/);

  // Price
  const priceMatch = bodyText.match(/\$\s*([\d,.]+)/);

  // Description
  const descSection = bodyText.match(/Product Description([\s\S]*?)(?:Looking for more|$)/);

  // All sellers on the page
  const sellers = [];
  document.querySelectorAll('a[href*="/shop/"]').forEach(link => {
    const name = link.textContent.trim();
    if (name && !sellers.includes(name)) sellers.push(name);
  });

  return {
    product_name: title || null,
    category: categoryName,
    description: descSection ? descSection[1].trim().substring(0, 500) : null,
    seller: sellerName || null,
    all_sellers: sellers,
    price: priceMatch ? '$' + priceMatch[1] : null,
    url: location.href,
    region: region || null,
    platform: platform || null,
    delivery_time: deliveryMatch ? deliveryMatch[1].trim() : null,
    subscription_duration: durationMatch ? durationMatch[1].trim() : null,
    stock: stockText ? stockText[1].trim() : null,
    seller_rating: ratingMatch ? ratingMatch[1] + '%' : null,
    _extracted_from: location.href,
    _extracted_at: new Date().toISOString()
  };
}
```

## Workflow: 3-Level Exhaustive Crawl

```
Level 1: Discover Categories
  Navigate to /searchAllGame?search={query}
  Set items-per-page to 400
  Extract category links + offer counts
  Paginate: ?search={query}&page=2, page=3, ...
  Stop when 0 new categories extracted

Level 2: Extract Products per Category
  For each category with > 0 offers:
    Navigate to category URL
    Extract product aggregations + individual offers
    Paginate: ?page=2, page=3, ...
    Stop when 0 new products (convergence)

Level 3: Extract Details (optional, for filtered results)
  For each product passing relevance filter:
    Navigate to /product-{id}/{slug}.html
    Extract full details + all sellers

Post: Filter by relevance → export CSV
```

## Anti-Bot

- No Cloudflare Turnstile encountered during testing with a standard browser session
- If Turnstile appears: wait 5 seconds for non-interactive challenges to resolve
- 3-5 second delay between page navigations to avoid rate limiting
- Use `wait_for_content()` after navigation — it detects blocks AND waits for
  content to render, replacing `wait_for_load()` + fixed delay
- If `wait_for_content()` returns `block: true`, emit `__UNOBSERVABLE__` for all
  fields instead of running extraction JS on the challenge page
- **Stealth fallback**: If CDP session hits Turnstile that `solve_turnstile()` cannot pass,
  use Patchright stealth browser:

```python
from stealth_helpers import stealth_session

with stealth_session() as s:
    s.goto("https://z2u.com/searchAllGame?search=chatgpt")
    # Set 400 items per page
    s.js("""(() => {
        const select = document.querySelector('select');
        if (select) {
            select.value = '400';
            select.dispatchEvent(new Event('change', { bubbles: true }));
            document.querySelectorAll('button').forEach(b => {
                if (b.textContent.trim() === 'Confirm') b.click();
            });
        }
    })()""")
    # All JS extraction from above works unchanged via s.js()
    categories = s.js("...")  # paste any extraction JS from this doc
```

All JS extraction snippets in this doc work with `s.js()` — Patchright's `page.evaluate()`
accepts arrow functions and IIFEs directly.

## Gotchas

- **Pagination URLs omit search param**: DOM pagination links go to `searchAllGame?page=2` without `search=`. Always construct manually.
- **Two listing types mixed**: Category pages show both `/product-{id}/` aggregations and `/items-{id}/` individual offers. Extract both.
- **Sidebar false positives**: `/items-` links appear in sidebar/footer. Filter by checking URL contains `/items-{number}/` (with trailing slash).
- **Sold out products**: Still listed but show "sold out" text. Include them in results — they indicate what was available.
- **Items per page resets on navigation**: Must re-select 400 on each new category page load.
- **Offer counts are approximate**: The "X Offers" count on search results may differ from actual offers on the category page.
- **localStorage is volatile**: Data accumulated in localStorage is lost if the tab is closed or navigated cross-origin. Dump results before closing tabs. Use the dump JS snippet after each crawl level — don't wait until the end. localStorage is same-origin scoped, so data from `z2u.com` pages is isolated from other domains.
