# Airbnb.com.au - Public Market Collection

Field-tested against Melbourne CBD apartment listings on 2026-04-27 using the browser harness.

Use this file for public Airbnb.com.au search/listing extraction and comp-set
observations. For host account collection, read `host-sources.md`. For storage,
read `schema-public-market.md`. For decisions and alerts, read
`analytics-alerts.md`. For discovery order and backend choice, read
`exploration-protocol.md`.

## Ownership

- Use this when: the user needs logged-out Airbnb search, comp, rank, guest-price,
  public listing, own-public, or guest-visible review evidence.
- Owns: public Airbnb extraction mechanics, logged-out guards, similarity
  filters, search/listing traps, public collector usage, and comp processing.
- Does not own: host-private collection, durable row contracts, final
  recommendations, or market pursue/watch/reject decisions.
- Next hop: `schema-public-market.md` for row contracts, `scripts/README.md` for
  runnable collectors, `market-research-playbook.md` for underwriting, and
  `decisioning.md` when evidence becomes an action.

## Quick summary

- Use browser navigation, not `http_get()`, for Airbnb pages.
- Collect public guest-market data logged out by default. Do not use the host
  auth bundle for public search, public listing, public review, or public price
  observations unless the explicit task is to compare logged-in personalization.
- Use Lightpanda first for public pages only after `diagnose_url_capability()`
  proves the expected text and fields are present.
- Apply the general backend-invariant extraction rule from
  `../../interaction-skills/backend-capability.md`: public market records must have the
  same canonical search/listing fields regardless of backend. If Lightpanda
  cannot produce Airbnb search/listing fields for the same context, use a fresh
  logged-out headful Chrome profile and keep the Lightpanda output only as a
  capability receipt.
- Search result pages expose the most reliable price data. Listing pages often show `loading` in the booking widget even when dates and guests are provided.
- `document.body.innerText` is enough to extract listing title, property type, capacity, bedrooms, beds, baths, rating, reviews, host, amenities, house rules, and visible location text.
- For revenue comps, scrape search result totals for a fixed stay length and guest count, then normalize to nightly guest-facing gross.
- Search result totals are shown excluding taxes and rounded to the nearest integer. Do not treat them as owner net revenue.
- For host intelligence, public comp data must be normalized with the exact
  search context: dates, nights, guests, filters, map area, device, logged-in
  state, currency, and observation time.
- For property-specific comp research, exact address text is only the starting
  point. Zoom the map or pass map bounds with `search_by_map=true`, then verify
  the page title is `homes within map area` before using counts.
- Use `Entire home` as the default Airbnb public-search room type. Remove that
  filter only when the task explicitly studies private-room or shared-room
  competition.
- Similar-comp filters must be explicit. Common apartment filters are
  `room_types[]=Entire home/apt`, `min_bedrooms`, optional `min_bathrooms`,
  `amenities[]=9` for free parking, target guest count, and any bounded price
  range used in the comp thesis.
- For normal comp intelligence, `logged_in_flag` should be `False`. If it is
  `True`, treat the run as a separate logged-in/personalized observation and do
  not mix it with logged-out guest-market comps.
- Multi-page search ranking and rank comparisons must be collected logged out.
  A host/owner session can personalize ordering toward the owner's account and
  makes rank observations unsuitable for market visibility analysis.

## Useful URL patterns

Search with dates, adults, and minimum bedrooms:

```text
https://www.airbnb.com.au/s/Melbourne--Victoria--Australia/homes?query=500%20Elizabeth%20Street%20Melbourne&checkin=2026-05-15&checkout=2026-05-18&adults=4&room_types%5B%5D=Entire%20home%2Fapt&min_bedrooms=3
```

Zoomed map-bounds search with similar-comp filters:

```text
https://www.airbnb.com.au/s/Melbourne--Victoria--Australia/homes?query=500%20Elizabeth%20Street%20Melbourne&checkin=2026-05-29&checkout=2026-06-01&adults=8&min_bedrooms=3&room_types%5B%5D=Entire%20home%2Fapt&amenities%5B%5D=9&price_min=1037&price_max=2425&search_by_map=true&sw_lat=-37.835&sw_lng=144.935&ne_lat=-37.785&ne_lng=144.995
```

