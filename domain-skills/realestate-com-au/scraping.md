# realestate.com.au - Property Listing Extraction

Field-tested against Melbourne apartment sale and rental pages on 2026-04-27 using the browser harness.

## Quick summary

- Prefer real browser navigation for listing pages. `http_get()` can return HTTP 429 for direct listing URLs even when the same URL loads in Chrome.
- After `new_tab(url)` and `wait_for_load()`, `document.body.innerText` contains the useful listing data in a stable, parseable order.
- Google result pages are a practical way to discover current `property-apartment-vic-*` listing IDs when address search pages hide the ID.
- For property-profile URLs under `/property/...`, browser navigation exposes off-market data, rent estimate, sales history, local market activity, and suburb price insights.
- Domain/building-profile pages may time out or render blank through the harness. Use realestate.com.au pages first, then fall back to Google snippets or browser-rendered Domain pages only when needed.

## Listing URL patterns

Common current listing pattern:

```text
https://www.realestate.com.au/property-apartment-vic-melbourne-{listing_id}
```

Common property profile pattern:

```text
https://www.realestate.com.au/property/{slug-address}
```

Example address-profile route:

```text
https://www.realestate.com.au/property/l30-unit-3003-500-elizabeth-st-melbourne-vic-3000
```

Search pages are useful for current listing discovery:

```text
https://www.google.com/search?q=1705%2F500+Elizabeth+Street+Melbourne+realestate.com.au
https://www.google.com/search?q=site:realestate.com.au/property-apartment-vic-melbourne+3405/500+Elizabeth+Street+Melbourne
```

## Browser extraction pattern

```python
new_tab("https://www.google.com/search?q=1705%2F500+Elizabeth+Street+Melbourne+realestate.com.au")
wait_for_load()
links = js("""
Array.from(document.querySelectorAll('a'))
  .map(a => ({text: a.innerText, href: a.href}))
  .filter(x => x.href.includes('realestate.com.au/property-apartment'))
  .slice(0, 5)
""")

new_tab(links[0]["href"])
wait_for_load()
text = js("document.body.innerText")
print(text[:8000])
```

## Fields visible in `body.innerText`

Sale listings commonly include:

| Field | Notes |
|---|---|
| Address | Near top, after `Buy / VIC / suburb / property type` breadcrumbs |
| Bed/bath/car icons | Rendered as separated lines, for example `3`, `2`, `1` |
| Price guide | For example `$675,000-$725,000` |
| Inspection times | Date and time lines if current |
| Publish date | In the description heading, for example `DATE PUBLISHED: 09 APR 2026` |
| Description | Free text, good for building name, floor level, view, furnishing, amenities |
| Agent and agency | Near lower page |
| Property ID | Useful stable reference |
| Page views | Useful demand signal when visible |

Rental listings commonly include:

| Field | Notes |
|---|---|
| Weekly rent | For example `$1,070 per week` |
| Bond | For example `Bond $6,420` |
| Availability | For example `Available now` |
| Furnishing | Often only in description or AI highlights |
| Property features | Balcony, robes, ensuites, floorboards, etc. |
| Agent and agency | Near lower page |
| Property ID | Useful stable reference |
| Page views | Useful demand signal when visible |

Property-profile pages commonly include:

| Field | Notes |
|---|---|
| Current/off-market status | For example `Off market` |
| Bed/bath/car | Reliable for high-level comp filtering |
| Rental income estimate | Includes confidence where available |
| Estimated yield | Compare against suburb average |
| Sales history | Last sold price and date |
| Local market activity | Counts for sale, rent, recently sold |
| Suburb price insights | Median price and growth for the selected bedroom/property type |

## Traps

- Do not rely on `http_get()` for listing pages. Direct listing fetches can 429 while browser navigation succeeds.
- The `page_info()` helper may show blank `url` and `title` even when the page is loaded. Verify with `document.documentElement.outerHTML` or `document.body.innerText`.
- Search result snippets can be stale, but they are good for finding listing IDs. Always open the listing page to verify current price and details.
- Bed/bath/car icons are plain text in `innerText`; preserve nearby context so a missing car space is not silently inferred as zero or one.
- For sale-value analysis, distinguish current sale listings from off-market property profiles. Off-market profiles can expose old sold prices that are not current asking prices.
- Lightpanda nightly `1.0.0-nightly.5816+a578f4d6` is not sufficient for listing extraction as of 2026-04-27. It loads a small KPSDK challenge document (`window.KPSDK`, `/ips.js?...`) with empty body text instead of the REA listing content.

## Minimal comp workflow

1. Use Google with exact unit/address terms to discover current sale and rent listing IDs.
2. Open each realestate.com.au listing in a browser tab.
3. Extract `document.body.innerText`.
4. Record address, listing type, bed/bath/car, price/rent, availability, publish date, floor level, furnishing, and property ID.
5. Use property-profile routes only for historical sale, rent estimates, and suburb market context.
