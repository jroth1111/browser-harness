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
| Contribution margin per stay | Net payout - actual stay costs |
| Owner net RevPAN | Owner net amount / available nights |
| Promotion margin safety | Discounted expected payout - variable stay cost |

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
| Demand-adjusted price index | Your total guest price / comp median for the same demand-context class |
| Promotion eligibility gap | Valuable dates ineligible for promotion because of block or median-price rules |

Decision-gate outputs:

- `airbnb_listing_opportunity_snapshot` joins own public state to public A-comps
  and produces the top conversion or pricing fix candidates.
- `airbnb_conversion_diagnosis` separates visibility, search-card click,
  listing-page conversion, price friction, trust, photo/design, amenity, and
  guest-segment problems.
- `airbnb_photo_product_gap_audit` compares own guest-visible content against
  A-comps and produces top photo/product fixes before broad price cuts.
- `airbnb_gallery_cro_execution_board` turns photo/product evidence into an
  exact hero, first-five order, proof-shot queue, captions, rollback, and A/B
  review window before gallery edits are logged.
- `airbnb_case_study_replay` turns operator-derived rescue/coaching patterns
  into evidence-backed recommendation experiments.
- `airbnb_calendar_action_candidate` turns calendar, comp, demand, and cost
  primitives into date-level actions with rollback criteria.
- `airbnb_settings_drift_finding` audits pricing settings, rule-sets,
  discounts, promotions, Smart Pricing, and date restrictions against the
  intended strategy before date-level actions are trusted.

Canonical year-view artifacts for dashboarding:

- full snapshot JSON:
  `domain-skills/airbnb/.private-data/insights-collections/<run_id>.json`
- family extracts:
  `.../<run_id>-conversion-only.json`,
  `.../<run_id>-occupancy-only.json`,
  `.../<run_id>-quality-only.json`
- rendered family daily trend views:
  `.../<run_id>-<family>-only-daily.html`
- rendered family summary views:
  `.../<run_id>-<family>-only-summary.html`

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
| Recommendation win rate | Successful recommendations / reviewed recommendations |
| Evidence freshness score | Fresh source observations / required source observations |

Decision-gate output:

- `airbnb_operations_risk_snapshot` converts recurring review, message, task,
  cleaning, maintenance, fee, and turnover signals into risk-class alerts.

## Demand context metrics

| Metric | Formula or source |
|---|---|
| Event premium capture | Event-period ADR / non-event comparable ADR |
| Holiday pace variance | Holiday booking pace - non-holiday baseline pace |
| Weather sensitivity | Booking or cancellation variance by weather suitability score |
| Market-shock flag | Regulation, transport, weather, or supply signal active for date |

## Market research metrics

| Metric | Formula or source |
|---|---|
| Market absorption pct | `1 - dated_available_count / undated_inventory_count` with cap-hit caveats |
| Stay-length scarcity score | Availability drop or crowding by 1, 2, 3, 7, 14, and 28-night searches |
| Guest-capacity gap score | Supply drop as guest count increases, validated by comp demand |
| Booking velocity proxy | Public calendar unavailable share plus recent review timing, confidence-labeled |
| Comp thesis confidence | Supporting comps and counterexamples for the claimed winning variable |
| Archetype fit score | Evidence that a repeatable market archetype applies to the candidate |
| Channel opportunity score | Channel-specific supply, demand, price, customer fit, and content fit |
| Downside underwriting pass | Expected low-case net revenue clears required risk threshold |

Decision-gate outputs:

- `airbnb_market_research_decision` is conservative: `pursue` requires strict
  comp selection, counterexamples, listing maturity, and slow-season survival.
- `airbnb_channel_strategy_snapshot` recommends additional channels only after
  market evidence supports the product and operations can handle the channel.

## Analysis playbooks

### Market research and dealflow

Question: Should I pursue, watch, or reject this market, building, property, or
repositioning idea?

Required workflow:

- Run `market-research-playbook.md`.
- Define research mode: opportunity discovery, property validation, or
  repositioning.
- Capture public search context logged out before using public rank or counts.
- Run absorption, stay-length, guest-capacity, comp-thesis, channel, midterm,
  and underwriting checks.
- Store derived outputs in `schema-market-research.md`.

Checks:

- research mode and candidate product are explicit
- absorption scans preserve cap-hit state and map boundary
- stay-length and guest-capacity gaps use matching search contexts
- comp thesis has supporting comps and counterexamples
- winning variables are replicable by the candidate product
- channel demand and content fit are not assumed from Airbnb alone
- midterm/monthly is treated as a stay-length segment with opportunity cost
- underwriting uses internal costs and includes downside case
- final decision is `pursue`, `watch`, `reject`, or `needs_more_data`

### Current-state sensing

Question: What is true right now about the market, competitors, and my own
listings?

Required workflow:

- Run `workflows-current-state.md`.
- Capture market demand state before interpreting competitor prices.
- Capture public competitor and own-listing guest-visible state logged out.
- Capture private host-only calendar, pricing, reservation, Insights, and
  quality state logged in only when needed.
- Assemble listing-date state rows before creating recommendations.

Checks:

- public comp context uses exact dates, nights, guests, filters, currency,
  device, map boundary, and logged-in flag
- public comp search has field-level evidence: valid cards or listing IDs plus
  total-price evidence for the requested stay
- own listing public state and competitor state use matching search contexts
- private host state has current calendar, price, rule, and Insights snapshots
- demand-context flags explain high or low comp pressure
- each bottleneck tag has evidence references
- backend parity is proven or the weaker backend has been rejected for that
  source family

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
- demand calendar
- internal cost model
- recommendation/action history