Useful filter query parameters:

| Filter | Query parameter |
|---|---|
| Entire home | `room_types[]=Entire home/apt` |
| Bedrooms | `min_bedrooms=<count>` |
| Bathrooms | `min_bathrooms=<count>` |
| Free parking | `amenities[]=9` |
| Air conditioning | `amenities[]=5` |
| Wi-Fi | `amenities[]=4` |
| Kitchen | `amenities[]=8` |
| Pool | `amenities[]=7` |
| Dryer | `amenities[]=34` |
| Instant Book | `ib=true` |
| Allows pets | `pets=1` |

Direct listing with dates and guests:

```text
https://www.airbnb.com.au/rooms/{room_id}?check_in=2026-05-15&check_out=2026-05-18&adults=4
```

Google discovery for exact-building listings:

```text
https://www.google.com/search?q=site:airbnb.com.au/rooms+Vision+500+Elizabeth+Melbourne+3+bedrooms+2+baths
https://www.google.com/search?q=site:airbnb.com/rooms+%22500+Elizabeth+Street%22+%223+bedrooms%22+Melbourne+Airbnb
```

## Search-result extraction

```python
url = (
    "https://www.airbnb.com.au/s/Melbourne--Victoria--Australia/homes"
    "?query=500%20Elizabeth%20Street%20Melbourne"
    "&checkin=2026-05-15&checkout=2026-05-18"
    "&adults=4&room_types%5B%5D=Entire%20home%2Fapt&min_bedrooms=3"
)
new_tab(url)
wait_for_load()
text = js("document.body.innerText")
print(text[:10000])
```

Prefer Airbnb's structured deferred state for repeatable card extraction when
it is present:

```python
data = js("""
(() => {
  const state = JSON.parse(
    document.querySelector('#data-deferred-state-0')?.textContent || '{}'
  );
  const results =
    state.niobeClientData?.[0]?.[1]?.data?.presentation?.staysSearch?.results;
  const title =
    results?.sectionConfiguration?.pageTitleSections?.sections?.[0]?.sectionData;
  const cards = results?.searchResults || [];
  return {
    structuredTitle: title?.structuredTitle,
    pageDisplayText: title?.pageDisplayText,
    cards: cards.map((card, index) => ({
      result_position: index + 1,
      listing_id: atob(card.demandStayListing?.id || '').split(':').pop(),
      visible_location_label: card.title,
      visible_title_short: card.subtitle,
      visible_rating: card.avgRatingA11yLabel || card.avgRatingLocalized,
      structured_price: card.structuredDisplayPrice,
      lat: card.demandStayListing?.location?.coordinate?.latitude,
      lng: card.demandStayListing?.location?.coordinate?.longitude,
    })),
  };
})()
""")
```

The same state also exposes the selected filters and the price histogram under
`results.filters.filterPanel.filterPanelSections.sections`. Preserve selected
filter chips with every comp run. The price-range section normally has
`sectionId == "FILTER_SECTION_CONTAINER:PRICE_RANGE"` and a
`priceHistogram` array.

Search result text commonly has repeated blocks in this shape:

```text
Apartment in Carlton
52F 180 MelbCbd Skyview 3BR2Bath. 8Pax. 2 CarPark
3 bedrooms
4 beds
2 baths
$1,147 AUD
$992 AUD total
4.93 out of 5 average rating, 337 reviews
```

Use the `total` price for stay-level comparison. The crossed or earlier price may be a discount anchor and should not be used as realized gross.

For host intelligence, record the search context before extracting cards:

