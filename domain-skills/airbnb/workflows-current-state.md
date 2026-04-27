# Airbnb.com.au - Current-State Workflows

Use this file when the host asks for the current state of the market,
competitors, or their own listings. These workflows are the sensing layer for a
closed-loop revenue system. They capture state; they do not apply price changes.

For public guest-visible data, stay logged out by default. For private host-only
data, use the authenticated host flow in `session-continuity.md`.

## Operating rule

Use the least-privileged source that answers the question.

| Question | Auth state | Primary files |
|---|---|---|
| What does a guest see in the market? | Logged out | `public-market.md`, `schema-public-market.md` |
| What are competitors charging and showing? | Logged out | `public-market.md`, `schema-public-market.md` |
| How does my listing appear to guests? | Logged out for public page/search; logged in only for hidden settings | `public-market.md`, `host-sources.md` |
| What is my bookable calendar and price state? | Logged in or iCal/export where available | `host-sources.md`, `schema-core.md`, `schema-performance.md` |
| What are my conversion, quality, and earnings signals? | Logged in | `host-sources.md`, `schema-performance.md`, `schema-core.md` |
| What demand drivers explain the state? | Public/external official sources | `schema-demand-context.md` |

Do not mix logged-out guest-market observations with logged-in personalized
observations in the same comp set.

## Workflow 0 - Define The State Run

Create a state run before collecting data. This keeps every observation
comparable.

Required inputs:

- host objective: pricing, restrictions, content, comp positioning, or calendar
  leakage
- listing IDs and public URLs
- market, suburb, building, or map boundary
- forward horizon: normally 0-90 days for tactical state and 90-365 days for
  seasonal state
- date samples: weekdays, weekends, peak dates, event dates, orphan gaps, and
  school/public holidays
- guest segments: adults, children, pets, work trip, family, group, long stay
- stay lengths: 1, 2, 3, 5, 7, 14, and 28 nights where relevant
- currency and observer country
- device type and logged-in flag

State run fields:

```text
state_run_id
observed_at
run_type
market
suburb_or_area
map_boundary
listing_ids
date_horizon_start
date_horizon_end
date_samples
guest_segments
stay_lengths
currency
device_type
logged_in_flag
backend
source_files
operator_notes
```

Acceptance rules:

- Every downstream observation references `state_run_id`.
- Public comp work normally uses `logged_in_flag = false`.
- If a logged-in public run is intentionally performed, it gets a separate
  `state_run_id` and a note explaining the personalization test.

## Workflow 1 - Market Demand State

Goal: explain demand pressure before looking only at competitor prices.

Sources:

- official public holiday and school holiday calendars
- venue/event calendars
- sport, concert, conference, festival, and tourism calendars
- weather and severe-weather forecasts
- transport and access disruption sources
- regulation or supply-change signals
- host manual notes about local demand drivers

Capture:

```text
market
suburb_or_area
calendar_date
day_of_week
weekend_flag
school_holiday_flag
public_holiday_flag
long_weekend_flag
event_name
event_category
event_intensity_score
expected_guest_segments
weather_risk_flag
transport_disruption_flag
regulatory_or_supply_signal
demand_confidence
observed_at
source_url
```

Cadence:

- Daily for next 14 days when pricing actions are active.
- Weekly for next 90 days.
- Monthly or event-triggered for 91-365 days.

Outputs:

- `airbnb_demand_calendar`
- event/holiday flags for booking-pace and comp-price interpretation
- manual review flags for high-intensity dates

## Workflow 2 - Public Competitor Market State

Goal: find what guest-visible substitutes are available, bookable, and priced at
right now.

Auth/backend:

- Start logged out.
- Use Lightpanda when the URL family passes capability checks.
- Use fresh/headful Chrome logged out when Lightpanda misses visual/rank/price
  evidence.
- Do not use the host auth bundle for normal comp work.

Search matrix:

For each market run, sample the same search context across:

- destination or map boundary
- check-in/check-out dates
- stay length
- adult/child/pet count
- bedrooms or other filters
- flexible versus exact dates when relevant
- desktop and mobile only when device comparison matters

Capture from each search:

```text
search_run_id
state_run_id
observed_at
destination
map_area_bounds_description
check_in_date
check_out_date
nights
guest_count_adults
guest_count_children
guest_count_pets
filters_applied
currency
logged_in_flag
device_type
results_count_visible
```

Capture from each result card:

```text
result_position
page_number_or_scroll_depth
listing_url
listing_id_if_extractable
visible_title_short
visible_location_label
visible_rating
visible_review_count
visible_badge
top_home_highlight_visible
top_percent_label
visible_price_total
visible_price_per_night
fees_included_flag
available_flag
hero_photo_subject_tag
obvious_differentiator_tags
```

Competitor inclusion rules:

- Same property type or defensible substitute.
- Similar capacity, bedrooms, beds, bathrooms, and guest segment.
- Same date/stay/guest search context.
- Same currency and logged-in state.
- Exclude irrelevant suburbs unless the host explicitly wants broader market
  substitution.
- Keep outliers, but tag them instead of silently deleting them.

Outputs:

- `airbnb_public_search_run`
- `airbnb_public_search_result_snapshot`
- `airbnb_public_price_availability_matrix`
- competitor supply count and availability share
- median and percentile guest-total prices
- comp price index inputs

## Workflow 3 - Competitor Listing State

Goal: understand why competitors can charge more, rank better, or convert better.

For each selected comp listing, open the public listing page logged out.

Capture:

```text
comp_listing_id
listing_url
market
property_type
room_type
max_guests
bedrooms
beds
bathrooms
rating
review_count
public_badges
top_home_highlight_visible
visible_amenities_core
parking_flag
pool_spa_flag
pet_friendly_flag
workspace_wifi_flag
family_amenities_flag
accessible_features_flag
house_rules_summary_flags
cancellation_policy_visible
photo_count
hero_photo_subject
review_theme_positive_tags
review_theme_negative_tags
observed_at
```

Review and content tags:

- cleanliness praise or complaint
- view/location praise
- check-in ease or friction
- bedding/sleep comfort
- noise
- Wi-Fi/workspace
- parking
- family suitability
- pet suitability
- value complaints

Outputs:

- `airbnb_public_comp_listing_snapshot`
- comp quality index inputs
- amenity gap list
- hero-photo/content benchmark
- quality-adjusted comp set

## Workflow 4 - Own Listing Guest-Visible State

Goal: see the host's listing exactly as a guest sees it before using private
host data.

Auth/backend:

- Logged out for public search and public listing pages.
- Same search contexts as competitor Workflow 2.
- Logged in only for private editor fields that are not guest-visible.

Capture guest-visible state:

```text
listing_id
public_listing_url
search_appears_flag
search_result_position
visible_title_short
visible_location_label
visible_price_total
visible_price_per_night
rating
review_count
visible_badges
hero_photo_subject
property_type
room_type
max_guests
bedrooms
beds
bathrooms
amenities_visible
house_rules_visible
cancellation_policy_visible
public_review_themes
guest_total_price_by_search_context
availability_by_search_context
minimum_stay_message
observed_at
logged_in_flag
```

Compare against competitors:

- total guest price percentile
- rating/review/badge percentile
- amenity gaps
- bookability gaps
- search-card weakness
- listing-page friction clues

Outputs:

- `airbnb_listing_content_audit`
- own listing rows in public search/result snapshots
- own listing public price/availability matrix
- guest-visible state summary

## Workflow 5 - Own Listing Private Host State

Goal: capture the host-only state that explains performance, economics, and
bookability.

Auth/backend:

- Logged in only.
- Prefer exports: earnings CSV, iCal/calendar export, downloadable reports.
- Use authenticated UI only when export is unavailable or the field is visible
  only in the UI.

Capture calendar and pricing:

```text
listing_id
calendar_date
status
status_reason
reservation_id
nightly_price
custom_price_flag
smart_pricing_flag
rule_set_id
minimum_stay
maximum_stay
check_in_allowed
checkout_allowed
observed_at
```

Capture reservation/economics:

```text
reservation_id
listing_id
reservation_status
booking_created_at
check_in_date
check_out_date
nights
guest_count_total
guest_count_children
guest_count_pets
booking_subtotal
cleaning_fee
other_host_fees
airbnb_host_service_fee
taxes_withheld
adjustments
net_payout
guest_total_price
currency
```

Capture conversion and quality:

```text
first_page_search_impressions
search_to_listing_conversion
listing_to_booking_conversion
views
wishlist_additions
booking_lead_time
occupancy_rate
nights_blocked
nights_booked
unbooked_nights
average_length_of_stay
average_nightly_rate
overall_rating
accuracy_5star_pct
checkin_5star_pct
cleanliness_5star_pct
communication_5star_pct
location_5star_pct
value_5star_pct
comparison_to_similar_listings
```

Capture private settings:

