# Airbnb.com.au - Host Intelligence Overview

Use this skill when the user is an Airbnb host or co-host and wants to improve
pricing, calendar control, conversion, operations, listing quality, comp-set
positioning, portfolio reporting, or Australian compliance awareness from
Airbnb.com.au data.

## 90-second cold start

If you read this skill cold, do not start in collector code. Use this route:

1. Identify what the user wants to decide, produce, or run.
2. Use the intent router below to choose the desired outcome and one first
   workflow/playbook file.
3. Use the two-axis model to identify the current control-flow stage and the
   evidence/source guardrails. Source family is a guardrail, not the first
   question.
4. Read `scripts/README.md` only when the task requires a run, probe, validation
   check, or helper contract. It tells you which scripts are runnable and which
   modules are helper-only.
5. Open schema files only after you know the output row, table, or artifact you
   need.

Before any Airbnb collection, preserve these invariants:

- Exports win when they contain the needed fields. Use UI/API scraping only
  when the UI is richer, the export omits the field, or reconciliation requires
  both; record that reason in the receipt.
- Public market evidence must come from logged-out guest-visible context.
  Owner-session search rank and public comp data are invalid by default.
- Host-private collection starts from a complete listing inventory unless the
  collector explicitly documents a narrower safe scope.
- Capability probes may discover drift and capability records; normal collectors
  consume validated capabilities instead of sniffing network traffic at runtime.
- `quarantined`, `partial`, or incompatible `source_class` data must not feed
  downstream renderers, BI exports, or reconciliations unless an explicit
  override is part of the task.

## Intent Router

Start here when the user speaks in business language. Pick the row that matches
the request, then read only the first workflow/playbook named for that row. This
is the canonical router for cold readers; later matrices expand this table by
artifact or execution detail and must not introduce a competing first step.

| User intent | Desired outcome | Read first | Script/helper if needed | Output owner |
|---|---|---|---|---|
| What should I run? | Runnable entry point or helper-only refusal | `scripts/README.md` | Script row named there | Governing workflow doc named by the script |
| Current market, competitor, or own-listing state | Source plan or current-state report | `workflows-current-state.md` | `collect_competitors.py`, `collect_own_public.py`, `collect_listings.py`, `sync_insights_year_view.py` as needed | Source schema family, then `decisioning.md` if actioned |
| Pricing, rule-set drift, Smart Pricing, discounts, promotions, or orphan nights | Settings drift finding, calendar action, or recommendation | `analytics-alerts.md`, `decisioning.md` | `audit_settings_drift`, `generate_calendar_actions` | `schema-performance.md`, `decisioning.md` |
| Conversion diagnosis, search-card click appeal, listing-page conversion, or price friction | Conversion diagnosis and next bottleneck action | `analytics-alerts.md`, then `public-market.md` | `diagnose_listing_conversion`, `audit_photo_product_gap`, `build_listing_opportunity_snapshot` | `schema-performance.md`, `schema-public-market.md`, `decisioning.md` |
| Photo, gallery, title, caption, design, or listing content optimization | Photo/product audit, gallery board, or content brief | `operator-insight-workflows.md`, then `content-optimization-playbook.md` | `audit_photo_product_gap`, `build_gallery_cro_execution_board`, `build_listing_content_optimization_brief` | `schema-performance.md`, `schema-core.md`, `decisioning.md` |
| Image-improvement prompts, photo/profit/Insights correlation, or low-cost design opportunities | Visual sidecar rows, prompt rows, or design opportunities | `visual-revenue-workflows.md` | Workflow 1-3 helpers or reports named there | `schema-visual-revenue.md`, `decisioning.md` if actioned |
| Market selection, property validation, co-hosting, expansion, arbitrage, or channel strategy | Pursue/watch/reject or channel strategy decision | `market-research-playbook.md` | `evaluate_market_research_pack`, `grade_public_comp`, `evaluate_slow_season_survival`, `evaluate_channel_strategy` | `schema-market-research.md`, `schema-finance.md`, `decisioning.md` |
| REA rent monitoring, building watchlist, rental lifecycle, or rental asking-price history | Building rent observations, events, and price snapshots | `realestate-building-rentals.md` | `collect_rea_building_rentals.py` | REA JSONL rows, then `schema-market-research.md` if underwritten |
| Operations, reviews, messages, cleaning, maintenance, tasks, or guest issues | Operations risk snapshot or recommendation | `analytics-alerts.md`, `schema-operations.md`, then `host-sources.md` | `collect_host_reviews.py`, `evaluate_operations_risk` | `schema-operations.md`, `decisioning.md` |
| Data freshness, provenance, redaction, quarantine, or output contracts | Validation check, redaction scan, schedule, or source-quality row | `data-quality.md`, then `scripts/README.md` | `run_integrity.py`, `redaction_scan.py`, `schedule_surface_refresh.py` | `data-quality.md`, `schemas/*.json` |
| Schema/table fields for an `airbnb_*` record | Authoritative row contract | Schema row index below | None unless a validator is needed | Named schema file |

## Two-Axis Model

Use the intent router to choose the task. Then classify the task on two
orthogonal axes so you do not confuse workflow stage with evidence source.

| Axis | Buckets | Use it to decide |
|---|---|---|
| Control-flow stage | intake/scope, source selection, capability check, collection, validation/provenance, normalized rows, decision gate, brief/recommendation, action/experiment/rollback, outcome review | Which file to read next and whether to run a collector, call a helper, or log an action |
| Evidence/source family | public Airbnb market, own public listing, host-private Airbnb, calendar/iCal export, host export, external market/REA, demand context, local visual evidence, internal/manual facts | Auth posture, privacy boundary, allowed joins, source freshness, and schema family |