```python
from datetime import datetime, timezone

observed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
search_run = {
    "observed_at": observed_at,
    "observer_location_country": "AU",
    "device_type": "desktop",
    "logged_in_flag": False,
    "currency": "AUD",
    "destination": "Melbourne, Victoria, Australia",
    "check_in_date": "2026-05-15",
    "check_out_date": "2026-05-18",
    "nights": 3,
    "guest_count_adults": 4,
    "filters_applied": ["room_types[]=Entire home/apt", "min_bedrooms=3"],
}
```

Reject or quarantine a public search run if the browser/session was logged in.
For rank/visibility work, there is no owner-session exception; use a fresh
logged-out profile and store logged-in rank only as a separate personalization
test when explicitly requested.

Reject or quarantine a public search run if it lacks field-level evidence. A
loaded Airbnb page title, search form, navigation links, or no-JavaScript alert
is not a valid comp source. For a price/rank search run, require:

- result cards or `/rooms/` links
- total-price strings for the requested dates and guests
- enough visible card text to associate title/location/property facts with
  price and rank
- the exact search context that produced the card set
- selected filter chips when filters are part of the comp definition
- map bounds and a `homes within map area` title when map zoom defines the comp
  boundary

Match validation to the Airbnb website contract before the browser run starts:

- check-in and check-out must be real ISO dates, and check-out must be after
  check-in
- stay length must equal the check-in/check-out span
- guest counts must fit Airbnb-style bounds (`adults` 1-16, adult + child
  total <= 16)
- public scans default to `room_types[]=Entire home/apt`; private-room or
  shared-room studies require explicit scope
- generated URLs must be Airbnb `/s/<destination>/homes` URLs with `checkin`,
  `checkout`, and `adults` query parameters
- price bands must be non-negative and ordered

If a public search bucket hits the requested result cap, split deterministic
bounded price bands, record the parent/child partition keys, and dedupe by
listing ID after collection. Do not use recursive partitioning for
host-private flows.

The search card fields to preserve are:

| Field | Why |
|---|---|
| `result_position` | Visibility |
| `page_number_or_scroll_depth` | Distinguishes initial viewport from lazy-loaded/scrolled results |
| `listing_url` | Stable comp reference |
| `visible_title_short` | Search-card message |
| `visible_location_label` | Market placement |
| `visible_rating` / `visible_review_count` | Trust signal |
| `visible_badge` | Guest Favourite/top-percent signal |
| `visible_price_total` | Guest-facing comp price |
| `visible_price_per_night` | ADR proxy where shown |
| `hero_photo_subject_tag` | Click appeal |
| `available_flag` | Supply signal |

## Listing-page extraction

```python
new_tab("https://www.airbnb.com.au/rooms/1603434441736660031?check_in=2026-05-15&check_out=2026-05-18&adults=4")
wait_for_load()
text = js("document.body.innerText")
print(text[:12000])
```

Listing text commonly includes:

| Field | Notes |
|---|---|
| Title | Near the top, before `Share` / `Save` |
| Property type and location | For example `Entire rental unit in Melbourne, Australia` |
| Capacity | For example `7 guests - 3 bedrooms - 5 beds - 2 baths` |
| Rating and reviews | For example `4.83 - 6 reviews` |
| Host | Host name and hosting duration |
| Description | Often includes building name, floor level, exact tower, amenities |
| Sleeping arrangement | Bedroom and living-room bed inventory |
| Amenities | Pool, gym, spa, sauna, lift, washer, air conditioning, etc. |
| Photo/product evidence | Hero subject, first five photo subjects, room proof, amenity proof, and design gap flags when image labels or captions are visible |
| House rules | Check-in, checkout, guest maximum |
| Fees/rules notes | Cleaning, lost keys, party restrictions when host discloses them |

For comp listing snapshots, add:

- `comp_listing_id` from the room URL.
- core amenity flags such as parking, pool/spa, pet-friendly,
  workspace/Wi-Fi, family amenities, and accessible features.
- cancellation policy where visible.
- photo count and hero-photo subject.
- first-five photo subjects when Airbnb exposes image labels, captions, or
  equivalent visible labels.
