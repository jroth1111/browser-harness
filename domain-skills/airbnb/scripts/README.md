# Airbnb scripts index

This directory holds the executable workflows and helper modules for the Airbnb
host-intelligence skill. Read this index before picking a script. For the
why/what behind each workflow, follow the "Governing markdown" link.

If you are reading the Airbnb skill cold, start in `../overview.md` first. This
file answers "what can be run"; the overview answers which user intent,
control-flow stage, and evidence/source family apply.

This file owns script invocation status only. Workflow markdown owns when and why
to run a surface, and schema markdown owns durable row fields.

Machine `source_family` values in this file are existing collector/receipt
values. Do not rename them here without a separate receipt migration.

Directory roles:

- **runner** — top-level orchestrator you invoke directly for a recurring job.
- **collector** — single-source data capture; usually invoked by hand or by a runner.
- **probe** — diagnostic. Confirms or refreshes an empirical fact about Airbnb's
  API. Run on demand, not on a schedule.
- **helper** — imported by the collectors/runner. Do not invoke directly.

Keep the scripts physically flat unless a task explicitly accepts a broad path
migration. Collectors and tests load helpers from
`domain-skills/airbnb/scripts/<name>.py`, so subdirectories would require a
coordinated update across docs, tests, import loaders, and command examples.

## Runners

| Script | Role | Control-flow stage | `source_family` | Purpose | Reads | Produces | Governing markdown |
|---|---|---|---|---|---|---|---|
| `sync_insights_year_view.py` | runner | collection + validation/render | `host_private` | Canonical Insights sync. Preflight cookies -> optional granularity probe -> `collect_insights.py` (patient mode) -> per-family extracts -> `data_display.render_dataset` HTML -> year-view receipt. Run this for the standard Insights workflow, not `collect_insights.py` directly. | latest complete `airbnb-live-listings-*.json`; ledger at `.private-data/insights-collections/.ledger.jsonl` | `airbnb-insights-year-view-*.json` snapshot, family extracts (`-conversion-only`/`-occupancy-only`/`-quality-only` JSON+CSV+HTML), `<run_id>-year-view-receipt.json` | `../host-sources.md` (year-view sync), `../e2e-insights-data-display-plan.md` |
| `schedule_surface_refresh.py` | runner | scheduling | `scheduler` | Local staleness scheduler. Reads capability receipts and emits a priority-ordered refresh task plan by source family. Does not contact Airbnb. | `.session-store/capability/*receipt.json`, `.private-data/capability-probes/*.json` | `.private-data/schedules/<run_id>.json`, `<run_id>-receipt.json` | `../host-sources.md`, `../public-market.md` |

## Collectors

All collectors write private outputs under ignored
`domain-skills/airbnb/.private-data/...` and a compact receipt under
`.session-store/capability/`. None type credentials; if login is required the
script stops at the login wall.

Run browser-backed collectors through the browser harness so helper functions
such as `new_tab`, `goto_url`, `js`, `wait_for_content`, and `browser_cookies`
are preloaded:

```bash
BH_NAME=<profile-name> BH_CDP_WS=http://127.0.0.1:<port> \
  python3 run.py < domain-skills/airbnb/scripts/<collector>.py
```

Do not invoke these collector files as plain `python3 <collector>.py`; they are
browser-harness programs, not standalone Python CLIs.