Capability probes, schedulers, redaction scans, and run-integrity checks are
control-plane tools. They validate or schedule evidence collection; they are not
business evidence sources by themselves.

## Evidence Source And Auth Guardrails

Use this table after the intent router has selected the task. It does not choose
the business workflow; it constrains the evidence source, auth posture, allowed
joins, and refusal guardrails for the source family already implied by the
intent.

| Evidence family | Machine `source_family` values | When this source is selected, use | Run or helper | Hard stop / guardrail |
|---|---|---|---|---|
| Public Airbnb market | `public_market` | `public-market.md`, then `workflows-current-state.md` | `collect_competitors.py`, `public_scan_planner.py` | Refuse owner cookies; validate dates, guests, currency, room type, limits, and URL inputs before a run. |
| Own public listing | `own_public` | `public-market.md`, then `workflows-current-state.md` Workflow 4 | `collect_own_public.py` | Observe as a logged-out guest; do not infer guest-visible state from host-only pages. |
| Host-private Airbnb | `host_private`, `host_private_sensitive` | `host-sources.md`, then `session-continuity.md` | `collect_listings.py`, `sync_insights_year_view.py`, `collect_host_reviews.py` | Do not type credentials; restore browser auth via manual session continuity and redacted manifests only. |
| Calendar/iCal export | `calendar_export`, `calendar` | `host-sources.md`, Calendar and iCal | `collect_calendar_export.py` | Do not treat a suspicious empty feed after prior non-empty data as a fresh zero-state without an explicit override. |
| Host export | `host_export` | `host-sources.md`, export-first sections | `collect_exports.py` | Do not scrape if the export has the needed field set; keep export and UI/API augmentation as separate observations. |
| External market / REA | `external_public_market` | `realestate-building-rentals.md`, then `market-research-playbook.md` | `collect_rea_building_rentals.py` | REA rent evidence does not approve an arbitrage deal; hand it to the market playbook for underwriting. |
| Demand context | `third_party_open_data` or schema-only demand rows | `workflows-current-state.md` Workflow 1, `schema-demand-context.md` | Manual/open-data import unless a workflow names a script | Keep as context with freshness/confidence; do not blend into Airbnb evidence without labeling the inference. |
| Local visual evidence | `local_visual_evidence` or schema-only visual rows | `visual-revenue-workflows.md` | Workflow 1-3 outputs named there | Do not fabricate property facts; use additive sidecars and accuracy gates. |
| Internal/manual facts | internal/manual source rows | `schema-finance.md`, `decisioning.md`, relevant workflow | None unless a report imports a local file | Keep costs, owner contracts, and action history source-tagged and private when sensitive. |
| Capability and quality control | `capability`, `scheduler` | `exploration-protocol.md`, `data-quality.md`, `scripts/README.md` | `probe_surfaces.py`, `probe_network_discovery.py`, `probe_chart_granularity.py`, `schedule_surface_refresh.py`, `redaction_scan.py`, `run_integrity.py` | Redacted capability/quality records support trust in a source; they are not production collectors or private payload stores. |

## Canonical Source Taxonomy

The labels above are the LLM-facing names. Persisted receipts and warehouse
manifests keep the existing machine values below; do not rename them without a
separate migration.

| LLM-facing label | Persisted value(s) | Typical scripts / files |
|---|---|---|
| public Airbnb market | `public_market` | `collect_competitors.py`, `public-market.md`, `schema-public-market.md` |
| own public listing | `own_public` | `collect_own_public.py`, `public-market.md`, `schema-public-market.md` |
| host-private Airbnb | `host_private`, `host_private_sensitive` | `collect_listings.py`, `sync_insights_year_view.py`, `collect_host_reviews.py`, `host-sources.md` |
| calendar/iCal export | `calendar_export`, `calendar` | `collect_calendar_export.py`, `host-sources.md`, `schema-core.md` |
| host export | `host_export` | `collect_exports.py`, `host-sources.md`, `schema-core.md`, `schema-finance.md` |
| external market / REA | `external_public_market` | `collect_rea_building_rentals.py`, `realestate-building-rentals.md` |
| demand context | `third_party_open_data` or demand-context schema rows | `workflows-current-state.md`, `schema-demand-context.md` |
| local visual evidence | `local_visual_evidence` or visual schema rows | `visual-revenue-workflows.md`, `schema-visual-revenue.md` |
| internal/manual facts | internal/manual source rows | `schema-finance.md`, `decisioning.md` |
| capability probe | `capability` | `probe_surfaces.py`, `probe_network_discovery.py`, `probe_chart_granularity.py`, `probe_single_day_windows.py` |
| scheduler | `scheduler` | `schedule_surface_refresh.py` |

## File map

Read the smallest file that matches the job. The `Kind` column tells you why
the file exists:

- **skill** — runtime guidance you should follow when executing a task.
- **schema** — table/field definitions for storing observations.
- **status** — current evidence ledger for the pipeline; informational, not
  prescriptive.
- **plan** — backlog or test plan; aspirational, not runtime guidance.
- **fact-table** — empirical reference data refreshed by a probe.

