# Airbnb.com.au - Authenticated Host Sources

Use this file for logged-in Airbnb host account collection. Use
`public-market.md` for public competitor extraction and the schema files for
storage.

Before collecting private data across sessions, read `session-continuity.md`.
Before assuming available fields, run `exploration-protocol.md` and update
`data-inventory.md` with account-specific source availability.

## Collection posture

- Stop at the login wall if the user has not granted access.
- Prefer downloads and exports when Airbnb provides them.
- Use authenticated UI text only when exports are unavailable.
- Record `observed_at`, listing scope, date filters, account currency, and the
  visible UI/source used for each capture.
- Store session continuity receipts in the ignored `.session-store/`; do not
  store raw cookies in tracked files.
- Do not type credentials from screenshots.

## Source map

| Source | Data obtainable | Refresh | Primary use |
|---|---|---:|---|
| Earnings dashboard | Recent earnings, projected earnings, listing-level earnings | Weekly/monthly | Revenue tracking |
| Earnings reports / CSV | Gross earnings, adjustments, host service fee, taxes withheld, net pay, nights booked, average length of stay, listing and payout method, cleaning fee | Monthly and after payout changes | Financial reporting, owner statements, tax preparation |
| Reservation details | Guest name, reservation dates, guest count, confirmation code, guest-paid price, status | On booking/change | Operations, check-in, cleaning, stay economics |
| Calendar / iCal export | Booked nights, blocked nights, availability state | Daily | Occupancy, gaps, accidental blocks, booking pace |
| Listing settings | Title, description, photos, capacity, amenities, fees, rules, cancellation, check-in/out, registration fields | Monthly and after edits | Listing accuracy, conversion, compliance tracking |
| Insights > Conversion | Impressions, search-to-listing, listing-to-booking, lead time, returning guests, views, wishlists | Daily/weekly | Funnel diagnosis |
| Insights > Occupancy & rates | Occupancy, blocked/booked/unbooked nights, check-ins, cancellation rate, length of stay, nightly rate | Weekly | Yield and calendar performance |
| Insights > Quality | 5-star category performance, overall rating, comparison to similar listings | Weekly/monthly | Operational quality control |
| Rule-sets | Price rules, LOS discounts, last-minute, early-bird, min/max stay, check-in/out requirements | Weekly and after edits | Yield rules and restriction control |
| Smart Pricing settings | On/off, min, max, overrides, discount interactions | Weekly and after edits | Rate governance |
| Messages / quick replies | Templates, triggers, placeholders, sent/skipped timeline | Monthly and per reservation | Communication consistency |
| Reviews | Review date, text, ratings, host response, themes | After review posts | Guest-experience intelligence |
| Personal data export | Account data file in HTML, Excel, or JSON where requested and available | On request/quarterly audit | Historical primitive discovery and backfill |
| Similar listings / price comparison | Airbnb-selected comparable listings, available/booked comparison context, typical nightly prices where shown | Weekly and before pricing changes | Pricing reasonableness and comp-set validation |
| Promotions and discounts | Weekly/monthly/early-bird/last-minute discounts, custom promotion eligibility, median-price constraints | Weekly and after pricing edits | Promotion governance and discount leakage control |
| Photo tour / listing editor | Room-level photo coverage, photo order, room amenities, accessibility features, sleeping arrangements | Monthly and after content edits | Listing quality and conversion |
| Top-home / Guest Favourite highlights | Search/listing badge visibility and top-percent labels where visible | Weekly/monthly | Trust-signal tracking |
| Help Centre pages | Feature definitions and responsible-hosting guidance | Monthly/quarterly | Feature and compliance awareness |

## Earnings and payout reporting

Primary fields:

- booking subtotal
- gross earnings
- adjustments
- Airbnb host service fee
- taxes withheld or remitted where visible
- net payout
- cleaning fee and other host fees
- nights booked
- average length of stay
- listing and payout method

Extraction order:

1. Download earnings report or CSV from the Airbnb earnings UI.
2. Parse the downloaded file with a structured CSV/PDF parser.
3. Use authenticated UI text only when exports are unavailable.

Use for net ADR, net RevPAN, owner statements, fee leakage, refunds,
adjustments, payout timing, and cleaning-fee recovery.

## Reservation details

Capture every booking or change event:

- confirmation code
- listing ID/name
- reservation status
- booking creation time if visible
- check-in/check-out dates
- nights
- guest count breakdown
- guest country/language if visible
- price breakdown and what the guest paid if visible
- special requests from messages

