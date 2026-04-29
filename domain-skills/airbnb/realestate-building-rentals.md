# Realestate.com.au Building Rental Monitor

Use this workflow when the host wants long-term rental price intelligence for
the apartment buildings where current Airbnb listings operate. The collector
answers: what comparable units are listed for rent in these buildings, when did
their asking rent change, when did they disappear as rented/unavailable, and
when did a known listing return to market?

## Ownership

- Use this when: the user needs REA asking-rent evidence, building watchlists,
  suburb rent scans, rental lifecycle events, or building rent history.
- Owns: REA source collection, building matching, retry/gone-listing semantics,
  idempotent REA ledgers, and rent observation table shapes.
- Does not own: Airbnb public comp extraction, final rental-arbitrage
  underwriting, pursue/watch/reject decisions, or action tracking.
- Next hop: `scripts/README.md` for the collector, `market-research-playbook.md`
  for arbitrage underwriting, and `decisioning.md` only after a decision becomes
  an action.

## Source Buildings

The monitored building universe starts with the latest complete Airbnb host
listing inventory:

```text
domain-skills/airbnb/.private-data/listing-collections/airbnb-live-listings-*.json
```

The collector reads the `records` array, selects active listings by default, and
normalizes private addresses into building keys. Unit prefixes and building
names are removed for the building key, so examples like `1303/38 Bank St` and
`38 Bank Street` join to the same building.

Private source addresses stay in `.private-data/`; committed docs must not list
the user's portfolio addresses.

The collector can also monitor a private shortlist of buildings where the host
does not currently operate. Use
`REA_BUILDING_RENTALS_BUILDING_WATCHLIST_FILE` or create the default private
file:

```text
domain-skills/airbnb/.private-data/realestate-rental-collections/rea-building-watchlist.json
```

Example shape:

```json
{
  "buildings": [
    {
      "id": "southbank-priority-001",
      "label": "Internal shortlist label",
      "address": "9 Example Street, Southbank VIC 3006",
      "reason": "Amenity-rich high-rise near demand generators",
      "priority": 25,
      "tags": ["pool", "gym", "cbd"],
      "target_bedrooms": [1, 2]
    }
  ]
}
```

CSV is also accepted with headers such as `id`, `label`, `address`, `reason`,
`priority`, `tags`, and `target_bedrooms`. Watchlist addresses are normalized
with the same building-key logic as Airbnb inventory addresses. If a watchlist
entry points to a building already present in the current portfolio, the target
is merged instead of searched twice.

## Runner

Run through the browser harness against a persistent headful Chrome profile:

```bash
BH_NAME=rea-building-rentals BH_CDP_WS=http://127.0.0.1:<port> \
  python3 run.py < domain-skills/airbnb/scripts/collect_rea_building_rentals.py
```

REA commonly serves Kasada/KPSDK challenge shells to direct HTTP, fresh
headless Chrome, and Lightpanda. Do not run this collector as plain `python3`
and do not treat an empty/challenge page as "no rental listings".

Useful smoke-test controls:

```bash
REA_BUILDING_RENTALS_LIMIT_BUILDINGS=1 \
REA_BUILDING_RENTALS_MAX_SEARCH_PAGES=1 \
REA_BUILDING_RENTALS_RETRY_MAX_ATTEMPTS=2 \
BH_NAME=rea-building-rentals BH_CDP_WS=http://127.0.0.1:<port> \
  python3 run.py < domain-skills/airbnb/scripts/collect_rea_building_rentals.py
```

## Outputs

Run snapshots are written to:

```text
domain-skills/airbnb/.private-data/realestate-rental-collections/
```

Each run produces:

- `<run_id>.json` - full run snapshot
- `<run_id>-observations.csv` - current observed rental listing states
- `<run_id>-events.csv` - price and availability events versus prior ledger
- `<run_id>-building-prices.csv` - building-level observed rent summaries for the run
- `<run_id>-search-runs.csv` - discovery queries and candidate URLs
- `<run_id>-failures.csv` - blocked pages, non-matching addresses, and parser failures when present
- `<run_id>-raw-listings.jsonl` - private raw listing text for audit

Cross-run ledgers:

- `rea-building-rental-observations.jsonl`
- `rea-building-rental-events.jsonl`
- `rea-building-rental-building-prices.jsonl`

The JSONL ledgers are idempotent upsert ledgers, not blind append logs. A retry
with the same `REA_BUILDING_RENTALS_RUN_ID` replaces the same observation/event
keys instead of adding duplicate rows.

The event ledger uses these event types:

- `first_seen_active`
- `first_seen_unavailable`
- `first_seen_unknown`
- `price_changed`
- `leased_confirmed`
- `rented_or_application_confirmed`
- `unavailable_confirmed`
- `listing_removed_or_unreachable`
- `relisted`
- `active_confirmed`
- `active_signal_lost`
- `availability_state_changed`

## Discovery and Revisit Semantics

For each building, the collector:

1. Revisits previously observed REA listing URLs for that building.
2. Adds manual seed URLs from `REA_BUILDING_RENTALS_SEED_URLS` or
   `REA_BUILDING_RENTALS_SEED_URLS_FILE`.
3. Searches realestate.com.au rentals with the suburb as the location query,
   for example `/rent/in-southbank+vic+3006/list-1`. The building address is
   not used as the REA location query because REA can route those searches
   inaccurately; it is kept as the post-fetch match key.
4. Paginates through every REA result page reported by the search result count
   unless `REA_BUILDING_RENTALS_MAX_SEARCH_PAGES` is set for a smoke test.
5. Parses search cards for address, weekly rent, listing URL, unit identifier,
   and REA property ID, keeping only observations whose parsed address belongs
   to the target building.
6. Opens matched listing pages by default to enrich bond, annual rent,
   bond-weeks equivalent, availability, unavailable/rented state, property
   type, furnishing status, pets policy, inspection/application lines, feature
   flags, and visible agency/contact lines; set
   `REA_BUILDING_RENTALS_OPEN_MATCHED_LISTINGS=0` to keep collection to
   search-result pages only.
7. Builds one building-price snapshot per monitored building, including both
   current Airbnb buildings and optional watchlist buildings, aggregating active
   observed weekly rents into min/median/mean/max summaries and bedroom buckets.
8. Compares current observations with the prior observation ledger to emit
   events.

Previously observed URLs are important: once a listing is seen, future runs keep
checking that exact URL even if it stops appearing in search results. That is
what allows the workflow to record rented/unavailable and relisted transitions
over time.

## 429 Retry and Gone-Listing Semantics

REA `HTTP 429` / too-many-requests responses are treated as retryable fetch
failures, not market evidence. The collector retries the same page with
exponential backoff before giving up:

- `REA_BUILDING_RENTALS_RETRY_MAX_ATTEMPTS`, default `4`
- `REA_BUILDING_RENTALS_RETRY_BASE_DELAY_SEC`, default `15`
- `REA_BUILDING_RENTALS_RETRY_MAX_DELAY_SEC`, default `180`

With defaults, retry sleeps are 15, 30, and 60 seconds before the fourth attempt.
If the final search-page attempt is still 429, the run is marked
`partial_failed` with `stop_reason = http_429_or_too_many_requests`.

A known listing URL that returns a not-found/removed page is different. Because
the previous observation ledger still has the old listing row, the collector
synthesizes a current observation for that same `listing_key` with:

- `listing_state = removed_or_unknown`
- `rent_per_week_aud = null`
- `unavailable_reason = page_not_found_or_removed`
- `listing_lifecycle_evidence = known_url_page_not_found_from_previous_observation`
- `listing_lifecycle_confidence = medium`
- `last_known_rent_per_week_aud` copied from the previous observation
- `last_known_listing_state` copied from the previous observation
- `removed_detection_failure_kind = page_not_found_or_removed`

That synthetic row lets the event ledger emit `listing_removed_or_unreachable`
even when the current REA page is a 404 and no address/rent can be parsed. The
collector does not synthesize removed observations for 429 or access-denied
pages.

The collector does not assume every disappeared listing was leased. It records
the evidence level:

| Evidence | Observation State | Event |
|---|---|---|
| Visible `Leased` text | `leased_or_unavailable` with `unavailable_reason = leased` | `leased_confirmed` |
| Visible `Deposit taken`, `Application approved`, or `Rented` | `leased_or_unavailable` with matching reason | `rented_or_application_confirmed` |
| Visible `No longer available` / `Not currently available` | `leased_or_unavailable` with matching reason | `unavailable_confirmed` |
| Known URL becomes 404/gone | `removed_or_unknown` with previous-row context | `listing_removed_or_unreachable` |

If the coarse state stays unavailable but the evidence improves later, the event
ledger records the upgraded evidence. For example, `no_longer_available` followed
by visible `Leased` emits `leased_confirmed` even though both observations are
`leased_or_unavailable`. If a listing later relists after a synthetic 404/gone
observation, price comparison falls back to `last_known_rent_per_week_aud` so a
new active price can still emit `price_changed`. A bare `404` in an apartment
address, such as `404/118 Kavanagh Street`, is not treated as a gone page;
removed-page detection requires actual not-found/error wording.

`relisted` is reserved for transitions from a known unavailable/removed state
back to active. If a prior row was only `unknown` and a later row has an active
price, the event is `active_confirmed`, not `relisted`. If an active listing
later loses both active-price and unavailable evidence, the event is
`active_signal_lost`.

When an agent relists the same unit under a fresh REA `property-id`, the
`listing_key` changes. The collector still emits `relisted` (and any
`price_changed`) by falling back to a `building_key + unit_identifier` alias
match against the prior ledger row, but only when the alias previous is in a
closed state (`leased_or_unavailable` or `removed_or_unknown`) so two
concurrent listings in the same unit are not folded into a single relist.
Alias-matched events carry `previous_match_basis = building_unit_alias` plus
`previous_listing_key` and `previous_rea_listing_url` for traceability.

Unavailable wording is interpreted from listing-context lines, not from every
piece of page chrome. Related-listing sections such as `Similar properties` or
`Recently leased` are ignored so a still-active unit with a visible price is not
misclassified because another nearby property has leased.

## Idempotency Model

The collector is designed for safe retries after browser failures, REA rate
limits, process crashes, or scheduled re-runs:

- Observation rows carry `observation_id = sha256(run_id, building_key, listing_key)`.
- Observation rows also carry `content_hash`, computed from material listing
  fields such as rent, availability state, unit, address, bedrooms, bathrooms,
  bond, and parse/match confidence.
- Event rows carry a deterministic `event_id` based on run, event type, listing
  key, old state/rent, and new state/rent.
- Cross-run ledgers use atomic JSONL upsert by those IDs. Running the same job
  twice with the same `run_id` does not duplicate observations, events, or raw
  listing text.
- Run snapshots, CSVs, receipts, and run-state checkpoints are written to a
  sibling temp file first, then atomically replaced.
- Event generation compares against the prior ledger excluding the current
  `run_id`, so a retry of a successful run emits the same per-run events instead
  of treating the first attempt as the previous market state.
- If a complete canonical snapshot already exists for a `run_id`, a later
  partial/blocked retry writes `<run_id>-failed-attempt.*` artifacts instead of
  overwriting the successful snapshot or mutating the cross-run ledgers.
- The checkpoint under `.private-data/realestate-rental-collections/.run-state/`
  records completed search pages and listing-page attempts for crash audit. It
  deliberately does not skip re-fetches on retry: REA fetches are read-only GET
  browser navigations, and re-fetching plus idempotent upsert is safer than
  pretending a checkpoint alone reconstructs observations.

The workflow keeps both a temporal snapshot ledger and a change-only event
ledger. Unchanged observations are still useful evidence that a listing remained
active or unavailable at a later timestamp; price/state noise is handled by the
event ledger, which only records first-seen, price, rented/removed, relisted,
and state-change transitions.

## Building Price Collection Update

After each run, the collector updates three related stores:

1. `rea-building-rental-observations.jsonl` stores listing-level observations
   keyed by `observation_id`.
2. `rea-building-rental-events.jsonl` stores listing-level changes keyed by
   `event_id`.
3. `rea-building-rental-building-prices.jsonl` stores building-level price
   snapshots keyed by `building_price_snapshot_id = sha256(run_id, building_key)`.