| File | Kind | Purpose |
|---|---|---|
| `README.md` | skill | Folder landing page and fast path for cold readers |
| `overview.md` | skill | Intent routing, two-axis model, source guardrails, build order, common executable entry points, schema index |
| `exploration-protocol.md` | skill | Discovery-first process for public, private, Lightpanda, and headful sources |
| `workflows-current-state.md` | skill | Sensing workflows for market, competitor, and own-listing current state |
| `market-research-playbook.md` | skill | Dealflow, opportunity discovery, property validation, market archetypes, and pursue/watch/reject decisions |
| `data-inventory.md` | skill | Public/private data primitive catalog and source matrix |
| `session-continuity.md` | skill | Auth/session continuity, cookie safety, local ignored session store |
| `host-sources.md` | skill | Authenticated host collection workflows and refresh cadence |
| `public-market.md` | skill | Public search/listing extraction and comp-set observations |
| `realestate-building-rentals.md` | skill | Realestate.com.au building rental monitor, suburb-wide search, lifecycle events, price snapshots, and building watchlist |
| `analytics-alerts.md` | skill | Derived metrics, playbooks, alerts, and dashboard tiles |
| `decisioning.md` | skill | Recommendation, experiment, action, and outcome tracking |
| `operator-insight-workflows.md` | skill | Operator-derived photo/product and case-study replay workflows |
| `content-optimization-playbook.md` | skill | Photo, gallery, title, and Airbnb-section copy optimization after evidence shows a content bottleneck |
| `visual-revenue-workflows.md` | skill | Image-improvement prompting, real-photo profit correlation, and low-cost interior-design opportunity workflows |
| `data-quality.md` | skill | Provenance, freshness, confidence, privacy, and QA rules |
| `schema-core.md` | schema | Listing, content, calendar, reservation, economics, payout/tax tables |
| `schema-performance.md` | schema | Pricing, rule-set, conversion, occupancy, and quality tables |
| `schema-operations.md` | schema | Reviews, guest context, message workflows, operations task tables |
| `schema-public-market.md` | schema | Public search run, search result, comp listing, price matrix tables |
| `schema-market-research.md` | schema | Absorption, stay-length, capacity, comp-thesis, channel, underwriting, and market-decision tables |
| `schema-visual-revenue.md` | schema | Image-improvement prompts, visual observations, image observations, and interior-design opportunity rows |
| `schema-finance.md` | schema | Internal costs, owner statements, margin, cash-flow, and capex tables |
| `schema-demand-context.md` | schema | Events, holidays, weather, regulation, and demand-context enrichments |
| `pipeline-fulfilment.md` | status | Current evidence ledger for host intelligence pipeline coverage |
| `enhancement-roadmap.md` | plan | Enhancement backlog and priority sequence |
| `e2e-insights-data-display-plan.md` | plan | End-to-end test plan for the Insights → display chain |
| `insights-granularity-map.md` | fact-table | Empirical `ChartQuery` granularity by horizon (refreshed by `scripts/probe_chart_granularity.py`) |
| `scripts/README.md` | skill | Index of executable runners, collectors, probes, and helpers |
| `schemas/*.json` | schema | Machine-checkable collection-output, collection-receipt, and warehouse-manifest contracts used by `scripts/run_integrity.py` |

## Directory and artifact roles

Use this table to separate reusable skill guidance from run evidence and test
support. Keep broad searches on the reusable surface unless the task explicitly
requires local run artifacts.

| Path | Role | Commit/search posture |
|---|---|---|
| `README.md`, `overview.md` | routers | Start here; these files route readers to workflows, scripts, and schema homes. |
| `*-workflows.md`, `*-playbook.md`, `host-sources.md`, `public-market.md`, `analytics-alerts.md`, `decisioning.md` | workflows and judgement rules | Reusable guidance. These files own control paths, refusal guards, decision rules, and handoffs, not durable field lists when a schema file exists. |
| `schema-*.md`, `data-quality.md`, `analytics-alerts.md`, `decisioning.md`, `realestate-building-rentals.md` | row-contract homes | Durable `airbnb_*` field lists and allowed values. `analytics-alerts.md` and `realestate-building-rentals.md` are deliberate schema exceptions called out in the schema row index. Use the schema row index below before editing or consuming a row. |
| `scripts/README.md` | executable index | Runnable vs helper-only classification, prerequisites, outputs, and refusal rules. |
| `scripts/*.py` | implementation | Open after the script index or a failing test identifies the relevant script. |
| `schemas/*.json` | machine contracts | JSON contracts for collection outputs, receipts, and warehouse manifests. |
| `fixtures/` | reusable test fixtures | Safe committed fixtures for parser, decision-gate, and skill-learning tests. Do not mix with private run artifacts. |
| `.private-data/` | private run evidence | Ignored local data: auth bundles, raw/source outputs, ledgers, downloaded images, and private exports. Do not commit or quote contents in docs. |
| `.session-store/` | local continuity store | Ignored local manifests, browser profiles, and capability receipts. Do not commit cookies or live auth state. |
| `outputs/` | generated shareable reports | Generated reports/workbooks. Link only sanitized artifacts when needed; keep raw private records in `.private-data/`. |

## Logical structure

The Airbnb skill intentionally keeps reusable markdown at the skill root and
uses this overview as the logical table of contents. Do not split files into
physical subdirectories unless the task explicitly accepts the path churn and all
references, tests, package data, and script constants are updated together.

