# Airbnb.com.au - Host Intelligence

Use this skill when the user is an Airbnb host or co-host and wants better
pricing, calendar control, conversion, operations, listing quality, comp-set
positioning, portfolio reporting, or Australian compliance awareness from
Airbnb.com.au data.

Read this with:

- `domain-skills/airbnb/scraping.md` for public search and listing extraction.
- `domain-skills/airbnb/data-model.md` for canonical tables, metrics, alerts,
  and build order.

## Operating principles

- Start with the host decision, then collect only the data needed to support it.
- Prefer Airbnb exports and structured host surfaces over brittle DOM scraping.
- Store snapshots over time. A single price, rank, calendar state, or conversion
  number is weak; a time series is useful.
- Normalize all public comp observations by dates, stay length, guest count,
  filters, geography, currency, and logged-in/device state.
- Separate guest-facing gross price from host payout and net owner economics.
- Treat tax, levy, registration, and regulation fields as compliance awareness,
  not legal or tax advice.

## Airbnb-specific vs reusable guidance

Keep Airbnb.com.au-specific material in this directory:

- Airbnb URL patterns, query parameters, search-card text shapes, and room IDs.
- Airbnb host surfaces such as Earnings, Calendar, Insights, Smart Pricing,
  rule-sets, quick replies, tasks, reviews, and the Regulations tab.
- Airbnb-specific semantics, such as search result totals excluding taxes,
  listing-page price widgets staying at `loading`, and Smart Pricing overriding
  rule-set intent.
- Australian Airbnb-visible fields such as registration/permit, tax, levy, and
  responsible-hosting surfaces.

Keep reusable browser/session mechanics in `interaction-skills/`:

- backend capability diagnosis for loaded-but-empty pages.
- solved-session HTTP retries after a browser profile passes a challenge.
- downloads, screenshots, tabs, dialogs, iframes, scrolling, cookies, and
  viewport mechanics.
- generic snapshot, confidence, and extraction-quality patterns that apply to
  other marketplace or travel sites.

## Source reliability ladder

| Tier | Source | Use first for |
|---|---|---|
| 1 | Earnings reports, CSV exports, iCal/calendar export, reservation print/details | Money, booked/blocked dates, reservation facts |
| 2 | Authenticated host UI: Insights, pricing, rule-sets, listing settings, messages, tasks | Funnel, rules, settings, operations |
| 3 | Public search results and public listing pages | Competitor visibility, total guest price, badges, amenity positioning |
| 4 | Internal/manual enrichments | Cleaning cost, owner mapping, maintenance tags, photo coverage, property reality |

## Host intake

Before scraping, capture the analysis frame:

| Input | Why |
|---|---|
| Host objective | Pricing, calendar leakage, conversion, operations, quality, comp-set, portfolio, compliance |
| Listing IDs or URLs | Stable join keys |
| Market/suburb/building | Comp-set boundary |
| Date horizon | Next 30/60/90/180 days or past reporting period |
| Guest segments | Adults, children, pets, business/family/group stays |
| Stay lengths | Weekend, midweek, 3-night, 7-night, monthly |
| Currency/account country | Price comparability |
| Logged-in permission | Determines whether host-only sources are available |
| Manual costs | Cleaning, linen, consumables, management, utilities, owner splits |

If the user is not logged in or cannot grant a browser session, limit the task to
public comp intelligence and ask for exported files when host economics are
needed.

## Authenticated source workflows

### Earnings and payout reporting

Primary output:

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

Extraction preference:

1. Download earnings report or CSV from the Airbnb earnings UI.
2. Parse the downloaded file with a structured CSV/PDF parser.
3. Use authenticated UI text only when exports are unavailable.

Use for:

- net ADR
- net RevPAN
- owner statements
- fee leakage
- refund/adjustment tracking
- payout timing
- cleaning-fee recovery

### Reservation details

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

### Calendar and iCal

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

Calendar snapshots should be daily for forward-looking dates. Never overwrite the
previous snapshot; booking pace depends on history.

### Listing settings and content audit

Capture monthly and after edits:

- title
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

Use public listing pages to verify how the listing appears to guests. Use the
host editor to check settings that are hidden from guests.

### Insights

Use Insights when available through professional hosting tools.

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

Use Insights as the funnel truth source. Public scraping can tell what the guest
sees, but it cannot replace authenticated conversion metrics.

### Pricing settings and Smart Pricing

Capture weekly and after edits:

- base price
- weekend price
- Smart Pricing enabled
- Smart Pricing min/max
- weekly and monthly discounts
- early-bird and last-minute discounts
- custom promotions
- cleaning, pet, extra guest, and additional fees

Important Airbnb-specific rule: Smart Pricing can override rule-set intent. If a
host expects a custom rule-set to control a period, check whether Smart Pricing
is active for that listing and date range.

### Rule-sets

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

### Messages and quick replies

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

### Reviews and quality themes

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

### Tasks and team operations

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

### Australian compliance awareness

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

## Public market workflows

Use `domain-skills/airbnb/scraping.md` for the browser steps. For a host, public
market observations should always record:

- observation timestamp
- destination or map area
- check-in/check-out
- nights
- adults/children/pets
- filters
- device type
- logged-in state
- currency
- listing URL
- rank/page/scroll depth
- visible total guest price
- visible nightly component if shown
- rating and review count
- badge
- bedrooms, beds, bathrooms, max guests
- core amenities
- availability for the search dates
- minimum-stay message if visible
- hero-photo subject
- QA screenshot reference for sampled runs

Public comp data is only decision-grade when it is normalized by exact guest
search context.

## Analysis playbooks

### Revenue management

Question: Am I pricing correctly by date, demand window, stay length, and guest
type?

Required data:

- future calendar snapshots
- reservation economics
- pricing settings
- Insights occupancy/rates
- public comp price matrix
- rule-sets and discounts

Checks:

- comp price index by date and stay length
- booking pace versus prior period or similar listings
- underpriced peak dates below 85% of comp median
- overpriced conversion risk above 125-130% of comp median with weak conversion
- long-stay discount leakage into high-demand periods
- Smart Pricing min/max or override conflicts

### Calendar control

Question: Which sellable nights are blocked, unbooked, underpriced, or
restricted?

Required data:

- iCal/calendar snapshot
- host calendar status reason
- reservations
- rules and pricing settings

Checks:

- accidental block without defined reason
- orphan 1-2 night gaps between bookings
- minimum-stay choke for common guest searches
- restricted check-in/check-out preventing otherwise sellable stays
- prep/advance notice rules blocking short lead-time demand

### Conversion diagnosis

Question: Is the problem visibility, click-through, listing-page conversion, or
price friction?

Required data:

- Insights conversion
- public search-card snapshot
- public listing content audit
- comp price matrix
- quality ratings/reviews

Interpretation:

| Pattern | Likely issue | Action |
|---|---|---|
| Low impressions, strong conversion | Visibility or bookability | Check price, availability, restrictions, minimum stays |
| High impressions, low search-to-listing | Search-card weakness | Improve hero photo, title, visible value, badge/quality signal |
| High views, low booking conversion | Listing-page friction | Review total price, fees, rules, cancellation, photos, reviews |
| High wishlists, low bookings | Interest without commitment | Test price, flexibility, minimum stay, offer/promotion |
| Falling lead time | Demand window shift | Adjust pacing and last-minute strategy |

### Guest operations

Question: Are messages, check-in, checkout, cleaning, and maintenance being
handled consistently?

Required data:

- reservations
- message workflow timelines
- operations tasks
- reviews and messages

Checks:

- scheduled message skipped
- check-in instructions missing or late
- same-day turnover overload
- repeated maintenance keyword
- pet stay without cleaning scope adjustment
- host review not submitted after checkout

### Listing quality

Question: Which amenities, photos, rules, or accuracy issues affect ratings and
conversion?

Required data:

- listing content audit
- public listing snapshot
- Insights quality
- reviews
- comp listing snapshots

Checks:

- photo coverage gaps
- amenity mismatch between listing and property reality
- repeated accuracy complaints
- value rating decline alongside high comp price index
- cleanliness decline tied to turnover load or cleaner assignment

### Competitive positioning

Question: How do my listings compare against similar Airbnb.com.au listings?

Required data:

- public search runs
- public comp listing snapshots
- public price/availability matrix
- own listing content and price settings

Checks:

- same dates, guests, stay length, currency, and filters
- like-for-like capacity and property type
- rating/review/badge premium
- amenity gaps such as parking, pool/spa, family features, workspace/Wi-Fi, pet
  suitability
- hero-photo subject and differentiator tags

### Portfolio reporting

Question: Which listings, owners, markets, and stay types are actually
profitable?

Required data:

- listing master
- calendar snapshots
- reservation economics
- payout/tax/levy table
- internal costs and owner mapping

Checks:

- net RevPAN by listing
- cancellation-adjusted revenue
- cleaning-fee recovery
- owner statement completeness
- market and stay-length profitability

## Example host workflow

Task: diagnose why a Melbourne CBD apartment has weak bookings for the next 60
days.

1. Export earnings/reservations for the last 12 months and current forward
   bookings.
2. Snapshot the calendar for the next 180 days, including blocked reasons where
   visible.
3. Capture Insights conversion, occupancy/rates, and quality for the same
   listing.
4. Capture pricing settings, discounts, Smart Pricing, and applied rule-sets.
5. Run public searches for 2-night weekend, 3-night midweek, 7-night, and
   family/pet segments in the same area.
6. Normalize public comp total price by nights and guest segment.
7. Produce findings in this order: inventory leakage, price index, conversion
   funnel, quality/amenity gaps, operations risks.

## Source anchors

Useful Airbnb help pages for validating UI semantics:

- `https://www.airbnb.com.au/help/article/2500` - performance dashboard and Insights areas.
- `https://www.airbnb.com.au/help/article/3632` - earnings reports and CSV export.
- `https://www.airbnb.com.au/help/article/99` - calendar sync and iCal behavior.
- `https://www.airbnb.com.au/help/article/3612` - why calendar nights may be blocked.
- `https://www.airbnb.com.au/help/article/2061` - rule-sets.
- `https://www.airbnb.com.au/help/article/1168` - Smart Pricing.
- `https://www.airbnb.com.au/help/article/459` - payout calculation.
- `https://www.airbnb.com.au/help/article/2897` - scheduled quick replies.
- `https://www.airbnb.com.au/help/article/3305` - short-term rental regulations.