Use reservation details to connect money, calendar dates, operations, messages,
reviews, and cleaning load.

## Calendar and iCal

Use iCal/exported calendar for the daily availability base:

- booked nights
- blocked nights
- imported external blocks
- reservation-linked dates when visible

Use the host calendar UI when you need reasons that iCal cannot express:

- owner block
- prep time
- minimum stay
- advance notice
- restricted check-in/check-out day
- pending request
- cancelled reservation block
- account/listing compliance block

Calendar snapshots should be daily for forward-looking dates. Never overwrite a
previous snapshot; booking pace depends on history.

## Listing settings and content audit

Capture monthly and after edits:

- live/listed status
- title
- full address from the authenticated editor
- public listing URL or host-editor path
- description sections
- photos and hero-photo subject
- capacity, beds, bedrooms, bathrooms
- amenities
- house rules
- cancellation policy
- check-in method/window
- checkout time
- instant book state
- registration or permit fields where visible
- photo tour room coverage and photo order
- room-level amenities, sleeping arrangements, and accessibility features
- badge/highlight visibility on public listing and search pages

Use public listing pages to verify how the listing appears to guests. Use the
host editor to check settings that are hidden from guests.

### Authenticated live-listing inventory workflow

Use this workflow when the host asks for all currently live Airbnb listings and
their private attributes.

Executable collector: `scripts/collect_listings.py`.

1. Restore the Airbnb host auth bundle into a separate fresh Chrome
   profile/process. Do not use a new tab in an already logged-in browser as the
   restore test.
2. Open `https://www.airbnb.com.au/hosting/listings` and verify it loads host
   content.
3. Inspect `script#data-injector-instances` and page network state for
   `BeehiveGetListingsQuery`.
4. Read `layout-init.api_config.key` from `script#data-initializer-bootstrap`
   and send it as `x-airbnb-api-key` for the persisted API request.
5. Fetch `/api/v3/BeehiveGetListingsQuery/<persisted_query_hash>` in pages,
   normally with request variables containing `limit: 30` and offsets of
   `0, 30, 60...` until `metadata.totalCount` is exhausted.
6. Treat `status == ACTIVE` as the live/listed inventory. Keep other statuses in
   the receipt counts, but do not include them in the live-listing output unless
   explicitly requested.
7. For each active listing, open
   `https://www.airbnb.com.au/hosting/listings/<listing_id>`. Airbnb redirects
   to the listing editor, commonly
   `/hosting/listings/editor/<listing_id>/details/photo-tour`.
8. Extract private detail fields from rendered editor text when the API row does
   not contain enough detail: full address after the `Location` label, `Number
   of guests`, `Property type`, room/photo lines, and photo count.
9. Save private JSON/CSV under
   `domain-skills/airbnb/.private-data/listing-collections/` and save a compact
   receipt under `.session-store/capability/`.

Recommended run shape:

```bash
python3 run.py --launch-profile domain-skills/airbnb/.session-store/profiles/listings \
  --port 52862 --url about:blank --json

AIRBNB_AUTH_STATE_PATH=domain-skills/airbnb/.private-data/auth-state/host-main-cdp-state.json \
BH_NAME=airbnb-listings BH_CDP_WS=http://127.0.0.1:52862 \
  python3 run.py < domain-skills/airbnb/scripts/collect_listings.py
```

Useful controls:

```text
AIRBNB_LISTINGS_RUN_ID=airbnb-live-listings-YYYYMMDDTHHMMSSZ
AIRBNB_LISTINGS_PAGE_LIMIT=30
AIRBNB_LISTINGS_LIMIT_ACTIVE=1
AIRBNB_LISTINGS_SKIP_DETAILS=1
AIRBNB_LISTINGS_DETAIL_PAUSE_SEC=1.5
AIRBNB_LISTINGS_QUERY_HASH=<rediscovered_hash_if_needed>
```

`AIRBNB_LISTINGS_SKIP_DETAILS=1` is only for API smoke tests. A
recommendation-grade live-listing inventory must open the authenticated editor
detail pages or otherwise prove every required private field.

Partial listing runs are marked with `partial_run: true`. Downstream collectors
must not use them by default; set `AIRBNB_LISTINGS_FILE` explicitly only when
running a deliberate partial smoke test.

Empirical source note from 2026-04-27: the listings overview API used
`BeehiveGetListingsQuery` with persisted hash
`6a50773b7e0bf1c1c7c54d7b12d12c2db5be0eb4ce1ebfb8df1c3b42a9e2aaca`.
Do not hard-code the hash as the only path; rediscover it from loaded scripts or
network state when possible and record the observed hash in the receipt.

