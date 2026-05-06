# Airbnb Insights to Data Display E2E Plan

## Goal

Verify an end-to-end chain for authenticated Airbnb host Insights data:

1. Source truth from logged-in Airbnb Insights surfaces and authenticated API
2. Collector output from `domain-skills/airbnb/scripts/collect_insights.py`
3. Display payload and rendered output from `data_display.render_dataset(...)`

The test passes only when key metrics and chart points are preserved across
source -> collected artifacts -> rendered display without loss or fabrication.

## Scope

- Listing scope: 1 active listing (bounded smoke)
- Metric routes: conversion, occupancy, quality
- Summary windows: last 7 days, last 30 days
- Chart windows:
  - rolling daily mode (forces `DAY` granularity)
  - single window mode (preserves Airbnb returned granularity)

## Preconditions

- Airbnb host session is logged in and available in browser harness context.
- Complete listing inventory exists in:
  - `domain-skills/airbnb/.private-data/listing-collections/airbnb-live-listings-*.json`
- Private output paths are writable:
  - `domain-skills/airbnb/.private-data/insights-collections/`
  - `domain-skills/airbnb/.session-store/capability/`

## Execution Steps

### Phase A - Source Truth Capture

For each test route and period:

- Open authenticated route:
  - `https://www.airbnb.com.au/performance/<family>/<subroute>/listing/<listing_id>?ds-start=-7&ds-end=0`
- Capture:
  - Screenshot
  - Visible metric label/value from DOM
  - Matching API response payload for `ListOfMetricsQuery`/`ChartQuery`
- Build manifest keyed by:
  - `listing_id`, `route_subroute`, `period_label`, `relative_ds_start`, `relative_ds_end`

### Phase B - Collector Run

Run:

- `collect_insights.py` in `rolling_daily` mode
- `collect_insights.py` in `single_window` mode

Use bounded environment overrides:

- `AIRBNB_INSIGHTS_LIMIT_LISTINGS=1`
- `AIRBNB_INSIGHTS_LIMIT_ROUTES=3`
- `AIRBNB_INSIGHTS_LIMIT_PERIODS=2`
- `AIRBNB_INSIGHTS_HISTORY_DAYS=14`

Validate:

- JSON artifact exists
- Receipt exists and indicates expected request/row counts
- Summary and daily rows match source-truth manifest keys and values

### Phase C - Data Display Render Fidelity

Render collector outputs with `data_display.render_dataset(...)`:

- Summary rows input for table/KPI/bar validation
- Daily rows input for line-series validation

Validate from embedded payload:

- Expected top-level payload keys are present
- Row keys and values match collector output
- Field-type inference is sensible (`numeric`, `categorical`, `url`, etc.)
- Aggregates reflect input row counts and chart axes

### Phase D - Visual Smoke

Open produced HTML report(s) and verify:

- KPI count is correct
- Table row counts/search filter behavior are correct
- Line view renders series and dates expected from daily rows

## Artifacts and Receipts

Primary outputs:

- Insights JSON/CSV under:
  - `domain-skills/airbnb/.private-data/insights-collections/`
- Capability receipts under:
  - `domain-skills/airbnb/.session-store/capability/`
- Rendered HTML outputs co-located with rendered source files

Optional E2E evidence folder:

- `domain-skills/airbnb/.private-data/.e2e/`
  - source manifests
  - screenshots
  - parity-check receipts

## Acceptance Criteria

- Authenticated source values match collector rows for tested keys.
- Collector rows match rendered payload rows for tested keys.
- No unexplained missing rows and no synthetic extra rows.
- Run receipt includes:
  - run id
  - listing/route/period scope
  - request counts
  - row counts
  - mismatch count (must be zero)

## Canonical implementation command

Use the year-view runner for the standard workflow:

- `python3 domain-skills/airbnb/scripts/sync_insights_year_view.py`

This command performs preflight, optional granularity probe refresh, incremental
collector sync with ledger-backed gap planning, per-family extraction
(`conversion`, `occupancy`, `quality`), `data_display` rendering, optional
browser-open verification, and capability receipt writeout.

## Sentinel-driven convergence

Airbnb's chart data is sparse — many (listing, route) pairs have only ~69 of 365
days populated historically. Without sentinels, every run re-requests the same
gaps even though Airbnb returns empty for them. The attempt-sentinel mechanism
records these "asked-and-got-nothing" windows so the planner skips them on
subsequent runs.

After the first full sync that introduces sentinels, a second pass will show a
large drop in `chart_request_count` in the receipt (expected ~80 % reduction for
the older tier). The `sentinel_rows_count` field in the run receipt shows how many
sentinel rows were emitted. Sentinel expiry ensures daily-tier gaps are re-tried
weekly in case Airbnb back-fills data.
