# Airbnb.com.au - Market Research Playbook

Use this file when the user asks where to start, expand, buy, rent, arbitrage,
co-host, reposition, or validate an Airbnb/short-term-rental property. This
playbook is self-contained: it includes the operator heuristics, data checks,
decision rules, and output format needed to run market research directly.

Market research answers one question:

```text
Can this exact product, in this exact boundary, for these guest segments and
stay lengths, produce enough margin after costs and risk?
```

Do not reduce market research to "city looks good" or "comps have high ADR".
The useful decision is property-specific and product-specific: what should be
offered, where, to whom, at what stay length, on which channel, and with what
downside protection.

Every market research run must produce a `Market Research Evidence Pack`:

```text
research mode gate
map-friction assessment
strict comp selection
listing maturity filter
counterexample matrix
slow-season survival model
underwriting summary
decision report
```

Do not issue a `pursue` decision without all seven parts. If the evidence pack is
incomplete, use `watch`, `reject`, or `needs_more_data`.

Use `scripts/decision_gates.py` to evaluate completed evidence packs. The
evaluator is a pure local helper: it consumes collected rows and returns a
decision record with `decision`, `confidence`, `evidence_refs`,
`missing_required_evidence`, `do_not_use_reason`, and
`recommended_next_action`.

For rental arbitrage, `realestate-building-rentals.md` supplies REA asking-rent,
building lifecycle, watchlist, and suburb-search evidence. This playbook owns
the underwriting model and the pursue/watch/reject decision.

## Ownership

- Use this when: the user asks where to expand, what property/product to target,
  whether a building/deal can work, or whether to pursue/watch/reject a market
  or arbitrage opportunity.
- Owns: research mode gates, proof standards, absorption/stay-length/capacity
  scans, comp-thesis counterexamples, slow-season survival, channel strategy,
  underwriting, and pursue/watch/reject decisions.
- Does not own: raw public Airbnb extraction mechanics, REA collection,
  host-private source collection, or durable row field lists.
- Next hop: `public-market.md` for Airbnb public mechanics,
  `realestate-building-rentals.md` for REA rent evidence, schema files for row
  contracts, and `decisioning.md` when a decision becomes an action.

## When to use

Use this playbook for:

- "Where should I Airbnb?"
- "Is this market saturated?"
- "Can this building/house work?"
- "Should I take this arbitrage/co-host/ownership deal?"
- "What property type should I look for?"
- "What amenities or design should I build before launch?"
- "Should I use midterm/monthly stays in this market?"
- "How do I compete against hotels, Vrbo, Booking.com, or other channels?"

If the user already has live listings and asks about a tactical issue such as
unbooked dates, pricing, rank, or conversion, start with
`workflows-current-state.md` and `analytics-alerts.md`; then use this playbook
only for the market/product-fit layer behind the issue.

## Core posture

- Start disqualification-first. Reject weak opportunities before money is spent.
- Treat public Airbnb search as a live market sensor, not as perfect truth.
- Public search work is logged out by default. Owner login can personalize rank.
- Separate supply, demand, price, quality, and product differentiation. A market
  can have many listings and still be undersupplied for a specific product.
- Counts, calendars, and price widgets are evidence with caveats. Airbnb may cap
  visible results, broaden map results, personalize pages, or show blocked dates
  that are not booked.
- A comp is useful only if it is comparable to the product the host can actually
  create. Do not validate a plain apartment with a comp whose success depends on
  a huge balcony, private pool, waterfront access, or another unreproducible
  feature.
- A beautiful winner is not evidence by itself. It becomes underwriting evidence
  only when the host can reproduce the reason it wins, or when equal-or-weaker
  comps in the same buying context still clear the required economics.
- A market thesis needs counterexamples. If every successful comp has one feature
  and similar comps without that feature fail, the feature is probably causal.
- Slow season is not a footnote. A property that works only in peak season
  should be rejected unless the user explicitly wants a seasonal or speculative
  asset.
- Midterm/monthly is a stay-length and customer-segment strategy, not a separate
  magic business. Use it when regulation, seasonality, operations, or demand
  support it.
- Channels have separate supply/demand curves. Airbnb, Vrbo, Booking.com,
  Whimstay, Furnished Finder, Google Hotels, and niche channels can each reward a
  different product and content presentation.

## Research modes

Choose one mode before collecting data.

