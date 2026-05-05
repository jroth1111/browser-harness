# DoorDash — Platform Guide

Field-tested against doordash.com on 2026-05-04 (Melbourne, AU).

**Cloudflare Turnstile** on all pages. CDP browsers detected via screenX/screenY bug, Runtime.enable side effects, debugger timing. Only SeleniumBase UC Mode bypasses.

## Access

```python
from seleniumbase import SB
import json, time

with SB(uc=True, test=True) as sb:
    sb.uc_open_with_reconnect("https://www.doordash.com/", 4)
    time.sleep(2)
    # Restore session (see overview.md for first-time setup)
    for c in json.load(open(".private-data/doordash_cookies.json")):
        try: sb.driver.add_cookie(c)
        except: pass
    sb.driver.refresh()
    time.sleep(3)
    # If Cloudflare challenge: sb.uc_gui_click_captcha()
```

## URLs

| Page | URL | Notes |
|---|---|---|
| Home | `https://www.doordash.com/` | Cloudflare Turnstile present |
| Browse all | `https://www.doordash.com/search/store/food` | Single query covers all categories |
| Search | `https://www.doordash.com/search/store/{query}` | Cuisine-specific search |
| Store page | `https://www.doordash.com/store/{store_id}` | Numeric ID only, no slug needed |
| Checkout | `https://www.doordash.com/checkout` | Fee breakdown here |
| Orders | `https://www.doordash.com/orders/` | Order history |

## Restaurant enumeration — CONFIRMED WORKING

**Browse-all approach**: Single `"food"` query covers restaurants, groceries, convenience, retail — everything for the delivery address. Scroll through infinite results until saturation.

Results: 743 unique restaurants in 216s. 100% name fill, 100% delivery_fee, 60% rating, 47% delivery_time.

### How it works

1. Navigate to `https://www.doordash.com/search/store/food`
2. Extract all `<a href*="/store/">` links from the page
3. Dedup by store_id (multiple links per card — keep the one with most text)
4. Parse card text: name before first `•` or rating, strip trailing distance/rating
5. Scroll down, repeat until 8 consecutive scrolls yield 0 new restaurants

### Store ID extraction (CONFIRMED regex patterns)

DoorDash URLs use `/store/{numeric_id}` format (no slug):
```javascript
// Primary: /store/12345
href.match(/\/store\/(\d+)$/)
// Fallback: /store/slug-12345
href.match(/\/store\/([\w-]+?)-(\d+)$/)
```

Strip query params from href before matching (`href.split('?')[0]`).

### Name parsing gotchas

Card text is concatenated: `"A25 Pizzeria4.5(200+)•1.4 mi•25 min•$0 delivery"`.
- Split on `•` or `|`, take first segment
- Strip trailing `\d+\.\d+\s*\(\d+` (rating like `4.5(200+)`)
- Strip trailing `\d+\.\d+\s*(mi|km)` (distance like `1.4 mi`)
- Name fill rate is 100% after these cleanups

## Menu extraction — CONFIRMED WORKING

**Primary method: Parse Next.js embedded data from page source.** No DOM scraping needed — all menu data is in `self.__next_f.push()` script tags as `StorePageCarouselItem` objects.

Results: 100% fill on name, price, description, image. ~25 items per restaurant. ~13s per restaurant (no scrolling).

### Data structure

DoorDash is a Next.js SPA. All menu data is server-rendered into script tags:

```javascript
self.__next_f.push([1,"..."])
```

Inside one ~800KB script, items appear as `StorePageCarouselItem` objects:

```json
{
  "__typename": "StorePageCarouselItem",
  "id": "24985850677",
  "name": "Butter Chicken",
  "description": "Chicken pieces roasted in tandoor & simmered in tomato...",
  "displayPrice": "A$22.50",
  "displayStrikethroughPrice": "",
  "imgUrl": "https://img.cdn4dd.com/cdn-cgi/image/..."
}
```

### Extraction approach

1. Get `sb.driver.page_source`
2. Find all `self.__next_f.push([1,"..."])` calls via regex
3. Decode each with `raw.encode("utf-8").decode("unicode_escape")`
4. Find the script containing `"StorePageCarouselItem"` (typically ~800KB)
5. Extract items via regex: `"__typename":"StorePageCarouselItem","id":"...","name":"...","description":"...","displayPrice":"...","imgUrl":"..."`
6. Dedup by item id

### Why not DOM scraping

- DoorDash menu cards show **item names only** (H3 elements), no prices
- Prices only appear in item detail modals (requires clicking each item)
- Category headers are H2 elements (Combos, Starters, Classic Curries, etc.)
- The Next.js data has everything in one parse — name, price, description, image URL

### Why not React internals

- `document.getElementById('__next')` returns null (Next.js 14 app router)
- React fiber tree walk found 0 items with props matching menu data
- The data is only in the raw page source, not accessible via JS runtime

## Auth detection

- Logged in: no "Sign In" in first 2000 chars of source, "DoorDash" in title
- Not logged in: login modal with iframe to `identity.doordash.com/auth`

## Store page DOM structure (for reference)

```
H2  Category headers: "Featured Items", "Most Ordered", "Combos", "Starters", ...
H3  Individual item names: "Butter Chicken", "Lamb Seekh Kebab", ...
    (NO prices visible in card listing — only in detail modals)
button[aria-label]  Navigation buttons, NOT menu items
```

Class names are styled-components hashes (`sc-eAyhxF cMeCVt`) — completely unreliable as selectors.

## Gotchas

- **No public API**: DoorDash uses private GraphQL at `/graphql/` with CSRF tokens. DOM/Next.js extraction is the only path.
- **DashPass pricing**: delivery fees differ for subscribers. Note which mode is active.
- **Required customizations**: adding items to cart forces selection of required options.
- **Fees at checkout only**: menu prices don't include delivery/service fees.
- **cf_clearance expires ~30min**: long extraction runs need cookie re-harvesting. Scripts handle this via `--resume` checkpointing.
- **Search result cap**: "food" query returns ~750-800 restaurants before saturation. Chao1 estimator suggests ~2000+ unseen — DoorDash likely caps results.
- **Location-dependent**: all data is for the delivery address in the user's account (Melbourne AU in testing).
