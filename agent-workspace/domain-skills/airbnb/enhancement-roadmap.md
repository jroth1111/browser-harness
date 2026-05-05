# Airbnb.com.au - Enhancement Roadmap

Use this file when deciding what to add next to the host intelligence system.
This is a forward-looking backlog only. The schema row index in `overview.md`
and the status ledger in `pipeline-fulfilment.md` are the authoritative sources
for what already exists.

## Implemented foundations

These layers are built and should not be added again. Edit the linked schema or
helper instead of proposing them as new work.

| Layer | Owner |
|---|---|
| Data quality and provenance (`airbnb_data_capture_run`, `airbnb_source_observation`, `airbnb_field_quality`) | `data-quality.md`, `scripts/run_integrity.py` |
| Internal finance (`airbnb_internal_cost_model`, `airbnb_owner_contract`, `airbnb_owner_statement`, `airbnb_capex_maintenance_plan`) | `schema-finance.md` |
| Demand context (`airbnb_market_event`, `airbnb_holiday_calendar`, `airbnb_weather_context`, `airbnb_demand_calendar`, etc.) | `schema-demand-context.md` |
| Market research, comp theses, channel, midterm, underwriting | `schema-market-research.md`, `market-research-playbook.md`, `decision_gates.evaluate_market_research_pack` |
| Recommendation/action/experiment/outcome attribution rows | `decisioning.md` |
| Conversion diagnosis, photo/product audit, gallery CRO, content brief, settings drift, calendar actions, operations risk, channel strategy | `scripts/decision_gates.py` |
| Visual-revenue, image-improvement prompts, design opportunities | `visual-revenue-workflows.md`, `schema-visual-revenue.md` |
| REA building rental monitoring | `realestate-building-rentals.md`, `scripts/collect_rea_building_rentals.py` |

## Open frontiers

Pulled from `pipeline-fulfilment.md` "Remaining evidence gaps" and from the
decision/learning loop end state. Each frontier is a candidate, not a committed
plan.

1. **Public rank longitudinal trend.** Today's public-rank rows are sampled,
   date-specific observations. Convert them into a stable trend by repeating
   across dates, guests, stay lengths, devices, and time-of-day; build a
   trend-aware view of search-card visibility instead of single-snapshot rank.
2. **Lightpanda field-level parity.** Lightpanda is a capability candidate
   only. Before promoting it for any public surface, prove field-level parity
   against headful Chrome for the exact public search and listing-page fields
   the collectors emit.
3. **Listing-level rating null discipline.** `rating_display_state`,
   `star_distribution_source`, and related fields already distinguish absent
   widgets from parser failure. Continue preserving nulls and never fill from
   host-aggregate review averages; revisit only if Airbnb exposes per-listing
   rating widgets more uniformly.
4. **Closed-loop outcome learning.** `airbnb_recommendation`,
   `airbnb_action_log`, `airbnb_experiment`, and `airbnb_outcome_attribution`
   rows exist; the loop closes only once outcome attribution feeds back into
   recommendation suppression (stop suggesting changes that repeatedly fail to
   move metrics) and into confidence weighting on future recommendations.

## Enhancement principles

- Do not add a metric unless it changes a decision.
- Prefer pure decision-gate helpers in `scripts/decision_gates.py` over
  browser-dependent recommendation logic. Collectors gather rows; helpers
  evaluate them.
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

## Examples of host questions the system should answer

- "This date is unbooked; is that because the market is soft, my price is high,
  minimum stay blocks common searches, or my search-card conversion is weak?"
- "If I discount this orphan night, does the expected margin beat cleaner and
  linen cost?"
- "Did changing the hero photo improve search-to-listing conversion after
  controlling for demand period?"
- "Are we underpricing because the comp set ignores a local event?"
- "Should we pursue, watch, or reject this building after absorption, capacity,
  comp-thesis, channel, and underwriting checks?"
- "Which recommendations repeatedly fail and should stop being suggested?"
