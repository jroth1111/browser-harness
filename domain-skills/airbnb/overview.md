# Airbnb.com.au - Host Intelligence Overview

Use this skill when the user is an Airbnb host or co-host and wants to improve
pricing, calendar control, conversion, operations, listing quality, comp-set
positioning, portfolio reporting, or Australian compliance awareness from
Airbnb.com.au data.

## File map

Read the smallest file that matches the job:

| File | Purpose |
|---|---|
| `overview.md` | Routing, objectives, principles, source ladder, build order |
| `enhancement-roadmap.md` | Enhancement backlog and priority sequence |
| `exploration-protocol.md` | Discovery-first process for public, private, Lightpanda, and headful sources |
| `workflows-current-state.md` | Sensing workflows for market, competitor, and own-listing current state |
| `data-inventory.md` | Public/private data primitive catalog and source matrix |
| `pipeline-fulfilment.md` | Current evidence ledger for host intelligence pipeline coverage |
| `session-continuity.md` | Auth/session continuity, cookie safety, local ignored session store |
| `host-sources.md` | Authenticated host collection workflows and refresh cadence |
| `public-market.md` | Public search/listing extraction and comp-set observations |
| `schema-core.md` | Listing, content, calendar, reservation, economics, payout/tax tables |
| `schema-performance.md` | Pricing, rule-set, conversion, occupancy, and quality tables |
| `schema-operations.md` | Reviews, guest context, message workflows, operations task tables |
| `schema-public-market.md` | Public search run, search result, comp listing, price matrix tables |
| `schema-finance.md` | Internal costs, owner statements, margin, cash-flow, and capex tables |
| `schema-demand-context.md` | Events, holidays, weather, regulation, and demand-context enrichments |
| `analytics-alerts.md` | Derived metrics, playbooks, alerts, and dashboard tiles |
| `decisioning.md` | Recommendation, experiment, action, and outcome tracking |
| `data-quality.md` | Provenance, freshness, confidence, privacy, and QA rules |

This split follows the data lifecycle:

1. Define a current-state run with dates, guests, stay lengths, market, backend,
   and logged-in state.
2. Collect public market and competitor data logged out by default.
3. Collect own-listing guest-visible state logged out.
4. Collect private host-only state logged in only when needed.
5. Enrich with demand context and internal finance data.
6. Store observations in data-family schemas.
7. Derive metrics, alerts, and host actions.
8. Track recommendations, experiments, and outcomes.

When starting a new Airbnb host engagement, read `exploration-protocol.md`
before assuming the available sources are known. For any task about the current
state of the market, competitors, or the host's own listings, run
`workflows-current-state.md` before making pricing or restriction
recommendations. Treat every Airbnb source as a primitive that can be composed
later for pricing, operations, quality, or portfolio decisions.

For generalizable mechanics, read `interaction-skills/data-source-exploration.md`
and `interaction-skills/session-continuity.md`. Airbnb files should contain
Airbnb-specific source names, fields, URLs, and examples.

## Host outcomes

| Business area | Main question |
|---|---|
| Revenue management | Am I pricing correctly by date, demand window, stay length, and guest type? |
| Calendar control | Which sellable nights are blocked, unbooked, underpriced, or restricted? |
| Conversion | Is the issue visibility, click-through, listing-page conversion, or price friction? |
| Guest operations | Are messages, check-in, checkout, cleaning, and maintenance handled consistently? |
| Listing quality | Which amenities, photos, rules, or accuracy issues affect ratings and conversion? |
| Competitive positioning | How do my listings compare with similar Airbnb.com.au listings? |
| Portfolio reporting | Which listings, owners, markets, and stay types are actually profitable? |
| Australian compliance awareness | Which Airbnb-visible tax, levy, registration, or responsible-hosting fields need tracking? |

## Operating principles

- Start with the host decision, then collect only the data needed to support it.
- Prefer Airbnb exports and structured host surfaces over brittle DOM scraping.
- Store snapshots over time. Every volatile observation needs `observed_at`.
- Preserve source context. Public price/rank without dates, guests, filters,
  currency, device, login state, and geography is not comparable.
- Keep guest-facing gross price, Airbnb host payout, and owner net economics
  separate.
- Treat Airbnb-visible tax, levy, registration, and regulation fields as
  compliance awareness, not legal or tax advice.
- Assign confidence to scraped values when the UI is ambiguous or partially
  loaded.

## Airbnb-specific vs reusable guidance

Keep Airbnb.com.au-specific material in this directory:

- Airbnb URL patterns, query parameters, search-card text shapes, and room IDs.
- Airbnb host surfaces such as Earnings, Calendar, Insights, Smart Pricing,
  rule-sets, quick replies, tasks, reviews, and Regulations.
- Airbnb semantics, such as search result totals excluding taxes, listing-page
  price widgets staying at `loading`, and Smart Pricing overriding rule-set
  intent.
- Australian Airbnb-visible registration/permit, tax, levy, and
  responsible-hosting surfaces.

Keep reusable browser/session mechanics in `interaction-skills/`:

- backend capability diagnosis for loaded-but-empty pages.
- solved-session HTTP retries after a browser profile passes a challenge.
- downloads, screenshots, tabs, dialogs, iframes, scrolling, cookies, viewport,
  and generic extraction-quality patterns.