| Mode | Use when | Decision |
|---|---|---|
| `opportunity_discovery` | The user can choose any market/property type | What product should we copy or build? |
| `property_validation` | The user has a specific building, unit, lease, house, or deal | Can this exact product safely make money? |
| `repositioning` | The user has an underperforming live listing | What market/product mismatch should be fixed? |

Mode changes the standard of proof:

- In `opportunity_discovery`, look for the strongest repeated winners and ask
  whether the user can reproduce the winning variables.
- In `property_validation`, ignore exciting comps the candidate cannot reproduce;
  prove that equal or worse comps are still profitable enough.
- In `repositioning`, compare the existing listing against winners and identify
  the smallest product, pricing, channel, or rules change that can close the gap.

Mode is a decision gate, not a label. If a run begins as discovery but the user
provides a specific address, building, lease, or purchase target, switch to
`property_validation` before using any comp for underwriting. If a run begins as
property validation but cannot find address-level or same-boundary evidence, do
not relax into broad market winners; return `needs_more_data`, `watch`, or
`reject`.

### Opportunity discovery mode

Use this mode only when the user can still choose the market, property type, or
product.

Required evidence:

```text
winning_product_patterns
repeated_winner_examples
winner_variable_matrix
reproducibility_assessment
counterexamples
recommended_product_profile
```

Workflow:

1. Run broad public searches across candidate markets or submarkets.
2. Vary guest count, stay length, season, and core filters.
3. Cluster repeated winners by product type, guest segment, anchor, amenity,
   capacity, rules, and channel.
4. Identify the winning variable for each cluster.
5. Check whether the host can reproduce the winning variable within budget and
   operations.
6. Hunt counterexamples before recommending the product profile.

A single standout listing is not an opportunity-discovery pattern. Require
multiple winners or a clearly repeated supply gap before recommending a product.

### Property validation mode

Use this mode when the user has a specific building, unit, house, lease, address,
co-host target, or acquisition candidate.

Required evidence:

```text
target_address_or_building
map_boundary_receipt
same_building_or_same_block_comps
equal_or_worse_profitable_comps
excluded_inspiration_comps
map_friction_assessment
listing_maturity_filter
validation_decision
```

Workflow:

1. Search the exact address, building name, street, and nearby landmark terms.
2. Apply the similarity filter pack before accepting comps.
3. Zoom or set map bounds until the result set is inside the defensible boundary.
4. Prefer same-building comps; otherwise use same-block or same-friction-boundary
   comps.
5. Look for equal-or-worse properties that still appear to be profitable.
6. Quarantine beautiful winners whose advantage the candidate cannot reproduce.
7. Apply listing-maturity filters before using any comp in base-case revenue.

Hard rules:

- Same-city winners do not validate a specific building.
- Same-radius comps do not validate a property if a river, highway, transit gap,
  unsafe walk, or different anchor changes guest behavior.
- Premium design, views, pools, balconies, parking, or waterfront access are
  evidence only when the candidate can reproduce them or weaker comps already
  work without them.
- `pursue` requires either same-building/same-block evidence or equal-or-worse
  comps inside the same defensible boundary.

### Repositioning mode

Use this mode when the host already operates the listing.

Required evidence:

```text
existing_listing_ref
current_public_search_appearance
current_price_and_availability_state
winner_gap_assessment
smallest_viable_change
post-change_measurement_plan
```

Do not use repositioning mode to justify a new acquisition unless the existing
listing is the candidate being evaluated.

## Required intake

Capture this before research:

```text
research_mode
candidate_market
candidate_suburb_or_area
candidate_address_or_building_if_known
business_model: owned | arbitrage | cohost | management | unknown
target_property_type
bedrooms
beds_possible
max_guests_possible
unique_features_possible
features_not_possible
budget_or_capex_limit
rent_or_mortgage_or_owner_terms
minimum_required_monthly_net
acceptable_downside_monthly_net
regulatory_constraints
target_channels
target_guest_segments
target_stay_lengths
launch_timeline
```

If the user does not know some fields, mark them unknown and keep the decision
at `watch` or `needs_more_data` until the missing field affects the conclusion.

Before external market research, inspect any existing downloaded host listing
inventory under `.private-data/listing-collections/`. Use the latest complete
`airbnb-live-listings-*.json` to identify the host's active properties,
addresses, bedroom/bathroom/bed/guest configurations, public URLs, and building
clusters. Market research should be anchored to the host's actual inventory
when it exists; do not run a generic market scan first and only later ask what
the host operates.