The building-price row is derived from the deduped observations for that run.
For each monitored building it records:

- target source: Airbnb inventory, building watchlist, or both
- observed listing count, active listing count, unavailable count, and unknown count
- active weekly rents as a sorted list
- min, median, mean, and max active weekly rent
- bedroom-level rent summaries when bedroom counts are visible
- active and observed listing keys used to produce the aggregate

That gives a clean time series at the building grain. Re-running the same
`run_id` upserts the same building snapshot; running a new scheduled collection
adds a new dated snapshot for each building.

## Scope Boundary And Market Handoff

This file owns REA source collection, building matching, listing lifecycle
events, and building-level asking-rent history. It does not approve a rental
arbitrage deal by itself.

When REA evidence is used for acquisition or rental arbitrage, hand it to
`market-research-playbook.md`:

- use current and historical weekly rent as rent inputs for
  `airbnb_deal_underwriting_summary`
- use building watchlist membership and suburb search coverage as evidence refs
  for `airbnb_market_research_run`
- use price changes, disappearance/relist events, and active supply counts as
  market pressure signals, not final pursue/watch/reject decisions
- use `decisioning.md` only after a market-research decision becomes an action
  such as call, inspect, apply, negotiate, or reject

The funnel below describes how REA rental observations graduate into market
research candidates. The market playbook owns final underwriting and
pursue/watch/reject decisions.

## Rental Arbitrage Funnel

The broader arbitrage funnel should work suburb-wide first, then narrow to
buildings and listings that are Pareto-efficient on two axes: lower long-term
rent and higher Airbnb attractiveness.

1. **Suburb universe** - choose target suburbs, then crawl every REA rent page
   for each suburb, not address-specific searches. Keep every active listing in
   the suburb-level candidate ledger, not only current portfolio buildings.
2. **Hard filters** - reject candidates before scoring when they fail obvious
   arbitrage gates: wrong property type, unsuitable bedroom count, or poor
   inspection/application signals.
3. **Rent efficiency** - normalize asking rent by bedroom count and expected
   sellable Airbnb capacity. Track rent per week, bond weeks, rent percentile
   within suburb/bedroom bucket, and recent price-change direction.
4. **Airbnb attractiveness** - score candidate-level conversion proxies:
   view quality, private outdoor space, building amenities, parking, guest
   capacity efficiency, natural light/aspect, renovation quality, bathroom
   quality, kitchen shell quality, layout clarity, perceived spaciousness,
   hotel-like common areas, noise/privacy signals, fixed climate control,
   laundry infrastructure, luggage accessibility, architectural uniqueness, and
   similarity to existing high-performing Airbnb listings.
5. **Comparable Airbnb yield** - join candidates to public Airbnb comps by
   suburb, bedroom count, guest capacity, amenity set, and location band. Use a
   conservative expected ADR and occupancy range, not the top comp.
6. **Economics** - calculate expected monthly gross, rent, utilities, cleaning
   margin, platform fees, furnishing amortization, vacancy buffer, and setup
   cash required. Keep base, downside, and upside cases.
7. **Pareto shortlist** - keep only candidates where no other candidate is both
   cheaper on expected rent and stronger on expected Airbnb attractiveness /
   margin. This avoids chasing merely cheap but low-demand properties, or
   attractive properties whose rent destroys margin.
8. **Action queue** - produce a ranked call/inspection/application list with
   evidence links, missing diligence items, and the specific reason each
   candidate beats the current shortlist frontier.

The monitoring collector is the building-level price-history component of that
funnel. The next executable layer would add a suburb-wide candidate ledger and a
scoring table so REA listings can graduate from broad suburb discovery into the
building watchlist.

Use these Airbnb attractiveness factors in the acquisition scoring table.
Suburb/location choice is intentionally excluded because target suburbs are
selected upstream. Operational setup items, pet friendliness, lease/regulatory
checks, furniture, styling, removable appliances, and whitegoods are also
excluded from this score. The score should measure what survives lease handover:
the building, fixed property features, layout, light, outlook, and structural
appeal.

