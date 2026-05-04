# Food Delivery — Safety

Consent gates, rate limits, and anti-detection for Uber Eats and DoorDash automation.

## Consent gates

| Level | Behavior | When to use |
|---|---|---|
| **confirm** | Show full order summary including all fees, user confirms before placing | Default for all orders |
| **draft-only** | Show cart contents, user completes checkout manually in browser | New users, calibration period |

### Hard consent requirements (regardless of configured level)

- Placing any order (financial transaction).
- Applying promo codes or coupons.
- Modifying delivery address selection.
- Cancelling an order.
- Reordering from order history.

## Rate limiting

| Action | Min delay | Max delay | Distribution |
|---|---|---|---|
| Between restaurant page navigations | 2.0s | 5.0s | Uniform random |
| Between menu scrolls | 1.0s | 3.0s | Uniform random |
| After adding item to cart | 1.5s | 3.0s | Uniform random |
| Between search queries | 2.0s | 4.0s | Uniform random |

## Session limits

| Limit | Default | Max | Rationale |
|---|---|---|---|
| Restaurant pages per session | 50 | 100 | Avoid bot detection |
| Orders per session | 5 | 10 | Financial transaction safety |
| Session duration | 30 min | 60 min | Avoid prolonged bot sessions |

## Anti-detection countermeasures

- Variable timing between all actions (use ranges above, never fixed delays).
- Navigate to a restaurant page without immediately interacting — browse behavior.
- Do not rapidly cycle through restaurants in sequence.
- After 15-20 restaurant pages, take a short break (10-30s).
- Scripts handle this automatically via SafetyGate and random_delay().

## Block / CAPTCHA handling

Both platforms may trigger blocks mid-session. The scripts handle this:

```python
# DoorDash Cloudflare Turnstile block
src = sb.driver.page_source[:1000]
if "Verify you are human" in src or "access denied" in src.lower():
    sb.uc_gui_click_captcha()  # OS-level click, not CDP
    time.sleep(5)
    # Check if still blocked — if so, skip and continue
```

Manual escalation:
1. Stop immediately on any block that `uc_gui_click_captcha()` doesn't clear.
2. Do not attempt to bypass via CDP or JS injection — it won't work.
3. Use `--resume` checkpoint to continue from where the session stopped.
4. Re-run the cookie capture flow in overview.md if session is expired.

## Order audit trail

Log all order-related actions with: timestamp, platform, restaurant, items, subtotal, fees, total, and result (placed / failed / cancelled by user).

Store in `.private-data/order-log.md` (gitignored).

## Emergency stop

Halt immediately on:
- Any block or CAPTCHA page that doesn't clear with `uc_gui_click_captcha()`.
- Auth redirect (user logged out mid-session).
- Unexpected page state (checkout shows different items than expected).
- User says "stop" at any point.

No queued actions. Log where the session stopped. Use `--resume` to continue later.