## Search grid

Define a repeatable public-search grid before opening Airbnb:

```text
map boundary: exact neighborhood, building cluster, suburb, or destination
map bounds: sw_lat, sw_lng, ne_lat, ne_lng when using map search
map-friction notes: barriers, anchors, walk/drive/transit times, same-side requirement
observer country and currency
device type
logged_in_flag = false
property type filters
room type filters
instant book filter state
amenity filters, if the thesis requires them
date samples: immediate, 30 days, 60 days, 90 days, peak, shoulder, slow, event
weekday/weekend samples
stay lengths: 1, 2, 3, 5, 7, 14, 28 nights where relevant
guest counts: 2, 4, 5, 6, 7, 8, and candidate max where relevant
pet count, children, or work-trip filters where relevant
```

Default Airbnb public-market scans use `Entire home` and no owner login. Only
remove the entire-home filter when the research question explicitly studies
private rooms, rooms, or shared-room competition. Use `Instant Book` only when
the target product will also use Instant Book, or run it as a sensitivity check.
Do not compare filtered and unfiltered runs as if they are the same market.

For property validation, use a similarity filter pack before treating results
as comps. The default apartment-building pack is:

```text
search_by_map = true
map bounds zoomed around the target address or building cluster
room_types[] = Entire home/apt
min_bedrooms = candidate bedrooms or required minimum
amenities[] = 9 when free parking is part of the product
price_min and price_max when validating a bounded price tier
adults = target guest count
min_bathrooms = candidate bathrooms when bathroom count is a comp variable
```

Airbnb's current filter IDs include:

| Filter | Query parameter |
|---|---|
| Entire home | `room_types[]=Entire home/apt` |
| 3+ bedrooms | `min_bedrooms=3` |
| 2+ bathrooms | `min_bathrooms=2` |
| Free parking | `amenities[]=9` |
| Air conditioning | `amenities[]=5` |
| Wi-Fi | `amenities[]=4` |
| Kitchen | `amenities[]=8` |
| Pool | `amenities[]=7` |
| Dryer | `amenities[]=34` |
| Instant Book | `ib=true` |
| Allows pets | `pets=1` |

An exact address query alone is not enough. Airbnb may still show a broad
`Homes in Melbourne` result set with distant substitutes. For absorption,
capacity, and comp-thesis work, zoom the map until the result title changes to
`homes within map area` or the map visibly contains only the defensible comp
boundary. Record the selected filter chips and the map bounds used for the run.

## Evidence gates

These gates apply before underwriting. They prevent one attractive listing,
one broad market count, or one peak-season price from becoming a false decision.

### Research mode gate

Before any comp is used, record:

```text
research_mode
mode_lock_reason
mode_switch_reason
required_evidence_present_flag
mode_specific_missing_evidence
mode_gate_result: pass | fail | needs_more_data
decision_constraint
```

Allowed decisions:

| Mode gate result | Decision impact |
|---|---|
| `pass` | Continue to comp grading and underwriting |
| `needs_more_data` | Use `watch` or collect missing evidence |
| `fail` | Use `reject` unless the user changes the candidate or mode |

Property validation cannot pass with broad-market winners alone. Opportunity
discovery cannot pass with one winner unless a repeated pattern and
reproducibility assessment are present.

### Map-friction gate

Map boundaries must describe guest behavior, not just geography. Record the
target boundary and the friction that makes two listings comparable or not
comparable.

Capture:

```text
target address, building, block, or map bounds
anchor type and anchor name
distance to anchor
walk time, drive time, and transit time where relevant
barrier type: river | highway | rail_line | unsafe_walk | hill | parking_gap | transit_gap | psychological_boundary | none
same-side requirement
guest segment affected
impact direction: helps | hurts | neutral | unknown
confidence
```

Use the friction assessment to reject comps that look nearby but serve a
different guest decision. For example, a comp across a highway, outside the
walkable hospital catchment, on the wrong side of a river, or far from the
relevant tram line is not an `A` comp unless the target guest segment would view
it as equivalent.

### Strict comp selection gate

Build the comp set around the exact buying situation. A comp must match the
candidate on all required fields unless the difference is explicitly recorded
and downgraded.

Required context:

```text
same map boundary or justified substitute boundary
same room type, with Entire home as the default Airbnb public-search room type
same property class: apartment, house, cabin, villa, loft, studio, or defensible substitute
same bedroom band
same bathroom band when bathroom count affects booking choice
same bed and sleep-capacity band
same target guest count
same stay length
same date sample and season
same core amenity filters when the product thesis depends on them
same currency, observer country, device, and logged-in state
same visible price context: total trip price versus nightly price
same channel when comparing channel-specific demand
```

Grade every comp:

| Grade | Meaning | Use |
|---|---|---|
| `A` | Same boundary, season, stay length, room type, capacity, and core amenities | Can support underwriting |
| `B` | One material difference that is named and sensitivity-tested | Can support a range or risk adjustment |
| `C` | Successful or beautiful, but materially different or not reproducible | Inspiration only |
| `reject` | Different buyer, season, boundary, room type, or unreproducible anchor | Do not use |

For each comp, record:

```text
comp_grade
matched_fields
mismatched_fields
winning_variable
can_host_reproduce: yes | no | partial | unknown
cost_to_reproduce
time_to_reproduce
operational_requirement
evidence_use: underwriting | sensitivity | inspiration | exclude
```

Hard rules:

- Do not use `C` or `reject` comps in base-case revenue.
- Do not use a comp with an unreproducible winner variable in underwriting.
- If all apparent winners are `C` or `reject`, the decision is `watch` or
  `reject`, not `pursue`.
- If the host has a plain unit, compare against plain/equal/weaker units before
  using premium design, view, pool, balcony, or theme comps.
- If the target is an apartment building, prefer same-building, same-block, or
  map-bounds comps over destination-level search results.

### Listing maturity gate

Public rank and calendar scarcity can be distorted by new-listing boosts,
blocked owner dates, or stale listings. Before using a comp in base-case
revenue, grade its maturity.

Capture:

```text
review count
rating
latest visible review date
recent review count window
first seen date, when available
future availability or scarcity signal
new listing flag
possible Airbnb boost flag
maturity grade: mature | promising | boosted_or_unproven | stale | unknown
underwriting use: base_case | sensitivity | inspiration | exclude
```

Interpretation:

| Signal | Maturity grade | Underwriting use |
|---|---|---|
| Meaningful review count plus recent reviews | `mature` | Base case allowed |
| Some reviews plus recent activity | `promising` | Sensitivity only |
| Low review count with high rank or scarce availability | `boosted_or_unproven` | Inspiration only |
| Old reviews and weak recent signal | `stale` | Exclude |
| Missing review recency or ambiguous calendar signal | `unknown` | Exclude or sensitivity only |

Hard rules:

- New or low-review listings cannot support base-case revenue without separate
  mature corroborating comps.
- Future unavailable dates are a booking proxy, not proof; blocked owner dates
  can look like demand.
- A high-ranking, low-review comp is a boost-risk comp until recent reviews or
  repeat observations prove stable demand.
- Use latest reviews, future availability, and review count together. Any one
  signal alone is weak.

### Counterexample gate

Every thesis must survive direct counterexamples. A thesis is not "CBD 3BRs do
well"; it is a causal statement such as:

```text
3BR entire-home CBD apartments with free parking win for 6-8 guest group stays
because capacity plus parking is scarce inside this map boundary.
```

For each thesis, collect the counterexample matrix:

```text
winner_with_feature
loser_with_feature
winner_without_feature
loser_without_feature
same_building_or_same_block_comp
better_design_weaker_location
worse_design_better_location
same_capacity_different_anchor
same_anchor_different_capacity
hotel_or_channel_substitute
```

Allowed outcomes:

```text
thesis_result: supported | contradicted | inconclusive
causal_feature: location | capacity | parking | view | pool | design | price | rules | channel | operations | unknown
confidence: high | medium | low
counterexample_that_could_kill_this
```

Interpretation:

| Evidence | Implication |
|---|---|
| Winners with the feature outperform similar listings without it | Feature may be causal |
| Losers with the feature also exist | Feature is not enough by itself |
| Better design loses to weaker design with better location | Location may dominate design |
| Worse design wins in the same building | Building or map boundary may be safe |
| Better design wins outside the boundary | Boundary may not matter as much as product |
| Hotels beat the Airbnb option on price and reliability | Treat the product as hotel-substitute competition |
| No true counterexample can be found | Keep confidence low |

Hard rules:

- `pursue` requires at least one supporting comp and one meaningful
  counterexample check.
- If counterexamples contradict the thesis, either revise the thesis and
  re-check it or reject the candidate.