| Field | What To Score |
|---|---|
| `view_score` | City, water, park, landmark, skyline, high-floor outlook, or otherwise photo-visible outlook |
| `private_outdoor_space_score` | Balcony, courtyard, terrace, patio, private outdoor area, outdoor area size and privacy |
| `building_amenity_score` | Pool, gym, sauna, rooftop, resident lounge, BBQ area, concierge, resort-style shared facilities |
| `parking_score` | Secure/allocated parking, garage, visitor parking, EV charger, easy loading access |
| `natural_light_score` | Large windows, bright rooms, corner apartment, good orientation, light reaching living and bedrooms |
| `renovation_quality_score` | Modern fixed finishes, flooring, paint, fixtures, cabinetry, general condition, low visible wear |
| `bathroom_quality_score` | Walk-in shower, bathtub, ensuite, two bathrooms, ventilation, lighting, hotel-like fixed finish |
| `kitchen_shell_score` | Bench space, cabinetry, layout, storage, fixed plumbing/electrical quality; do not score removable appliances or whitegoods |
| `layout_quality_score` | Separate bedroom, real living zone, dining zone, study nook, balcony connection, clear circulation |
| `spaciousness_score` | Room proportions, ceiling height, storage, uncluttered floor area, not visibly cramped |
| `building_common_area_score` | Lobby, lift quality, corridors, secure entry, concierge desk, premium common-area presentation |
| `noise_privacy_score` | High floor, double glazing, courtyard-facing aspect, corner position, not visibly exposed to traffic/nightlife |
| `climate_control_score` | Fixed split system, ducted heating/cooling, fixed ceiling fans, visible built-in climate control |
| `laundry_infrastructure_score` | Internal laundry, laundry cupboard, washer taps, dryer vent/space; do not score washer/dryer appliances |
| `accessibility_luggage_score` | Elevator, step-free path, wide entry, easy luggage movement from street/parking to apartment |
| `architectural_uniqueness_score` | Heritage shell, loft, floor-to-ceiling glass, exposed brick, unusual layout, memorable fixed architecture |

### Candidate Scoring Weights

Use this as the default prior for an `airbnb_revenue_pull_score` until enough
local comp data exists to fit market-specific weights. The score is intentionally
separate from rent efficiency: it estimates revenue upside before asking whether
the rent is cheap enough.

Airbnb's own search guidance says listing quality, popularity, price, and
location heavily influence search, and that photos/videos, listing
characteristics, and amenities contribute to quality and engagement. Airbnb also
exposes guest filters for amenities such as parking, patio/balcony, gym, pool,
hot tub, elevator, EV charger, air conditioning, bedrooms, beds, bathrooms, and
accessibility features. This weighting therefore favours fixed features that
can lift click-through, conversion, ADR, occupancy, or filter visibility without
depending on furniture or removable appliances.

| Field | Weight | Revenue Link | Scoring Notes |
|---|---:|---|---|
| `view_score` | 18 | ADR and click-through | Strongest single photo-visible premium when the view is real and can lead the hero image |
| `building_amenity_score` | 18 | ADR, occupancy, filter visibility | Pool and gym carry most of this score; sauna, rooftop, lounge, BBQ, concierge add secondary lift |
| `private_outdoor_space_score` | 15 | Conversion and ADR | Balcony/courtyard/terrace with usable size, privacy, and outlook |
| `parking_score` | 14 | Occupancy and filter visibility | Secure/allocated parking, garage, EV charger, easy loading; strongest where parking is scarce |
| `guest_capacity_efficiency_score` | 6 | Revenue per booked night | Layout can sleep more guests cleanly relative to rent without degrading experience |
| `natural_light_score` | 6 | Click-through and perceived quality | Bright rooms, large windows, good orientation, corner apartment, light in living and bedrooms |
| `layout_quality_score` | 6 | Conversion and review risk | Clear living/dining/sleeping zones, separate bedroom, study nook, balcony connection, low awkwardness |
| `renovation_quality_score` | 5 | ADR and review risk | Modern fixed finishes, flooring, paint, cabinetry, low visible wear |
| `bathroom_quality_score` | 4 | ADR and guest confidence | Ensuite, two bathrooms, walk-in shower, bathtub, ventilation, hotel-like fixed finish |
| `spaciousness_score` | 3 | Conversion and review risk | Good proportions, storage, ceiling height, uncluttered floor area |
| `kitchen_shell_score` | 2 | Longer-stay conversion | Bench space, cabinetry, storage, fixed services; do not score removable appliances or whitegoods |
| `building_common_area_score` | 1 | Perceived premium | Lobby, corridors, lifts, secure entry, concierge desk, premium arrival experience |
| `noise_privacy_score` | 1 | Review protection | High floor, double glazing, courtyard aspect, corner position, privacy from neighbours/traffic |
| `climate_control_score` | 1 | Filter visibility and review protection | Fixed split system, ducted heating/cooling, fixed ceiling fans |
| `accessibility_luggage_score` | 1 | Conversion and operational ease | Elevator, step-free path, wide entry, easy movement from parking/street to apartment |
| `laundry_infrastructure_score` | 1 | Longer-stay utility | Internal laundry, laundry cupboard, taps, dryer vent/space only |

