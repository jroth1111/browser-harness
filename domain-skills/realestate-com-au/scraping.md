# realestate.com.au - Property Listing Extraction

Field-tested against Melbourne apartment sale and rental pages on 2026-04-27 using the browser harness.

## Quick summary

- Prefer real browser navigation with a persistent, headful Chrome profile for listing pages. `http_get()`, Lightpanda, and fresh headless Chrome can receive only a Kasada/KPSDK challenge shell.
- After `new_tab(url)` and `wait_for_load()`, call `wait_for_content()` before extraction. Treat `reason == "blocked"` as a backend capability failure, not as an empty property page.
- When the page is genuinely served, `document.body.innerText` contains the useful listing data in a stable, parseable order.
- Google result pages are a practical way to discover current `property-apartment-vic-*` listing IDs when address search pages hide the ID.
- For property-profile URLs under `/property/...`, browser navigation exposes off-market data, rent estimate, sales history, local market activity, and suburb price insights.
- Domain/building-profile pages may time out or render blank through the harness. Use realestate.com.au pages first, then fall back to Google snippets or browser-rendered Domain pages only when needed.

## Backend capability rule

Realestate.com.au uses Kasada/KPSDK protection. A backend that speaks CDP is not automatically capable of loading this site.

Observed on 2026-04-27:

| Backend | Result |
|---|---|
| Persistent headful Chrome profile | Can serve listing/profile content. Use this first. |
| Fresh `http_get()` | HTTP 429 with KPSDK headers and a tiny challenge document. |
| Fresh headless Chrome | Loads a tiny `window.KPSDK`/`/ips.js` document with empty body text. |
| Lightpanda nightly `1.0.0-nightly.5816+a578f4d6` | Same KPSDK challenge shell; not sufficient for listing extraction. |

Do not try to repair this with selector changes, longer sleeps, user-agent overrides, or `navigator.webdriver` patches. The listing HTML/JSON was not served, so there is no property data in the DOM to extract. Switch to a capable backend, usually the user's already-running headful Chrome profile, or a self-hosted Chromium-derived browser whose fingerprint/profile layer has already been validated for this domain.

## Robust headful session workflow

Once a headful Chrome profile has passed the REA challenge, the browser's same-domain cookies can be reused for direct HTTP fetches. This is the fastest robust path for bulk property/profile pages because it avoids rendering every page while still using the solved browser session.

```python
# Seed/refresh a real headful Chrome session, then HTTP-fetch with those cookies.
result = fetch_with_browser_session(
    "https://www.realestate.com.au/property-house-vic-tarneit-143160680",
    seed_url="https://www.realestate.com.au/property/l30-unit-3003-500-elizabeth-st-melbourne-vic-3000/",
    retries=1,
)
if not result["ok"]:
    raise RuntimeError(f"REA fetch failed: {result['reason']} {result['block']}")

html = result["text"]
exchange = extract_argonaut_exchange(html)
print(exchange.keys())
```

Notes:

- `fetch_with_browser_session()` records compact `attempts` evidence: fetch result, seed result, retry result.
- `http_get_browser_session()` and `fetch_with_browser_session()` filter cookies to the target domain. They do not send `realestate.com.au` cookies to `property.com.au`.
- This workflow does not make fresh Lightpanda or fresh headless Chrome pass the initial challenge. It reuses an already-valid browser session.
- If you need Lightpanda/headless for the rest of a workflow, use headful Chrome to seed/fetch REA HTML first, then pass the extracted data to the lightweight backend.
- On property-profile pages, `extract_argonaut_exchange(html)` commonly contains `resi-property_property-profile -> property_detail_data` with the parsed profile payload.

## Robust headless/Lightpanda workflow

For headless or Lightpanda backends, diagnose before extracting:

```python
diag = diagnose_url_capability(
    "https://www.realestate.com.au/property-house-vic-tarneit-143160680",
    min_text=500,
    timeout=20,
)
print(diag["backend"]["kind"], diag["reason"], diag["block"], diag["recommendation"])
```

Expected blocked result for weak backends:

```text
headless_chrome blocked {'blocked': True, 'kind': 'kasada_kpsdk', ...}
```

When this happens, do not continue with DOM selectors in that backend. Seed/fetch with a persistent headful Chrome profile, extract the Argonaut/text data, then hand the extracted data to the headless workflow if needed.

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
status = wait_for_content(min_text=500, timeout=20)
if not status["ok"]:
    raise RuntimeError(f"REA content unavailable: {status['reason']} {status.get('block')}")
text = status["text"]
print(text[:8000])
```

For quick diagnosis on a suspect backend:

```python
new_tab("https://www.realestate.com.au/property-house-vic-tarneit-143160680")
wait_for_load()
status = wait_for_content(min_text=500, timeout=20)
print(status["reason"], status["block"], status["url"], status["textLength"], status["html"][:300])
```

If this prints `blocked` with `kind: kasada_kpsdk`, stop using that backend for REA. The robust action is backend replacement, not DOM work.

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
- Lightpanda and fresh headless Chrome failures are backend capability failures for this domain. A CDP-compatible backend still needs enough real browser surface and session state to pass REA's server-side/browser challenge.

## Minimal comp workflow

1. Use Google with exact unit/address terms to discover current sale and rent listing IDs.
2. Open each realestate.com.au listing in a browser tab.
3. Extract `document.body.innerText`.
4. Record address, listing type, bed/bath/car, price/rent, availability, publish date, floor level, furnishing, and property ID.
5. Use property-profile routes only for historical sale, rent estimates, and suburb market context.
