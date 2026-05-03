# Food Delivery — Overview

Automated food delivery automation for Uber Eats and DoorDash via browser-harness CDP.
Browse restaurants, extract menus, compare prices across platforms, place orders, and track deliveries.

## Prerequisites

- **Anti-bot bypass required**: Both platforms block CDP-connected browsers. Use SeleniumBase UC Mode (`uc=True`) to bypass Cloudflare Turnstile (DoorDash) and WAF (Uber Eats). See "Accessing platforms" below.
- User must be logged into the target platform. The skill does not handle login credentials — ask the user to log in manually if needed.
- For placing orders: user must have a valid delivery address and payment method configured on the platform.
- For cross-platform comparison: user must be logged into both platforms (separate tabs).

## Cold-start sequence

1. Identify platform (Uber Eats / DoorDash). Read `platforms/<platform>.md`.
2. Identify user intent. Use the intent router below.
3. If cross-platform comparison, read both platform files.
4. Execute.

## Intent router

| User intent | Read first | When to escalate |
|---|---|---|
| Browse restaurants near me | `platforms/<platform>.md` restaurant list section | `safety.md` if block detected |
| Search for a specific restaurant or cuisine | `platforms/<platform>.md` search section | Comparison workflow below if user wants both platforms |
| View restaurant menu / menu items | `platforms/<platform>.md` menu extraction section | — |
| Compare prices across platforms | Both platform files, comparison workflow below | — |
| Place an order | `platforms/<platform>.md` order flow section | `safety.md` (order consent gate required) |
| Track delivery / order status | `platforms/<platform>.md` tracking section | — |
| View order history / past receipts | `platforms/<platform>.md` order history section | — |
| Cancel or modify an order | `platforms/<platform>.md` order management section | `safety.md` (modification consent gate) |
| Safety concern, rate limit, block | `safety.md` | Stop and ask user |

## Cross-platform comparison workflow

1. Open both platforms in separate tabs.
2. For each platform: navigate to the same restaurant (or search for the same cuisine).
3. Extract: item name, item price, delivery fee, service fee, taxes, total, estimated delivery time, available promotions.
4. Present side-by-side comparison.

Caveats:
- Restaurant availability and pricing may differ across platforms.
- Same-named restaurants may not be the same physical location.
- Fees (delivery, service) may only be visible at checkout. Prioritize checkout-level totals for accurate comparison.
- Prices are point-in-time snapshots; promotional pricing is time-limited.

## Key invariants

- Never place an order without explicit user confirmation (hard consent gate). See `safety.md`.
- Never modify or cancel an order without explicit user request.
- Never handle login credentials or payment information.
- Never apply promo codes or coupons without explicit user request.
- Stop on any block, CAPTCHA, auth redirect, or suspicious page state.
- Human-like timing between all automated actions. See `safety.md`.
- Delivery addresses and payment details must be pre-configured by the user on the platform.
- All prices are location-dependent. Note the active delivery address in any output.

## File map

```
overview.md              <- you are here
safety.md                <- consent gates, rate limits, anti-detection
platforms/ubereats.md    <- Uber Eats specific selectors and flows
platforms/doordash.md    <- DoorDash specific selectors and flows
```

## Accessing platforms

Both platforms have strong anti-bot protection that detects CDP connections. Browser-harness and MCP DevTools tools **cannot access these sites directly**.

**Use SeleniumBase UC Mode** (installed in browser-harness `.venv`):

```python
from seleniumbase import SB

with SB(uc=True, test=True) as sb:
    sb.uc_open_with_reconnect("https://www.doordash.com/", 4)
    # If full-page Cloudflare challenge appears:
    sb.uc_gui_click_captcha()  # OS-level click, not CDP

    # For Uber Eats:
    sb.uc_open_with_reconnect("https://www.ubereats.com/", 4)
```

Run via: `.venv/bin/python3 <<'PY' ... PY`

UC Mode works by disconnecting the WebDriver during the challenge window and using a patched chromedriver that removes automation flags. OS-level `pyautogui` clicks bypass the screenX/screenY detection bug in cross-origin iframes.

## Browser automation approach

This skill runs through the Claude/browser-harness conversation loop — no standalone scripts.

1. Browser produces artifact (`capture_screenshot()`, `js()`)
2. Claude reads artifact (multimodal: screenshots + extracted text)
3. Claude decides next action
4. User consents for financial actions (per `safety.md` consent gates)
5. Claude issues browser command (`click_at_xy`, `type_text`)

Use `capture_screenshot()` + coordinate clicks as the primary interaction method, per harness conventions. Drop to DOM/selector work only when the target has no visible geometry.

`wait_for_content()` after each navigation — check `block` field before running extraction JS.
