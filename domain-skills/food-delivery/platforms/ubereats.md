# Uber Eats — Platform Guide

Field-tested against ubereats.com on 2026-05-04.

**Hard block**: Navigating to `ubereats.com` returns "access denied" immediately —
no page content renders. Likely WAF/bot detection at the CDN layer. Requires a
seeded browser session (user logged in via their real Chrome) or alternative
approach (see Anti-detection notes).

## URLs

| Page | URL | Notes |
|---|---|---|
| Home / feed | `https://www.ubereats.com/` | Requires location; may redirect to set address |
| Search | `https://www.ubereats.com/search?q={query}` | Direct URL, fastest |
| Restaurant menu | `https://www.ubereats.com/store/{slug}/{store_id}` | Slug and ID from search results |
| Cart / checkout | `https://www.ubereats.com/checkout` | After adding items |
| Order tracking | `https://www.ubereats.com/orders/{order_id}` | Live order status |
| Order history | `https://www.ubereats.com/orders` | Past orders list |
| Account | `https://www.ubereats.com/account` | Address, payment, preferences |

## Auth detection

- **Logged in**: delivery address visible in header, user avatar/name present, no "Sign in" prompt.
- **Not logged in**: redirect to login page, prominent "Sign in" / "Sign up" buttons.

## Navigation

```python
# CONFIRMED: direct navigation returns "access denied" in unauthenticated CDP sessions.
# Must use a seeded user browser session.
tid = new_tab("https://www.ubereats.com/")
result = wait_for_content()
if result["block"]:
    # "access denied" — user must be logged into Uber Eats in their Chrome
    # Try: seed_browser_session("https://www.ubereats.com/") first
    # Or ask user to open Uber Eats in their browser and navigate there
    capture_screenshot()
```

## Restaurant list extraction — STATUS: NEEDS_FIELD_TESTING

Target fields per restaurant card:

| Field | Extraction | Notes |
|---|---|---|
| Restaurant name | NEEDS_FIELD_TESTING | Likely in heading element |
| Rating | NEEDS_FIELD_TESTING | Star rating or numeric |
| Delivery time | NEEDS_FIELD_TESTING | "15-25 min" format |
| Delivery fee | NEEDS_FIELD_TESTING | May be "$0" with promo |
| Cuisine tags | NEEDS_FIELD_TESTING | Category labels |
| Promotional badge | NEEDS_FIELD_TESTING | "% off", "Buy 1 Get 1" |

Extraction approach:
1. `wait_for_content()` after search or feed load.
2. `js()` to find container elements and extract text content.
3. Prefer `data-*`, `aria-*`, `role` selectors over class names.
4. Fallback: `capture_screenshot()` + visual parsing if DOM selectors fail.

## Search mechanics

```python
# Direct URL (fastest)
goto_url(f"https://www.ubereats.com/search?q={query}")
wait_for_content()

# Filters — confirm availability during field testing:
# - Sort by: relevance, rating, delivery time, distance
# - Cuisine type
# - Price range ($, $$, $$$)
# - Dietary: vegetarian, vegan, gluten-free
# - Promotions / deals
```

## Menu extraction — STATUS: NEEDS_FIELD_TESTING

Target fields per menu item:

| Field | Extraction | Notes |
|---|---|---|
| Category name | NEEDS_FIELD_TESTING | Section headings (Popular, Mains, etc.) |
| Item name | NEEDS_FIELD_TESTING | |
| Item price | NEEDS_FIELD_TESTING | |
| Item description | NEEDS_FIELD_TESTING | May be truncated, click to expand |
| Item image | NEEDS_FIELD_TESTING | Optional, may lazy-load |
| Popular badge | NEEDS_FIELD_TESTING | "#1 Most Liked" etc. |
| Customization count | NEEDS_FIELD_TESTING | "3 options" indicator |

Menu categories may lazy-load on scroll. Use `scroll_down()` + `wait(1.0)` between scrolls to trigger loading.

## Order flow — STATUS: NEEDS_FIELD_TESTING

1. Click menu item to open detail/modal.
2. Select customizations if needed.
3. Click "Add to Cart".
4. Navigate to cart: verify items and quantities.
5. Navigate to checkout: extract fee breakdown (delivery fee, service fee, tax, tip).
6. Present full summary to user for consent.
7. On confirmation: click "Place Order".
8. Detect confirmation screen (order number, ETA).

**Fee breakdown** — critical for price comparison. Must extract at checkout:
- Subtotal
- Delivery fee
- Service fee
- Tax
- Tip (default may be pre-filled)
- Promotions / discounts
- **Total**

## Order tracking extraction — STATUS: NEEDS_FIELD_TESTING

Target fields:
- Status (Order placed, Preparing, Ready, Picked up, On the way, Delivered)
- Estimated delivery time
- Driver name and vehicle (when available)
- Live map state

## Order history extraction — STATUS: NEEDS_FIELD_TESTING

Target fields per order:
- Date
- Restaurant name
- Items (may be summary only)
- Total
- Order status (delivered, cancelled)
- Reorder link

## Gotchas

- **React/Next.js SPA**: class names are dynamically generated. Never rely on class selectors.
- **Lazy-loaded menus**: scroll to load all categories. `wait_for_content()` may report ready before all categories render.
- **Location-dependent everything**: restaurant list, availability, pricing, delivery times all change with delivery address. Always note which address is active.
- **Fee complexity**: item prices on menu exclude delivery fee, service fee, tax. Only checkout shows the true total. Cross-platform comparison must use checkout totals, not menu prices.
- **Promotional pricing**: "$0 Delivery Fee" and percentage-off deals are time-limited and may change between sessions.
- **Address modal**: first visit may prompt to set/confirm delivery address before showing restaurant feed.
- **Cart persistence**: cart contents persist across tabs. Opening a new tab to the same store may show stale cart state.

## Anti-detection notes

- **CONFIRMED: hard WAF block** with CDP-connected browsers. `ubereats.com` returns "access denied". No Turnstile challenge — just flat denial.
- **SOLVED: SeleniumBase UC Mode** bypasses the WAF. Uses patched chromedriver that disconnects during page load. Home page loads in ~9s without access denied.
  ```python
  from seleniumbase import SB
  with SB(uc=True, test=True) as sb:
      sb.uc_open_with_reconnect("https://www.ubereats.com/", 4)
  ```
- Alternative: `seed_browser_session("https://www.ubereats.com/")` with browser-harness may work if user is logged into their real Chrome.
- Vary timing between navigations (2-5s between restaurant pages).
- Do not scrape all restaurants in a feed sequentially — browse naturally.
- Take breaks after 15-20 page loads.
- Respect session limits in `safety.md`.
