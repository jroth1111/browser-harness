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

General backend parity rules live in `interaction-skills/backend-capability.md`.
For Airbnb, apply those rules to Airbnb-specific search contexts, listing URLs,
host pages, and required fields below.

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

Empirical note from 2026-04-27: Victoria public-holiday and school-term source
URLs were reachable with normal HTTP fetches and contained the expected 2026
holiday/term markers. Keep these as demand-context sources, but still store the
source URL, observed timestamp, and confidence for each extracted flag.

## Workflow 2 - Public Competitor Market State

Goal: find what guest-visible substitutes are available, bookable, and priced at
right now.

Auth/backend:

- Start logged out.
- Use Lightpanda when the URL family passes capability checks.
- Use fresh/headful Chrome logged out when Lightpanda misses visual/rank/price
  evidence.
- Do not use the host auth bundle for normal comp work.
- Require the general backend-invariant output rule from
  `interaction-skills/backend-capability.md`: a Lightpanda run and a headful
  Chrome run for the same Airbnb search context should normalize to matching
  search-result records. If they do not, keep the headful data for host
  intelligence and store the Lightpanda result only as a capability receipt.

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

Field-level acceptance:

- A public search run is usable for competitor state only when it has result-card
  evidence, not merely page text.
- For comp price intelligence, require listing URLs or stable listing IDs plus
  visible total prices for the exact dates, guests, currency, and filters.
- For rank/visibility intelligence, require stable card ordering or record that
  rank is unavailable for the backend.
- If `document.body.innerText` contains only the Airbnb no-JavaScript shell,
  navigation/menu text, or a search form with no result cards, classify the
  source as `backend_capability_failed`.
- Do not calculate median comp price, comp price index, market compression, or
  under/overpricing alerts from a search run with zero valid cards or zero
  valid prices.

Empirical backend rule:

- On 2026-04-27, logged-out Lightpanda could load Airbnb Melbourne search pages
  but produced zero `/rooms/` links and zero AUD total prices. Fresh logged-out
  headful Chrome for the same search context produced hydrated result text,
  room links, and total prices. For Airbnb public search/card extraction, use
  Lightpanda only after it proves field-level parity with headful Chrome.

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
- `airbnb_public_target_competitor_snapshot`
- competitor supply count and availability share
- median and percentile guest-total prices
- comp price index inputs

Executable workflow:

- Use `scripts/collect_competitors.py` for closest-competitor collection from
  the latest live-listing inventory.
- Run logged out in a fresh browser profile.
- Capture multiple future check-in dates as separate search contexts so the
  comp set and price matrix form a time series over repeated runs.
- Store raw search/listing checkpoints and receipts under ignored private paths.

## Workflow 3 - Competitor Listing State

Goal: understand why competitors can charge more, rank better, or convert better.

For each selected comp listing, open the public listing page logged out. The
selected comp list may come from Workflow 2, a host-curated comp URL list,
Google or search-engine discovery, or Airbnb listing URLs found in prior
headful public searches. Do not make Workflow 3 depend exclusively on
Lightpanda search-result links.

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

Field-level acceptance:

- A listing snapshot is usable only when it captures at least the room/listing
  ID, title or location label, capacity/property facts, rating or review count
  where visible, and amenity/content signals relevant to the comp decision.
- If a backend returns only the Airbnb no-JavaScript shell or a skeletal listing
  title without property facts, treat it as a backend capability failure for the
  listing snapshot and retry in logged-out headful Chrome.
- Listing-page price widgets are not enough for comp pricing unless they render
  a total guest price for the exact dates and guests. Prefer Workflow 2 search
  totals for the price matrix.

Empirical note from 2026-04-27: a logged-out headful Chrome room page opened
from a hydrated public search result produced a usable comp listing snapshot:
title, capacity text, rating text, review signal, and amenity hits were visible.
Use this path when Lightpanda search cannot provide room links or when
Lightpanda listing pages expose only skeletal/no-JavaScript content.

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
- Requires either host-provided public listing URLs or a reliable
  private-host-to-public listing mapping. If neither exists, emit
  `own_listing_public_url_missing` and do not infer guest-visible state from
  host-only pages.
- Empirical note from 2026-04-27: restored Lightpanda auth loaded
  `/hosting/listings`, but that page exposed zero `/rooms/` links. Do not assume
  the host listings overview provides a public URL mapping; verify the mapping
  field before running own-listing public capture.

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