Executable collector smoke on 2026-04-27: a fresh Chrome profile restored the
private host auth bundle, fetched all three overview API pages (`70` listings:
`27` active, `43` unlisted), opened one active editor detail page, and passed
the required-field gate for that record. This smoke was intentionally partial
and is not a downstream listing scope.

Field-level acceptance:

- Overview pagination must reconcile to `metadata.totalCount`.
- Status counts must be recorded before filtering to active listings.
- Every active record must include `listing_id`, `listing_name`, `status`,
  `address`, `bedrooms`, `bathrooms`, `beds`, and `max_guests`.
- If the API row and editor text disagree, store both source values and mark the
  record for manual review instead of silently overwriting.
- Do not print full addresses into shared docs or commits; keep them in ignored
  private artifacts.

## Insights

Use Insights when available through professional hosting tools.

Airbnb Performance/Insights data must be collected per listing. Use account-level
or "All listings" pages only for source discovery, navigation, and filter
inventory. Do not store portfolio averages as listing facts.

Conversion:

- first-page search impressions
- search-to-listing conversion
- listing-to-booking conversion
- views
- wishlist additions
- booking lead time
- returning guests
- comparison to similar listings where shown

Occupancy and rates:

- occupancy rate
- nights blocked
- nights booked
- unbooked nights
- check-ins
- cancellation rate
- average length of stay
- average nightly rate
- future-period flag

Quality:

- overall rating
- 5-star percentage
- accuracy
- check-in
- cleanliness
- communication
- location
- value
- comparison to similar listings where shown

Insights are the funnel truth source. Public scraping can show what a guest
sees, but it cannot replace authenticated conversion metrics.

### Authenticated per-listing Performance API workflow

Use this workflow for listing-level views, conversion, occupancy, rates, and
quality metrics.

1. Start from a verified live-listing inventory so the listing scope is
   `status == ACTIVE`.
2. Restore the Airbnb host auth bundle into a separate fresh Chrome
   profile/process.
3. Open one authenticated Performance route to establish Airbnb bootstrap state,
   for example
   `/performance/conversion/p3_impressions/listing/<listing_id>?ds-start=-1&ds-end=0`.
4. Use Network events or loaded scripts to discover the persisted query hashes.
   Empirical hashes observed on 2026-04-27:
   - `ListOfMetricsQuery`:
     `d72f771d4dd59e594aeefbd90d5a5510d72c4c732f596f6d663af00bb27fac3c`
   - `ChartQuery`:
     `3e1e441e3bac1937e60c1b0409b53286e338804dd94c68575c556289a3b07580`
   - page bootstrap queries such as `QualityPageQuery`, `OccupancyPageQuery`,
     and `ConversionPageQuery` are useful for discovery, but
     `ListOfMetricsQuery` and `ChartQuery` are the efficient collection APIs.
5. Send same-origin authenticated `GET /api/v3/<Query>/<hash>` requests from the
   browser context with `operationName`, `variables`, and persisted-query
   `extensions`.
6. Required request arguments:
   - `metricType`: `QUALITY`, `OCCUPANCY`, or `CONVERSION`
   - `groupBys`: `["RATING_CATEGORY"]`
   - `groupByValues`: the metric subroute, such as `overall`,
     `occupancy_rate`, `conversion_rate`, `p3_impressions`, or `wishlist`
   - `filters.listingIds`: exactly one listing ID for listing-level capture
   - `relativeDsStart` and `relativeDsEnd`: relative date-window bounds
7. Choose the chart/history mode by the decision being supported:
   - `AIRBNB_INSIGHTS_CHART_MODE=rolling_daily`: call `ChartQuery` in rolling
     7-day windows. Airbnb returns `DAY` granularity for these windows. Use this
     for recent tactical history, then de-duplicate overlapping window endpoints
     by `listing_id`, metric, series, and date.
   - `AIRBNB_INSIGHTS_CHART_MODE=single_window`: call one broad `ChartQuery`
     window. Use this for long-horizon trend reconnaissance where fewer API
     calls matter more than daily granularity. Preserve Airbnb's returned
     `series_granularity` (`DAY`, `WEEK`, or `MONTH`) instead of pretending it is
     daily.
