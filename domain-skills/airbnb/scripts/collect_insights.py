"""Collect per-listing Airbnb Performance/Insights metrics.

Run from the browser-harness repo with an authenticated browser context:

    BH_NAME=airbnb-insights BH_CDP_WS=http://127.0.0.1:52862 \
      python3 run.py < domain-skills/airbnb/scripts/collect_insights.py

The collector uses Airbnb's authenticated Performance API from inside the
browser context:

- ListOfMetricsQuery: period summary metrics
- ChartQuery: chart/history points. `AIRBNB_INSIGHTS_CHART_MODE=rolling_daily`
  uses rolling 7-day windows to force DAY granularity; `single_window` asks
  Airbnb for one broad trend window and preserves Airbnb's returned granularity.

Private outputs are written under ignored domain-skills/airbnb/.private-data/.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import os
import time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

import login_session


BASE = "https://www.airbnb.com.au"
LISTINGS_PATH = Path("domain-skills/airbnb/.private-data/listing-collections")
SESSION_PATH = Path("domain-skills/airbnb/.session-store/capability")
OUTPUT_PATH = Path("domain-skills/airbnb/.private-data/insights-collections")
LEDGER_PATH = OUTPUT_PATH / ".ledger.jsonl"

OPERATION_HASHES = {
    "ListOfMetricsQuery": "d72f771d4dd59e594aeefbd90d5a5510d72c4c732f596f6d663af00bb27fac3c",
    "ChartQuery": "3e1e441e3bac1937e60c1b0409b53286e338804dd94c68575c556289a3b07580",
}

SUMMARY_PERIODS = [
    {"label": "last_7_days", "ds_start": -7, "ds_end": 0},
    {"label": "last_30_days", "ds_start": -30, "ds_end": 0},
    {"label": "last_365_days", "ds_start": -365, "ds_end": 0},
]

ROUTES = [
    {"family": "quality", "metric_type": "QUALITY", "subroute": "overall", "label": "Overall quality"},
    {"family": "quality", "metric_type": "QUALITY", "subroute": "accuracy", "label": "Accuracy"},
    {"family": "quality", "metric_type": "QUALITY", "subroute": "checkin", "label": "Check-in"},
    {"family": "quality", "metric_type": "QUALITY", "subroute": "cleanliness", "label": "Cleanliness"},
    {"family": "quality", "metric_type": "QUALITY", "subroute": "communication", "label": "Communication"},
    {"family": "quality", "metric_type": "QUALITY", "subroute": "location", "label": "Location"},
    {"family": "quality", "metric_type": "QUALITY", "subroute": "value", "label": "Value"},
    {"family": "occupancy", "metric_type": "OCCUPANCY", "subroute": "occupancy_rate", "label": "Occupancy rate"},
    {"family": "occupancy", "metric_type": "OCCUPANCY", "subroute": "cancellation_rate", "label": "Cancellation rate"},
    {"family": "occupancy", "metric_type": "OCCUPANCY", "subroute": "length_of_stay", "label": "Length of stay"},
    {"family": "occupancy", "metric_type": "OCCUPANCY", "subroute": "nightly_rate", "label": "Nightly rate"},
    {"family": "conversion", "metric_type": "CONVERSION", "subroute": "conversion_rate", "label": "Booking conversion"},
    {"family": "conversion", "metric_type": "CONVERSION", "subroute": "booking_window", "label": "Booking lead time"},
    {"family": "conversion", "metric_type": "CONVERSION", "subroute": "return_guest", "label": "Returning guests"},
    {"family": "conversion", "metric_type": "CONVERSION", "subroute": "p3_impressions", "label": "Views"},
    {"family": "conversion", "metric_type": "CONVERSION", "subroute": "wishlist", "label": "Wishlist additions"},
]


def _load_local_module(module_filename, module_name):
    path = Path("domain-skills/airbnb/scripts") / module_filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_planner = _load_local_module("insights_planner.py", "airbnb_insights_planner")
_ledger = _load_local_module("insights_ledger.py", "airbnb_insights_ledger")


def latest_live_listing_file() -> Path:
    explicit = os.environ.get("AIRBNB_LISTINGS_FILE")
    if explicit:
        return Path(explicit)
    files = sorted(LISTINGS_PATH.glob("airbnb-live-listings-*.json"))
    if not files:
        raise SystemExit(f"No live-listing collection found under {LISTINGS_PATH}")
    complete = [path for path in files if is_complete_live_listing_file(path)]
    if not complete:
        raise SystemExit(
            f"No complete live-listing collection found under {LISTINGS_PATH}; "
            "set AIRBNB_LISTINGS_FILE explicitly for a partial smoke test"
        )
    return complete[-1]


def is_complete_live_listing_file(path: Path) -> bool:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    active_status_count = int((data.get("status_counts") or {}).get("ACTIVE") or 0)
    records = data.get("records") or []
    validation = data.get("field_validation") or {}
    return (
        bool(records)
        and len(records) == int(data.get("active_count") or 0)
        and len(records) == active_status_count
        and validation.get("all_active_detail_pages_ok") is True
        and not data.get("partial_run")
    )


def wrapper_value(value):
    if not isinstance(value, dict):
        return None
    if "doubleValue" in value:
        return value.get("doubleValue")
    if "longValue" in value:
        try:
            return int(value.get("longValue"))
        except (TypeError, ValueError):
            return value.get("longValue")
    if "stringValue" in value:
        return value.get("stringValue")
    if "booleanValue" in value:
        return value.get("booleanValue")
    return None


def metric_unit(unit):
    unit = unit or {}
    return {
        "metric_name": unit.get("metricName"),
        "metric_label": unit.get("label"),
        "value": wrapper_value(unit.get("value")),
        "value_type": unit.get("valueType"),
        "value_string": unit.get("valueString"),
        "value_change": wrapper_value(unit.get("valueChange")),
        "value_change_type": unit.get("valueChangeType"),
        "value_change_string": unit.get("valueChangeString"),
        "currency": unit.get("currency"),
    }


def route_path(route, listing_id, ds_start, ds_end):
    return (
        f"{BASE}/performance/{route['family']}/{route['subroute']}/listing/{listing_id}"
        f"?ds-start={ds_start}&ds-end={ds_end}"
    )


def rolling_windows(history_days, window_days=7):
    windows = []
    start = -int(history_days)
    while start < 0:
        end = min(start + window_days, 0)
        windows.append({"label": f"daily_{start}_{end}", "ds_start": start, "ds_end": end})
        start = end
    return windows


def chart_windows_for_history(history_days):
    mode = os.environ.get("AIRBNB_INSIGHTS_CHART_MODE", "rolling_daily")
    if mode == "single_window":
        return [{"label": f"chart_{-int(history_days)}_0", "ds_start": -int(history_days), "ds_end": 0}]
    if mode != "rolling_daily":
        raise SystemExit(f"Unsupported AIRBNB_INSIGHTS_CHART_MODE={mode!r}; use rolling_daily or single_window")
    return rolling_windows(history_days)


def apply_patient_mode():
    if os.environ.get("AIRBNB_INSIGHTS_PATIENT_MODE") != "1":
        return
    os.environ.setdefault("AIRBNB_INSIGHTS_BATCH_SIZE", "2")
    os.environ.setdefault("AIRBNB_INSIGHTS_BATCH_DELAY_SEC", "5")
    os.environ.setdefault("AIRBNB_INSIGHTS_RETRY_LIMIT", "5")
    os.environ.setdefault("AIRBNB_INSIGHTS_429_BACKOFF_SEC", "300")
    os.environ.setdefault("AIRBNB_INSIGHTS_STOP_AFTER_429_BATCHES", "1")


def performance_request(operation_name, route, listing_id, ds_start, ds_end):
    client = "web-performance-dash-chart" if operation_name == "ChartQuery" else "web-performance-dash-metrics"
    variables = {
        "request": {
            "clientName": client,
            "arguments": {
                "metricType": route["metric_type"],
                "relativeDsEnd": ds_end,
                "relativeDsStart": ds_start,
                "groupBys": ["RATING_CATEGORY"],
                "groupByValues": [route["subroute"]],
                "filters": {"listingIds": [str(listing_id)]},
            },
            "useStubbedData": False,
        }
    }
    return {
        "operationName": operation_name,
        "hash": OPERATION_HASHES[operation_name],
        "variables": variables,
    }


def read_response_text(response):
    data = response.read()
    return data.decode("utf-8", errors="replace")


def fetch_performance_one(item, api_key, base_headers):
    if os.environ.get("AIRBNB_INSIGHTS_FORCE_429_SIM") == "1":
        return {**item["meta"], "ok": False, "status": 429, "error": "forced_429_simulation"}
    extensions = {"persistedQuery": {"version": 1, "sha256Hash": item["hash"]}}
    path = (
        f"/api/v3/{item['operationName']}/{item['hash']}"
        f"?operationName={item['operationName']}"
        "&locale=en-AU&currency=AUD"
        f"&variables={quote(json.dumps(item['variables'], separators=(',', ':')))}"
        f"&extensions={quote(json.dumps(extensions, separators=(',', ':')))}"
    )
    url = BASE + path
    headers = {
        **base_headers,
        "Accept": "application/json",
        "Accept-Encoding": "identity",
        "X-Airbnb-API-Key": api_key,
        "X-Airbnb-GraphQL-Platform": "web",
        "X-CSRF-Without-Token": "1",
    }
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=float(os.environ.get("AIRBNB_INSIGHTS_FETCH_TIMEOUT_SEC", "20"))) as response:
            text = read_response_text(response)
            return {**item["meta"], "ok": 200 <= response.status < 300, "status": response.status, "data": json.loads(text)}
    except HTTPError as error:
        text = read_response_text(error)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = {"text": text[:500]}
        return {**item["meta"], "ok": False, "status": error.code, "data": data}
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        return {**item["meta"], "ok": False, "status": None, "error": str(error)}


def fetch_performance_batch(requests, api_key, base_headers):
    return [fetch_performance_one(item, api_key, base_headers) for item in requests]


def result_key(meta):
    return "|".join(
        str(meta.get(key, ""))
        for key in (
            "request_kind",
            "listing_id",
            "route_family",
            "route_subroute",
            "relative_ds_start",
            "relative_ds_end",
        )
    )


def load_checkpoint(path):
    if not path.exists():
        return {}
    rows = {}
    with path.open() as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("ok"):
                rows[result_key(row)] = row
    return rows


def append_checkpoint(path, rows):
    if not rows:
        return
    with path.open("a") as handle:
        for row in rows:
            handle.write(json.dumps(row, separators=(",", ":"), ensure_ascii=False) + "\n")


def run_request_batches(label, requests, api_key, base_headers, checkpoint_path):
    checkpointed = load_checkpoint(checkpoint_path)
    requests_to_run = [
        request
        for request in requests
        if result_key(request["meta"]) not in checkpointed
    ]
    results = list(checkpointed.values())
    failures = []
    batch_size = int(os.environ.get("AIRBNB_INSIGHTS_BATCH_SIZE", "4"))
    delay = float(os.environ.get("AIRBNB_INSIGHTS_BATCH_DELAY_SEC", "1.5"))
    retry_limit = int(os.environ.get("AIRBNB_INSIGHTS_RETRY_LIMIT", "3"))
    backoff = float(os.environ.get("AIRBNB_INSIGHTS_429_BACKOFF_SEC", "90"))
    stop_after_429_batches = int(os.environ.get("AIRBNB_INSIGHTS_STOP_AFTER_429_BATCHES", "2"))
    consecutive_429_batches = 0
    if checkpointed:
        print(json.dumps({
            "phase": label,
            "checkpoint_path": str(checkpoint_path),
            "checkpointed_ok": len(checkpointed),
            "remaining": len(requests_to_run),
            "total": len(requests),
        }), flush=True)
    for index in range(0, len(requests_to_run), batch_size):
        batch = requests_to_run[index : index + batch_size]
        pending = batch
        batch_results = []
        for attempt in range(retry_limit + 1):
            if attempt:
                time.sleep(backoff if any(r.get("status") == 429 for r in batch_results) else delay * attempt)
            batch_results = fetch_performance_batch(pending, api_key, base_headers)
            retryable = [
                req
                for req, result in zip(pending, batch_results)
                if result.get("status") == 429 or result.get("error")
            ]
            if not retryable:
                break
            pending = retryable
        results.extend(batch_results)
        append_checkpoint(checkpoint_path, [result for result in batch_results if result.get("ok")])
        failures.extend([result for result in batch_results if not result.get("ok")])
        if batch_results and all(result.get("status") == 429 for result in batch_results):
            consecutive_429_batches += 1
        else:
            consecutive_429_batches = 0
        print(json.dumps({
            "phase": label,
            "progress": len(checkpointed) + min(index + len(batch), len(requests_to_run)),
            "total": len(requests),
            "failures": len(failures),
            "consecutive_429_batches": consecutive_429_batches,
        }), flush=True)
        if consecutive_429_batches >= stop_after_429_batches:
            remaining = requests_to_run[index + len(batch) :]
            for item in remaining:
                failures.append({
                    **item["meta"],
                    "ok": False,
                    "status": 429,
                    "error": "stopped_after_sustained_rate_limit",
                })
            break
        if delay:
            time.sleep(delay)
    return results, failures


def components(result):
    data = result.get("data") or {}
    if not isinstance(data, dict):
        return []
    data = data.get("data") or {}
    if not isinstance(data, dict):
        return []
    porygon = data.get("porygon") or {}
    if not isinstance(porygon, dict):
        return []
    perf = porygon.get("getPerformanceComponents") or {}
    if not isinstance(perf, dict):
        return []
    rows = perf.get("components") or []
    return rows if isinstance(rows, list) else []


def parse_summary(result):
    rows = []
    for component in components(result):
        if component.get("componentName") != "LIST_OF_METRICS_SECTION":
            continue
        for metric in component.get("metrics") or []:
            rows.append(metric_unit(metric))
    return rows


def parse_chart(result):
    rows = []
    chart_sections = [
        component
        for component in components(result)
        if component.get("componentName") == "PIVOT_CHART_SECTION"
    ]
    for section in chart_sections:
        primary = metric_unit(section.get("primaryMetric"))
        secondary = [metric_unit(metric) for metric in section.get("secondaryMetrics") or []]
        for series_index, chart in enumerate(section.get("metricLineCharts") or []):
            for point in chart.get("dataPoints") or []:
                rows.append({
                    "section_title": section.get("title"),
                    "series_index": series_index,
                    "series_label": chart.get("label"),
                    "series_granularity": chart.get("granularity"),
                    "is_comparison_series": series_index > 0,
                    "ds": point.get("ds"),
                    "label": point.get("label"),
                    "value": wrapper_value(point.get("value")),
                    "value_type": point.get("valueType"),
                    "value_string": point.get("valueString"),
                    "primary_metric_name": primary.get("metric_name"),
                    "primary_metric_label": primary.get("metric_label"),
                    "primary_value": primary.get("value"),
                    "primary_value_string": primary.get("value_string"),
                    "secondary_metrics": secondary,
                    "description": section.get("description"),
                })
    return rows


def build_requests_from_plan(plan_items, listings_by_id, routes_by_subroute, operation_name):
    requests = []
    for item in plan_items:
        listing_id = str(item["listing_id"])
        route = routes_by_subroute[item["route_subroute"]]
        req = performance_request(
            operation_name,
            route,
            listing_id,
            int(item["relative_ds_start"]),
            int(item["relative_ds_end"]),
        )
        label = item.get("period_label")
        if not label:
            mode = item.get("chart_mode")
            label = f"{mode}_{item['relative_ds_start']}_{item['relative_ds_end']}"
        req["meta"] = {
            "request_kind": item.get("request_kind") or ("daily_chart" if operation_name == "ChartQuery" else "summary"),
            "listing_id": listing_id,
            "listing_name": (listings_by_id.get(listing_id) or {}).get("listing_name"),
            "route_family": route["family"],
            "route_subroute": route["subroute"],
            "route_label": route["label"],
            "period_label": label,
            "relative_ds_start": int(item["relative_ds_start"]),
            "relative_ds_end": int(item["relative_ds_end"]),
            "chart_mode": item.get("chart_mode"),
            "source_url": route_path(route, listing_id, int(item["relative_ds_start"]), int(item["relative_ds_end"])),
        }
        requests.append(req)
    return requests


def write_csv(path, rows):
    if not rows:
        return
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    apply_patient_mode()
    observed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    run_id = os.environ.get("AIRBNB_INSIGHTS_RUN_ID") or "airbnb-insights-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    listing_file = latest_live_listing_file()
    listing_run = json.loads(listing_file.read_text())
    listings = listing_run.get("records") or []
    if os.environ.get("AIRBNB_INSIGHTS_LIMIT_LISTINGS"):
        listings = listings[: int(os.environ["AIRBNB_INSIGHTS_LIMIT_LISTINGS"])]
    routes = ROUTES[: int(os.environ.get("AIRBNB_INSIGHTS_LIMIT_ROUTES", len(ROUTES)))]
    summary_periods = SUMMARY_PERIODS[: int(os.environ.get("AIRBNB_INSIGHTS_LIMIT_PERIODS", len(SUMMARY_PERIODS)))]
    history_days = int(os.environ.get("AIRBNB_INSIGHTS_HISTORY_DAYS", "365"))

    OUTPUT_PATH.mkdir(parents=True, exist_ok=True)
    SESSION_PATH.mkdir(parents=True, exist_ok=True)

    api_key = os.environ.get("AIRBNB_API_KEY")
    auth_context = "skip_bootstrap"
    if os.environ.get("AIRBNB_INSIGHTS_SKIP_BOOTSTRAP") != "1":
        # Ensure same-origin API key/bootstrap is present before API-only collection.
        first_listing_id = str(listings[0]["listing_id"])
        goto_url(route_path(routes[0], first_listing_id, -1, 0))
        wait_for_load()
        wait(2)
        api_key = api_key or js("JSON.parse(document.querySelector('#data-initializer-bootstrap')?.textContent || '{}')['layout-init']?.api_config?.key")
        if not api_key:
            raise SystemExit("Could not read Airbnb API key from page bootstrap")
        base_headers = login_session.browser_session_headers(
            cdp,
            BASE + "/api/v3/",
            cookie_urls=[BASE + "/"],
        )
        auth_context = "live_browser_session_bootstrap"
    else:
        if not api_key:
            api_key = "forced-bootstrap-skip"
        base_headers = {}

    listings_by_id = {str(listing["listing_id"]): listing for listing in listings}
    routes_by_subroute = {route["subroute"]: route for route in routes}
    today = date.fromisoformat(observed_at[:10])
    ledger_index = _ledger.read_ledger_index(LEDGER_PATH)
    planner_output = _planner.plan_requests(
        listings=listings,
        routes=routes,
        today=today,
        ledger_index=ledger_index,
        summary_periods=summary_periods,
        daily_horizon_days=int(os.environ.get("AIRBNB_INSIGHTS_DAILY_HORIZON_DAYS", "90")),
        older_horizon_days=int(os.environ.get("AIRBNB_INSIGHTS_OLDER_HORIZON_DAYS", "275")),
        weekly_window_days=int(os.environ.get("AIRBNB_INSIGHTS_WEEKLY_WINDOW_DAYS", "28")),
    )
    summary_requests = build_requests_from_plan(
        planner_output.summary_requests,
        listings_by_id=listings_by_id,
        routes_by_subroute=routes_by_subroute,
        operation_name="ListOfMetricsQuery",
    )
    chart_requests = build_requests_from_plan(
        planner_output.chart_requests,
        listings_by_id=listings_by_id,
        routes_by_subroute=routes_by_subroute,
        operation_name="ChartQuery",
    )

    summary_raw_path = OUTPUT_PATH / f"{run_id}-summary-raw.jsonl"
    chart_raw_path = OUTPUT_PATH / f"{run_id}-daily-chart-raw.jsonl"
    summary_results, summary_failures = run_request_batches(
        "summary",
        summary_requests,
        api_key,
        base_headers,
        summary_raw_path,
    )
    chart_results, chart_failures = run_request_batches(
        "daily_chart",
        chart_requests,
        api_key,
        base_headers,
        chart_raw_path,
    )
    failures = [*summary_failures, *chart_failures]

    summary_rows = []
    for result in summary_results:
        if not result.get("ok"):
            continue
        parsed = parse_summary(result)
        if not parsed:
            failures.append({**result, "ok": False, "error": "no_summary_metrics"})
        for row in parsed:
            summary_rows.append({**{k: v for k, v in result.items() if k not in {"data"}}, **row})

    daily_rows = []
    for result in chart_results:
        if not result.get("ok"):
            continue
        parsed = parse_chart(result)
        if not parsed:
            failures.append({**result, "ok": False, "error": "no_chart_points"})
        for row in parsed:
            daily_rows.append({**{k: v for k, v in result.items() if k not in {"data"}}, **row})

    # De-duplicate overlapping 7-day chart windows while preserving comparison
    # series separately.
    seen = set()
    deduped_daily_rows = []
    for row in daily_rows:
        key = (
            row.get("listing_id"),
            row.get("route_family"),
            row.get("route_subroute"),
            row.get("series_index"),
            row.get("ds"),
            row.get("primary_metric_name"),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped_daily_rows.append(row)
    daily_rows = deduped_daily_rows
    ledger_rows = [
        {
            "listing_id": row.get("listing_id"),
            "route_family": row.get("route_family"),
            "route_subroute": row.get("route_subroute"),
            "series_index": row.get("series_index"),
            "ds": row.get("ds"),
            "primary_metric_name": row.get("primary_metric_name"),
            "value": row.get("value"),
            "value_string": row.get("value_string"),
            "value_type": row.get("value_type"),
            "series_granularity": row.get("series_granularity"),
            "observed_at": observed_at,
            "run_id": run_id,
            "source_url": row.get("source_url"),
        }
        for row in daily_rows
        if row.get("ds")
    ]
    _ledger.append_ledger_rows(LEDGER_PATH, ledger_rows)

    output = {
        "run_id": run_id,
        "observed_at": observed_at,
        "auth_context": auth_context,
        "source": {
            "listing_scope": str(listing_file),
            "summary_api": "ListOfMetricsQuery",
            "daily_chart_api": "ChartQuery",
            "transport": "Python HTTP replay with browser-session cookies and Airbnb bootstrap API key",
            "operation_hashes": OPERATION_HASHES,
            "granularity_strategy": "tiered planner: rolling_daily for recent window + single_window chunks for older window; preserve returned series_granularity",
            "chart_mode": "tiered_gap_sync",
            "checkpoint_strategy": "successful raw API responses are appended to JSONL after each batch and skipped on rerun when AIRBNB_INSIGHTS_RUN_ID is reused",
            "ledger_path": str(LEDGER_PATH),
        },
        "listing_count": len(listings),
        "route_count": len(routes),
        "summary_periods": summary_periods,
        "history_days": history_days,
        "chart_mode": "tiered_gap_sync",
        "chart_window_count": len(chart_requests),
        "summary_request_count": len(summary_requests),
        "chart_request_count": len(chart_requests),
        "summary_rows_count": len(summary_rows),
        "chart_rows_count": len(daily_rows),
        "daily_rows_count": len(daily_rows),
        "failures_count": len(failures),
        "summary_raw_path": str(summary_raw_path),
        "chart_raw_path": str(chart_raw_path),
        "summary_rows": summary_rows,
        "daily_rows": daily_rows,
        "failures": failures[:100],
    }

    json_path = OUTPUT_PATH / f"{run_id}.json"
    summary_csv_path = OUTPUT_PATH / f"{run_id}-summary-rows.csv"
    daily_csv_path = OUTPUT_PATH / f"{run_id}-daily-rows.csv"
    receipt_path = SESSION_PATH / f"{run_id}-receipt.json"
    json_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    write_csv(summary_csv_path, summary_rows)
    write_csv(daily_csv_path, daily_rows)

    expected_summary = len(listings) * len(routes) * len(summary_periods)
    expected_charts = len(chart_requests)
    receipt = {
        "run_id": run_id,
        "observed_at": observed_at,
        "listing_count": len(listings),
        "route_count": len(routes),
        "summary_period_count": len(summary_periods),
        "history_days": history_days,
        "chart_mode": "tiered_gap_sync",
        "chart_window_count": len(chart_requests),
        "summary_request_count": len(summary_requests),
        "chart_request_count": len(chart_requests),
        "expected_summary_requests": expected_summary,
        "expected_chart_requests": expected_charts,
        "summary_rows_count": len(summary_rows),
        "chart_rows_count": len(daily_rows),
        "daily_rows_count": len(daily_rows),
        "failures_count": len(failures),
        "all_api_requests_ok": not [f for f in failures if f.get("status") != 200],
        "all_parsers_found_rows": len(failures) == 0,
        "summary_raw_path": str(summary_raw_path),
        "chart_raw_path": str(chart_raw_path),
        "json_path": str(json_path),
        "summary_csv_path": str(summary_csv_path),
        "chart_csv_path": str(daily_csv_path),
        "daily_csv_path": str(daily_csv_path),
        "failure_sample": [
            {
                "listing_id": f.get("listing_id"),
                "route_subroute": f.get("route_subroute"),
                "period_label": f.get("period_label"),
                "status": f.get("status"),
                "error": f.get("error"),
            }
            for f in failures[:10]
        ],
    }
    receipt_path.write_text(json.dumps(receipt, indent=2))
    print(json.dumps(receipt, indent=2), flush=True)


main()
