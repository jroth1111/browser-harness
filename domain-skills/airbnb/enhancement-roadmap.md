# Airbnb.com.au - Enhancement Roadmap

Use this file when deciding what to add next to the host intelligence system.
The goal is to move from descriptive reporting to decision support and then to a
learning system.

## Highest-leverage enhancements

| Priority | Enhancement | Why it matters | Files |
|---:|---|---|---|
| 1 | Data quality and provenance layer | Prevents stale, partial, or ambiguous scraped data from driving bad decisions | `data-quality.md` |
| 2 | Internal finance layer | Airbnb payout is not owner profit; true margin needs cleaning, linen, utilities, management, maintenance, owner splits, and capex | `schema-finance.md` |
| 3 | Demand-context layer | Pricing needs event, holiday, weather, transport, regulation, and market-shock context, not only Airbnb comps | `schema-demand-context.md` |
| 4 | Recommendation and outcome tracking | Records what the system advised, what the host changed, and whether it worked | `decisioning.md` |
| 5 | Promotion and discount governance | Prevents search-rank promotions and discounts from leaking into peak dates or eroding margin | `schema-performance.md`, `analytics-alerts.md` |
| 6 | Content quality scoring | Turns photos, photo tours, amenities, badges, and review themes into conversion levers | `schema-core.md`, `public-market.md` |
| 7 | Market-relative comp scoring | Combines Airbnb similar listings, manual comps, and public search observations with confidence | `schema-public-market.md`, `analytics-alerts.md` |
| 8 | Operations risk prediction | Links turnover load, message gaps, cleaner capacity, maintenance recurrence, and reviews | `schema-operations.md`, `analytics-alerts.md` |

## Enhancement principles

- Do not add a metric unless it changes a decision.
- Track every recommendation as an action candidate with expected impact,
  confidence, owner, deadline, and outcome.
- Prefer leading indicators over lagging reports: booking pace, search
  impressions, orphan nights, price index, and message skips beat month-end
  revenue alone.
- Keep internal costs separate from Airbnb-visible financials.
- Store raw source evidence and field confidence so a bad scrape can be traced
  and excluded.
- Compare against both Airbnb-selected similar listings and a host-curated comp
  set; neither is sufficient alone.

## New data families to add

1. Data quality:
   - capture run
   - source observation
   - field quality
   - freshness SLA
   - screenshot/download evidence

2. Internal finance:
   - property cost model
   - actual stay cost
   - owner contract
   - owner statement
   - capex and maintenance reserve

3. Demand context:
   - public/school holidays
   - local events
   - weather and disruption days
   - transport/flight/event access signals
   - regulation or supply-change events

4. Decisioning:
   - recommendation
   - action log
   - experiment
   - outcome attribution
   - decision review

## Upgrade path

Phase A - trust the data:

1. Add `airbnb_data_capture_run`.
2. Add field-level confidence and freshness.
3. Require evidence references for values that trigger alerts.

Phase B - understand true profit:

1. Add internal cost and owner contract tables.
2. Calculate contribution margin per stay.
3. Add margin-safe pricing and promotion alerts.

Phase C - understand demand:

1. Add market event and holiday calendars.
2. Add demand-window tags to future dates.
3. Explain booking pace and price recommendations using context.

Phase D - learn from actions:

1. Create recommendation and action logs.
2. Track pre/post metrics and control windows.
3. Promote recommendations only after observed lift or defensible evidence.

## Examples of better host questions after enhancement

- "This date is unbooked; is that because the market is soft, my price is high,
  minimum stay blocks common searches, or my search-card conversion is weak?"
- "If I discount this orphan night, does the expected margin beat cleaner and
  linen cost?"
- "Did changing the hero photo improve search-to-listing conversion after
  controlling for demand period?"
- "Are we underpricing because the comp set ignores a local event?"
- "Which recommendations repeatedly fail and should stop being suggested?"
