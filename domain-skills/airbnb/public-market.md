# Airbnb.com.au - Public Market Collection

Field-tested against Melbourne CBD apartment listings on 2026-04-27 using the browser harness.

Use this file for public Airbnb.com.au search/listing extraction and comp-set
observations. For host account collection, read `host-sources.md`. For storage,
read `schema-public-market.md`. For decisions and alerts, read
`analytics-alerts.md`. For discovery order and backend choice, read
`exploration-protocol.md`.

## Quick summary

- Use browser navigation, not `http_get()`, for Airbnb pages.
- Use Lightpanda first for public pages only after `diagnose_url_capability()`
  proves the expected text and fields are present.
- Search result pages expose the most reliable price data. Listing pages often show `loading` in the booking widget even when dates and guests are provided.
- `document.body.innerText` is enough to extract listing title, property type, capacity, bedrooms, beds, baths, rating, reviews, host, amenities, house rules, and visible location text.
- For revenue comps, scrape search result totals for a fixed stay length and guest count, then normalize to nightly guest-facing gross.
- Search result totals are shown excluding taxes and rounded to the nearest integer. Do not treat them as owner net revenue.
- For host intelligence, public comp data must be normalized with the exact
  search context: dates, nights, guests, filters, map area, device, logged-in
  state, currency, and observation time.

## Useful URL patterns

Search with dates, adults, and minimum bedrooms:

```text
https://www.airbnb.com.au/s/Melbourne--Victoria--Australia/homes?query=500%20Elizabeth%20Street%20Melbourne&checkin=2026-05-15&checkout=2026-05-18&adults=4&min_bedrooms=3
```

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
    "&adults=4&min_bedrooms=3"
)
new_tab(url)
wait_for_load()
text = js("document.body.innerText")
print(text[:10000])
```

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
    "filters_applied": ["min_bedrooms=3"],
}
```

The search card fields to preserve are:

| Field | Why |
|---|---|
| `result_position` | Visibility |
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
| House rules | Check-in, checkout, guest maximum |
| Fees/rules notes | Cleaning, lost keys, party restrictions when host discloses them |

For comp listing snapshots, add:

- `comp_listing_id` from the room URL.
- core amenity flags such as parking, pool/spa, pet-friendly,
  workspace/Wi-Fi, family amenities, and accessible features.
- cancellation policy where visible.
- photo count and hero-photo subject.
- top-home, Guest Favourite, and top-percent highlight visibility.
- positive and negative review themes.

## Traps

- Price widgets on individual listing pages can stay at `loading`; use search result totals for pricing evidence.
- Airbnb search may return nearby suburbs and broader Melbourne results even when the query is a specific address. Keep only comps matching the target building or a defensible CBD substitute.
- Listing pages may provide the exact building address in description text, but the map section still says exact location is provided after booking.
- Search result totals exclude taxes. They are guest-facing gross before tax, not platform-adjusted host payout and not net income.
- A minimum-bedroom search can still include non-target locations. Filter by title, suburb, property type, bedroom/bath count, and whether the listing text mentions the building/address.
- Lightpanda nightly `1.0.0-nightly.5816+a578f4d6` can extract Airbnb listing and search-result text as of 2026-04-27. Pages include a visible no-JavaScript warning in `innerText`, but the useful static content still appears.
- If headless or Lightpanda produces a loaded-but-empty page, run
  `diagnose_url_capability(url)` before debugging selectors.
- Authenticated host pages should not be scraped with public assumptions. Use a
  logged-in browser session, prefer exports/downloads, and stop at the login
  wall if the user has not granted access.

## Public comp workflow

1. Search exact building/address terms in Airbnb and Google to identify in-building listings.
2. Open listing pages and extract capacity, bedrooms, baths, floor level, amenities, rating, reviews, and host maturity.
3. Search the broader suburb/CBD with the same dates, guests, and bedroom count to collect price totals.
4. Normalize stay totals by nights to produce guest-facing nightly gross.
5. Build a comp price index: target total guest price / median comp total guest
   price for the same dates, guests, filters, and stay length.
6. Compare against host economics only after accounting for taxes/levies,
   platform fees, management, cleaning, utilities, consumables, linen,
   insurance, vacancy, and wear.

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