| Layer | Files | Owns | Handoff |
|---|---|---|---|
| Entry and routing | `README.md`, `overview.md` | Cold start, intent router, two-axis model, source guardrails, artifact map, schema lookup | Points to one workflow or script index row |
| Source and sensing workflows | `exploration-protocol.md`, `workflows-current-state.md`, `host-sources.md`, `public-market.md`, `realestate-building-rentals.md`, `data-inventory.md`, `session-continuity.md` | What source to collect, auth posture, refusal guards, output locations, source-specific acceptance rules | Writes source rows into the schema family named by the workflow |
| Decision and action playbooks | `market-research-playbook.md`, `analytics-alerts.md`, `operator-insight-workflows.md`, `content-optimization-playbook.md`, `visual-revenue-workflows.md`, `decisioning.md` | Judgement rules, gates, scoring, recommendation/action/outcome flow | Reads collected rows, emits schema rows or decisioning rows |
| Durable row contracts | `schema-*.md`, `data-quality.md`, `decisioning.md`, plus deliberate exceptions in `analytics-alerts.md` and `realestate-building-rentals.md` | Row grains, field lists, allowed values, joins, refresh semantics | Workflow docs may name these rows but should not duplicate their full contracts |
| Executable control plane | `scripts/README.md`, `scripts/*.py` | What is runnable, what is helper-only, env vars, outputs, local guards, probes | Collectors/probes write ignored run artifacts and receipts; helpers are imported only |
| Reusable fixtures and machine contracts | `fixtures/`, `schemas/*.json` | Parser, decision-gate, skill-learning fixtures and JSON validation contracts | Tests and guards consume these; do not mix with private run output |
| Local/generated artifacts | `.private-data/`, `.session-store/`, root `outputs/` | Private evidence, session continuity, generated reports/workbooks | Ignored by git; cite paths only when sanitized and relevant |

## Expanded Routing Matrix

Use this section after the canonical Intent Router when the task spans multiple
artifacts or you need the full read/collect/decide/output chain. It expands the
intent router; it is not a second router and should not override the first
workflow selected above.

Start with the user’s host question, then read progressively until you have
enough context.

The skill is organized as an intent-first ladder:

```text
intent -> desired outcome -> control-flow stage -> evidence/source family -> script/helper -> schema/output
```

Do not jump straight to implementation files. First identify which rung you are
on and only open the next rung when the current one is insufficient.

Progressive read order:

1. Read this `overview.md` file for routing, source reliability, executable
   entry points, and schema lookup.
2. Choose one row in the Intent Router, then use the matching row below only
   when you need the expanded chain. Read only the `Read first` files for that
   row.
3. If data must be collected, open `scripts/README.md` and the governing
   markdown named for the collector. Do not open collector code until you need
   implementation details or a parser contract.
4. If data already exists, use `scripts/decision_gates.py` helpers on collected
   rows. These helpers are pure local evaluators and do not browse or collect.
5. If a decision becomes a host action, switch to `decisioning.md` for
   recommendation, action log, experiment, rollback, and outcome tracking.
6. Open schema files only when you need field names for a table or output
   record.

For content work specifically: collect or inspect public presentation first,
run `audit_photo_product_gap()` or `diagnose_listing_conversion()`, then use
`content-optimization-playbook.md` for the subject-level brief and
`build_gallery_cro_execution_board()` when exact photo IDs are available.

Stop-reading rules:

- If the user asks "what should I run?", stop after `scripts/README.md` plus the
  governing workflow file for that script.
- If the user asks "what does this row mean?", stop after the relevant schema
  and the decision helper that consumes it.
- If the user asks for a recommendation, do not open action-tracking docs until
  the decision helper returns `fix`, `pursue`, or another actionable decision.
- If the user asks for photo/copy/content changes, do not open
  `content-optimization-playbook.md` until public presentation evidence or a
  user-supplied listing brief exists.
- If a schema field is unclear, use the schema row index below instead of
  searching every file.

## Progressive Artifact Map

Use this map when you know the artifact you have or need.

| You have | Next question | Open next | Produce |
|---|---|---|---|
| Host objective only | What evidence is needed? | Task router row below | State-run scope or source plan |
| Listing IDs / URLs | Which public/private sources apply? | `workflows-current-state.md`, then `public-market.md` or `host-sources.md` | Source collection plan |
| Public search/listing rows | Are comps valid and comparable? | `schema-public-market.md`, `scripts/decision_gates.py` | comp grades, listing opportunity, public evidence rows |
| Own public audit + A-comps | Is content the bottleneck? | `operator-insight-workflows.md`, `scripts/decision_gates.py` | `airbnb_photo_product_gap_audit` |
| Content-facing issue class | What should change? | `content-optimization-playbook.md` | `airbnb_listing_content_optimization_brief` |
| Exact photo IDs + current order | What can be published? | `content-optimization-playbook.md`, `scripts/decision_gates.py` | `airbnb_gallery_cro_execution_board` |
| Public photos/contact sheets + economics workbook | Which visual patterns correlate with revenue or profit? | `visual-revenue-workflows.md` Workflow 2 | `airbnb_visual_listing_observation`, `airbnb_visual_image_observation`, calibration workbook |
| Inferior images + listing facts | What image-edit prompt is safe and commercially useful? | `visual-revenue-workflows.md` Workflow 1 | `airbnb_image_improvement_prompt` |
| Visual gaps + high/low pattern summaries | What is the cheapest design or staging improvement? | `visual-revenue-workflows.md` Workflow 3 | `airbnb_interior_design_opportunity`, `airbnb_portfolio_design_action` |
| Current listing inventory + REA building watchlist | What long-term rents are moving in these buildings? | `realestate-building-rentals.md`, `scripts/README.md` | REA observations, events, and building price snapshots |
| Calendar/pricing/rule rows | Is there a tactical pricing/rule action? | `analytics-alerts.md`, `decisioning.md`, `scripts/decision_gates.py` | settings drift finding or calendar action candidate |
| Decision-gate `fix` / `pursue` | How do we track implementation? | `decisioning.md` | recommendation, action log, experiment |
| Completed action window | Did it work? | `decisioning.md`, `analytics-alerts.md` | outcome attribution |