| Script | Role | Control-flow stage | `source_family` | Auth | Reads | Produces | Refuses to run if | Governing markdown |
|---|---|---|---|---|---|---|---|---|
| `collect_listings.py` | collector | collection | `host_private` | logged-in (host) | bootstrap API key from `/hosting/listings`; optional `AIRBNB_AUTH_STATE_PATH` private bundle | `airbnb-live-listings-*.json` and `.csv` under `.private-data/listing-collections/` | bootstrap API key cannot be read | `../host-sources.md` (Authenticated live-listing inventory workflow), `../workflows-current-state.md` Workflow 5 |
| `collect_calendar_export.py` | collector | collection | `calendar_export` | export URL / local `.ics` file | `AIRBNB_ICAL_SOURCE`, `AIRBNB_ICAL_LISTING_ID`; prior calendar-export collection for empty-feed protection | iCal event rows and daily `airbnb_calendar_snapshot`-style rows under `.private-data/calendar-export-collections/` | source/listing ID is missing, or an empty feed follows a prior non-empty feed without `AIRBNB_ICAL_ALLOW_EMPTY=1` | `../host-sources.md` (Calendar and iCal) |
| `collect_exports.py` | collector | collection | `host_export` | downloaded export file / directory | `AIRBNB_EXPORT_KIND`, `AIRBNB_EXPORT_SOURCE`; supports `earnings_csv`, `reservation_detail`, and `personal_data_catalog` | normalized host-export rows under `.private-data/export-collections/` plus schema-validated receipt | kind/source is missing or unsupported | `../host-sources.md` (export-first ingestion) |
| `collect_insights.py` | collector | collection | `host_private` | logged-in (host) | latest complete `airbnb-live-listings-*.json`; cross-run ledger | per-listing summary + chart rows under `.private-data/insights-collections/`; ledger appends; sentinel rows for empty windows | host auth cookies missing or listing inventory is `partial_run: true` (override with `AIRBNB_LISTINGS_FILE`) | `../host-sources.md` (Authenticated per-listing Performance API workflow), `../workflows-current-state.md` Workflow 5 |
| `collect_host_reviews.py` | collector | collection | `host_private` | logged-in (host) | latest complete listing inventory; default scope `ACTIVE` | `airbnb_review`-shaped rows under `.private-data/review-collections/` | listing inventory missing or partial unless `AIRBNB_HOST_REVIEWS_LISTING_SCOPE` is set explicitly | `../host-sources.md` (Reviews and quality themes) |
| `collect_competitors.py` | collector | collection | `public_market` | logged-out (fresh profile) | latest complete listing inventory | search runs, search-card rows, comp price matrix, target-comp links, deduplicated comp listing snapshots under `.private-data/public-market-collections/` | known Airbnb authenticated-session cookies are present, or listing inventory is `partial_run: true` | `../public-market.md` (Executable competitor collection), `../workflows-current-state.md` Workflow 2 |
| `collect_own_public.py` | collector | collection | `own_public` | logged-out (fresh profile) | latest complete listing inventory | own public listing audits, review summaries, review snapshots, search-appearance rows under `.private-data/own-public-collections/` | known Airbnb authenticated-session cookies are present, or listing inventory is `partial_run: true` | `../public-market.md` (Executable own public collection), `../workflows-current-state.md` Workflow 4 |
| `collect_rea_building_rentals.py` | collector | collection | `external_public_market` | public REA browser session | latest complete listing inventory; optional private building watchlist; prior REA observation/building-price ledgers | building-level REA rental observations, building price snapshots, event rows, raw listing text, run-state checkpoints, and idempotent cross-run JSONL ledgers under `.private-data/realestate-rental-collections/` | no complete Airbnb listing inventory is available, or REA pages are served as challenge/blocked pages | `../realestate-building-rentals.md`, `domain-skills/realestate-com-au/scraping.md` |

Owner-cookie refusal exists because logged-in profiles personalize Airbnb search
ranking toward the owner's listings; rank/visibility numbers from such a run
are not valid market evidence.

Public search collectors default to `room_types[]=Entire home/apt`. Use a
different room type only for tasks that explicitly study private-room or
shared-room competition.

## Probes

Probes are one-shot diagnostics. Re-run only when the empirical answer might
have moved.

| Script | Role | Control-flow stage | `source_family` | Purpose | Re-run when | Output |
|---|---|---|---|---|---|---|
| `probe_surfaces.py` | probe | capability check | `capability` | Capability probe for Airbnb source families: public comp search, own public audit, private listing inventory, host reviews, calendar/availability, calendar export, pricing rules, earnings/reservations/payouts, market scans, and regression hashes. It records reachability and redacted resource/hash evidence, not sensitive payloads. | A collector starts failing, a new Airbnb UI surface is needed, or the capability receipt for a surface is stale under `surface_capabilities.py` cadence. | `.private-data/capability-probes/<run_id>.json` and `.session-store/capability/<run_id>-receipt.json` |
| `probe_network_discovery.py` | probe | capability/discovery | `capability` | Probe browser performance-resource logs for redacted API/resource families and operation hash prefixes. Discovery only; never stores response payloads and must not become a production collector path. | A page/API route changes, a collector needs source discovery, or regression evidence is needed for endpoint families. | `.private-data/network-discovery/<run_id>.json` and `.session-store/capability/<run_id>-receipt.json` |
| `probe_chart_granularity.py` | probe | fact-table refresh | `capability` | Probe `ChartQuery` for `conversion_rate`, `occupancy_rate`, and `overall` across horizons 14-365 days; refresh the granularity reference table. | `../insights-granularity-map.md` is older than 30 days, or chart granularities look wrong in a recent run. `sync_insights_year_view.py` invokes this automatically when stale unless `--skip-probe`. | `../insights-granularity-map.md` (committed) and `.private-data/insights-collections/airbnb-insights-granularity-probe.json` |
| `probe_single_day_windows.py` | probe | capability/regression | `capability` | Confirm `ChartQuery` rejects zero-width windows like `(0,0)` or `(-7,-7)`. Backstops the planner's `daily_end = today - 1` rule. | A planner change reintroduces single-day windows or `ChartQuery` boundary behavior is suspected to have changed. | `.private-data/insights-collections/airbnb-insights-single-day-window-probe.json` |

## Local guards

| Script | Role | Control-flow stage | `source_family` | Purpose |
|---|---|---|---|---|
| `redaction_scan.py` | guard | validation/provenance | n/a (local guard) | Local scanner for redacted fixtures, receipts, manifests, and docs. It skips `.private-data` and `.session-store` by default and fails on token, cookie, email, and phone-like raw identifiers. |