```text
base_price
weekend_price
smart_pricing_enabled
smart_pricing_min
smart_pricing_max
weekly_discount_pct
monthly_discount_pct
early_bird_discount_rules
last_minute_discount_rules
custom_promotion_active
cleaning_fee
pet_fee
extra_guest_fee
rule_set_name
date_range_start
date_range_end
length_of_stay_discount
minimum_nights
maximum_nights
check_in_day_rules
checkout_day_rules
instant_book_enabled
cancellation_policy
registration_or_permit_id
```

Outputs:

- `airbnb_calendar_snapshot`
- `airbnb_reservation`
- `airbnb_reservation_economics`
- `airbnb_pricing_settings`
- `airbnb_rule_set`
- `airbnb_insights_conversion`
- `airbnb_insights_occupancy_rates`
- `airbnb_insights_quality`
- private capability receipts

## Workflow 6 - Build Listing-Date State

Goal: combine all observations into one date-level state object for control and
diagnosis.

State key:

```text
listing_id + calendar_date + observed_at
```

Derived fields:

```text
lead_time_days
status
status_reason
current_nightly_price
current_guest_total_price
minimum_stay
maximum_stay
check_in_allowed
checkout_allowed
smart_pricing_flag
rule_set_id
custom_price_flag
booked_flag
blocked_flag
available_to_sell_flag
orphan_gap_flag
same_day_turnover_risk
current_comp_price_index
quality_adjusted_comp_price_index
market_compression_score
event_intensity_score
booking_pace_gap
conversion_health_score
value_rating_risk
expected_cleaning_margin
data_freshness_score
field_confidence_score
```

Current-state interpretation:

| State pattern | Meaning |
|---|---|
| Available, behind pace, high comp price index | Potential overpricing or weak demand |
| Available, behind pace, fair comp price index | Diagnose conversion, restrictions, content, or demand |
| Available, ahead of pace, low comp price index | Potential underpricing |
| Blocked without reason | Calendar leakage |
| Available but absent from common searches | Restriction choke or visibility issue |
| High views and weak booking conversion | Listing-page or total-price friction |
| Low impressions and good conversion | Visibility or bookability issue |
| Value rating falling with high price index | Reputation/value risk |

Output:

- date-level current-state table
- bottleneck tags
- evidence references
- recommendation candidates for `decisioning.md`

## Workflow 7 - Cadence

Event-driven loop:

- Trigger: new booking, cancellation, alteration, block, review, comp spike, or
  event discovery.
- Run: affected listing/date state rebuild.
- Output: changed-state note and any urgent bottleneck tags.

Daily tactical loop:

- Horizon: 0-90 days.
- Run: calendar, comp prices, availability, orphan gaps, demand flags.
- Output: high-demand unbooked dates, under/overpriced risk, restriction choke,
  and margin-risk candidates.

Weekly revenue loop:

- Horizon: 90-365 days.
- Run: demand calendar, school/public holidays, event periods, comp-set refresh,
  rule-set review.
- Output: medium-term pace and peak-date protection candidates.

Monthly learning loop:

- Run: outcome attribution, pace curve updates, comp-set weights, elasticity
  estimates, conversion/quality trends.
- Output: model calibration notes and changed guardrail recommendations.

Post-stay reputation loop:

- Trigger: review posted or message/theme discovered.
- Run: quality category, review themes, operations task history, pricing/value
  context.
- Output: value-rating risk, content fixes, operations fixes, or price-premium
  adjustment candidates.

## Quality Gates

Before using current-state data for recommendations:

- Public comps are logged out unless explicitly marked as personalization tests.
- Prices have exact dates, nights, guests, currency, and logged-in state.
- Competitors are like-for-like or tagged with substitution rationale.
- Own listing public state and competitor state use the same search context.
- Private host state has a capability receipt and source freshness timestamp.
- Calendar state is a snapshot, not an overwritten latest-only value.
- Demand-context sources are cited and confidence-scored.
- Every derived bottleneck has source evidence, not just an inference.

## Deliverables

For a host-facing current-state report, produce:

1. Market state: demand calendar, compression, events, holidays, disruption.
2. Competitor state: visible supply, comp prices, availability, trust signals,
   amenity gaps, review themes.
3. Own listing public state: guest-visible price, rank, content, availability,
   badges, reviews, and bookability.
4. Own listing private state: calendar, reservations, pricing settings,
   rule-sets, Insights, quality, economics.
5. Listing-date state table: one row per listing/date/observed_at.
6. Bottleneck diagnosis: visibility, search-card appeal, listing-page friction,
   price friction, restriction choke, calendar leakage, quality risk, or
   operational constraint.
7. Evidence gaps: stale, missing, logged-in/public mismatch, low confidence, or
   not comparable.
