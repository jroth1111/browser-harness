"""Collect per-listing Airbnb Performance/Insights metrics.

Role: collector (private). Prefer the runner `sync_insights_year_view.py` for
the standard year-view workflow — it adds preflight cookie checks, optional
granularity probe, family extracts, and HTML rendering. Use this script
directly only for ad-hoc/bounded captures.

Reads:
    - Latest complete `airbnb-live-listings-*.json` under
      `.private-data/listing-collections/` (override with
      `AIRBNB_LISTINGS_FILE`).
    - Cross-run ledger at `.private-data/insights-collections/.ledger.jsonl`
      (override with `AIRBNB_INSIGHTS_LEDGER_PATH`). Sentinel rows mark windows
      Airbnb has confirmed empty so they are not re-requested.
    - Authenticated `/api/v3/ListOfMetricsQuery/<hash>` and
      `/api/v3/ChartQuery/<hash>` from inside the browser context.

Produces:
    - `domain-skills/airbnb/.private-data/insights-collections/<run_id>.json`
      (summary + daily rows + sentinels).
    - Ledger appends in the same directory.
    - `domain-skills/airbnb/.session-store/capability/<run_id>-receipt.json`.

Requires (env, optional unless noted):
    - `AIRBNB_INSIGHTS_RUN_ID`, `AIRBNB_INSIGHTS_PATIENT_MODE`,
      `AIRBNB_INSIGHTS_LIMIT_LISTINGS`, `AIRBNB_INSIGHTS_LIMIT_ROUTES`,
      `AIRBNB_INSIGHTS_LIMIT_PERIODS`, `AIRBNB_INSIGHTS_HISTORY_DAYS`,
      `AIRBNB_INSIGHTS_CHART_MODE` — see host-sources.md.
    - `AIRBNB_LISTINGS_FILE` — point at an alternative listing artifact (smoke
      runs only; production scope is the newest complete inventory).

Refuses to run if:
    - No complete `airbnb-live-listings-*.json` artifact exists and
      `AIRBNB_LISTINGS_FILE` is not set.
    - Authenticated Airbnb host cookies are missing from the browser context.

The tiered planner uses rolling 7-day windows for recent daily primitives and
larger single-window chunks for older history while preserving Airbnb's
returned granularity (`DAY`/`WEEK`/`MONTH`).

Run from the browser-harness repo with an authenticated browser context:

    BH_NAME=airbnb-insights BH_CDP_WS=http://127.0.0.1:52862 \
      python3 run.py < domain-skills/airbnb/scripts/collect_insights.py

Private outputs are written under ignored domain-skills/airbnb/.private-data/.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

import login_session


BASE = "https://www.airbnb.com.au"
LISTINGS_PATH = Path("domain-skills/airbnb/.private-data/listing-collections")
SESSION_PATH = Path("domain-skills/airbnb/.session-store/capability")
OUTPUT_PATH = Path("domain-skills/airbnb/.private-data/insights-collections")
# AIRBNB_INSIGHTS_LEDGER_PATH lets isolated/test runs target a sandbox ledger
# rather than the production one.
LEDGER_PATH = Path(os.environ.get("AIRBNB_INSIGHTS_LEDGER_PATH", str(OUTPUT_PATH / ".ledger.jsonl")))

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
_listing_scope = _load_local_module("listing_scope.py", "airbnb_listing_scope")
_operation_hashes = _load_local_module("operation_hashes.py", "airbnb_operation_hashes")
_integrity = _load_local_module("run_integrity.py", "airbnb_run_integrity")
_surfaces = _load_local_module("surface_capabilities.py", "airbnb_surface_capabilities")

CAPABILITY_REGISTRY_PATH = SESSION_PATH / "capability-registry.json"


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


def validate_collection_scope(listings, routes):
    if not listings:
        raise SystemExit("No listings in scope for Airbnb Insights collection")
    if not routes:
        raise SystemExit("No routes in scope for Airbnb Insights collection")


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


def resolve_horizons(env=os.environ):
    """Resolve tiered planner horizons with AIRBNB_INSIGHTS_HISTORY_DAYS as a legacy total."""
    total_history_days = int(env.get("AIRBNB_INSIGHTS_HISTORY_DAYS", "365"))
    daily_horizon_days = int(env.get("AIRBNB_INSIGHTS_DAILY_HORIZON_DAYS", str(min(90, total_history_days))))
    older_horizon_days = int(
        env.get("AIRBNB_INSIGHTS_OLDER_HORIZON_DAYS", str(max(0, total_history_days - daily_horizon_days)))
    )
    weekly_window_days = int(env.get("AIRBNB_INSIGHTS_WEEKLY_WINDOW_DAYS", "56"))
    if daily_horizon_days < 0 or older_horizon_days < 0 or weekly_window_days < 2:
        raise SystemExit(
            "Airbnb Insights horizons must be non-negative and weekly window days must be at least 2"
        )
    return {
        "history_days": daily_horizon_days + older_horizon_days,
        "daily_horizon_days": daily_horizon_days,
        "older_horizon_days": older_horizon_days,
        "weekly_window_days": weekly_window_days,
        "legacy_history_days": total_history_days,
    }


def apply_patient_mode():
    if os.environ.get("AIRBNB_INSIGHTS_PATIENT_MODE") != "1":
        return
    os.environ.setdefault("AIRBNB_INSIGHTS_BATCH_SIZE", "2")
    os.environ.setdefault("AIRBNB_INSIGHTS_BATCH_DELAY_SEC", "5")
    os.environ.setdefault("AIRBNB_INSIGHTS_RETRY_LIMIT", "5")
    os.environ.setdefault("AIRBNB_INSIGHTS_429_BACKOFF_SEC", "300")
    os.environ.setdefault("AIRBNB_INSIGHTS_STOP_AFTER_429_BATCHES", "1")


def fetch_text(url, headers=None, timeout=20.0):
    request = Request(url, headers=headers or {})
    with urlopen(request, timeout=timeout) as response:
        return read_response_text(response)


def discover_operation_hashes_from_page(base_headers):
    context = js(
        """(() => ({
            html: document.documentElement.outerHTML,
            scripts: Array.from(document.scripts).map(script => script.src).filter(Boolean),
            resources: performance.getEntriesByType('resource').map(entry => entry.name)
        }))()"""
    ) or {}
    seed_texts = [context.get("html") or ""]
    seed_urls = []
    for value in [*(context.get("scripts") or []), *(context.get("resources") or [])]:
        if isinstance(value, str) and "/airbnb/static/packages/web/" in value and value.endswith(".js"):
            seed_urls.append(value)
    seen = set()
    seed_urls = [url for url in seed_urls if not (url in seen or seen.add(url))]
    headers = {
        **(base_headers or {}),
        "Accept": "application/javascript,text/javascript,*/*",
        "Accept-Encoding": "identity",
    }

    def fetcher(url):
        return fetch_text(
            url,
            headers=headers,
            timeout=float(os.environ.get("AIRBNB_INSIGHTS_HASH_FETCH_TIMEOUT_SEC", "20")),
        )

    return _operation_hashes.discover_operation_hashes(
        fetcher,
        operation_names=tuple(OPERATION_HASHES),
        seed_texts=seed_texts,
        seed_urls=seed_urls,
        max_fetches=int(os.environ.get("AIRBNB_INSIGHTS_HASH_DISCOVERY_MAX_FETCHES", "80")),
    )


def performance_request(operation_name, route, listing_id, ds_start, ds_end, operation_hashes=None):
    operation_hashes = operation_hashes or OPERATION_HASHES
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
        "hash": operation_hashes[operation_name],
        "variables": variables,
    }


def read_response_text(response):
    data = response.read()
    return data.decode("utf-8", errors="replace")


def graphql_error_summary(payload):
    if not isinstance(payload, dict):
        return None
    errors = payload.get("errors")
    if not errors:
        return None
    first = errors[0] if isinstance(errors, list) and errors else errors
    if not isinstance(first, dict):
        return str(first)[:500]
    message = first.get("message") or "GraphQL error"
    extensions = first.get("extensions") or {}
    error_class = extensions.get("errorClass") or extensions.get("errorType") or extensions.get("code")
    if error_class:
        return f"{message} ({error_class})"[:500]
    return str(message)[:500]


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
            payload = json.loads(text)
            error = graphql_error_summary(payload)
            result = {
                **item["meta"],
                "ok": 200 <= response.status < 300 and error is None,
                "status": response.status,
                "data": payload,
            }
            if error is not None:
                result["error"] = error
            return result
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
        successful_results = []
        final_failures = []
        for attempt in range(retry_limit + 1):
            if attempt:
                time.sleep(backoff if any(r.get("status") == 429 for r in batch_results) else delay * attempt)
            batch_results = fetch_performance_batch(pending, api_key, base_headers)
            retryable = []
            for req, result in zip(pending, batch_results):
                if result.get("ok"):
                    successful_results.append(result)
                elif result.get("status") == 429 or result.get("error"):
                    retryable.append((req, result))
                else:
                    final_failures.append(result)
            if not retryable:
                break
            if attempt >= retry_limit:
                final_failures.extend(result for _, result in retryable)
                break
            pending = [req for req, _ in retryable]
        batch_results = [*successful_results, *final_failures]
        results.extend(batch_results)
        append_checkpoint(checkpoint_path, successful_results)
        failures.extend(final_failures)
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


def has_graphql_errors(result):
    data = result.get("data")
    return isinstance(data, dict) and bool(data.get("errors"))


def is_confirmed_empty_chart(result):
    """True only for a recognized chart payload with explicit empty series."""
    if has_graphql_errors(result):
        return False
    chart_sections = [
        component
        for component in components(result)
        if component.get("componentName") == "PIVOT_CHART_SECTION"
    ]
    if not chart_sections:
        return False
    for section in chart_sections:
        if "metricLineCharts" not in section:
            return False
        charts = section.get("metricLineCharts")
        if not isinstance(charts, list):
            return False
        for chart in charts:
            points = chart.get("dataPoints")
            if not isinstance(points, list):
                return False
            if points:
                return False
    return True


def build_requests_from_plan(plan_items, listings_by_id, routes_by_subroute, operation_name, operation_hashes=None):
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
            operation_hashes=operation_hashes,
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
    all_listings = listing_run.get("records") or []
    if not all_listings:
        raise SystemExit(f"Listing source file {listing_file} has zero records — refusing to run.")
    source_status_counts = listing_run.get("status_counts") or _listing_scope.status_counts(all_listings)
    total_active_listings = int(source_status_counts.get("ACTIVE") or 0)
    listings, listing_scope = _listing_scope.select_listings(
        all_listings,
        os.environ.get("AIRBNB_INSIGHTS_LISTING_SCOPE"),
    )
    total_scope_listings = len(listings)
    if not listings:
        raise SystemExit(
            f"Listing source file {listing_file} produced zero listings for scope {listing_scope['label']}"
        )
    listing_limit = os.environ.get("AIRBNB_INSIGHTS_LIMIT_LISTINGS")
    if listing_limit:
        listings = listings[: int(listing_limit)]
        print(json.dumps({
            "warning": "listing_scope_limited",
            "limit": int(listing_limit),
            "total_scope_listings": total_scope_listings,
            "scoped_listing_count": len(listings),
        }), flush=True)
    listing_ids_in_scope = [str(l["listing_id"]) for l in listings]
    routes = ROUTES[: int(os.environ.get("AIRBNB_INSIGHTS_LIMIT_ROUTES", len(ROUTES)))]
    summary_periods = SUMMARY_PERIODS[: int(os.environ.get("AIRBNB_INSIGHTS_LIMIT_PERIODS", len(SUMMARY_PERIODS)))]
    validate_collection_scope(listings, routes)
    horizons = resolve_horizons()

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
    registry_hashes, registry_sources = _operation_hashes.operation_hashes_from_registry(
        _surfaces.load_capability_registry(CAPABILITY_REGISTRY_PATH),
        tuple(OPERATION_HASHES),
        surface_id="host_reviews",
    )
    discovery = {"hashes": {}, "sources": {}, "visited_count": 0, "remaining_queue_count": 0}
    if os.environ.get("AIRBNB_INSIGHTS_SKIP_BOOTSTRAP") != "1" and os.environ.get("AIRBNB_INSIGHTS_DISABLE_HASH_DISCOVERY") != "1":
        try:
            discovery = discover_operation_hashes_from_page(base_headers)
        except Exception as error:
            discovery = {
                "hashes": {},
                "sources": {},
                "visited_count": 0,
                "remaining_queue_count": 0,
                "error": str(error)[:500],
            }
    merged_discovered_hashes = {**registry_hashes, **(discovery.get("hashes") or {})}
    operation_hashes, operation_hash_sources = _operation_hashes.resolve_operation_hashes(
        OPERATION_HASHES,
        discovered=merged_discovered_hashes,
    )
    for operation, hash_value in registry_hashes.items():
        if operation_hashes.get(operation) == hash_value and operation_hash_sources.get(operation) == "discovered":
            operation_hash_sources[operation] = registry_sources.get(operation) or "capability_registry"
    capability_registry_entries = _surfaces.load_capability_registry(CAPABILITY_REGISTRY_PATH)
    capability_registry_refs = []
    for operation, hash_value in operation_hashes.items():
        entry = _surfaces.capability_registry_entry(
            "host_reviews",
            observed_at=observed_at,
            endpoint_url=f"{BASE}/performance/quality/overall",
            operation_name=operation,
            operation_hash=hash_value,
            provenance={"source": operation_hash_sources.get(operation)},
        )
        capability_registry_entries = _surfaces.upsert_capability_registry(capability_registry_entries, entry)
        capability_registry_refs.append(_surfaces.registry_ref(entry))
    _surfaces.save_capability_registry(CAPABILITY_REGISTRY_PATH, capability_registry_entries)
    capability_registry_ref = {
        "registry_path": str(CAPABILITY_REGISTRY_PATH),
        "entries": capability_registry_refs,
    }

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
        daily_horizon_days=horizons["daily_horizon_days"],
        older_horizon_days=horizons["older_horizon_days"],
        weekly_window_days=horizons["weekly_window_days"],
    )
    summary_requests = build_requests_from_plan(
        planner_output.summary_requests,
        listings_by_id=listings_by_id,
        routes_by_subroute=routes_by_subroute,
        operation_name="ListOfMetricsQuery",
        operation_hashes=operation_hashes,
    )
    chart_requests = build_requests_from_plan(
        planner_output.chart_requests,
        listings_by_id=listings_by_id,
        routes_by_subroute=routes_by_subroute,
        operation_name="ChartQuery",
        operation_hashes=operation_hashes,
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
            summary_rows.append({
                **{k: v for k, v in result.items() if k not in {"data"}},
                "source_family": "host_private",
                "surface_class": "host_private",
                "auth_context": auth_context,
                **row,
            })

    daily_rows = []
    sentinel_rows = []
    for result in chart_results:
        if not result.get("ok"):
            continue
        parsed = parse_chart(result)
        if not parsed:
            rel_start = result.get("relative_ds_start")
            rel_end = result.get("relative_ds_end")
            if is_confirmed_empty_chart(result) and rel_start is not None and rel_end is not None:
                sentinel_ds = today + timedelta(days=int(rel_start))
                span_days = max(1, int(rel_end) - int(rel_start) + 1)
                sentinel_rows.append({
                    "listing_id": result.get("listing_id"),
                    "route_family": result.get("route_family"),
                    "route_subroute": result.get("route_subroute"),
                    "series_index": 0,
                    "ds": sentinel_ds.isoformat(),
                    "primary_metric_name": _ledger.SENTINEL_PRIMARY_METRIC,
                    "_attempt_span_days": span_days,
                    "_attempt_window_kind": result.get("chart_mode") or "single_window",
                    "value": None,
                    "value_string": None,
                    "value_type": "ATTEMPT_SENTINEL",
                    "series_granularity": _ledger.SENTINEL_GRANULARITY,
                    "observed_at": observed_at,
                    "run_id": run_id,
                    "source_url": result.get("source_url"),
                    "source_family": "host_private",
                    "surface_class": "host_private",
                    "auth_context": auth_context,
                })
            else:
                failures.append({**result, "ok": False, "error": "no_chart_points"})
        for row in parsed:
            daily_rows.append({
                **{k: v for k, v in result.items() if k not in {"data"}},
                "source_family": "host_private",
                "surface_class": "host_private",
                "auth_context": auth_context,
                **row,
            })

    # De-duplicate sentinel rows by (listing, route, ds). If multiple empty
    # windows start on the same day, keep the one with the broadest span so we
    # do not accidentally shrink coverage when a wider single_window and a
    # narrower rolling_daily window overlap.
    seen_sentinels = {}
    for row in sentinel_rows:
        key = (
            row.get("listing_id"),
            row.get("route_family"),
            row.get("route_subroute"),
            row.get("ds"),
        )
        existing = seen_sentinels.get(key)
        row_span = int(row.get("_attempt_span_days") or 1)
        existing_span = int((existing or {}).get("_attempt_span_days") or 1)
        if (
            existing is None
            or row_span > existing_span
            or (
                row_span == existing_span
                and str(row.get("observed_at") or "") >= str(existing.get("observed_at") or "")
            )
        ):
            seen_sentinels[key] = row
    sentinel_rows = list(seen_sentinels.values())

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
    _ledger.append_ledger_rows(LEDGER_PATH, sentinel_rows)

    json_path = OUTPUT_PATH / f"{run_id}.json"
    summary_csv_path = OUTPUT_PATH / f"{run_id}-summary-rows.csv"
    daily_csv_path = OUTPUT_PATH / f"{run_id}-daily-rows.csv"
    receipt_path = SESSION_PATH / f"{run_id}-receipt.json"
    prior_counts = _integrity.latest_prior_count(
        OUTPUT_PATH,
        count_keys=("summary_rows_count", "daily_rows_count", "sentinel_rows_count"),
        current_run_id=run_id,
    )
    current_metric_count = len(summary_rows) + len(daily_rows) + len(sentinel_rows)
    last_good_guard = _integrity.last_good_guard(
        subject="host_private_insights_metric_rows",
        current_count=current_metric_count,
        prior_positive_count=prior_counts["prior_positive_count"],
        allow_empty=os.environ.get("AIRBNB_INSIGHTS_ALLOW_EMPTY") == "1",
    )
    warehouse_exports = _integrity.warehouse_manifest([
        {
            "table": "airbnb_insights_metric_snapshot",
            "path": str(summary_csv_path),
            "row_count": len(summary_rows),
            "grain": "listing_id + route_subroute + period_label + observed_at",
            "source_family": "host_private",
            "surface_class": "host_private",
            "auth_context": auth_context,
        },
        {
            "table": "airbnb_insights_chart_point",
            "path": str(daily_csv_path),
            "row_count": len(daily_rows),
            "grain": "listing_id + route_subroute + series_index + ds",
            "source_family": "host_private",
            "surface_class": "host_private",
            "auth_context": auth_context,
        },
    ])
    output = _integrity.stamp_collection_contract({
        "run_id": run_id,
        "observed_at": observed_at,
        "auth_context": auth_context,
        "source_family": "host_private",
        "surface_class": "host_private",
        "collection_status": _integrity.collection_status(
            last_good_guard_record=last_good_guard,
            failures_count=len(failures),
            complete=len(failures) == 0,
        ),
        "source": {
            "listing_scope": str(listing_file),
            "summary_api": "ListOfMetricsQuery",
            "daily_chart_api": "ChartQuery",
            "transport": "Python HTTP replay with browser-session cookies and Airbnb bootstrap API key",
            "operation_hashes": operation_hashes,
            "operation_hash_sources": operation_hash_sources,
            "operation_hash_discovery": discovery,
            "capability_registry_ref": capability_registry_ref,
            "granularity_strategy": "tiered planner: rolling_daily for recent window + single_window chunks for older window; preserve returned series_granularity",
            "chart_mode": "tiered_gap_sync",
            "checkpoint_strategy": "successful raw API responses are appended to JSONL after each batch and skipped on rerun when AIRBNB_INSIGHTS_RUN_ID is reused",
            "ledger_path": str(LEDGER_PATH),
        },
        "last_good_guard": last_good_guard,
        "warehouse_exports": warehouse_exports,
        "listing_count": len(listings),
        "listing_status_scope": listing_scope["label"],
        "total_source_listings": len(all_listings),
        "total_scope_listings": total_scope_listings,
        "total_active_listings": total_active_listings,
        "listing_scope_complete": len(listings) == total_scope_listings,
        "listing_ids_in_scope": listing_ids_in_scope,
        "route_count": len(routes),
        "summary_periods": summary_periods,
        "history_days": horizons["history_days"],
        "horizons": horizons,
        "chart_mode": "tiered_gap_sync",
        "chart_window_count": len(chart_requests),
        "summary_request_count": len(summary_requests),
        "chart_request_count": len(chart_requests),
        "summary_rows_count": len(summary_rows),
        "chart_rows_count": len(daily_rows),
        "daily_rows_count": len(daily_rows),
        "sentinel_rows_count": len(sentinel_rows),
        "failures_count": len(failures),
        "summary_raw_path": str(summary_raw_path),
        "chart_raw_path": str(chart_raw_path),
        "summary_rows": summary_rows,
        "daily_rows": daily_rows,
        "failures": failures[:100],
    },
        source_family="host_private",
        surface_class="host_private",
        auth_context=auth_context,
        collection_status=_integrity.collection_status(
            last_good_guard_record=last_good_guard,
            failures_count=len(failures),
            complete=len(failures) == 0,
        ),
        last_good_guard_record=last_good_guard,
        warehouse_exports=warehouse_exports,
        capability_registry_ref=capability_registry_ref,
    )

    _integrity.write_collection_json(json_path, output)
    write_csv(summary_csv_path, summary_rows)
    write_csv(daily_csv_path, daily_rows)

    expected_summary = len(listings) * len(routes) * len(summary_periods)
    expected_charts = len(chart_requests)
    receipt = _integrity.stamp_collection_contract({
        "run_id": run_id,
        "observed_at": observed_at,
        "auth_context": output["auth_context"],
        "source_family": output["source_family"],
        "surface_class": output["surface_class"],
        "collection_status": output["collection_status"],
        "last_good_guard": last_good_guard,
        "warehouse_exports": warehouse_exports,
        "listing_count": len(listings),
        "listing_status_scope": listing_scope["label"],
        "total_source_listings": len(all_listings),
        "total_scope_listings": total_scope_listings,
        "total_active_listings": total_active_listings,
        "listing_scope_complete": len(listings) == total_scope_listings,
        "listing_ids_in_scope": listing_ids_in_scope,
        "route_count": len(routes),
        "summary_period_count": len(summary_periods),
        "history_days": horizons["history_days"],
        "horizons": horizons,
        "chart_mode": "tiered_gap_sync",
        "chart_window_count": len(chart_requests),
        "summary_request_count": len(summary_requests),
        "chart_request_count": len(chart_requests),
        "expected_summary_requests": expected_summary,
        "expected_chart_requests": expected_charts,
        "summary_rows_count": len(summary_rows),
        "chart_rows_count": len(daily_rows),
        "daily_rows_count": len(daily_rows),
        "sentinel_rows_count": len(sentinel_rows),
        "failures_count": len(failures),
        "operation_hashes": operation_hashes,
        "operation_hash_sources": operation_hash_sources,
        "operation_hash_discovery": discovery,
        "capability_registry_ref": capability_registry_ref,
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
    },
        source_family="host_private",
        surface_class="host_private",
        auth_context=output["auth_context"],
        collection_status=output["collection_status"],
        last_good_guard_record=last_good_guard,
        warehouse_exports=warehouse_exports,
        capability_registry_ref=capability_registry_ref,
    )
    _integrity.write_receipt_json(receipt_path, receipt)
    print(json.dumps(receipt, indent=2), flush=True)


if __name__ == "__main__":
    main()