## Storage And Output Map

Use this when a user asks where prior work, run outputs, ledgers, or generated
artifacts should be found.

| Artifact family | Default location | Governing file |
|---|---|---|
| Private listing inventory | `.private-data/listing-collections/` | `host-sources.md` |
| Calendar export snapshots | `.private-data/calendar-export-collections/` | `host-sources.md` |
| Host export parses | `.private-data/export-collections/` | `host-sources.md` |
| Insights year-view and family extracts | `.private-data/insights-collections/` | `host-sources.md`, `scripts/README.md` |
| Host reviews | `.private-data/review-collections/` | `host-sources.md` |
| Public competitor collections | `.private-data/public-market-collections/` | `public-market.md` |
| Own public listing audits | `.private-data/own-public-collections/` | `public-market.md` |
| REA rental observations, events, ledgers, watchlist | `.private-data/realestate-rental-collections/` | `realestate-building-rentals.md` |
| Photo manifests, downloaded images, contact sheets, visual observations | `.private-data/photo-observations/{run_id}/` | `visual-revenue-workflows.md`, `schema-visual-revenue.md` |
| Image-improvement prompt rows | `.private-data/image-improvement-prompts/{run_id}.json` | `visual-revenue-workflows.md` Workflow 1, `schema-visual-revenue.md` |
| Interior-design opportunity rows | `.private-data/interior-design-opportunities/{run_id}.json` | `visual-revenue-workflows.md` Workflow 3, `schema-visual-revenue.md` |
| Generated visual-profit/Insights workbooks/reports | `outputs/{run_id}/` | `visual-revenue-workflows.md` Workflow 2 |
| Capability probes and receipts | `.private-data/capability-probes/`, `.session-store/capability/` | `exploration-protocol.md`, `data-quality.md` |
| Refresh schedules and task plans | `.private-data/schedules/` | `scripts/schedule_surface_refresh.py`, `scripts/README.md` |
| Redacted contract schemas | `schemas/*.json` | `data-quality.md`, `scripts/run_integrity.py` |

Private `.private-data/` and `.session-store/` outputs are local evidence stores,
not committed documentation. If a run creates a shareable workbook or report,
link the `outputs/{run_id}/` artifact and keep raw private records local.

