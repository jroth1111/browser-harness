# Food Delivery — Overview

Automated food delivery for Uber Eats and DoorDash via SeleniumBase UC Mode.
Browse restaurants, extract menus, compare prices across platforms, place orders, and track deliveries.

## Prerequisites

- **Anti-bot bypass required**: Both platforms block CDP-connected browsers. Use SeleniumBase UC Mode (`uc=True`) to bypass Cloudflare Turnstile (DoorDash) and WAF (Uber Eats). See "Accessing platforms" below.
- User must be logged into the target platform. The skill does not handle login credentials — use the cookie capture flow below for first-time setup.
- For placing orders: user must have a valid delivery address and payment method configured on the platform.
- For cross-platform comparison: user must be logged into both platforms (separate tabs).

## Cold-start sequence

1. Check if cookies exist in `.private-data/`. If not, run the cookie capture flow below.
2. Identify platform (Uber Eats / DoorDash). Read `platforms/<platform>.md`.
3. Identify user intent. Use the intent router below.
4. If cross-platform comparison, read both platform files.
5. Execute.

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
.private-data/           <- session cookies (gitignored, never commit)
  doordash_cookies.json
  ubereats_cookies.json
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

## Session management

### First-time setup: capture cookies

Cookies are stored in `.private-data/` (gitignored). On first use, capture the user's login session:

```python
from seleniumbase import SB
import json, time, os

with SB(uc=True, test=True) as sb:
    # --- DoorDash ---
    sb.uc_open_with_reconnect("https://www.doordash.com/", 4)
    time.sleep(2)
    # Ask user to log in manually in the browser window
    # Wait for signal file (since input() doesn't work from heredoc):
    #   user runs: touch /tmp/dd_done
    while not os.path.exists("/tmp/dd_done"):
        time.sleep(1)
    os.remove("/tmp/dd_done")

    cookies = sb.driver.get_cookies()
    with open("domain-skills/food-delivery/.private-data/doordash_cookies.json", "w") as f:
        json.dump(cookies, f)

    # --- Uber Eats ---
    sb.uc_open_with_reconnect("https://www.ubereats.com/", 4)
    time.sleep(2)
    # Ask user to log in, then: touch /tmp/ue_done
    while not os.path.exists("/tmp/ue_done"):
        time.sleep(1)
    os.remove("/tmp/ue_done")

    cookies = sb.driver.get_cookies()
    with open("domain-skills/food-delivery/.private-data/ubereats_cookies.json", "w") as f:
        json.dump(cookies, f)
```

### Restoring a session

Load saved cookies to skip login on subsequent runs:

```python
from seleniumbase import SB
import json, time

with SB(uc=True, test=True) as sb:
    # Open platform first (must be on-domain to set cookies)
    sb.uc_open_with_reconnect("https://www.doordash.com/", 4)
    time.sleep(2)

    # Inject saved cookies
    with open("domain-skills/food-delivery/.private-data/doordash_cookies.json") as f:
        for c in json.load(f):
            try:
                sb.driver.add_cookie(c)
            except:
                pass  # domain mismatch is expected for some cookies

    # Reload with authenticated session
    sb.driver.refresh()
    time.sleep(3)
    # Now logged in — proceed with automation
```

### Cookie expiry

- DoorDash `cf_clearance` cookie expires after ~30 minutes. Other session cookies may last longer.
- Uber Eats session cookies typically last days to weeks.
- If a restored session shows logged-out state, re-run the capture flow.

### Cookie storage

- Location: `domain-skills/food-delivery/.private-data/*.json`
- Gitignored — never committed to the repo.
- Contains session tokens — treat as sensitive. Do not log or display cookie values.

## Browser automation approach

This skill runs through the Claude/browser-harness conversation loop — no standalone scripts.

1. Browser produces artifact (`capture_screenshot()`, `js()`)
2. Claude reads artifact (multimodal: screenshots + extracted text)
3. Claude decides next action
4. User consents for financial actions (per `safety.md` consent gates)
5. Claude issues browser command (`click_at_xy`, `type_text`)

Use `capture_screenshot()` + coordinate clicks as the primary interaction method, per harness conventions. Drop to DOM/selector work only when the target has no visible geometry.

`wait_for_content()` after each navigation — check `block` field before running extraction JS.