- If a thesis depends on a feature the host cannot reproduce, reject or change
  the property search.
- If all counterexamples are missing because the search was too broad, zoom the
  map or narrow filters before deciding.

### Slow-season survival gate

Split the calendar before underwriting:

```text
peak season
shoulder season
slow season
slow-season holidays or events
ordinary slow-season weekdays
ordinary slow-season weekends
```

For each period, rerun the same comp filter pack:

```text
map bounds
Entire home
property class
bedroom/bath/bed/sleep capacity
core amenities
guest count
1, 2, 3, 5, 7, 14, and 28-night stays where relevant
weekday and weekend samples
```

Calculate:

```text
slow_season_adr_floor
slow_season_occupancy_floor
slow_season_weekday_gap
slow_season_weekend_gap
slow_season_14_day_or_monthly_option
slow_season_break_even_occupancy
slow_season_low_case_net
cash_buffer_required
```

Evaluate slow-season levers only after the floor is known:

```text
5-day discount for weak weeks
14-day discount before monthly discounts begin
temporary 2-night minimum instead of 3-night minimum
seasonal hero photo or listing copy
holiday-specific fit, such as dining seats for Thanksgiving or Christmas setup
amenity completeness for filtered searches
temporary pet, kid, or cancellation flexibility when operationally acceptable
last-minute channel or monthly channel support
```

Hard rules:

- Do not use peak-season ADR in slow-season underwriting.
- Do not assume the candidate belongs in the top quality band unless strict
  comps and counterexamples prove it.
- Reject if the low case fails after realistic slow-season discounts.
- Use `watch` if peak and shoulder work but slow season has not been tested.
- Reject if the deal survives only by assuming perfect pricing, perfect ops, no
  competitor discounting, and no channel shock.
- Treat slow-season tactics as product and pricing changes with costs, not as
  free revenue.

## Workflow

### 0. Lock the research mode and boundary

Goal: prevent broad-market discovery evidence from being used as
property-specific proof.

1. Select `opportunity_discovery`, `property_validation`, or `repositioning`.
2. Record why the mode applies.
3. If a specific address, building, lease, purchase target, or co-host target is
   known, use `property_validation`.
4. Record the map boundary and map-friction assumptions before collecting comps.
5. If the boundary cannot be made defensible, return `needs_more_data` before
   underwriting.

### 1. Run the absorption scan

Goal: determine whether visible supply is getting consumed.

For each map boundary and segment:

1. Run an undated or flexible search and record the visible inventory count.
2. Run dated searches for the same boundary, filters, guests, and stay length.
3. Record the dated available count.
4. Calculate:

```text
absorption_pct = 1 - dated_available_count / undated_inventory_count
```

Interpretation:

| Pattern | Meaning | Action |
|---|---|---|
| High undated count, very low dated count | Demand is consuming supply or hosts are blocking heavily | Continue; inspect quality and prices |
| Low undated count, high dated count | Small supply but weak demand | Be cautious; do not call it undersupplied |
| High undated count, high dated count | Saturated or wrong date/segment | Narrow boundary or find a product gap |
| Search cap hit | Count is not exact | Zoom in, narrow filters, or record only a lower-bound inference |

Airbnb may show counts such as `300+`; that is not an exact denominator. If the
undated search hits a cap and the dated search returns a small exact count, you
may record a lower-bound absorption signal. If both searches hit caps, the scan
does not prove absorption.

For address-level or building-cluster absorption, reject any run whose title is
still a broad destination such as `Over 1,000 homes in Melbourne` unless the
research question is explicitly broad-market discovery. Use the zoomed map area
count, not the broad address-query count, for property validation.

### 2. Run the stay-length gap scan

Goal: identify whether the market is undersupplied for common stay lengths.

For each date sample, run the same search for:

```text
1 night
2 nights
3 nights
5 nights
7 nights
14 nights
28 nights, when midterm/monthly is relevant
```

Look for:

- one-night scarcity: 1-night availability is much lower than 2- or 3-night
  availability.
- minimum-stay crowding: many comps require 2 or 3 nights.
- weekly/monthly gaps: longer stays are poorly served or priced irrationally.
- rule-set opportunity: a candidate can charge a premium for scarce short stays
  while using length-of-stay discounts to compete for longer stays.

Do not assume the best strategy is always the lowest minimum stay. A one-night
premium must still cover cleaning, linen, consumables, and turnover risk.