- room proof flags for bedroom, bathroom, kitchen, living area, and workspace.
- amenity proof flags for parking, pool/spa, view, family, pet, self-check-in,
  laundry, and air conditioning.
- visible amenity claims, amenity claims proven in photos, missing photo proof,
  design gap flags, and the normalized photo/product score.
- top-home, Guest Favourite, and top-percent highlight visibility.
- public review star distribution where visible. Airbnb exposes percentages on
  some listing pages; store the percentage and an estimated count derived from
  `review_count`, rather than pretending Airbnb gave an exact count.
- positive and negative review themes.

## Traps

- Price widgets on individual listing pages can stay at `loading`; use search result totals for pricing evidence.
- Airbnb search may return nearby suburbs and broader Melbourne results even when the query is a specific address. Keep only comps matching the target building or a defensible CBD substitute.
- An address query can still produce a broad `Homes in Melbourne` result set.
  Do not use that count for building validation. Zoom the map or use
  `search_by_map=true` with explicit bounds, then confirm the title says
  `homes within map area`.
- URL `price_min` and `price_max` parameters must be validated against the
  visible selected chips and card totals. Airbnb's selected price chip and card
  total semantics can diverge across contexts; record both instead of assuming
  the URL parameter alone proves the price tier.
- Similar-comp filters should be part of the observation key. A 3-bedroom,
  free-parking, entire-home search is a different market slice from a broad
  3-bedroom search.
- Listing pages may provide the exact building address in description text, but the map section still says exact location is provided after booking.
- Search result totals exclude taxes. They are guest-facing gross before tax, not platform-adjusted host payout and not net income.
- A minimum-bedroom search can still include non-target locations. Filter by title, suburb, property type, bedroom/bath count, and whether the listing text mentions the building/address.
- Lightpanda can load Airbnb pages but may stop at generic no-JavaScript shell
  content. On 2026-04-27, logged-out Lightpanda loaded Melbourne search pages
  with title and about 1,189 characters of text, but produced zero room links
  and zero AUD total prices. Fresh logged-out headful Chrome for the same search
  exposed hydrated result cards, room links, and total prices. Treat this as a
  backend capability failure for public comp search, not as usable low-confidence
  market data.
- Direct listing pages in Lightpanda may expose a title and room links but still
  miss capacity, reviews, amenities, and date-specific price evidence. Require
  listing-snapshot field evidence before using Lightpanda for Workflow 3.
- A logged-out headful Chrome room page opened from a hydrated public search
  result produced usable listing-snapshot fields on 2026-04-27: title, capacity,
  rating/review signal, and amenity text. Prefer this path for comp listing
  snapshots when Lightpanda lacks parity.
- If headless or Lightpanda produces a loaded-but-empty page, run
  `diagnose_url_capability(url)` before debugging selectors.
- Authenticated host pages should not be scraped with public assumptions. Use a
  logged-in browser session, prefer exports/downloads, and stop at the login
  wall if the user has not granted access.
- Public pages should not be scraped with private host assumptions. If the URL
  is guest-visible, start from a logged-out Lightpanda or fresh browser context
  and only switch to logged-in state when the public source itself proves
  inaccessible without login.

## Public comp workflow

Choose the public comp workflow by research mode.

### Property-validation workflow

Use this when the user has a specific building, address, lease, purchase, or
co-host target.

1. Start from a logged-out browser profile.
2. Search exact building/address terms in Airbnb and Google to identify
   in-building listings.
3. Apply `Entire home` by default. Remove it only when the task explicitly
   studies rooms or shared-room competition.
4. Apply the similarity filter pack before accepting comps: bedrooms, bathrooms
   when material, target guest count, core amenities, and bounded price range
   when the thesis depends on price tier.
5. Zoom or pass map bounds with `search_by_map=true` until the result title and
   visible map support a defensible boundary. Save selected filter chips, title,
   map bounds, and screenshot/text receipt.
6. Record map friction: rivers, highways, rail lines, unsafe walks, parking
   gaps, transit gaps, same-side requirements, walk/drive/transit times, and the
   anchor the guest segment cares about.
