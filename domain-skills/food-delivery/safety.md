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
- Take occasional screenshots without action — mimics reading.
- After 15-20 restaurant pages, consider a short break (10-30s).
- Do not repeatedly add and remove items from cart.

## Block / CAPTCHA handling

1. `wait_for_content()` returns `{block: true}` or `{ok: false}` → **stop immediately**.
2. `capture_screenshot()` to document the block state.
3. Notify user with the block reason.
4. Do not attempt to bypass CAPTCHA or WAF challenges automatically.
5. If user authorizes recovery, follow `interaction-skills/waf-bypass.md`.
6. Log the block event: platform, URL, reason, timestamp.

## Order audit trail

Log all order-related actions with: timestamp, platform, restaurant, items, subtotal, fees, total, and result (placed / failed / cancelled by user).

Store in `.private-data/order-log.md` (gitignored).

## Emergency stop

Halt immediately on:
- Any block or CAPTCHA page.
- Auth redirect (user logged out mid-session).
- Unexpected page state (checkout shows different items than expected).
- User says "stop" at any point.

No queued actions. Log where the session stopped.