### 3. Run the guest-capacity supply curve

Goal: find underserved group sizes.

For the same map boundary and date posture, run counts by guest capacity:

```text
2 guests
4 guests
5 guests
6 guests
7 guests
8 guests
candidate max guests
```

Record the visible supply count for each. A steep drop from 4 to 5, 5 to 6, or 6
to 7 guests can indicate a capacity gap. Validate the gap with comps before
acting: a supply drop matters only if the market has demand from that group size
and if the candidate can host that group comfortably and legally.

Useful outputs:

```text
capacity_gap_score
recommended_sleep_count
bed_configuration_notes
group_segment_hypothesis
```

### 4. Inspect price distribution and booking pace

Goal: infer what price bands are being consumed.

If Airbnb exposes a price histogram or price-slider distribution for the search
context, capture it for:

- undated/flexible inventory.
- future dated inventory.
- near-term/last-minute inventory.
- the same context one week later, if possible.

Use missing or shrinking price bands as a clue for what may have booked or been
blocked. Do not treat this as exact revenue. It is a directional signal that
must be checked against listing pages, public calendars, review recency, and
the candidate economics.

Capture:

```text
price_band_low
price_band_high
visible_count_in_band
search_context
histogram_capture_quality
```

### 5. Build a strict comp set

Goal: create a comp set that matches the exact buyer, stay, product, and map
context.

Before treating a listing as evidence, grade it with the strict comp selection
gate. Start with `A` comps, use `B` comps only for sensitivity, and keep `C`
comps as product inspiration.

For each comp, capture:

```text
listing URL and ID
rank or result position
comp grade
evidence use
property type
room type
capacity
bedrooms/beds/baths
location marker
map-boundary fit
hero photo subject
obvious anchor or differentiator
rating and review count
recent review timing
future blocked/booked proxy
visible prices for sampled stays
minimum stay behavior
cleaning-fee inference if visible or inferable
amenity flags
review themes
matched fields
mismatched fields
winning variable
replication requirement
```

Reject or downgrade comps when:

- the map boundary is broader than the defensible comp area.
- the room type differs from the target room type.
- the stay length, guest count, or season differs.
- the comp wins because of a feature the host cannot reproduce.
- the comp is priced on nightly display while the candidate is evaluated on
  total guest price.
- the comp is a hotel substitute and the candidate lacks hotel-like reliability,
  check-in, parking, or transparency.

Then state the thesis in one sentence:

```text
This comp appears to win because <feature> matters more than <alternative>.
```

Examples of valid thesis variables:

- walkable water access.
- private pool, hot tub, deck, balcony, yard, or rooftop.
- category-like anchor: piano, cabin, treehouse, lake house, historic loft,
  waterfront cottage, game room, sauna, view, unique architecture.
- exact building or street.
- capacity gap: sleeps 6+ where most nearby units sleep 2-4.
- low-friction business stay: last-minute, reliable, stocked, no-fuss.
- family trust: kitchen, laundry, safe layout, yard, parking, pet fit.
- monthly fit: workspace, Wi-Fi, laundry, full kitchen, neutral livability.
- hotel-substitute consistency: cleanliness, check-in, parking, transparency.

### 6. Hunt counterexamples

A thesis is weak until counterexamples are checked.

For each thesis, find:

- a winner with the feature.
- a loser with the feature.
- a winner without the feature.
- a loser without the feature.
- a listing in the same building or nearby block, where possible.
- a better-designed listing with weaker location.
- a worse-designed listing with better location.
- a listing with similar capacity but different anchor.
- a listing with similar anchor but different capacity.
- a hotel or non-Airbnb channel substitute when the guest segment would consider
  it.

Interpretation:

| Evidence | Implication |
|---|---|
| Similar comps with feature win, without feature fail | Feature likely matters |
| Better design without feature loses to weaker design with feature | Feature may beat interior quality |
| Same building works with worse product | Candidate building may be safe |
| Winner relies on unreproducible feature | Reject or change product search |
| No counterexamples found | Keep confidence low |

Do not validate a deal by admiring one winner. Validate it by proving the user
can reproduce the reason the winner wins, or by proving that lesser comps still
clear the user's underwriting threshold.

Required output:

```text
thesis_result
causal_feature
supporting_comp_refs
counterexample_refs
contradictions
confidence
counterexample_that_would_change_the_decision
```

### 7. Estimate future booking velocity