| User asks for | Read first | Collect or run | Decide with | Output records |
|---|---|---|---|---|
| Current market, competitor, or own-listing state | `workflows-current-state.md`, then `public-market.md` or `host-sources.md` | `scripts/collect_competitors.py`, `scripts/collect_own_public.py`, `scripts/collect_listings.py`, `scripts/sync_insights_year_view.py` as needed | `scripts/decision_gates.py` for conversion, opportunity, settings, calendar, and operations decisions | Source rows in `schema-public-market.md`, `schema-core.md`, `schema-performance.md`, then recommendations in `decisioning.md` |
| Market selection, property validation, co-hosting, expansion, or arbitrage | `market-research-playbook.md` | Public comp searches, own listing inventory when available, demand context, internal costs | `evaluate_market_research_pack`, `grade_public_comp`, `grade_listing_maturity`, `evaluate_slow_season_survival` | `schema-market-research.md`, `schema-finance.md`, `schema-demand-context.md` |
| Public comp set, rank, guest-visible price, or listing-page evidence | `public-market.md`, then `workflows-current-state.md` Workflow 2-4 | `scripts/collect_competitors.py` or `scripts/collect_own_public.py` from a logged-out profile | `grade_public_comp`, `grade_listing_maturity`, `build_listing_opportunity_snapshot` | `schema-public-market.md` |
| Host calendar, pricing settings, Insights, reviews, exports, or private listing data | `host-sources.md`, then `session-continuity.md` | `scripts/collect_listings.py`, `scripts/collect_calendar_export.py`, `scripts/collect_exports.py`, `scripts/sync_insights_year_view.py`, `scripts/collect_host_reviews.py` | `audit_settings_drift`, `generate_calendar_actions`, `evaluate_operations_risk` | `schema-core.md`, `schema-performance.md`, `schema-operations.md`, `schema-finance.md` |
| Pricing, rule-set drift, Smart Pricing, discounts, promotions, or orphan nights | `analytics-alerts.md`, `decisioning.md`, then `host-sources.md` for source details | Calendar/pricing/rule-set sources plus demand context and margin floor | `audit_settings_drift`, `generate_calendar_actions` | `airbnb_settings_drift_finding`, `airbnb_calendar_action_candidate`, `airbnb_recommendation`, `airbnb_action_log` |
| Conversion diagnosis, search-card click appeal, listing-page conversion, or price friction | `analytics-alerts.md`, `public-market.md`, then `decisioning.md` | Own public audit, own search appearance, public A-comps, Insights conversion when available | `diagnose_listing_conversion`, `audit_photo_product_gap`, `build_listing_opportunity_snapshot` | `schema-performance.md`, `schema-public-market.md`, `decisioning.md` |
| Photo, gallery, title, caption, design, or content optimization | `operator-insight-workflows.md`, then `content-optimization-playbook.md` | Own public audit, candidate photo IDs, current photo order, A-comp visual patterns, conversion metrics | `audit_photo_product_gap`, `build_gallery_cro_execution_board`, `build_listing_content_optimization_brief` | `airbnb_photo_product_gap_audit`, `airbnb_gallery_cro_execution_board`, `airbnb_listing_content_optimization_brief`, then `decisioning.md` |
| Image-improvement prompts, photo/profit/Insights correlation, or low-cost interior-design opportunities | `visual-revenue-workflows.md`, then `schema-visual-revenue.md`; use `content-optimization-playbook.md` only when action copy is needed | Public listing photos, contact sheets, own public audit, listing inventory, Insights conversion rows, and optional Excel/CSV economics | Workflow 1 prompt accuracy gate, Workflow 2 correlation analysis, Workflow 3 opportunity scoring | `schema-visual-revenue.md` rows, then `decisioning.md` if actioned |
| Realestate.com.au building rent monitoring, building watchlist, rental lifecycle, or rental asking-price history | `realestate-building-rentals.md`, then `market-research-playbook.md` when turning rent evidence into an arbitrage decision | Complete listing inventory, optional private building watchlist, REA suburb searches, prior REA ledgers | Building rent summaries, lifecycle events, and arbitrage rent inputs | `rea-building-rental-observations.jsonl`, `rea-building-rental-events.jsonl`, `rea-building-rental-building-prices.jsonl`, then `schema-market-research.md` or `decisioning.md` if actioned |
| Guest operations, cleaning, check-in, messages, maintenance, tasks, or review themes | `analytics-alerts.md`, `schema-operations.md`, then `host-sources.md` | Host reviews, message workflows, tasks, turnover calendar, maintenance notes | `evaluate_operations_risk` | `airbnb_operations_risk_snapshot`, `airbnb_recommendation`, `airbnb_action_log` |
| Channel strategy, direct booking, Vrbo, Booking.com, Google, Marriott, or monthly fallback | `market-research-playbook.md`, then `schema-market-research.md` | Public channel demand snapshots, product fit, operations capacity, Airbnb-native comp evidence | `evaluate_channel_strategy`, `evaluate_market_research_pack` | `airbnb_channel_strategy_snapshot`, `airbnb_market_research_decision`, `decisioning.md` |
| Data freshness, provenance, source confidence, or redaction quality | `data-quality.md`, then `scripts/README.md` | Source receipts, capability probes, redaction scan | `scripts/run_integrity.py`, `scripts/redaction_scan.py`, `scripts/schedule_surface_refresh.py` | `airbnb_data_capture_run`, `airbnb_source_observation`, `airbnb_field_quality` |

If a task spans multiple rows, collect primitives first, then use the pure
decision helpers in `scripts/decision_gates.py`. Do not browse from
`decision_gates.py`; it evaluates already-collected rows.

## Visual And Content Boundaries

Use this boundary when a task mentions photos, gallery order, copy, design,
image prompts, or revenue correlation. This is the compact visual/content
decision path:

```text
guest-visible evidence -> diagnosis -> visual calibration or content brief -> action/experiment -> outcome review
```

| Layer | Authoritative file | Owns | Does not own |
|---|---|---|---|
| Guest-visible evidence capture | `public-market.md`, `host-sources.md`, source collectors | Public listing photos, search cards, listing facts, comp evidence, host inventory | Visual scoring, prompts, or action approval |
| Diagnosis | `operator-insight-workflows.md`, `scripts/decision_gates.py` | Whether a content/photo/product issue is probably the bottleneck | Publishable copy, image-edit prompts, or schema definitions |
| Visual calibration and candidate generation | `visual-revenue-workflows.md` | Photo/profit correlation, safe image-improvement prompt generation, design-opportunity scoring | Implemented listing edits or final action tracking |
| Visual row contracts | `schema-visual-revenue.md` | Fields for visual observations, image prompts, and design opportunities | Workflow judgement rules |
| Publishable content brief | `content-optimization-playbook.md` | Guest-facing title, above-fold copy, gallery order, captions, and shot briefs after a content gate | Raw evidence collection, visual correlation, or action tracking |
| Action and learning | `decisioning.md` | Accepted recommendation, rollback, experiment, and outcome review | Source collection or visual row schema |

If a workflow produces evidence or a candidate recommendation, store it in the
source or visual schema family first. If the host accepts the change, create the
decisioning records next.

## Decision-helper lookup

Use this table when you already have collected rows and need to produce a
decision, alert, recommendation candidate, or action candidate. These helpers
are pure local evaluators in `scripts/decision_gates.py`; they do not browse,
mutate Airbnb, or collect source data.