Score each field from `0` to `5`, then normalize:

```text
airbnb_revenue_pull_score =
  sum((field_score / 5) * field_weight)
```

Then combine it with rent efficiency for a candidate score:

```text
candidate_arbitrage_score =
  0.60 * airbnb_revenue_pull_score
  + 0.40 * rent_efficiency_score
```

Use Pareto filtering before final ranking: keep candidates that are not dominated
by another listing with both lower rent and higher `airbnb_revenue_pull_score`.
The weighted score ranks the survivors; it should not hide a clearly dominated
candidate.

Once enough local observations exist, replace the prior weights with fitted
weights using realized or comp-derived revenue as the target:

```text
target = expected_monthly_airbnb_gross
features = structural/photo/listing fields above
controls = suburb, bedroom count, guest capacity, season, available nights
```

Fit a regularized model, keep monotonic constraints where obvious, and compare
the learned weights back to this prior before changing production scoring.

## Table Shape

Observation rows include:

| Field | Meaning |
|---|---|
| `observation_id` | Stable retry key for this run/building/listing |
| `content_hash` | Hash of material listing state for change detection |
| `observed_at` | UTC observation timestamp |
| `building_key` | Normalized street/suburb/state/postcode key |
| `building_address` | Human-readable building address |
| `target_sources` | `airbnb_inventory`, `building_watchlist`, or both |
| `source_airbnb_listing_ids` | Airbnb listings that place us in this building |
| `source_watchlist_ids` | Private watchlist IDs that place this building under monitoring |
| `rea_listing_id` | REA property/listing ID when extractable |
| `rea_listing_url` | Canonical REA listing URL |
| `unit_identifier` | Unit/apartment prefix when visible |
| `listing_address` | Parsed REA listing address |
| `rent_per_week_aud` | Asking weekly rent |
| `annual_rent_aud` | Weekly rent multiplied by 52 when rent is visible |
| `bond_aud` | Bond when visible |
| `bond_weeks_equivalent` | Bond divided by weekly rent when both are visible |
| `availability_text` | Visible availability text |
| `listing_state` | `active`, `leased_or_unavailable`, `removed_or_unknown`, or `unknown` |
| `unavailable_reason` | Specific unavailable signal such as `leased`, `deposit_taken`, or `page_not_found_or_removed` |
| `listing_lifecycle_evidence` | Evidence source behind the lifecycle state |
| `listing_lifecycle_confidence` | `high`, `medium`, or `low` confidence in the lifecycle state |
| `property_type` | REA property type inferred from URL or page text |
| `furnishing_status` | `furnished`, `partly_furnished`, `unfurnished`, or blank |
| `pets_policy_text` | Visible pets-related line when present |
| `inspection_times` | Visible inspection/open-home lines when present |
| `application_text` | Visible application-related lines when present |
| `property_features` | Matched feature flags such as balcony, study, pool, secure parking, and fixed building amenities |
| `agency_or_contact_lines` | Visible agency/contact lines when present |
| `match_confidence` | How the page was matched to the building |
| `parse_confidence` | Whether address and rent were both parsed |

Event rows include old/new state and old/new rent so downstream reports can
produce a building-level rental price timeline. Each event row also includes an
`event_id` so alerting or downstream sync can be retried without duplicate
notifications.