Goal: distinguish stale, lucky, or blocked comps from active demand.

Public Airbnb calendars do not reliably distinguish booked from blocked dates,
so call this a proxy. Capture:

```text
next_30_day_unavailable_pct
next_60_day_unavailable_pct
future_weekends_unavailable_count
future_weekdays_unavailable_count
latest_review_date
recent_review_count_window
new_listing_flag
booking_velocity_confidence
```

Signals:

- new listing with immediate reviews and future unavailable dates: possible
  booking velocity.
- old listing with many reviews but no future unavailable dates: investigate
  seasonality, stale listing, high price, or manual blocks.
- high unavailable future weekends but empty weekdays: weekend-led demand.
- last-minute bookings only: weak forward demand or deliberate pacing.

### 8. Classify the market archetype

Use archetypes as hypothesis prompts, not as proof.

| Archetype | Look for | Common failure sign |
|---|---|---|
| Walkable water | beach/lake/river access, photos prove distance, simple parking | Too far from water or no visual proof |
| Supply dry | nearby destination with legal/supply constraint, steep capacity scarcity | Demand also weak, not just supply low |
| Nostalgic family stay | lake/yard/family memories, enough beds, practical kitchen | Overbuilt luxury that families do not need |
| Historic/story property | red brick, loft, old-world charm, character neighborhood | Generic high-rise competing with hundreds |
| Hotel hollow | up-and-coming area with restaurants/art/events but few hotels | Safety/reputation issue not offset by demand |
| Category anchor | piano, treehouse, cabin, view, sauna, game room, rooftop, unique architecture | Anchor hidden in photos or too easy to copy |
| Business/medical/monthly | hospitals, projects, relocation, workspace, laundry, parking | Vacation-style setup without livability |
| Event/venue proximity | stadium, convention center, festival, wedding venue | Demand only a few days/year |
| Hotel-substitute consistency | cleanliness, check-in reliability, transparent fees, easy parking | Host rules, fees, or ops feel inconsistent |

### 9. Run channel demand research

Goal: avoid assuming Airbnb is the only market.

For each relevant channel, record the customer type and content implications.

| Channel | Typical research angle | Content implication |
|---|---|---|
| Airbnb | broad discovery, category-like anchors, search rank, reviews | lead with emotional anchor and fit |
| Vrbo | family/group vacation, homes, kitchens, yards | lead with family, layout, kitchen, parking |
| Booking.com / Priceline | hotel-substitute, business, mobile, last-minute | lead with reliability, location, essentials |
| Whimstay / last-minute channels | distressed last-minute demand | protect Airbnb rates; discount channel separately |
| Furnished Finder / monthly channels | travel nurses, relocation, insurance, corporate housing | lead with livability, laundry, workspace, bills |
| BringFido or pet channels | pet-friendly demand | lead with yard, pet rules, nearby walks |
| Google Hotels / direct | branded search and hotel comparison | show consistency, cancellation clarity, location |
| Marriott Homes & Villas / luxury channels | curated high-trust homes | only relevant if quality and ops meet that bar |

Channel demand is a market-research input. It can turn a weak Airbnb-only deal
into a viable multi-channel product, or it can expose that the product lacks a
clear customer anywhere.

### 10. Check midterm/monthly viability

Use midterm/monthly as a segment when:

- local regulation restricts stays below 30 nights.
- slow season has weak short-stay demand.
- operations capacity favors fewer turnovers.
- the property is livable for work/relocation/insurance stays.
- monthly search on Airbnb or other channels shows real demand.

Required checks:

```text
28-night search count and prices
monthly comp quality
monthly discount needed
monthly net after utilities and cleaning
long-stay amenity gaps
short-stay opportunity cost in peak season
regulatory reason, if any
```

Avoid monthly-first bias when short stays are legal and profitable. A healthy
strategy may use peak-season short stays and slow-season monthly stays.

### 11. Model slow-season survival

Goal: prove the candidate can survive ordinary weak periods, not just peak
compression.

Run the same strict comp set across peak, shoulder, slow, slow-holiday, ordinary
weekday, and ordinary weekend samples. For each segment, record:

```text
season_segment
date_sample
nights
guest_count
available_A_comp_count
available_B_comp_count
price_floor_A_comps
price_median_A_comps
price_floor_B_comps
occupancy_or_absorption_proxy
candidate_required_total_price
candidate_required_occupancy
slow_season_low_case_net
survival_pass_flag
```

