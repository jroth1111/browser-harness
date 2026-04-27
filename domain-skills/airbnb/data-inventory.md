# Airbnb.com.au - Data Inventory and Primitives

Use this as the registry of Airbnb data primitives. A primitive is a small,
source-grounded fact that can be recombined later for pricing, conversion,
operations, quality, or portfolio decisions.

General primitive discovery rules live in
`interaction-skills/data-source-exploration.md`. This file is Airbnb-specific:
source names, Airbnb surfaces, and Airbnb examples belong here.

## Primitive design

Each primitive should carry:

- source name
- public/private scope
- source URL, file, or navigation path
- capture method
- backend suitability
- account/listing/date scope
- `observed_at`
- confidence
- privacy class
- target schema

For current-state work, every primitive should also carry `state_run_id` when it
belongs to a market, competitor, or own-listing state run from
`workflows-current-state.md`.

## Current-state primitive groups

| State group | Primitive families | Auth posture | Target files |
|---|---|---|---|
| Market demand state | events, holidays, weather, transport, regulation/supply signals | Public/external | `schema-demand-context.md` |
| Competitor market state | public search runs, search cards, comp prices, comp availability | Logged out | `schema-public-market.md` |
| Competitor listing state | comp amenities, rules, reviews, badges, hero subjects, rating/review count | Logged out | `schema-public-market.md` |
| Own guest-visible state | own public rank, price, availability, badges, rules, amenities, review themes | Logged out | `public-market.md`, `schema-core.md` |
| Own private host state | calendar, reservations, economics, pricing, rules, Insights, quality | Logged in only when needed | `host-sources.md`, schema files |
| Listing-date state | combined date-level state, pace gap, comp index, restriction choke, quality risk | Mixed from source primitives | `analytics-alerts.md`, `decisioning.md` |

## Public Airbnb primitives

| Primitive family | Examples | Capture method | Backend |
|---|---|---|---|
| Search context | destination, map bounds, dates, guests, filters, currency, device, login state | Public search URL + screenshot/text | Lightpanda only if Airbnb cards render with field parity; otherwise headful |
| Search-card visibility | rank, page/scroll depth, title, location label, badge, rating, review count, price | Public search text/DOM/screenshot | Lightpanda only if card order and fields match headful |
| Public listing facts | room ID, property type, capacity, bedrooms, beds, bathrooms, location text | Listing page text/DOM | Lightpanda only after listing-fact field contract passes |
| Public price/availability | total guest price, nightly component, minimum-stay message, unavailable message | Search results first; listing page second | Backend with total-price field parity |
| Public trust signals | Guest Favourite, top-home highlight, top-percent label, review count, rating | Search/listing page | Backend with visible trust-signal parity |
| Public content quality | hero subject, photo count, photo tour signals, amenities, rules | Listing page text/visual audit | Headful for visual QA; Lightpanda only for matching text fields |
| Public review themes | review text, host response, stay metadata where visible | Listing review section | Lightpanda only if reviews render with field parity |
| Public Help/Resource docs | feature definitions, pricing tools, policy semantics | Static pages | Lightpanda or HTTP |

For own guest-visible collection, run `scripts/collect_own_public.py` logged
out against a fresh browser profile. It consumes the complete live-listing
inventory, opens each own public listing page, records content/review/rating
fields, and runs own-listing public search appearances for date-specific rank
and price context. Public data from this workflow belongs in
`airbnb_own_public_listing_audit`, `airbnb_own_public_review_summary`, and
`airbnb_own_public_search_appearance`.

## Authenticated Airbnb primitives

