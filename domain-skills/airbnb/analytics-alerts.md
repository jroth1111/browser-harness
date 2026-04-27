# Airbnb.com.au - Analytics and Alerts

Use this file after collecting host/account data and public market data.

## Revenue and yield metrics

| Metric | Formula |
|---|---|
| Booked nights | Count booked `calendar_date` values |
| Available nights | Sellable nights excluding defined non-sellable blocks |
| Occupancy rate | Booked nights / available nights |
| ADR | Nightly revenue / booked nights |
| Net ADR | Net payout allocated to nights / booked nights |
| RevPAN | Revenue / available nights |
| Net RevPAN | Net payout / available nights |
| Booking lead time | Check-in date - booking created date |
| Booking pace | Future booked nights as of `observed_at` |
| Cancellation-adjusted revenue | Confirmed revenue - refunds/adjustments + cancellation fees |
| Fee ratio | Fees charged / total guest price |
| Host-fee take rate | Host service fee / booking subtotal |
| Cleaning-fee recovery | Cleaning fee collected / actual cleaning cost |
| Long-stay discount impact | Discounted revenue vs standard nightly revenue |

## Conversion metrics

| Metric | Formula or source |
|---|---|
| Search visibility index | First-page impressions vs target/similar listings |
| Search-card conversion | Search-to-listing conversion |
| Listing-page conversion | Listing-to-booking conversion |
| Wishlist friction index | High wishlists plus low bookings |
| Returning guest rate | Airbnb returning guests metric |
| Comp price index | Your total guest price / median comp-set total guest price |
| Comp quality index | Rating/review/badge profile vs comp set |
| Minimum-stay choke score | Failed or weakened bookability from LOS rules |

## Quality and operations metrics

| Metric | Formula |
|---|---|
| Cleanliness defect rate | Cleanliness-negative tags / stays |
| Check-in friction rate | Check-in-negative tags / stays |
| Accuracy complaint rate | Accuracy-negative tags / stays |
| Maintenance recurrence | Repeated issue tags by listing |
| Message workflow success | Scheduled messages sent on time / eligible reservations |
| Review completion rate | Host reviews submitted / eligible stays |
| Low-rating early warning | Category rating decline vs prior period |
| Turnover load | Check-ins + checkouts by date |
| Pet-stay margin | Pet fees - pet-related cleaning/repair cost |

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

## `airbnb_alerts`

Alert event table.

Fields:

- `alert_id`
- `listing_id`
- `reservation_id`
- `calendar_date`
- `alert_type`
- `severity`
- `trigger_value`
- `threshold_value`
- `source_tables`
- `recommended_action`
- `status`
- `created_at`
- `resolved_at`

## Alert rules

| Alert | Trigger |
|---|---|
| High-demand date unbooked | Future date remains available while target pace is behind |
| Underpriced peak date | Your total guest price < 85% of comparable median |
| Overpriced conversion risk | Your price > 125-130% of comp median and conversion weakens |
| Accidental block | Blocked night without defined reason |
| Orphan-night alert | 1-2 night gap between bookings |
| Minimum-stay choke | Common guest search dates blocked by min-stay rules |
| Smart Pricing conflict | Smart Pricing active where custom rule intention exists |
| Discount drift | Discount applies to peak or event period unexpectedly |
| Quality drop | Any category rating falls below threshold |
| Repeated review theme | Same negative theme appears twice within N stays |
| Message skipped | Scheduled check-in/checkout message skipped |
| Turnover overload | Same-day checkouts/check-ins exceed cleaner capacity |
| Levy/tax field mismatch | Airbnb-visible levy/tax field inconsistent with listing jurisdiction |

## Highest-ROI dashboard

| Tile | Source tables |
|---|---|
| Net RevPAN by listing | Reservation economics + calendar |
| Forward booking pace | Calendar snapshots + reservations |
| Comp price index | Public price matrix + pricing settings |
| Search funnel | Insights conversion |
| Occupancy and blocked-night mix | Calendar + Insights |
| Orphan nights | Calendar snapshot |
| Rule-set conflicts | Rule-set + pricing settings + calendar |
| Quality category trend | Insights quality + reviews |
| Review theme recurrence | Reviews |
| Turnover workload | Reservations + operations tasks |
| Message workflow status | Message workflow + reservations |
| High-demand unbooked dates | Calendar + comp availability + price matrix |