Checks:

- comp price index by date and stay length
- no comp price index or price-risk alert is calculated from a run with zero
  valid competitor cards or missing total prices
- booking pace versus prior period or similar listings
- underpriced peak dates below 85% of comp median
- overpriced conversion risk above 125-130% of comp median with weak conversion
- long-stay discount leakage into high-demand periods
- Smart Pricing min/max or override conflicts
- pricing-software sync drift before trusting calendar prices
- stale manual overrides after their review window
- rule-set overlap, rule-set gaps, and date restrictions that contradict the
  intended strategy
- margin safety before discounting or lowering minimum stays
- prior recommendation outcomes for the same listing/date class

### Rule-set and settings drift audit

Question: Are active Airbnb settings still aligned with the intended strategy
for each listing/date window?

Required data:

- pricing settings
- rule-sets and applied date ranges
- calendar snapshots
- demand context
- internal margin floor
- intended strategy baseline
- pricing-software sync evidence when an external pricing source is the
  authority

Checks:

- discount or promotion leakage into peak, event, holiday, or strong-pace dates
- effective price after discounts below margin floor
- Smart Pricing active where custom rule-set or manual control should govern
- Smart Pricing minimum below margin floor
- overlapping rule-sets or conflicting active controls
- high-demand date without required rule-set coverage
- stale manual override beyond its review window
- pricing-software sync stale or flat when software should be the authority
- minimum-stay, check-in, or checkout restrictions blocking relevant demand
- promotion intended but Airbnb eligibility or median-price rules block it

### Calendar control

Question: Which sellable nights are blocked, unbooked, underpriced, or
restricted?

Required data:

- iCal/calendar snapshot
- host calendar status reason
- reservations
- rules and pricing settings
- demand context
- internal cost model

Checks:

- accidental block without defined reason
- orphan 1-2 night gaps between bookings
- minimum-stay choke for common guest searches
- restricted check-in/check-out preventing otherwise sellable stays
- prep/advance notice rules blocking short lead-time demand
- orphan-night discount still profitable after cleaning and linen cost

### Conversion diagnosis

Question: Is the problem visibility, click-through, listing-page conversion, or
price friction?

Required data:

- Insights conversion
- public search-card snapshot
- public listing content audit
- comp price matrix
- quality ratings/reviews
- recent content/action changes

Interpretation:

| Pattern | Likely issue | Action |
|---|---|---|
| Low impressions, strong conversion | Visibility or bookability | Check price, availability, restrictions, minimum stays |
| High impressions, low search-to-listing | Search-card weakness | Improve hero photo, title, visible value, badge/quality signal |
| High views, low booking conversion | Listing-page friction | Review total price, fees, rules, cancellation, photos, reviews |
| High wishlists, low bookings | Interest without commitment | Test price, flexibility, minimum stay, offer/promotion |
| Falling lead time | Demand window shift | Adjust pacing and last-minute strategy |
| Conversion changes after action | Intervention effect or confounder | Check action log, demand context, and control window |

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
- photo tour and room-level amenity coverage
- normalized photo/product evidence from own public and public comp collectors

Checks:

- own hero subject versus repeated A-comp hero subject
- whether first five photos prove the main guest promise
- bedroom, bed, bathroom, kitchen, living, and thesis-amenity proof
- whether amenity claims visible in text are proven by visible image labels or
  captions when available
- whether design gap flags explain weak conversion before price changes
- trust signal gap from review count, rating, badge visibility, or maturity
- whether content/rules match the intended guest segment
- whether price is the issue only after content and trust blockers are ruled out

Use `operator-insight-workflows.md` for photo/product gap audits and case-study
replay experiments derived from operator patterns.

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
- owner contracts
- capex/maintenance plans

Checks:

- net RevPAN by listing
- cancellation-adjusted revenue
- cleaning-fee recovery
- owner statement completeness
- market and stay-length profitability
- recommendation ROI by listing and owner

### Demand-context diagnosis

Question: Is performance explained by a demand driver outside Airbnb-native
data?

Required data:

- calendar snapshots
- public comp price matrix
- demand calendar
- market events
- holiday calendar
- weather and transport signals

Checks:

- high-demand dates without price or rule-set changes
- comp prices rising around events while own price stays flat
- holiday periods blocked by minimum stay or check-in rules
- weather/disruption periods causing cancellation or booking softness
- regulation or supply-change events affecting availability assumptions

### Recommendation review

Question: Which recommendations are useful enough to keep suggesting?

Required data:

- recommendations
- action logs
- experiments
- outcome attribution
- demand context
- relevant source observations and field quality

Checks:

- accepted vs rejected recommendation rate
- measured wins, losses, and inconclusive outcomes
- stale recommendations with expired evidence
- recommendation types repeatedly rolled back
- lift claims with too many confounders

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
| Data freshness breach | Required source is older than its freshness SLA |
| Low-confidence recommendation | Recommendation relies on low-confidence or conflicting fields |
| Negative contribution stay | Expected or actual stay margin below zero |
| Discount margin breach | Promotion or discount pushes expected stay below target margin |
| Demand event missed | Strong demand-context signal with no price/rule review |
| Stale action review | Implemented action has passed its review window without outcome attribution |

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
| Contribution margin by stay type | Reservation economics + internal costs |
| Demand-context calendar | Market events + holidays + weather + calendar |
| Recommendation outcomes | Recommendations + actions + outcome attribution |
| Data freshness and confidence | Capture runs + source observations + field quality |