## Source reliability ladder

| Tier | Source | Use first for |
|---|---|---|
| 1 | Earnings reports, CSV exports, iCal/calendar export, reservation print/details | Money, booked/blocked dates, reservation facts |
| 2 | Authenticated host UI: Insights, pricing, rule-sets, listing settings, messages, tasks | Funnel, rules, settings, operations |
| 3 | Airbnb personal data export | Historical account, host, reservation, payout, message, and listing primitives where included |
| 4 | Public search results and public listing pages | Competitor visibility, total guest price, badges, amenity positioning |
| 5 | Internal/manual enrichments | Cleaning cost, owner mapping, maintenance tags, photo coverage, property reality |
| 6 | External demand context | Events, school/public holidays, weather, transport, regulation, market shocks |

## Host intake

Capture this before scraping:

| Input | Why |
|---|---|
| Host objective | Selects the analysis playbook |
| Listing IDs or URLs | Stable join keys |
| Market, suburb, or building | Comp-set boundary |
| Date horizon | Next 30/60/90/180 days or past reporting period |
| Guest segments | Adults, children, pets, business/family/group stays |
| Stay lengths | Weekend, midweek, 3-night, 7-night, monthly |
| Currency/account country | Price comparability |
| Logged-in permission | Determines whether host-only sources are available |
| Manual costs | Cleaning, linen, consumables, management, utilities, owner splits |
| Action history | Prior price/content/rule/ops changes and the dates they happened |

If the user is not logged in or cannot grant a browser session, limit the task to
public comp intelligence and ask for exported files when host economics are
needed.

## Build order

Phase 1 - core business intelligence:

0. Run the public/private exploration protocol.
1. Create session-continuity metadata for private authenticated work.
2. `airbnb_listing_master`
3. `airbnb_calendar_snapshot`
4. `airbnb_reservation`
5. `airbnb_reservation_economics`
6. `airbnb_pricing_settings`
7. `airbnb_insights_conversion`
8. `airbnb_insights_occupancy_rates`
9. `airbnb_insights_quality`

Outcome: revenue, occupancy, booking pace, conversion, and quality visibility.

Phase 2 - decision-grade data foundation:

1. `airbnb_data_capture_run`
2. `airbnb_source_observation`
3. `airbnb_field_quality`
4. `airbnb_internal_cost_model`
5. `airbnb_market_event`
6. `airbnb_demand_calendar`

Outcome: auditable freshness, field confidence, true costs, and demand context.

Phase 3 - revenue optimization:

1. `airbnb_rule_set`
2. `airbnb_public_search_run`
3. `airbnb_public_search_result_snapshot`
4. `airbnb_public_comp_listing_snapshot`
5. `airbnb_public_price_availability_matrix`
6. `airbnb_own_public_listing_audit`
7. `airbnb_own_public_review_summary`
8. `airbnb_own_public_search_appearance`
9. Price-index and booking-pace alerts

Outcome: comp-set price intelligence, own guest-visible positioning, and
restriction optimization.

Phase 4 - operational scale:

1. `airbnb_message_workflow`
2. `airbnb_operations_task`
3. Review-theme tagging
4. Cleaner and maintenance recurrence reports
5. Turnover load alerts

Outcome: repeatable guest operations and property quality control.

Phase 5 - learning system:

1. `airbnb_recommendation`
2. `airbnb_action_log`
3. `airbnb_experiment`
4. `airbnb_outcome_attribution`
5. Decision review dashboard

Outcome: the system learns which price, content, rule, and operations changes
actually improve host results.

## Source anchors

Useful Airbnb help pages for validating UI semantics:

- `https://www.airbnb.com.au/help/article/2500` - performance dashboard and Insights areas.
- `https://www.airbnb.com.au/help/article/3632` - earnings reports and CSV export.
- `https://www.airbnb.com.au/help/article/3255` - personal data export formats and categories.
- `https://www.airbnb.com.au/help/article/2499` - professional hosting tools.
- `https://www.airbnb.com.au/help/article/99` - calendar sync and iCal behavior.
- `https://www.airbnb.com.au/help/article/3612` - why calendar nights may be blocked.
- `https://www.airbnb.com.au/help/article/2061` - rule-sets.
- `https://www.airbnb.com.au/help/article/1168` - Smart Pricing.
- `https://www.airbnb.com.au/help/article/459` - payout calculation.
- `https://www.airbnb.com.au/help/article/2897` - scheduled quick replies.
- `https://www.airbnb.com.au/help/article/3305` - short-term rental regulations.
- `https://www.airbnb.com.au/help/article/2652` - similar listings.
- `https://www.airbnb.com.au/resources/hosting-homes/a/using-airbnb-pricing-tools-707` - pricing tools, discounts, promotions, fees.
- `https://www.airbnb.com.au/resources/hosting-homes/a/help-your-listing-stand-out-658` - photos and amenities.
- `https://www.airbnb.com.au/resources/hosting-homes/a/how-to-organize-listing-photos-into-a-home-tour-456` - photo tour.
- `https://www.airbnb.com.au/help/article/2719` - custom promotion eligibility and median price.
- `https://www.airbnb.com.au/resources/hosting-homes/a/new-highlight-helps-top-homes-stand-out-666` - top-home highlights and top-percent labels.
