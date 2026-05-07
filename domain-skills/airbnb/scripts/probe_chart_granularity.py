"""Probe Airbnb ChartQuery granularity across horizons."""

from __future__ import annotations

import json
import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from browser_harness import login_session


BASE = "https://www.airbnb.com.au"
LISTINGS_PATH = Path("domain-skills/airbnb/.private-data/listing-collections")
OUTPUT_JSON = Path("domain-skills/airbnb/.private-data/insights-collections/airbnb-insights-granularity-probe.json")
OUTPUT_MD = Path("domain-skills/airbnb/insights-granularity-map.md")
HASH = "3e1e441e3bac1937e60c1b0409b53286e338804dd94c68575c556289a3b07580"  # ChartQuery
HORIZONS = [14, 28, 56, 90, 180, 275, 365]
ROUTES = [
    {"family": "conversion", "metric_type": "CONVERSION", "subroute": "conversion_rate"},
    {"family": "occupancy", "metric_type": "OCCUPANCY", "subroute": "occupancy_rate"},
    {"family": "quality", "metric_type": "QUALITY", "subroute": "overall"},
]


def _load_local_module(module_filename, module_name):
    path = Path("domain-skills/airbnb/scripts") / module_filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_operation_hashes = _load_local_module("operation_hashes.py", "airbnb_operation_hashes")
_integrity = _load_local_module("run_integrity.py", "airbnb_run_integrity")


def is_complete_live_listing_file(path: Path):
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return False

    def safe_int(value) -> int:
        if isinstance(value, bool):
            return 0
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    status_counts = data.get("status_counts")
    if not isinstance(status_counts, dict):
        status_counts = {}
    active_status_count = safe_int(status_counts.get("ACTIVE"))
    records = data.get("records") or []
    validation = data.get("field_validation") or {}
    return (
        bool(records)
        and len(records) == safe_int(data.get("active_count"))
        and len(records) == active_status_count
        and validation.get("all_active_detail_pages_ok") is True
        and not data.get("partial_run")
    )


def latest_live_listing_file():
    files = sorted(LISTINGS_PATH.glob("airbnb-live-listings-*.json"))
    complete = [path for path in files if is_complete_live_listing_file(path)]
    if not complete:
        raise SystemExit("No complete listing inventory found for probe")
    return complete[-1]


def read_api_key():
    return js("JSON.parse(document.querySelector('#data-initializer-bootstrap')?.textContent || '{}')['layout-init']?.api_config?.key")


def route_url(route, listing_id, ds_start=-2, ds_end=-1):
    return (
        f"{BASE}/performance/{route['family']}/{route['subroute']}/listing/{listing_id}"
        f"?ds-start={ds_start}&ds-end={ds_end}"
    )


