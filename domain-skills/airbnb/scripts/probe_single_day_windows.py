"""Probe Airbnb ChartQuery behavior for single-day windows.

Hypothesis to test: (0, 0) fails because today's daily data is unavailable, but
single-day past windows like (-1, -1), (-7, -7) succeed. If true, the planner's
`daily_end = today - 1` cap is sufficient. If false, we need belt-and-suspenders
defense against any zero-width window.

Probes for one ACTIVE listing × one route per family across these window shapes:
- (0, 0)     - today only (known failure)
- (-1, -1)   - yesterday only
- (-2, -2)   - day before yesterday
- (-7, -7)   - one week ago, single day
- (-30, -30) - one month ago, single day
- (-1, 0)    - 2-day window ending today
- (-7, -1)   - canonical 7-day window ending yesterday
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

import login_session


BASE = "https://www.airbnb.com.au"
LISTINGS_PATH = Path("domain-skills/airbnb/.private-data/listing-collections")
OUTPUT_JSON = Path("domain-skills/airbnb/.private-data/insights-collections/airbnb-insights-single-day-window-probe.json")
HASH = "3e1e441e3bac1937e60c1b0409b53286e338804dd94c68575c556289a3b07580"

WINDOWS = [
    {"label": "(0,0) today only", "ds_start": 0, "ds_end": 0},
    {"label": "(-1,-1) yesterday only", "ds_start": -1, "ds_end": -1},
    {"label": "(-2,-2) day before yesterday", "ds_start": -2, "ds_end": -2},
    {"label": "(-7,-7) week ago single day", "ds_start": -7, "ds_end": -7},
    {"label": "(-30,-30) month ago single day", "ds_start": -30, "ds_end": -30},
    {"label": "(-1,0) two-day ending today", "ds_start": -1, "ds_end": 0},
    {"label": "(-7,-1) canonical 7-day ending yesterday", "ds_start": -7, "ds_end": -1},
]

ROUTES = [
    {"family": "conversion", "metric_type": "CONVERSION", "subroute": "p3_impressions"},
    {"family": "occupancy", "metric_type": "OCCUPANCY", "subroute": "occupancy_rate"},
    {"family": "quality", "metric_type": "QUALITY", "subroute": "overall"},
]


def is_complete_live_listing_file(path):
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


def latest_live_listing_file():
    files = sorted(LISTINGS_PATH.glob("airbnb-live-listings-*.json"))
    complete = [path for path in files if is_complete_live_listing_file(path)]
    if not complete:
        raise SystemExit("No complete listing inventory found for probe")
    return complete[-1]


def chart_request(route, listing_id, ds_start, ds_end):
    return {
        "operationName": "ChartQuery",
        "hash": HASH,
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


def fetch_one(api_key, base_headers, route, listing_id, ds_start, ds_end):
    item = chart_request(route, listing_id, ds_start, ds_end)
    extensions = {"persistedQuery": {"version": 1, "sha256Hash": HASH}}
    path = (
        f"/api/v3/ChartQuery/{HASH}?operationName=ChartQuery&locale=en-AU&currency=AUD"
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
    with urlopen(request, timeout=30) as response:
        status = response.status
        payload = json.loads(response.read().decode("utf-8", errors="replace"))
    has_errors = bool(payload.get("errors"))
    error_class = None
    error_type = None
    if has_errors:
        first_error = (payload.get("errors") or [{}])[0]
        ext = first_error.get("extensions") or {}
        error_class = ext.get("errorClass")
        error_type = ext.get("errorType")
    components = (
        (payload.get("data") or {})
        .get("porygon", {})
        .get("getPerformanceComponents")
        or {}
    ).get("components", []) if isinstance(payload.get("data"), dict) else []
    point_count = 0
    granularity = None
    for component in components or []:
        if component.get("componentName") != "PIVOT_CHART_SECTION":
            continue
        for chart in component.get("metricLineCharts") or []:
            granularity = granularity or chart.get("granularity")
            point_count += len(chart.get("dataPoints") or [])
    return {
        "http_status": status,
        "has_graphql_errors": has_errors,
        "error_class": error_class,
        "error_type": error_type,
        "point_count": point_count,
        "granularity": granularity,
    }


def main():
    observed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    listing_data = json.loads(latest_live_listing_file().read_text())
    listing_id = str((listing_data.get("records") or [])[0]["listing_id"])

    first_route_url = f"{BASE}/performance/{ROUTES[0]['family']}/{ROUTES[0]['subroute']}/listing/{listing_id}?ds-start=-1&ds-end=0"
    goto_url(first_route_url)
    wait_for_load()
    wait(2)
    api_key = js("JSON.parse(document.querySelector('#data-initializer-bootstrap')?.textContent || '{}')['layout-init']?.api_config?.key")
    if not api_key:
        raise SystemExit("Could not read Airbnb API key from bootstrap")
    base_headers = login_session.browser_session_headers(cdp, BASE + "/api/v3/", cookie_urls=[BASE + "/"])

    rows = []
    for route in ROUTES:
        for window in WINDOWS:
            result = fetch_one(api_key, base_headers, route, listing_id, window["ds_start"], window["ds_end"])
            rows.append(
                {
                    "route_family": route["family"],
                    "route_subroute": route["subroute"],
                    "window": window["label"],
                    "ds_start": window["ds_start"],
                    "ds_end": window["ds_end"],
                    **result,
                }
            )
            print(json.dumps({**rows[-1]}), flush=True)

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(
        json.dumps(
            {
                "observed_at": observed_at,
                "listing_id_probe": listing_id,
                "rows": rows,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps({"summary_path": str(OUTPUT_JSON), "rows_count": len(rows)}))


main()