| Helper | Use when | Main output |
|---|---|---|
| `evaluate_market_research_pack` | A market, building, property, arbitrage, co-hosting, or repositioning pack needs a pursue/watch/reject decision | `airbnb_market_research_decision` |
| `grade_public_comp` | A public comp needs A/B/C/reject grading before underwriting or sensitivity use | `comp_grade` |
| `grade_listing_maturity` | A public listing may be new, boosted, stale, mature, or only promising | `maturity_grade` |
| `evaluate_slow_season_survival` | A deal or live listing must prove weak-month survivability | `survival_decision` |
| `diagnose_listing_conversion` | Conversion weakness must be separated into visibility, click, listing-page, price, trust, photo, amenity, or segment issues | `airbnb_conversion_diagnosis` |
| `audit_photo_product_gap` | Own guest-visible content must be compared with A-comps before broad price cuts | `airbnb_photo_product_gap_audit` |
| `build_gallery_cro_execution_board` | A photo/gallery issue needs exact hero, first-five order, proof-shot queue, captions, rollback, and A/B review window | `airbnb_gallery_cro_execution_board` |
| `build_listing_content_optimization_brief` | A content-facing issue needs title, above-fold copy, gallery, captions, section copy, and test plan | `airbnb_listing_content_optimization_brief` |
| `evaluate_case_study_replay` | A rescue, makeover, or coaching pattern must become a bounded experiment with counterexamples | `airbnb_case_study_replay` |
| `audit_settings_drift` | Pricing settings, rule-sets, Smart Pricing, discounts, promotions, or restrictions may have drifted from strategy | `airbnb_settings_drift_finding` |
| `generate_calendar_actions` | Calendar/date rows need tactical price, promotion, minimum-stay, orphan-night, discount, or no-action candidates | `airbnb_calendar_action_candidate` |
| `evaluate_operations_risk` | Reviews, messages, tasks, cleaning, maintenance, or turnover load should produce risk alerts | `airbnb_operations_risk_snapshot` |
| `evaluate_channel_strategy` | Channel expansion or monthly/midterm fallback should be considered after market evidence exists | `airbnb_channel_strategy_snapshot` |
| `build_listing_opportunity_snapshot` | Own public rank, own price, A-comp price, maturity, and conversion evidence should be joined into one listing opportunity record | `airbnb_listing_opportunity_snapshot` |

If a helper returns `needs_more_data`, collect the missing source primitives
instead of filling fields optimistically. If it returns `monitor`, `watch`, or
`reject`, store that result as decision evidence; do not turn it into a host
action unless the recommended next action is evidence collection or explicit
rejection.

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
recommendations. For acquisition, expansion, arbitrage, co-hosting, market
selection, property validation, or repositioning, read
`market-research-playbook.md` before giving a pursue/watch/reject decision.
Treat every Airbnb source as a primitive that can be composed later for pricing,
operations, quality, market research, or portfolio decisions.

For generalizable mechanics, read `../../interaction-skills/data-source-exploration.md`
and `../../interaction-skills/session-continuity.md`. Airbnb files should contain
Airbnb-specific source names, fields, URLs, and examples.

For rescue, makeover, coaching, or operator-pattern work, read
`operator-insight-workflows.md` after the relevant current-state or
market-research source files. Those workflows turn recurring operator themes
into auditable photo/product gap audits and case-study replay experiments.
When those gates justify a content action, read
`content-optimization-playbook.md` to generate the actual hero, gallery, title,
caption, section-copy, and A/B-test brief.

For tasks that explicitly connect listing photos to revenue or profit, or that
ask for image-generation prompts or low-cost design changes, read
`visual-revenue-workflows.md`. It defines the repeatable image-prompt,
real-photo correlation, and interior-design opportunity workflows plus the
sidecar files that should be saved beside listing data.

## Host outcomes

| Business area | Main question |
|---|---|
| Market research and dealflow | Should I pursue, watch, or reject this market, building, property, or repositioning idea? |
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

Keep reusable browser/session mechanics in `../../interaction-skills/`:

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

Phase 3 - market and revenue optimization:

1. `airbnb_rule_set`
2. `airbnb_public_search_run`
3. `airbnb_public_search_result_snapshot`
4. `airbnb_public_comp_listing_snapshot`
5. `airbnb_public_price_availability_matrix`
6. `airbnb_market_research_run`
7. `airbnb_market_absorption_snapshot`
8. `airbnb_stay_length_gap_snapshot`
9. `airbnb_guest_capacity_curve_snapshot`
10. `airbnb_price_distribution_snapshot`
11. `airbnb_competitor_booking_velocity_proxy`
12. `airbnb_comp_thesis`
13. `airbnb_comp_thesis_evidence`
14. `airbnb_market_archetype_assessment`
15. `airbnb_channel_demand_snapshot`
16. `airbnb_midterm_viability_snapshot`
17. `airbnb_deal_underwriting_summary`
18. `airbnb_market_research_decision`
19. `airbnb_own_public_listing_audit`
20. `airbnb_own_public_review_summary`
21. `airbnb_own_public_review_snapshot`
22. `airbnb_own_public_search_appearance`
23. Price-index, booking-pace, market-research, and bookability alerts

Outcome: comp-set price intelligence, own guest-visible positioning, and
market/product-fit decisions.

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

## Common Executable Entry Points

This is a shortcut table only. `scripts/README.md` is the authoritative
executable index for script role, control-flow stage, source family,
prerequisites, outputs, refusal rules, and helper-only modules.

