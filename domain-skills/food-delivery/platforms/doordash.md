# DoorDash — Platform Guide

Field-testing status: PENDING. Selectors and URL patterns below are anticipated
and must be confirmed during first live session.

## URLs

| Page | URL | Notes |
|---|---|---|
| Home / feed | `https://www.doordash.com/` | Requires location; may prompt for address |
| Search | `https://www.doordash.com/search/store/{query}` | Direct URL (pattern to confirm) |
| Restaurant menu | `https://www.doordash.com/store/{restaurant-slug}-{store_id}` | Slug + numeric ID |
| Cart / checkout | `https://www.doordash.com/checkout` | After adding items |
| Order tracking | `https://www.doordash.com/orders/{order_id}/track` | Live order status |
| Order history | `https://www.doordash.com/orders` | Past orders list |
| Account | `https://www.doordash.com/account` | Address, payment, DashPass |

## Auth detection

- **Logged in**: delivery address in header, user avatar present, no "Sign in" prompt.
- **Not logged in**: "Sign In" / "Sign Up" buttons prominent, may redirect to auth wall.
- **DashPass indicator**: DashPass logo or badge visible when subscribed (affects pricing display).

## Navigation

```python
tid = new_tab("https://www.doordash.com/")
result = wait_for_content()
if result["block"]:
    capture_screenshot()
    # stop and notify user
```

## Restaurant list extraction — STATUS: NEEDS_FIELD_TESTING

Target fields per restaurant card:

| Field | Extraction | Notes |
|---|---|---|
| Restaurant name | NEEDS_FIELD_TESTING | |
| Rating | NEEDS_FIELD_TESTING | Numeric + star count |
| Delivery time | NEEDS_FIELD_TESTING | "20-35 min" format |
| Delivery fee | NEEDS_FIELD_TESTING | "$2.99" or "Free" with DashPass |
| Cuisine tags | NEEDS_FIELD_TESTING | |
| DashPass badge | NEEDS_FIELD_TESTING | "$0 delivery" indicator for subscribers |
| Promotional badge | NEEDS_FIELD_TESTING | "% off", deals |

Extraction approach:
1. `wait_for_content()` after search or feed load.
2. `js()` to find container elements and extract text content.
3. Prefer `data-*`, `aria-*`, `role` selectors over class names.
4. Fallback: `capture_screenshot()` + visual parsing if DOM selectors fail.

## Search mechanics

```python
# Direct URL (pattern to confirm during field testing)
goto_url(f"https://www.doordash.com/search/store/{query}")
wait_for_content()

# Filters — confirm availability during field testing:
# - Sort by: recommended, rating, delivery time, distance, popularity
# - Cuisine type
# - Price range ($, $$, $$$, $$$$)
# - Dietary: vegetarian, vegan, gluten-free
# - DashPass eligible
# - Offers / deals / free delivery
# - Pickup vs delivery toggle
```

## Menu extraction — STATUS: NEEDS_FIELD_TESTING

Target fields per menu item:

| Field | Extraction | Notes |
|---|---|---|
| Category name | NEEDS_FIELD_TESTING | Section headings (Popular Items, Mains, Sides, etc.) |
| Item name | NEEDS_FIELD_TESTING | |
| Item price | NEEDS_FIELD_TESTING | |
| Item description | NEEDS_FIELD_TESTING | May be truncated |
| Item image | NEEDS_FIELD_TESTING | Optional |
| Popular badge | NEEDS_FIELD_TESTING | "Most Ordered" etc. |
| Customization count | NEEDS_FIELD_TESTING | "Required: choose 1" etc. |

DoorDash menu items often open a customization modal/popup when clicked.
Items may be grouped under collapsible category headers.

## Order flow — STATUS: NEEDS_FIELD_TESTING

1. Click menu item to open detail modal.
2. Select required customizations ( DoorDash enforces "required choice" selections).
3. Adjust quantity if needed.
4. Click "Add to Cart" or "Add Item".
5. Navigate to cart: verify items, quantities, and special instructions.
6. Navigate to checkout: extract full fee breakdown.
7. Present full summary to user for consent.
8. On confirmation: click "Place Order".
9. Detect confirmation screen.

**Fee breakdown** — critical for price comparison. Must extract at checkout:
- Subtotal
- Delivery fee (different for DashPass vs non-DashPass)
- Service fee
- Regulatory fees (may appear)
- Tax
- Tip (default pre-filled, often 15-20%)
- Promotions / DashPass savings
- **Total**

## Order tracking extraction — STATUS: NEEDS_FIELD_TESTING

Target fields:
- Status (Order confirmed, Preparing, Picked up, On the way, Delivered)
- Estimated delivery time
- Driver name, photo, vehicle (when available)
- Live map state
- "Contact driver" / "Contact support" options

## Order history extraction — STATUS: NEEDS_FIELD_TESTING

Target fields per order:
- Date
- Restaurant name
- Items (summary or full list)
- Total
- Order status (delivered, cancelled)
- Reorder button
- Receipt link

## Gotchas

- **React SPA with obfuscated classes**: same as Uber Eats — never rely on class selectors. Use `data-*`, `aria-*`, `role`, or structural relationships.
- **DashPass pricing**: delivery fees and service fees differ between DashPass and non-DashPass users. The skill must detect which mode is active and note it in comparisons.
- **Required customizations**: DoorDash forces selection of required options (e.g., "Choose your protein") before adding to cart. The modal blocks the add button until selections are complete.
- **Store slug format**: URL pattern uses `{name}-{store_id}`. The slug may change if the restaurant updates its name.
- **Pickup vs delivery toggle**: DoorDash defaults to delivery but supports pickup. The toggle is prominent and easy to misclick.
- **Address prompt**: first visit prompts for delivery address. The feed is empty until an address is set.
- **Fees at checkout only**: menu prices don't include delivery/service fees. Comparison must use checkout totals.
- **Double-check DashPass detection**: DashPass-eligible restaurants show "$0 delivery" but only for subscribers. Non-subscribers see the regular fee.

## Anti-detection notes

- Same principles as Uber Eats: variable timing, natural browsing patterns, session limits.
- DoorDash has been known to use PerimeterX bot detection.
- If `wait_for_content()` reports a block, follow `safety.md` and `interaction-skills/waf-bypass.md`.
- Respect session limits in `safety.md`.
