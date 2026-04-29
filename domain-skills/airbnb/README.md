# Airbnb.com.au Host Intelligence Skill

Start with `overview.md`. It is the intent router for the Airbnb skill: user
intent, desired outcome, control-flow stage, evidence/source guardrails,
executable lookup, schema index, and source anchors.

Use this directory when the user is an Airbnb host or co-host and wants to
improve pricing, calendar control, conversion, operations, listing quality,
market selection, comp positioning, portfolio reporting, or Australian
compliance awareness from Airbnb.com.au data.

## Intent-First Fast Path

| If the user intent is | Start here | Outcome |
|---|---|---|
| "What should I run?" | `scripts/README.md`, then the governing workflow named there | Runnable entry point or helper-only refusal |
| Current market, competitor, or own-listing state | `overview.md` intent router, then `workflows-current-state.md` | Source plan or current-state report |
| Pricing, rules, Smart Pricing, calendar action, or orphan nights | `analytics-alerts.md`, `decisioning.md`, then `host-sources.md` only for source details | Settings drift finding, calendar action, or recommendation |
| Conversion diagnosis, click appeal, listing-page conversion, or price friction | `overview.md`, then `analytics-alerts.md` and `public-market.md` | Conversion diagnosis and next decision helper |
| Photo, gallery, title, caption, or listing content optimization | `operator-insight-workflows.md`, then `content-optimization-playbook.md` | Photo/product audit, gallery board, or content brief |
| Image-improvement prompts, photo/profit correlation, or low-cost design opportunities | `visual-revenue-workflows.md` | Visual sidecar rows, prompt rows, or design opportunity rows |
| Acquisition, arbitrage, property validation, market selection, or channel strategy | `market-research-playbook.md` | Pursue/watch/reject or channel strategy decision |
| REA long-term rent monitoring for buildings or suburbs | `realestate-building-rentals.md` | REA observations, events, and rent snapshots |
| Operations, reviews, guest issues, messages, cleaning, maintenance, or tasks | `analytics-alerts.md`, `schema-operations.md`, then `host-sources.md` | Operations risk snapshot or recommendation |
| Data freshness, redaction, provenance, quarantine, or output contracts | `data-quality.md`, then `scripts/README.md` | Validation check, redaction scan, or source-quality row |
| Schema/table fields for an `airbnb_*` record | Schema row index in `overview.md` | Authoritative row contract |

## Cold Reader Map

If you are reading this folder cold, use this order:

1. `overview.md` - choose the user intent, desired outcome, control-flow stage,
   evidence/source guardrails, script/helper, and schema/output row.
2. One workflow file - read only the file that matches the task:
   `workflows-current-state.md`, `host-sources.md`, `public-market.md`,
   `market-research-playbook.md`, `operator-insight-workflows.md`,
   `content-optimization-playbook.md`, `realestate-building-rentals.md`, or
   `visual-revenue-workflows.md`.
3. `scripts/README.md` - open this only when something must be run or a helper
   contract must be checked.
4. Schema or decision docs - open these only after the workflow names the output row:
   `schema-*.md`, `data-quality.md`, or `decisioning.md`.

Do not start in collector code unless the script index or a failing test points
you there. The markdown files define source rules, refusal guards, output
contracts, and acceptance criteria.

## Where Things Live

| Need | Location |
|---|---|
| Main router and schema lookup | `overview.md` |
| Executable script lookup | `scripts/README.md` |
| Public Airbnb comps and own guest-visible audits | `public-market.md` |
| Private host inventory, Insights, reviews, exports, and session rules | `host-sources.md`, `session-continuity.md` |
| Realestate.com.au building rental monitor | `realestate-building-rentals.md`, `scripts/collect_rea_building_rentals.py` |
| Rental arbitrage, market selection, underwriting, channel strategy | `market-research-playbook.md`, `schema-market-research.md`, `schema-finance.md` |
| Photo prompt, visual-profit calibration, and design opportunity workflows | `visual-revenue-workflows.md`, `schema-visual-revenue.md` |
| Gallery/title/copy execution briefs after a content decision | `content-optimization-playbook.md` |
| Recommendation, action, experiment, rollback, and outcome tracking | `decisioning.md` |
| Provenance, freshness, redaction, quarantine, and output contracts | `data-quality.md`, `scripts/run_integrity.py`, `schemas/*.json` |
| Runnable vs helper-only script classification | `scripts/README.md` |
| Durable `airbnb_*` row fields | Schema row index in `overview.md`, then the named schema file |
| Reusable parser/decision fixtures | `fixtures/` |

Private run data is under ignored `domain-skills/airbnb/.private-data/`.
Shareable generated workbooks and reports usually go under `outputs/{run_id}/`.
Committed docs should describe shapes and workflows, not private addresses,
cookies, raw guest details, or portfolio-specific secrets.

The root markdown files are intentionally flat and organized logically by
`overview.md`. Treat physical moves as a broad path migration: update every
cross-reference, script constant, package-data expectation, and test path in the
same change.

When reviewing or searching the reusable skill surface, exclude private run
stores unless the task explicitly asks for local evidence records:

```bash
rg "pattern" domain-skills/airbnb \
  --glob '!domain-skills/airbnb/.private-data/**' \
  --glob '!domain-skills/airbnb/.session-store/**' \
  --glob '!outputs/**'

find domain-skills/airbnb \
  -path '*/.private-data' -prune -o \
  -path '*/.session-store' -prune -o \
  -path '*/outputs' -prune -o \
  -type f -print
```

## Default Flow

1. Identify the host decision.
2. Read the matching row in `overview.md` under **Intent Router**, then use
   **Expanded Routing Matrix** only if the task spans multiple artifacts.
3. Collect the smallest source primitives needed for the decision.
4. Evaluate collected rows with `scripts/decision_gates.py` when a decision is
   needed.
5. Store source observations in the relevant schema family.
6. Turn accepted recommendations into `decisioning.md` action, experiment, and
   outcome records.

## Source State Defaults

- Public market, public comps, own public rank, and guest-visible listing pages
  are logged-out observations by default.
- Host calendar, pricing settings, Insights, reviews, messages, tasks, exports,
  and listing editor fields are logged-in observations only when needed.
- Public Airbnb comp searches default to `Entire home` unless the task
  explicitly studies private-room or shared-room competition.
- Do not mix logged-out market observations and logged-in personalized
  observations in the same comp set.

## Implementation Pointers

- Browser-backed collectors live in `scripts/` and are run through
  `browser-harness`, not as plain standalone Python files.
- Pure decision helpers live in `scripts/decision_gates.py`; they do not browse,
  mutate Airbnb, or read private artifacts.
- Photo/product normalization lives in `scripts/photo_product_evidence.py`.
- Public scan planning and default comp filters live in
  `scripts/public_scan_planner.py`.
- Data quality, freshness, confidence, receipts, and redaction rules live in
  `data-quality.md`.
