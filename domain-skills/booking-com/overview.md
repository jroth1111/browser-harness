# Booking.com — Skill Router

Use this skill for Booking.com public-property extraction and Booking.com
Extranet host workflows.

## Cold Start

1. If the URL is `https://admin.booking.com/` or the user is acting as a host,
   read `host_bookingcom.md`.
2. If the URL is `https://www.booking.com/` or the user needs public market,
   search, or guest-visible property data, read `scraping.md`.
3. Keep authenticated host downloads and receipts under ignored local state, not
   in reusable guidance. Suggested paths:
   `domain-skills/booking-com/.private-data/host-bookingcom/` for downloaded
   source files and
   `domain-skills/booking-com/.session-store/host-bookingcom/` for session
   manifests.

## Source Families

| Source family | Use | Auth posture | First file |
|---|---|---|---|
| `public_market` | Guest-visible search, property pages, sitemap discovery, public comps | Logged out or guest context | `scraping.md` |
| `host_private` | Extranet reservations, bookings, invoices, payout or finance documents across all properties | Logged-in host/co-host session | `host_bookingcom.md` |

## Guardrails

- Do not type credentials for the user. Open the Extranet in the user's browser
  profile and ask them to complete login, MFA, or account selection manually.
- Start host collection by enumerating all visible properties. A single selected
  property is not enough for portfolio data.
- Prefer first-party export or document-download surfaces over scraping rendered
  tables. Use UI/API extraction only to fill gaps left by exports.
- Record per-property coverage, empty states, skipped rows, and blocked
  surfaces in a receipt before claiming the portfolio is complete.