| Goal | Run | Notes |
|---|---|---|
| Refresh the host's live private listing inventory | `scripts/collect_listings.py` | Other private collectors read its output. Run this first. |
| Refresh calendar export / iCal daily availability snapshots | `scripts/collect_calendar_export.py` | Export-source path for booked/blocked nights; hashes event IDs and preserves last-good state on empty-feed regressions. |
| Refresh per-listing Insights for dashboards | `scripts/sync_insights_year_view.py` | Canonical Insights entry point. Wraps `collect_insights.py` with preflight, optional probe refresh, family extracts, and HTML rendering. Do not call `collect_insights.py` directly for the standard workflow. |
| Refresh authenticated host review rows | `scripts/collect_host_reviews.py` | Default scope is `ACTIVE` listings. |
| Refresh logged-out competitor comp set | `scripts/collect_competitors.py` | Refuses to run if owner cookies are present or listing inventory is partial. |
| Audit how the host's own listings appear to a guest | `scripts/collect_own_public.py` | Same logged-out guard as competitors. |
| Track long-term rental asking prices in current or watchlisted buildings | `scripts/collect_rea_building_rentals.py` | Public REA browser workflow. Searches by suburb, filters by building, revisits known URLs, and records price/lifecycle events. |
| Evaluate collected rows into decisions and actions | `scripts/decision_gates.py` | Pure helper module. Import it from reports/tests; it does not browse or collect. |
| Refresh `ChartQuery` granularity reference | `scripts/probe_chart_granularity.py` | One-off; `sync_insights_year_view.py` triggers it automatically when stale. |

Helper modules (`insights_ledger.py`, `insights_planner.py`,
`extract_route_family.py`, `listing_scope.py`, `public_scan_planner.py`,
`decision_gates.py`) are imported by collectors, reports, tests, and runners;
do not invoke them directly.

## Schema row index

Quick lookup from a table name to the file that defines its fields. Use this
when an alert, recommendation, or workflow mentions an `airbnb_*` table and you
need its schema.

Workflow docs may name output rows and describe judgement rules, but the files
below own the durable field lists. If a workflow and schema disagree, use the
schema as the row contract and treat the workflow as control-path guidance.

| Table | File |
|---|---|
| `airbnb_listing_master`, `airbnb_listing_content_audit`, `airbnb_gallery_cro_execution_board`, `airbnb_listing_content_optimization_brief`, `airbnb_calendar_snapshot`, `airbnb_reservation`, `airbnb_reservation_economics`, `airbnb_payout_tax_levy` | `schema-core.md` |
| `airbnb_pricing_settings`, `airbnb_rule_set`, `airbnb_insights_conversion`, `airbnb_insights_occupancy_rates`, `airbnb_insights_quality`, `airbnb_insights_metric_snapshot`, `airbnb_insights_chart_point`, `airbnb_conversion_diagnosis`, `airbnb_photo_product_gap_audit`, `airbnb_case_study_replay`, `airbnb_calendar_action_candidate`, `airbnb_settings_drift_finding` | `schema-performance.md` |
| `airbnb_review`, `airbnb_guest_profile_minimal`, `airbnb_message_workflow`, `airbnb_operations_task`, `airbnb_operations_risk_snapshot` | `schema-operations.md` |
| `airbnb_public_search_run`, `airbnb_public_search_result_snapshot`, `airbnb_public_comp_listing_snapshot`, `airbnb_public_price_availability_matrix`, `airbnb_public_target_competitor_snapshot`, `airbnb_own_public_listing_audit`, `airbnb_own_public_review_summary`, `airbnb_own_public_review_snapshot`, `airbnb_own_public_search_appearance`, `airbnb_listing_opportunity_snapshot` | `schema-public-market.md` |
| `airbnb_market_research_run`, `airbnb_research_mode_gate`, `airbnb_map_friction_assessment`, `airbnb_market_absorption_snapshot`, `airbnb_stay_length_gap_snapshot`, `airbnb_guest_capacity_curve_snapshot`, `airbnb_price_distribution_snapshot`, `airbnb_competitor_booking_velocity_proxy`, `airbnb_listing_maturity_filter`, `airbnb_comp_thesis`, `airbnb_comp_selection_gate`, `airbnb_comp_thesis_evidence`, `airbnb_counterexample_matrix`, `airbnb_market_archetype_assessment`, `airbnb_channel_demand_snapshot`, `airbnb_channel_strategy_snapshot`, `airbnb_midterm_viability_snapshot`, `airbnb_slow_season_survival_model`, `airbnb_deal_underwriting_summary`, `airbnb_market_research_decision` | `schema-market-research.md` |
| `airbnb_internal_cost_model`, `airbnb_reservation_actual_cost`, `airbnb_owner_contract`, `airbnb_owner_statement`, `airbnb_capex_maintenance_plan` | `schema-finance.md` |
| `airbnb_market_event`, `airbnb_holiday_calendar`, `airbnb_weather_context`, `airbnb_transport_access_signal`, `airbnb_regulatory_market_signal`, `airbnb_demand_calendar` | `schema-demand-context.md` |
| `airbnb_data_capture_run`, `airbnb_source_observation`, `airbnb_field_quality` | `data-quality.md` |
| `airbnb_recommendation`, `airbnb_action_log`, `airbnb_experiment`, `airbnb_outcome_attribution` | `decisioning.md` |
| `airbnb_alerts` | `analytics-alerts.md` (deliberate schema exception; alert rules and dashboard playbooks live with the alert row) |
| `airbnb_image_improvement_prompt`, `airbnb_visual_listing_observation`, `airbnb_visual_image_observation`, `airbnb_interior_design_opportunity`, `airbnb_portfolio_design_action` | `schema-visual-revenue.md` |
| REA rental observation/event/building-price JSONL rows | `realestate-building-rentals.md` (deliberate schema exception; source lifecycle semantics and JSONL row shapes live together) |

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