## Helpers (do not invoke directly)

| Module | Role | Control-flow stage | `source_family` | Used by | Purpose |
|---|---|---|---|---|---|
| `insights_ledger.py` | helper | normalized rows | `host_private` | `collect_insights.py`, `insights_planner.py` | JSONL ledger reader/writer; bucket builder for covered-date lookups; sentinel expiry rules. |
| `insights_planner.py` | helper | source selection/collection | `host_private` | `collect_insights.py` | Tiered request planner. Emits summary + rolling-daily + single-window chart requests, skipping ledger-covered and sentinel-covered windows. |
| `extract_route_family.py` | helper | validation/render | `host_private` | `sync_insights_year_view.py` | Splits a year-view snapshot into `conversion`/`occupancy`/`quality` family extracts (JSON + summary CSV + daily CSV). Importable for ad-hoc extracts but not a direct workflow. |
| `listing_scope.py` | helper | intake/scope | mixed | `collect_listings.py`, `collect_insights.py`, `collect_host_reviews.py`, `collect_own_public.py`, `collect_competitors.py` | Parses listing-scope selectors (`active`, `all`, `statuses:...`, `ids:...`) and filters records. |
| `operation_hashes.py` | helper | capability/collection | `host_private`, `capability` | `collect_insights.py`, `collect_listings.py`, `probe_chart_granularity.py`, `probe_single_day_windows.py`, `probe_surfaces.py` | Discovers, validates, and resolves Airbnb persisted GraphQL operation hashes from loaded pages, web bundles, env overrides, and the local capability registry before falling back to known hashes. |
| `photo_product_evidence.py` | helper | decision gate | n/a (local evaluator input) | `decision_gates.py`, reports, tests | Normalizes photo/product evidence, proof flags, subject tags, and visual signals before content/photo decision gates consume them. |
| `public_scan_planner.py` | helper | source selection/collection | `public_market`, `own_public` | `collect_competitors.py`, `collect_own_public.py` | Validates public-market options, expands check-in/stay matrices, and manages optional price bands/recursive public search partitioning. |
| `decision_gates.py` | helper | decision gate | n/a (pure local evaluator) | reports, tests, recommendation builders | Pure local evaluators for market research gates, comp grading, listing maturity, opportunity snapshots, slow-season survival, conversion diagnosis, photo/product audits, gallery CRO execution boards, listing content optimization briefs, rule-set/settings drift, calendar actions, operations risk, and channel strategy. |
| `run_integrity.py` | helper | validation/provenance | n/a (control-plane validator) | Airbnb collectors, runners, probes | JSON-schema-style receipt/output contract validation, downstream refusal guards, last-good empty-run quarantine checks, warehouse/BI export manifests, redaction helpers, and step checkpoints. |
| `surface_capabilities.py` | helper | capability/scheduling | `capability`, `scheduler`, source-specific families | collectors, `probe_surfaces.py`, `probe_network_discovery.py`, `schedule_surface_refresh.py` | Shared surface catalog, redacted capability receipts, network discovery summaries, operation-hash summaries, source-family/surface-class labels, persisted capability registry helpers, and staleness planning for Airbnb source families. |

## Quick "what do I run?" map

| Goal | Run |
|---|---|
| Refresh the host's live private listing inventory | `collect_listings.py` |
| Refresh calendar export / iCal daily availability snapshots | `collect_calendar_export.py` |
| Parse downloaded Airbnb earnings, reservation, or personal-data exports | `collect_exports.py` |
| Refresh per-listing Insights (conversion, occupancy, quality) for dashboards | `sync_insights_year_view.py` |
| Refresh authenticated host review rows | `collect_host_reviews.py` |
| Refresh logged-out competitor comp set + price matrix | `collect_competitors.py` |
| Audit how the host's own listings appear to a guest | `collect_own_public.py` |
| Track long-term rental asking prices in buildings where current Airbnb listings operate | `collect_rea_building_rentals.py` |
| Decide which Airbnb source family is stale enough to refresh next | `schedule_surface_refresh.py` |
| Check whether an Airbnb source family is still reachable without collecting private payloads | `probe_surfaces.py` |
| Discover changed Airbnb API/resource families from browser network logs | `probe_network_discovery.py` |
| Confirm or refresh `ChartQuery` granularity facts | `probe_chart_granularity.py` |
| Scan Airbnb fixtures/docs/receipts for raw secrets before committing | `redaction_scan.py` |

For workflow context (when, why, acceptance criteria) read
`domain-skills/airbnb/workflows-current-state.md`. For the executable details
of each surface, read `domain-skills/airbnb/host-sources.md` (private) and
`domain-skills/airbnb/public-market.md` (public).

For decision-helper selection, read the **Decision-helper lookup** in
`domain-skills/airbnb/overview.md`. `decision_gates.py` is import-only: it
evaluates already-collected rows and should not be used as a browser or
collection entry point.