Then test whether slow-season tactics are necessary and economical:

```text
5_day_discount_needed
14_day_discount_needed
temporary_minimum_stay_change
seasonal_photo_or_copy_needed
holiday_fit_upgrade_needed
amenity_filter_gap_to_fix
temporary_rule_flexibility_needed
channel_support_needed
net_after_tactics
```

Decision discipline:

- `pursue` only if slow-season low case clears the acceptable downside or if the
  user explicitly accepts a seasonal asset.
- `watch` when peak and shoulder are strong but slow-season evidence is missing.
- `reject` when slow-season survival depends on C-grade comps, unreproducible
  features, or prices above the proven comp floor.
- `needs_more_data` when the market has no reliable slow-season sample yet.

### 12. Underwrite the deal

Use public market data only after it has been filtered through product fit.

Minimum underwriting fields:

```text
expected_monthly_gross_low
expected_monthly_gross_base
expected_monthly_gross_high
seasonal_shape
rent_or_mortgage
utilities
cleaning_cost_net_of_cleaning_fee
linen_consumables
platform_or_channel_fees
management_or_labor
insurance
maintenance_reserve
capex_or_furnishing_amortization
owner_split_or_cohost_fee
expected_monthly_net_low
expected_monthly_net_base
break_even_occupancy_or_revenue
cash_buffer_required
slow_season_low_case_net
slow_season_survival_pass_flag
```

Decision discipline:

- If candidate economics fail in the low case, reject unless the user explicitly
  accepts that risk.
- If the candidate cannot reproduce the winning comp variable, reject or change
  the property search.
- If strict comps or counterexamples do not support the revenue assumption,
  downgrade the decision to `watch`, `reject`, or `needs_more_data`.
- If slow-season low case fails after realistic discounts and channel support,
  reject unless the user explicitly accepts a seasonal asset.
- If the only path to profit requires perfect pricing, perfect ops, and no
  market shock, reject.
- If the deal is viable only on one channel, record channel concentration risk.

### 13. Produce the decision report

End every market research run with this structure:

```text
decision: pursue | watch | reject | needs_more_data
confidence: high | medium | low
research_mode
candidate product
market boundary
winning thesis
replicable feature
primary disqualifier checked
top supporting comps
top counterexamples
strict comp selection result
counterexample matrix result
absorption signal
stay-length gap
capacity gap
slow-season survival result
channel opportunities
midterm/monthly role
underwriting result
required next action
what would change the decision
```

Use `pursue` only when the product fit, comp thesis, absorption signal, and
underwriting all support the decision, and the strict comp, counterexample, and
slow-season gates pass. Use `watch` when the market is promising but the
candidate, channel, slow-season floor, or thesis is not proven. Use `reject`
when the candidate cannot reproduce the winning variables, cannot survive slow
season, or cannot clear economics. Use `needs_more_data` when a missing input
would materially change the decision.

## Data quality rules

- Every public observation must record search context: dates, nights, guests,
  filters, currency, map boundary, device, observer country, and login state.
- Public rank/visibility observations must be logged out unless explicitly
  testing personalization.
- Result counts from capped searches are lower-bound evidence only.
- Calendar unavailable dates are not automatically bookings.
- Search-result prices are guest-facing gross before tax unless the UI proves
  otherwise; do not treat them as host payout or net owner income.
- If map movement changes the boundary, the run is not comparable.
- If a search returns zero valid cards or no total prices, it is an evidence gap,
  not a market signal.
- If using an external revenue chart, record source, geography, period, and
  confidence. Do not blend external ADR/occupancy with Airbnb public observations
  without labeling the inference.

## Relationship to other Airbnb files

- Use `workflows-current-state.md` to define the state run and collect market,
  competitor, own-public, and private host observations.
- Use `public-market.md` for Airbnb public search/listing extraction mechanics.
- Use `realestate-building-rentals.md` for REA asking-rent history, building
  watchlists, suburb-wide rental observations, and listing lifecycle evidence
  before rental-arbitrage underwriting.
- Use `schema-public-market.md` for raw public search and comp observations.
- Use `schema-market-research.md` for derived market-research outputs from this
  playbook.
- Use `schema-finance.md` for true cost and owner economics.
- Use `schema-demand-context.md` for holidays, events, weather, transport, and
  regulation.
- Use `decisioning.md` when a market-research finding becomes a recommendation,
  experiment, action, or outcome review.
