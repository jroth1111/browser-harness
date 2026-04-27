# Airbnb.com.au - Session Continuity

Use this for private Airbnb host work that spans multiple agent sessions.

General session-continuity rules live in
`interaction-skills/session-continuity.md`. This file keeps Airbnb-specific seed
URLs, source receipts, and local manifest fields.

## Local ignored store

This repo ignores domain-local session paths, including:

```text
domain-skills/airbnb/.session-store/
domain-skills/airbnb/.private-data/
```

Use `.session-store/` for Airbnb continuity manifests and capability receipts.
Use `.private-data/` only for temporary Airbnb exports the user explicitly wants
kept outside git, such as downloaded CSV/PDF/JSON reports during a task.

If the user explicitly wants to avoid logging in again from another browser
session, store the raw restorable auth bundle under
`.private-data/auth-state/`. This bundle contains live cookie/storage values and
must stay ignored, local, and permission-restricted. The `.session-store/`
manifest should only reference that private bundle and record verification
receipts.

The Airbnb auth bundle is for private host-only sources only. Do not restore it
for public guest-visible collection such as search results, public listing pages,
public reviews, public prices, amenities, rules, or Help/Resource Centre pages.
Those sources should be observed logged out unless the explicit task is to test
logged-in personalization.

Recommended layout:

```text
domain-skills/airbnb/.session-store/
  profiles/
    <profile-label>.json
  capability/
    <date>-<backend>-<source>.json
  manifests/
    <task-or-host-label>.json
```

These files are local working state, not portable skill content.

## `airbnb_session_manifest`

Session metadata. Do not store raw cookie values.

Fields:

- `session_manifest_id`
- `profile_label`
- `browser_backend`
- `cdp_endpoint_label`
- `airbnb_account_label`
- `logged_in_observed`
- `mfa_required_observed`
- `last_successful_private_url`
- `last_private_capture_at`
- `cookie_names`
- `cookie_domains`
- `local_storage_keys`
- `session_storage_keys`
- `capability_receipt_refs`
- `expires_or_recheck_after`
- `notes`

## Capability receipt

For each Airbnb source, save a compact receipt:

```json
{
  "source": "earnings_csv",
  "backend": "chromium",
  "profile_label": "host-main",
  "logged_in": true,
  "url_or_path_redacted": "https://www.airbnb.com.au/users/transaction_history",
  "observed_at": "2026-04-27T00:00:00Z",
  "ok": true,
  "fields_visible": ["gross_earnings", "host_service_fee", "net_pay"],
  "cookie_names": ["_airbed_session_id"],
  "download_available": true,
  "notes": "Do not store cookie values."
}
```

For public guest-visible receipts, `logged_in` should normally be `false`.
For private host-only receipts, `logged_in` should be `true` and the receipt
should identify the private source family being proven.

## Browser profile flow

Use this flow only for private host-only Airbnb work. Public guest-visible work
should start from a logged-out Lightpanda or fresh browser context and use
`public-market.md`.

1. Attach browser-harness to the user's normal Chrome profile.
2. Navigate to Airbnb host dashboard, hosting page, or another safe Airbnb page.
3. If login/MFA is required, ask the user to complete it.
4. Run `seed_browser_session()` against a safe Airbnb page.
5. Record cookie names/domains and source capability, not cookie values.
6. Use `fetch_with_browser_session()` only for same-domain authenticated fetches
   after the profile has loaded useful private content.
7. If a private restorable auth bundle is required, export it with
   `login_session.session_state(...)` into `.private-data/auth-state/` and verify
   it in a separate fresh browser profile/process.

Example:

```python
seed = seed_browser_session(
    "https://www.airbnb.com.au/hosting",
    min_text=500,
    timeout=30,
    close=False,
)
print(seed["ok"], seed["reason"], seed.get("cookieNames", []))
```

## Lightpanda and private data

Lightpanda should not be the primary backend for private Airbnb host pages unless
an explicit capability receipt proves the source works. It lacks the full Chrome
profile, rendering, and fingerprint surface. Use it for public sources and static
docs first; use headful Chrome for private authenticated exploration and exports.

Observed on 2026-04-27: Lightpanda could restore a saved Airbnb host auth bundle
and load these private host URLs when driven through `lightpanda_control.py` and
`login_session.restore_session_state_and_verify()`:

- `https://www.airbnb.com.au/hosting`
- `https://www.airbnb.com.au/hosting/listings`
- `https://www.airbnb.com.au/hosting/reservations`

The required cookie restore route was per-cookie `Network.setCookie`; Lightpanda
reported bulk cookie setters as unavailable for the saved bundle. Keep the
capability receipt under `.session-store/capability/` and recheck before using
Lightpanda for new private Airbnb source families.

## Airbnb seed URLs

Prefer safe, broad pages for session checks:

- `https://www.airbnb.com.au/hosting`
- `https://www.airbnb.com.au/hosting/listings`
- `https://www.airbnb.com.au/users/transaction_history`
- `https://www.airbnb.com.au/hosting/reservations`

Use the least sensitive page that proves the needed source is reachable.

## Continuity rules

- Reuse a profile label instead of rediscovering auth state each time.
- Recheck private session capability before collecting data.
- Do not treat a new tab in the same logged-in Chrome profile as a restore test.
  Verify restorable auth state by importing it into a separate fresh browser
  profile/process and loading authenticated host resources.
- If a private capture fails, distinguish expired auth, MFA, source layout
  change, backend limitation, and parser failure.
- Delete temporary exports from `.private-data/` after the user no longer needs
  them.