8. Use `ListOfMetricsQuery` for summary windows such as last 7, 30, and 365
   days. Compose higher-period views from stored daily primitives where possible,
   but keep Airbnb's own period summaries for rates, ratios, averages, and
   quality percentages.
9. Persist successful raw API responses to run-scoped JSONL checkpoints after
   each batch. Reuse the same run ID to resume later; retry failed or
   rate-limited requests instead of treating them as durable data.

Empirical coverage captured on 2026-04-27:

- `airbnb-insights-20260427T095000Z-daily30`: 27 active listings, 16 metric
  routes, 1,296 summary API requests, 2,160 rolling chart requests, 2,025
  summary rows, 26,784 chart rows, all chart rows at `DAY` granularity, 0
  failures.
- `airbnb-insights-20260427T095000Z-trend365`: 27 active listings, 16 metric
  routes, 432 broad chart requests, 11,232 chart rows, 13 monthly trend points
  per route/listing, 0 failures.

Rate-limit handling:

- Airbnb may return HTTP `429` when too many Performance API calls are issued.
- Use small batches, per-request timeouts, inter-batch delays, and exponential or
  fixed backoff.
- If consecutive batches return only `429`, stop the run, store a partial
  receipt, wait for cooldown, and resume later. Do not continue hammering the
  API.
- Prefer fewer API calls over more browser navigation. The browser should be
  used for authentication/bootstrap, API discovery, and fields not present in
  the backend response; it should not be used as the primary transport for
  metrics already available through `ListOfMetricsQuery` or `ChartQuery`.

Per-listing acceptance:

- Every stored metric row includes `listing_id`, metric family, subroute,
  relative date window, source URL/API, `observed_at`, and value metadata.
- Daily chart rows include `ds`, series label/index, granularity, value, and
  whether the row is a comparison series.
- A run is recommendation-grade only when every active listing has the required
  route/date coverage or a clear unavailable/rate-limited receipt.

## Pricing settings and Smart Pricing

Capture weekly and after edits:

- base price
- weekend price
- Smart Pricing enabled
- Smart Pricing min/max
- weekly and monthly discounts
- early-bird and last-minute discounts
- custom promotions
- cleaning, pet, extra guest, and additional fees
- promotion eligibility and median-price basis where Airbnb shows it
- similar-listing comparison context where Airbnb shows it

Airbnb-specific rule: Smart Pricing can override rule-set intent. If the host
expects a custom rule-set to control a period, check whether Smart Pricing is
active for that listing and date range.

Airbnb-specific promotion rule: custom promotion eligibility can depend on the
date being unblocked, recently unblocked enough to establish a median price, and
inside Airbnb's eligible promotion window. Record the reason when Airbnb marks a
date ineligible.

## Rule-sets

Capture each rule-set and the dates/listings it affects:

- rule-set name/ID
- date range
- listing IDs applied
- nightly price adjustment
- length-of-stay discounts
- last-minute discounts
- early-bird discounts
- minimum and maximum nights
- check-in and checkout day rules
- Smart Pricing interaction

Rule-sets are high leverage and high risk. They can raise peak yield, fill gaps,
or accidentally make profitable searches unbookable.

## Messages and quick replies

Capture monthly and per reservation:

- template name
- listing applicability
- trigger type
- trigger offset
- placeholders/details used
- last-minute booking behavior
- sent/skipped/upcoming timeline
- guest response needed flag

Check for placeholder failures where Airbnb cannot populate a detail because the
listing lacks the underlying field.

## Reviews and quality themes

Capture after review publication:

- review date
- stay month if visible
- review text
- category ratings if visible to host
- host response
- recurring themes

Recommended theme tags:

- cleanliness
- accuracy
- check-in
- noise
- beds/sleep
- Wi-Fi/work
- value
- maintenance
- parking
- family suitability
- pet suitability

Use themes as evidence for operational fixes, not as isolated anecdotes.

## Tasks and team operations

If the host uses Airbnb teams/tasks, capture:

- task type
- reservation/listing link
- due time
- assigned role
- completion time
- issue found flag
- photo evidence flag

If Airbnb tasks are not used, create an internal operations task table from
reservations and messages.

## Australian compliance awareness

Track Airbnb-visible fields and guidance links:

- registration or permit number fields
- listing regulation tab status where visible
- taxes withheld or remitted in earnings reports
- levy/tax collection flags where visible
- jurisdiction/state/territory
- declaration status where visible
- report download timestamp

Do not infer legal compliance from absence of a visible warning. Record what
Airbnb exposes and tell the user to verify local obligations with a qualified
advisor or official government source.