| Primitive family | Examples | Capture method | Backend |
|---|---|---|---|
| Earnings exports | gross earnings, adjustments, host fee, taxes withheld, net pay, nights, payout method | CSV/PDF download | Headful profile |
| Earnings dashboard | recent/projected/listing earnings | Auth UI text/screenshot | Headful profile |
| Reservations | confirmation code, guest count, dates, status, price breakdown | Auth UI/print/download | Headful profile |
| Calendar and iCal | booked/blocked dates, availability, imported blocks | iCal export + calendar UI | Headful for export; parser after download |
| Block reasons | prep, advance notice, min stay, restricted check-in/out, pending/cancelled blocks | Calendar UI date inspection | Headful profile |
| Host listing inventory API | listing IDs, status, title/name, nickname, bedrooms, bathrooms, beds, location label, Instant Book, modified time, host editor path | `BeehiveGetListingsQuery` from `/hosting/listings` with browser-authenticated API key | Headful profile first; Lightpanda only after field parity receipt |
| Listing editor | full address, guest count, property type, photo count, room/photo tour lines, title, descriptions, photos, rooms, amenities, rules, policies, registration fields | Auth UI/editor text after opening `/hosting/listings/<listing_id>` | Headful profile |
| Pricing settings | base/weekend price, Smart Pricing min/max, fees, discounts, promotions | Auth UI | Headful profile |
| Rule-sets | date ranges, price adjustments, LOS discounts, check-in/out rules | Auth UI | Headful profile |
| Insights conversion | impressions, search-to-listing, listing-to-booking, views, wishlists, lead time | Authenticated `ListOfMetricsQuery` and `ChartQuery` with `filters.listingIds` | Headful bootstrap plus browser-context API fetch |
| Insights occupancy/rates | occupancy, booked/blocked/unbooked nights, check-ins, cancellations, ADR | Authenticated `ListOfMetricsQuery` and `ChartQuery` with `filters.listingIds` | Headful bootstrap plus browser-context API fetch |
| Insights quality | overall/category 5-star performance and similar-listing comparison | Authenticated Performance API plus UI review sections where needed | Headful bootstrap plus browser-context API fetch |
| Messages/quick replies | templates, triggers, placeholders, sent/skipped timeline | Auth UI | Headful profile |
| Tasks/teams | task type, due date, assignment, checklist, completion | Auth UI | Headful profile |
| Regulations/tax | registration/permit fields, declaration status, tax/levy fields | Auth UI/help docs | Headful profile |
| Personal data export | profile, messages, search history, reservations, host payout/listing categories where included | Account privacy data export | Headful request + local parser |

Airbnb's personal data file can be requested in HTML, Excel, or JSON format and
may include host-relevant categories such as listings, reservations, payouts, and
messages when present in the account.

For own live-listing collection, run `scripts/collect_listings.py`. It uses the
inventory API as the canonical source for listing enumeration and status
filtering, then uses the listing editor only for fields the API does not expose
or that need private UI verification. Store full addresses and raw private
outputs only in ignored `.private-data/` artifacts. Partial smoke runs are
marked `partial_run: true` and are not canonical downstream scope unless
explicitly selected with `AIRBNB_LISTINGS_FILE`.

For Insights collection, the canonical scope is listing-specific. The
Performance app's "All listings" route is useful for discovery, but stored rows
must include `filters.listingIds` evidence or an equivalent listing-specific
route. Recent tactical history should come from rolling 7-day `ChartQuery`
windows because Airbnb returns `DAY` granularity there. Long-horizon trend
sweeps may use one broad `ChartQuery` window to reduce request volume, but those
rows must keep Airbnb's returned `series_granularity` because longer ranges can
be monthly or weekly rather than daily.

## Internal host primitives

| Primitive family | Examples | Target file |
|---|---|---|
| Costs | cleaning, linen, utilities, consumables, insurance, management, maintenance | `schema-finance.md` |
| Owner contracts | owner split, guarantees, pass-through costs, statement cadence | `schema-finance.md` |
| Property reality | actual amenities, maintenance issues, photo truth, accessibility | `schema-core.md` |
| Operations capacity | cleaner availability, turnover limits, maintenance SLAs | `schema-operations.md` |
| Action history | price/content/rule/message changes and dates | `decisioning.md` |

## External demand primitives

| Primitive family | Examples | Target file |
|---|---|---|
| Events | concerts, sport, conferences, festivals, local venue events | `schema-demand-context.md` |
| Holidays | public holidays, school holidays, long weekends | `schema-demand-context.md` |
| Weather | severe weather, rain, heat, outdoor suitability | `schema-demand-context.md` |
| Transport/access | airport disruption, rail shutdown, major road closure, cruise arrivals | `schema-demand-context.md` |
| Regulation/supply | night caps, registration changes, local restrictions, market supply shocks | `schema-demand-context.md` |

## Primitive composition examples

| Host decision | Primitive blocks |
|---|---|
| Raise price for a weekend | calendar availability + booking pace + comp total price + event signal + quality/trust premium |
| Discount an orphan night | gap length + minimum stay rules + cleaning cost + comp availability + margin floor |
| Change hero photo | search-card conversion + hero subject + comp hero subjects + content action history |
| Fix check-in process | check-in rating trend + review themes + message timeline + task completion |
| Owner statement | earnings export + reservation economics + actual costs + owner contract |
| Compliance review | listing jurisdiction + Airbnb regulation fields + official source signal + calendar block reason |