7. Open listing pages and extract capacity, bedrooms, baths, floor level,
   amenities, rating, reviews, latest review signal, host maturity, and future
   availability clues.
8. Prefer same-building comps. If none exist, use same-block or same-friction
   boundary comps. Search specifically for equal-or-worse properties that still
   appear to book or price profitably.
9. Quarantine beautiful, premium, or unreproducible listings as `inspiration`
   unless the candidate can reproduce the winning variable.
10. Apply listing-maturity filters before using any comp in base-case revenue.

### Opportunity-discovery workflow

Use this when the host can still choose the market, property type, or product.

1. Search broader markets and submarkets logged out.
2. Run multiple guest counts, stay lengths, and seasons.
3. Cluster repeated winners by product type, capacity, amenity, anchor, location
   type, channel, and rule set.
4. Identify the winning variable for each repeated cluster.
5. Search for loser and counterexample listings with and without that variable.
6. Recommend a product profile only when repeated winners and reproducibility
   are both present.

### Shared comp processing

1. Normalize stay totals by nights to produce guest-facing nightly gross.
2. Grade each comp before using it: `A` for same boundary, room type, capacity,
   season, stay length, and core amenities; `B` for one named material
   difference; `C` for inspiration only; `reject` for excluded comps.
3. Build a comp price index: target total guest price / median `A` comp total guest
   price for the same dates, guests, filters, and stay length.
4. Compare against host economics only after accounting for taxes/levies,
   platform fees, management, cleaning, utilities, consumables, linen,
   insurance, vacancy, and wear.

For acquisition, expansion, arbitrage, co-hosting, or property-validation work,
continue from raw public comp observations into `market-research-playbook.md`.
That playbook adds absorption scans, stay-length gaps, guest-capacity curves,
strict comp grading, comp-thesis counterexamples, slow-season survival, channel
demand, midterm viability, underwriting, and pursue/watch/reject decisions.

## Executable competitor collection

Use `scripts/collect_competitors.py` for repeatable logged-out competitor
collection from the current live-listing inventory.

Default behavior:

- reads the latest `airbnb-live-listings-*.json` private artifact produced by
  `scripts/collect_listings.py`
- uses only `status == ACTIVE` listings as targets
- searches Airbnb logged out by target address/building, check-in date,
  3-night stay, adult count, `Entire home`, and minimum bedroom count
- refuses to run if known Airbnb authenticated-session cookies are present,
  because owner-login state biases public ranking
- records date-specific public search runs, search-card result rows, price
  matrix rows, target-to-comp links, and deduplicated public comp listing
  snapshots
- optionally partitions logged-out public searches by URL price bands via
  `AIRBNB_COMP_PRICE_BANDS` (for example `0-250,251-500,501-`) so high-volume
  markets can be scanned without relying on one broad result page
- includes planner helpers for research-mode gates, `Entire home` similarity
  filter validation, and listing-maturity grading so property-validation scans
  do not silently treat broad winners or boosted low-review listings as
  base-case comps
- can recursively split bounded price bands when a visible result bucket hits
  the requested result cap. Use this only for logged-out public market scans,
  not host-private flows.
- validates check-in/check-out spans, stay lengths, guest counts, room-type
  filters, result limits, scroll limits, price bands, currency, generated
  Airbnb search URLs, and Airbnb room URL shapes before producing receipts
- scrolls the lazy-loaded search result window up to
  `AIRBNB_COMP_MAX_SEARCH_SCROLLS` while preserving first-seen card order as
  the bounded rank window
- writes raw search/listing JSONL checkpoints plus JSON/CSV outputs under
  ignored `.private-data/public-market-collections/`
- marks suspicious zero-result runs as quarantined when a prior non-empty run
  exists, instead of letting an empty scrape silently replace last-good evidence
- stores a receipt under ignored `.session-store/capability/`
- refuses partial listing inventories by default. Use `AIRBNB_LISTINGS_FILE`
  only when intentionally testing against a partial scope.

Useful controls:

```text
AIRBNB_COMP_CHECKIN_DATES=2026-05-15,2026-06-12
AIRBNB_COMP_CHECKIN_OFFSETS=14,30,60,90
AIRBNB_COMP_CHECKIN_RANGE=2026-05-15..2026-06-12
AIRBNB_COMP_CHECKIN_STEP_DAYS=7
AIRBNB_COMP_NIGHTS=3,7
AIRBNB_COMP_STAY_LENGTH_RANGE=2..7
AIRBNB_COMP_PRICE_BANDS=0-250,251-500,501-
AIRBNB_COMP_AUTO_PRICE_PARTITION=1
AIRBNB_COMP_AUTO_PRICE_MIN=0
AIRBNB_COMP_AUTO_PRICE_MAX=2000
AIRBNB_COMP_PARTITION_TRIGGER_VISIBLE_RESULTS=12
AIRBNB_COMP_PARTITION_MAX_DEPTH=2
AIRBNB_COMP_TOP_RESULTS=12
AIRBNB_COMP_TOP_COMPS_PER_CONTEXT=8
AIRBNB_COMP_MAX_LISTING_SNAPSHOTS=120
AIRBNB_COMP_MAX_SEARCH_SCROLLS=6
AIRBNB_COMP_LISTING_SCOPE=active
AIRBNB_COMP_NAV_DELAY_SEC=4
AIRBNB_COMP_LIMIT_LISTINGS=1
AIRBNB_LISTINGS_FILE=agent-workspace/domain-skills/airbnb/.private-data/listing-collections/<explicit-complete-or-smoke>.json
```

Run against a fresh logged-out agent Chrome profile:

```bash
browser-harness --launch-profile agent-workspace/domain-skills/airbnb/.session-store/profiles/public-comps \
  --port 52870 --url about:blank --json

BH_NAME=airbnb-public-comps BH_CDP_WS=http://127.0.0.1:52870 \
  python3 run.py < agent-workspace/domain-skills/airbnb/scripts/collect_competitors.py
```

Empirical run on 2026-04-27:

- 27 active target listings
- 4 forward check-in dates: 2026-05-11, 2026-05-27, 2026-06-26, 2026-07-26
- 108 search contexts
- 1,296 search-card price rows
- 864 target-to-comp links
- 120 deduplicated public listing snapshots
- 0 failures

Validation from that run: every target had four search contexts, every search
context had cards, every target had comp links, all card rows had titles and
total prices, all listing snapshots had rating and capacity fields, and 110 of
120 listing snapshots exposed visible review star distribution. A targeted
scroll smoke on 2026-04-27 verified `AIRBNB_COMP_MAX_SEARCH_SCROLLS`, rank
window metadata, logged-out guard, and competitor snapshot output on a
one-listing run with 0 failures.

## Executable own public collection

Use `scripts/collect_own_public.py` to audit the host's own live listings as a
logged-out guest. This workflow closes the gap between private listing
inventory and what guests can actually see in public search/listing pages.

Default behavior:

- reads the latest complete `airbnb-live-listings-*.json` private artifact
  produced by `scripts/collect_listings.py`
- uses only `status == ACTIVE` listings as targets
- opens every public room page logged out and records content, amenity, rules,
  badge, rating-category, review-count, and review-star-distribution fields
- records `rating_category_source`, `star_distribution_source`,
  `star_distribution_confidence`, and
  `visible_individual_review_star_count` so absent or partial review widgets are
  treated as Airbnb visibility states, not silently as parser failures
- emits `airbnb_own_public_review_snapshot` rows for individual visible public
  reviews, including rendered star label, date label, review text, and theme
  tags
- runs logged-out public searches for each target listing using target address
  or location, dates, stay length, adult count, `Entire home`, and bedroom
  filter
- refuses to run if known Airbnb authenticated-session cookies are present,
  because own-listing rank must not be observed from the owner's account
- records whether the host listing appears in the bounded collected result
  window, its rank, visible title/location, total guest price, rating, review
  count, badge, and rank observation confidence