def chart_request(route, listing_id, ds_start, ds_end, hash_value=HASH):
    return {
        "operationName": "ChartQuery",
        "hash": hash_value,
        "variables": {
            "request": {
                "clientName": "web-performance-dash-chart",
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
        },
    }


def chart_bounds_for_horizon(horizon):
    # ChartQuery rejects windows ending at relative 0 because same-day data lags.
    return -int(horizon), -1


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


def fetch_chart(api_key, base_headers, route, listing_id, horizon, hash_value=HASH):
    ds_start, ds_end = chart_bounds_for_horizon(horizon)
    item = chart_request(route, listing_id, ds_start, ds_end, hash_value=hash_value)
    extensions = {"persistedQuery": {"version": 1, "sha256Hash": hash_value}}
    path = (
        f"/api/v3/ChartQuery/{hash_value}?operationName=ChartQuery&locale=en-AU&currency=AUD"
        f"&variables={quote(json.dumps(item['variables'], separators=(',', ':')))}"
        f"&extensions={quote(json.dumps(extensions, separators=(',', ':')))}"
    )
    request = Request(
        BASE + path,
        headers={
            **base_headers,
            "Accept": "application/json",
            "Accept-Encoding": "identity",
            "X-Airbnb-API-Key": api_key,
            "X-Airbnb-GraphQL-Platform": "web",
            "X-CSRF-Without-Token": "1",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
            status = response.status
    except HTTPError as error:
        text = error.read().decode("utf-8", errors="replace")
        return {
            "ok": False,
            "status": error.code,
            "relative_ds_start": ds_start,
            "relative_ds_end": ds_end,
            "granularity": [],
            "error": text[:500],
        }
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        return {
            "ok": False,
            "status": None,
            "relative_ds_start": ds_start,
            "relative_ds_end": ds_end,
            "granularity": [],
            "error": str(error),
        }
    graphql_error = graphql_error_summary(payload)
    if graphql_error is not None:
        return {
            "ok": False,
            "status": status,
            "relative_ds_start": ds_start,
            "relative_ds_end": ds_end,
            "granularity": [],
            "error": graphql_error,
        }
    components = (
        (payload.get("data") or {})
        .get("porygon", {})
        .get("getPerformanceComponents", {})
        .get("components", [])
    )
    rows = []
    for component in components:
        if component.get("componentName") != "PIVOT_CHART_SECTION":
            continue
        for chart in component.get("metricLineCharts") or []:
            rows.append(chart.get("granularity"))
    return {
        "ok": True,
        "status": status,
        "relative_ds_start": ds_start,
        "relative_ds_end": ds_end,
        "granularity": sorted({row for row in rows if row}),
        "error": None,
    }


def write_markdown(observed_at, listing_id, rows):
    lines = [
        "# Airbnb Insights Chart Granularity Map",
        "",
        f"- observed_at: `{observed_at}`",
        f"- listing_id_probe: `{listing_id}`",
        "- source: authenticated `ChartQuery` probes",
        "",
        "| route_subroute | horizon_days | relative_ds_start | relative_ds_end | status | returned_granularity | error |",
        "|---|---:|---:|---:|---|---|---|",
    ]
    for row in rows:
        gran = ", ".join(row["granularity"]) if row["granularity"] else "none"
        status = "ok" if row.get("ok") else f"failed:{row.get('status')}"
        error = (row.get("error") or "").replace("|", "\\|")[:120]
        lines.append(
            f"| {row['route_subroute']} | {row['horizon_days']} | "
            f"{row['relative_ds_start']} | {row['relative_ds_end']} | {status} | {gran} | {error} |"
        )
    OUTPUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    observed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    listing_data = json.loads(latest_live_listing_file().read_text())
    listing_id = str((listing_data.get("records") or [])[0]["listing_id"])

    goto_url(route_url(ROUTES[0], listing_id))
    wait_for_load()
    wait(2)
    api_key = read_api_key()
    if not api_key:
        raise SystemExit("Could not read Airbnb API key from bootstrap")
    base_headers = login_session.browser_session_headers(cdp, BASE + "/api/v3/", cookie_urls=[BASE + "/"])
    operation_hashes, _ = _operation_hashes.resolve_operation_hashes({"ChartQuery": HASH})
    chart_hash = operation_hashes["ChartQuery"]

    rows = []
    for route in ROUTES:
        for horizon in HORIZONS:
            result = fetch_chart(api_key, base_headers, route, listing_id, horizon, hash_value=chart_hash)
            rows.append(
                {
                    "route_family": route["family"],
                    "route_subroute": route["subroute"],
                    "horizon_days": horizon,
                    **result,
                }
            )
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    payload = _integrity.stamp_collection_contract(
        {
            "run_id": "airbnb-insights-granularity-probe",
            "observed_at": observed_at,
            "listing_id_probe": listing_id,
            "rows": rows,
        },
        source_family="capability",
        surface_class="capability",
        auth_context="probe_browser_context",
        collection_status="complete" if not [row for row in rows if not row.get("ok")] else "partial_failed",
    )
    _integrity.write_collection_json(OUTPUT_JSON, payload)
    write_markdown(observed_at, listing_id, rows)
    failures = [row for row in rows if not row.get("ok")]
    result = {
        "observed_at": observed_at,
        "listing_id_probe": listing_id,
        "rows_count": len(rows),
        "failures_count": len(failures),
        "markdown_path": str(OUTPUT_MD),
    }
    print(json.dumps(result))
    if failures:
        raise SystemExit(f"Granularity probe recorded {len(failures)} failed requests; see {OUTPUT_JSON}")


if __name__ == "__main__":
    import sys
    if any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
        print((__doc__ or "").strip())
        raise SystemExit(0)
    main()
