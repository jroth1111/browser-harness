# Uber Eats — Platform Guide

Field-tested against ubereats.com on 2026-05-04 (Melbourne, AU).

**WAF hard block** with standard CDP browsers — "access denied" immediately, no page content. Use the food-delivery Patchright stealth helper.

## Access

```python
from lib.stealth_session import create_stealth_session

s = create_stealth_session("ubereats")
try:
    print(s.js("document.title"))
finally:
    s.close()
```

## URLs

| Page | URL | Notes |
|---|---|---|
| Home | `https://www.ubereats.com/` | May prompt for delivery address |
| Browse all | `https://www.ubereats.com/search?q=food` | Returns all options |
| Search | `https://www.ubereats.com/search?q={query}` | Query-specific |
| Store page | `https://www.ubereats.com/store/{slug}/{store_id}` | Slug + ID |
| Checkout | `https://www.ubereats.com/checkout` | Fee breakdown |
| Orders | `https://www.ubereats.com/orders` | Order history |

## Restaurant enumeration — CONFIRMED WORKING

Browse-all with `"food"` query. Results saturate quickly (82 restaurants in 37s, 0 estimated unseen — likely all available for the delivery area).

### Store ID format

Uber Eats uses `/store/{slug}/{store_id}` where store_id is a base64-like string:
```
https://www.ubereats.com/store/nandos-elizabeth-st/F5sh58oFUZq6l-ps6Ejzww
```

Strip query params before extracting (some links append `?sc=SEARCH_SUGGESTION`).

### Name parsing

Card text appends cuisine tags: `"Bravas! Mexican FoodMexican"`. Strip trailing cuisine keywords. Name fill rate: 99%.

Rating, delivery fee, and delivery time were 0% fill in testing — Uber Eats card text may not include these in the same format as DoorDash.

## Menu extraction — NOT YET TESTED

Uber Eats menu pages need the same exploration as DoorDash to determine the best extraction method. Likely approaches:
1. Check for embedded JSON/React data in page source (similar to DoorDash's `__next_f`)
2. DOM scraping with category headers + item containers
3. DOM has `button[aria-label]` for items and `h2/h3` for categories

The `extract_menus.py` script has a DOM fallback (`extract_menu_from_dom`) that should work for Uber Eats as a starting point.

## Auth detection

- Logged in: "Order food" in title, no "Sign in" in first 3000 chars of source
- Not logged in: redirect to login, "Sign in" / "Sign up" visible

## Gotchas

- **Search saturates fast**: only ~82 restaurants returned for "food" query in Melbourne AU. May need multiple queries for full coverage in larger cities.
- **No public API**: Uber Eats uses POST-based APIs with CSRF tokens at `/_p/api/getSearchFeedV1`, `getSearchHomeV2`, etc. DOM extraction confirmed as the path.
- **Location-dependent**: everything varies by delivery address.
- **Session cookies last longer** than DoorDash — days to weeks.