- scrolls the lazy-loaded search result window up to
  `AIRBNB_OWN_PUBLIC_MAX_SEARCH_SCROLLS` and records scroll depth for the
  first-seen own-listing card
- writes JSON/CSV outputs under ignored `.private-data/own-public-collections/`
- stores a capability receipt under ignored `.session-store/capability/`
- refuses partial listing inventories by default. Use `AIRBNB_LISTINGS_FILE`
  only when intentionally testing against a partial scope.

Useful controls:

```text
AIRBNB_OWN_PUBLIC_CHECKIN_DATES=2026-05-15,2026-06-12
AIRBNB_OWN_PUBLIC_CHECKIN_OFFSETS=14,30,60,90
AIRBNB_OWN_PUBLIC_NIGHTS=3,7
AIRBNB_OWN_PUBLIC_TOP_RESULTS=30
AIRBNB_OWN_PUBLIC_MAX_SEARCH_SCROLLS=6
AIRBNB_OWN_PUBLIC_LISTING_SCOPE=active
AIRBNB_OWN_PUBLIC_NAV_DELAY_SEC=2
AIRBNB_OWN_PUBLIC_LIMIT_LISTINGS=1
AIRBNB_LISTINGS_FILE=agent-workspace/domain-skills/airbnb/.private-data/listing-collections/<explicit-complete-or-smoke>.json
```

Run against a fresh logged-out agent Chrome profile:

```bash
browser-harness --launch-profile agent-workspace/domain-skills/airbnb/.session-store/profiles/own-public \
  --port 52872 --url about:blank --json

BH_NAME=airbnb-own-public BH_CDP_WS=http://127.0.0.1:52872 \
  python3 run.py < agent-workspace/domain-skills/airbnb/scripts/collect_own_public.py
```

Search-card parsing trap: Airbnb cards may put date lines such as
`26 to 30 May`, `26-30 May`, or `29 May to 1 June` before the title. Do not
accept the first non-empty card line as `visible_title_short`; skip date, price,
capacity, badge, rating, and "Show price breakdown" lines, then prefer the
first remaining title-like line after the location label.

Empirical own-public run on 2026-04-27:

- 27 active target listings
- 27 logged-out public listing-page content audits
- 27 logged-out public review summaries
- 27 logged-out search/rank contexts for 2026-05-27 to 2026-05-30
- 3 own listings appeared in the top 30 result window for their target context
- 27 of 27 review rows had listing-level review count
- 16 of 27 review rows exposed listing-level overall rating
- 18 of 27 review rows exposed star distribution; 15 exposed rating categories
- 0 failures

Validation from that run: every public listing page loaded, every target search
context had cards, every content row had title/capacity fields, every review row
had a listing-level review count, and no own search-appearance row had a date
string parsed as the title. The rows without overall rating were no-review or
low-review listings where Airbnb did not expose a listing average. The rows
without star distribution or categories were missing because Airbnb did not
expose those widgets in the logged-out listing text. The executable receipt
records the logged-out guard and zero authenticated-session cookie names before
collecting rank fields; a post-run cookie check also found zero authenticated
session cookie names. A targeted scroll smoke on 2026-04-27 verified
`AIRBNB_OWN_PUBLIC_MAX_SEARCH_SCROLLS`, rank window metadata, review display
state counters, and logged-out guard on a one-listing run with 0 failures.

## Host-facing outputs

Public Airbnb.com.au extraction should feed these host decisions:

- underpriced peak date
- overpriced conversion risk
- minimum-stay choke
- weak search-card positioning
- amenity or trust-signal gap
- high-demand unbooked date
- comp quality premium or discount

## Similar-listing validation

When Airbnb exposes similar listings or comparable price context in a logged-in
host flow, record Airbnb's comparison separately from your manually curated comp
set. Airbnb's similar-listing logic can consider location, size, features,
amenities, ratings, reviews, and other listings guests browse. Treat that as a
platform-relative pricing signal, not as a complete market definition.