Start by collecting the live-listing inventory. This establishes the authoritative
private listing set for subsequent calendar, pricing, Insights, and quality
collection.

Live-listing inventory capture:

```text
listing_id
listing_name
nickname
status
api_state
public_listing_url
host_editor_path
address
address_source
location_label
property_type_summary
max_guests
bedrooms
beds
bathrooms
photo_count
instant_book_enabled
modified_at
source_overview
source_detail_url
observed_at
```

Live-listing inventory source order:

1. Use `/hosting/listings` and `BeehiveGetListingsQuery` for enumeration,
   pagination, status counts, and fields present in the API row.
2. Filter `status == ACTIVE` for live/listed output.
3. Open each active listing's authenticated editor route for private detail
   fields such as full address, guest count, property type, and photo tour
   signals.
4. Store JSON/CSV outputs in ignored `.private-data/listing-collections/` and a
   receipt in `.session-store/capability/`.

Live-listing acceptance:

- Overview pagination reconciles to Airbnb's reported `metadata.totalCount`.
- Status counts are retained before active filtering.
- Required fields for every active listing: `listing_id`, `listing_name`,
  `status`, `address`, `bedrooms`, `bathrooms`, `beds`, and `max_guests`.
- Private artifacts may contain full addresses; shared docs and commits must
  not.

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
listing_id
metric_family
metric_subroute
period_label
relative_ds_start
relative_ds_end
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
source_query
source_url
observed_at
```

Insights collection rule:

- Capture Insights per listing, not as "All listings" averages.
- Prefer Airbnb's authenticated Performance APIs once discovered:
  `ListOfMetricsQuery` for summary windows and `ChartQuery` for chart/history
  points.
- Use `AIRBNB_INSIGHTS_CHART_MODE=rolling_daily` with rolling 7-day `ChartQuery`
  windows for recent daily primitives. Use
  `AIRBNB_INSIGHTS_CHART_MODE=single_window` for broad trend sweeps when API
  call volume is the binding constraint; preserve `series_granularity` because
  longer Airbnb chart windows may return weekly or monthly points.
- Compose higher-period views from daily primitives when the metric is additive;
  keep Airbnb's own period summary rows for rates, ratios, and averages.
- Stop and store a partial receipt on sustained HTTP `429`; resume after
  cooldown instead of continuing to send requests.
- Treat backend/API collection as canonical for Insights fields when the API
  response is listing-scoped and field-complete. Use browser rendering only to
  establish auth/bootstrap, discover request shapes, verify parity, or fill
  fields the API does not expose.
- Latest verified runs on 2026-04-27:
  `airbnb-insights-20260427T095000Z-daily30` covered 27 active listings across
  16 routes with 2,025 summary rows and 26,784 daily chart rows;
  `airbnb-insights-20260427T095000Z-trend365` covered the same listing/route
  scope with 11,232 monthly trend rows. Both receipts recorded 0 failures.

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

Partial-state rule:

- If comp median price is missing, mark price-index fields as `unknown` and
  suppress underpriced/overpriced recommendations.
- If own public listing state is missing, tag `own_listing_public_url_missing`
  and suppress search-card and guest-visible listing-page conclusions.
- If private host state is available but public market state failed, the system
  can still report calendar, reservation, pricing-setting, and Insights state,
  but must label market-relative conclusions as evidence gaps.
- A listing-date state row may exist as a diagnostic shell, but it is not a
  pricing recommendation input until the required public, private, and demand
  evidence for that decision has passed field-level validation.

Empirical note from 2026-04-27: with headful public comp search available, a
diagnostic listing-date row could include competitor card count, total-price
count, and a sample comp median. It remained recommendation-ineligible because
own public listing state and host calendar/iCal state were missing. Preserve
that distinction: comp evidence alone is not enough for host pricing action.

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
- Requires prior recommendation/action history and booking outcomes. A one-off
  current-state run can prepare the tables but cannot validate elasticity or
  recommendation accuracy.

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
- Backend parity is proven for any backend-specific extraction path, or the
  non-parity is recorded and the workflow falls back to a backend that produces
  the canonical fields.
- Page-level success is not enough. Each source must pass field-level acceptance
  for the specific workflow output it feeds.

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
