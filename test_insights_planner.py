import importlib.util
from datetime import date
from pathlib import Path


def load_module(path, name):
    path = Path(path)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_planner():
    return load_module("domain-skills/airbnb/scripts/insights_planner.py", "airbnb_insights_planner")


def sample_inputs():
    listings = [{"listing_id": "100"}]
    routes = [
        {"family": "conversion", "subroute": "p3_impressions"},
        {"family": "quality", "subroute": "overall"},
    ]
    periods = [
        {"label": "last_7_days", "ds_start": -7, "ds_end": 0},
        {"label": "last_30_days", "ds_start": -30, "ds_end": 0},
    ]
    today = date(2026, 4, 28)
    return listings, routes, periods, today


def test_fresh_ledger_full_plan():
    planner = load_planner()
    listings, routes, periods, today = sample_inputs()
    plan = planner.plan_requests(
        listings=listings,
        routes=routes,
        today=today,
        ledger_index={},
        summary_periods=periods,
        daily_horizon_days=14,
        older_horizon_days=14,
        weekly_window_days=7,
    )
    assert len(plan.summary_requests) == len(listings) * len(routes) * len(periods)
    assert len(plan.chart_requests) > 0
    assert {"rolling_daily", "single_window"} <= {row["chart_mode"] for row in plan.chart_requests}


def test_up_to_date_ledger_yields_no_chart_requests():
    planner = load_planner()
    listings, routes, periods, today = sample_inputs()
    ledger = {}
    for route in routes:
        for day in range(0, 29):
            ds = (today.replace(day=28) - planner.timedelta(days=day)).isoformat()
            key = ("100", route["family"], route["subroute"], 0, ds, route["subroute"])
            ledger[key] = {
                "listing_id": "100",
                "route_family": route["family"],
                "route_subroute": route["subroute"],
                "series_index": 0,
                "ds": ds,
                "primary_metric_name": route["subroute"],
                "observed_at": "2026-04-28T00:00:00Z",
            }
    plan = planner.plan_requests(
        listings=listings,
        routes=routes,
        today=today,
        ledger_index=ledger,
        summary_periods=periods,
        daily_horizon_days=14,
        older_horizon_days=14,
        weekly_window_days=7,
    )
    assert len(plan.summary_requests) == len(listings) * len(routes) * len(periods)
    assert plan.chart_requests == []


def test_partial_ledger_requests_only_missing():
    planner = load_planner()
    listings, routes, periods, today = sample_inputs()
    route = routes[0]
    ledger = {
        ("100", route["family"], route["subroute"], 0, "2026-04-25", route["subroute"]): {
            "listing_id": "100",
            "route_family": route["family"],
            "route_subroute": route["subroute"],
            "series_index": 0,
            "ds": "2026-04-25",
            "primary_metric_name": route["subroute"],
            "observed_at": "2026-04-25T00:00:00Z",
        }
    }
    plan = planner.plan_requests(
        listings=[{"listing_id": "100"}],
        routes=[route],
        today=today,
        ledger_index=ledger,
        summary_periods=periods,
        daily_horizon_days=7,
        older_horizon_days=0,
        weekly_window_days=7,
    )
    daily = [row for row in plan.chart_requests if row["chart_mode"] == "rolling_daily"]
    assert daily, "Expected a gap-fill request for missing recent days"
    starts = [row["relative_ds_start"] for row in daily]
    ends = [row["relative_ds_end"] for row in daily]
    assert min(starts) == -7
    assert (-2, -1) in {(row["relative_ds_start"], row["relative_ds_end"]) for row in daily}
    # daily_end is today-1 (relative -1) to avoid the Airbnb malformed-input error
    # that occurs when asking for a window ending on today (relative 0).
    assert max(ends) == -1


def test_internal_daily_ledger_gap_is_replanned():
    planner = load_planner()
    listings, routes, periods, today = sample_inputs()
    route = routes[0]
    ledger = {}
    for ds in ["2026-04-21", "2026-04-22", "2026-04-23", "2026-04-25", "2026-04-26", "2026-04-27"]:
        ledger[("100", route["family"], route["subroute"], 0, ds, route["subroute"])] = {
            "listing_id": "100",
            "route_family": route["family"],
            "route_subroute": route["subroute"],
            "series_index": 0,
            "ds": ds,
            "primary_metric_name": route["subroute"],
            "observed_at": "2026-04-28T00:00:00Z",
        }

    plan = planner.plan_requests(
        listings=[{"listing_id": "100"}],
        routes=[route],
        today=today,
        ledger_index=ledger,
        summary_periods=periods,
        daily_horizon_days=7,
        older_horizon_days=0,
        weekly_window_days=7,
    )

    daily_windows = [
        (row["relative_ds_start"], row["relative_ds_end"])
        for row in plan.chart_requests
        if row["chart_mode"] == "rolling_daily"
    ]
    assert len(daily_windows) == 1
    start, end = daily_windows[0]
    assert start <= -4 <= end
    assert end <= -1


def test_tier_boundary_no_overlap_between_daily_and_older():
    planner = load_planner()
    listings, routes, periods, today = sample_inputs()
    plan = planner.plan_requests(
        listings=[{"listing_id": "100"}],
        routes=[routes[0]],
        today=today,
        ledger_index={},
        summary_periods=periods,
        daily_horizon_days=14,
        older_horizon_days=14,
        weekly_window_days=7,
    )
    daily = [row for row in plan.chart_requests if row["chart_mode"] == "rolling_daily"]
    older = [row for row in plan.chart_requests if row["chart_mode"] == "single_window"]
    assert daily and older
    assert min(row["relative_ds_start"] for row in daily) >= -14
    assert max(row["relative_ds_end"] for row in older) <= -15


def test_default_weekly_window_days_elicits_week_granularity():
    """Probe shows Airbnb returns WEEK granularity for windows >=56 days.

    Regression guard: the default must not drop back below the WEEK-eliciting
    threshold without an accompanying probe update.
    """
    planner = load_planner()
    import inspect

    sig = inspect.signature(planner.plan_requests)
    assert sig.parameters["weekly_window_days"].default >= 56


def test_no_window_has_start_equal_to_end():
    """Empirically verified: Airbnb's ChartQuery rejects ANY window where
    relative_ds_start == relative_ds_end with malformed_input, regardless of
    position. Every emitted window must have at least 2 days span.
    """
    planner = load_planner()
    listings, routes, periods, today = sample_inputs()
    plan = planner.plan_requests(
        listings=listings,
        routes=routes,
        today=today,
        ledger_index={},
        summary_periods=periods,
        daily_horizon_days=14,
        older_horizon_days=14,
        weekly_window_days=56,
    )
    for row in plan.chart_requests:
        assert row["relative_ds_start"] < row["relative_ds_end"], (
            f"Zero-length window emitted: {row}. Airbnb will reject this."
        )


def test_planner_rejects_weekly_window_days_below_two():
    planner = load_planner()
    listings, routes, periods, today = sample_inputs()

    import pytest

    with pytest.raises(ValueError, match="weekly_window_days must be at least 2"):
        planner.plan_requests(
            listings=listings,
            routes=routes,
            today=today,
            ledger_index={},
            summary_periods=periods,
            daily_horizon_days=0,
            older_horizon_days=1,
            weekly_window_days=1,
        )


def test_single_day_gap_padded_to_full_window():
    """When the only missing date is a single day, the planner must pad the
    window to its full window_days width (anchored at end_ds) so the API is
    given a valid 7-day window. The ledger dedupes the overlap.
    """
    planner = load_planner()
    listings, routes, periods, today = sample_inputs()
    route = routes[0]
    listing = listings[0]
    # Pre-seed the ledger with every day except the one furthest into the
    # daily horizon end.
    from datetime import timedelta as td

    ledger = {}
    for offset in range(7, 90):  # cover daily_start..daily_end-1 leaving daily_end uncovered
        ds = (today - td(days=offset + 1)).isoformat()
        ledger[(listing["listing_id"], route["family"], route["subroute"], 0, ds, route["subroute"])] = {
            "listing_id": listing["listing_id"],
            "route_family": route["family"],
            "route_subroute": route["subroute"],
            "series_index": 0,
            "ds": ds,
            "primary_metric_name": route["subroute"],
            "series_granularity": "DAY",
            "observed_at": "2026-04-28T00:00:00Z",
        }
    plan = planner.plan_requests(
        listings=[listing],
        routes=[route],
        today=today,
        ledger_index=ledger,
        summary_periods=[],
        daily_horizon_days=90,
        older_horizon_days=0,
        weekly_window_days=56,
    )
    assert plan.chart_requests, "Expected the single-day gap to be filled"
    for row in plan.chart_requests:
        span = row["relative_ds_end"] - row["relative_ds_start"]
        assert span >= 1, f"Window must have ≥2 day span; got {row}"


def test_daily_end_excludes_today_to_avoid_malformed_input():
    """Regression guard: relative_ds_end=0 (today) triggers ServiceBadRequestError
    on Airbnb's ChartQuery; daily windows must end at most at today-1.
    """
    planner = load_planner()
    listings, routes, periods, today = sample_inputs()
    plan = planner.plan_requests(
        listings=listings,
        routes=routes,
        today=today,
        ledger_index={},
        summary_periods=periods,
        daily_horizon_days=14,
        older_horizon_days=14,
        weekly_window_days=56,
    )
    daily = [row for row in plan.chart_requests if row["chart_mode"] == "rolling_daily"]
    assert daily
    assert max(row["relative_ds_end"] for row in daily) <= -1
    assert all(row["relative_ds_start"] <= row["relative_ds_end"] for row in daily)


def test_month_granularity_does_not_satisfy_daily_backfill():
    planner = load_planner()
    today = date(2026, 4, 28)
    route = {"family": "conversion", "subroute": "p3_impressions"}
    ledger = {
        ("100", route["family"], route["subroute"], 0, "2026-01-20", route["subroute"]): {
            "listing_id": "100",
            "route_family": route["family"],
            "route_subroute": route["subroute"],
            "series_index": 0,
            "ds": "2026-01-20",
            "primary_metric_name": route["subroute"],
            "series_granularity": "MONTH",
            "observed_at": "2026-04-01T00:00:00Z",
        }
    }

    plan = planner.plan_requests(
        listings=[{"listing_id": "100"}],
        routes=[route],
        today=today,
        ledger_index=ledger,
        summary_periods=[],
        daily_horizon_days=90,
        older_horizon_days=0,
        weekly_window_days=56,
    )

    rolling_windows = [
        (row["relative_ds_start"], row["relative_ds_end"])
        for row in plan.chart_requests
        if row["chart_mode"] == "rolling_daily"
    ]
    assert rolling_windows
    assert min(start for start, _ in rolling_windows) == -90
    assert any(start <= -90 <= end for start, end in rolling_windows)


def test_planner_emits_summary_request_for_every_listing_route_period():
    """Critical safety property: every (listing, route, period) triple gets a
    summary request, and every listing gets gap-fill chart coverage (when the
    ledger is empty). No listing can be silently dropped.
    """
    planner = load_planner()
    today = date(2026, 4, 28)
    listings = [{"listing_id": str(i)} for i in range(1, 28)]  # 27 listings (production count)
    routes = [
        {"family": "conversion", "subroute": "p3_impressions"},
        {"family": "conversion", "subroute": "wishlist"},
        {"family": "occupancy", "subroute": "occupancy_rate"},
    ]
    periods = [
        {"label": "last_7_days", "ds_start": -7, "ds_end": 0},
        {"label": "last_30_days", "ds_start": -30, "ds_end": 0},
        {"label": "last_365_days", "ds_start": -365, "ds_end": 0},
    ]
    plan = planner.plan_requests(
        listings=listings,
        routes=routes,
        today=today,
        ledger_index={},
        summary_periods=periods,
        daily_horizon_days=90,
        older_horizon_days=275,
        weekly_window_days=56,
    )

    # 27 listings × 3 routes × 3 periods = 243 summary requests.
    assert len(plan.summary_requests) == 27 * 3 * 3
    summary_listing_ids = {r["listing_id"] for r in plan.summary_requests}
    assert summary_listing_ids == {str(i) for i in range(1, 28)}, (
        "Planner must emit at least one summary request for every input listing"
    )

    # With empty ledger, every listing must also get chart requests.
    chart_listing_ids = {r["listing_id"] for r in plan.chart_requests}
    assert chart_listing_ids == {str(i) for i in range(1, 28)}, (
        "Planner must emit at least one chart request for every input listing when ledger is empty"
    )


def test_planner_does_not_drop_listings_with_partial_ledger_coverage():
    """If listing A's ledger is fully covered and listing B's is empty, the
    planner must still emit chart requests for B.
    """
    planner = load_planner()
    ledger_module = load_module("domain-skills/airbnb/scripts/insights_ledger.py", "airbnb_insights_ledger")
    today = date(2026, 4, 28)
    listings = [{"listing_id": "A"}, {"listing_id": "B"}]
    routes = [{"family": "conversion", "subroute": "p3_impressions"}]
    periods = [{"label": "last_7_days", "ds_start": -7, "ds_end": 0}]

    # Pre-seed listing A with full daily-tier coverage.
    from datetime import timedelta as td
    ledger = {}
    for offset in range(1, 91):
        ds = (today - td(days=offset)).isoformat()
        row = {
            "listing_id": "A",
            "route_family": "conversion",
            "route_subroute": "p3_impressions",
            "series_index": 0,
            "ds": ds,
            "primary_metric_name": "p3_impressions",
            "series_granularity": "DAY",
            "observed_at": "2026-04-28T00:00:00Z",
        }
        ledger[ledger_module.ledger_key(row)] = row

    plan = planner.plan_requests(
        listings=listings,
        routes=routes,
        today=today,
        ledger_index=ledger,
        summary_periods=periods,
        daily_horizon_days=90,
        older_horizon_days=0,
        weekly_window_days=56,
    )

    # Both listings get summary requests.
    assert {r["listing_id"] for r in plan.summary_requests} == {"A", "B"}
    # Listing B (empty ledger) gets chart requests; listing A has no daily-tier gaps.
    chart_listing_ids = {r["listing_id"] for r in plan.chart_requests}
    assert "B" in chart_listing_ids


def test_sentinel_covered_window_is_not_replanned():
    """Older-tier gaps covered by active attempt sentinels must not generate new
    chart requests. The sentinel (series_granularity=ATTEMPT_RANGE) expands over
    _attempt_span_days days in build_latest_ds_index, which the planner then
    treats as covered dates.
    """
    planner = load_planner()
    ledger_module = load_module("domain-skills/airbnb/scripts/insights_ledger.py", "airbnb_insights_ledger")
    listings, routes, periods, today = sample_inputs()
    route = routes[0]

    # Build a sentinel covering 56 days in the older tier.
    # ds_start = 200 days ago, span = 56 days -> covers [200, 145] days ago.
    from datetime import timedelta
    sentinel_ds = (today - timedelta(days=200)).isoformat()
    sentinel_observed = (today - timedelta(days=1)).isoformat() + "T00:00:00Z"
    sentinel = {
        "listing_id": "100",
        "route_family": route["family"],
        "route_subroute": route["subroute"],
        "series_index": 0,
        "ds": sentinel_ds,
        "primary_metric_name": ledger_module.SENTINEL_PRIMARY_METRIC,
        "_attempt_span_days": 56,
        "_attempt_window_kind": "single_window",
        "value": None,
        "value_string": None,
        "value_type": "ATTEMPT_SENTINEL",
        "series_granularity": ledger_module.SENTINEL_GRANULARITY,
        "observed_at": sentinel_observed,
        "run_id": "run-sentinel",
        "source_url": "",
    }
    ledger_index = {ledger_module.ledger_key(sentinel): sentinel}

    plan = planner.plan_requests(
        listings=[{"listing_id": "100"}],
        routes=[route],
        today=today,
        ledger_index=ledger_index,
        summary_periods=[],
        daily_horizon_days=90,
        older_horizon_days=275,
        weekly_window_days=56,
    )

    # All 56 sentinel-covered dates should be absent from chart_requests.
    sentinel_start = today - timedelta(days=200)
    sentinel_end = sentinel_start + timedelta(days=55)
    for req in plan.chart_requests:
        # Convert relative offsets back to absolute dates
        req_start_abs = today + timedelta(days=req["relative_ds_start"])
        req_end_abs = today + timedelta(days=req["relative_ds_end"])
        # No request should overlap the sentinel range [sentinel_start, sentinel_end]
        overlap = req_start_abs <= sentinel_end and req_end_abs >= sentinel_start
        assert not overlap, (
            f"Request {req} overlaps sentinel range {sentinel_start}–{sentinel_end}"
        )


def test_comparison_series_rows_do_not_affect_gap_math():
    planner = load_planner()
    listings, routes, periods, today = sample_inputs()
    route = routes[0]
    ledger = {
        ("100", route["family"], route["subroute"], 1, "2026-04-28", route["subroute"]): {
            "listing_id": "100",
            "route_family": route["family"],
            "route_subroute": route["subroute"],
            "series_index": 1,
            "ds": "2026-04-28",
            "primary_metric_name": route["subroute"],
            "observed_at": "2026-04-28T00:00:00Z",
        }
    }
    plan = planner.plan_requests(
        listings=[{"listing_id": "100"}],
        routes=[route],
        today=today,
        ledger_index=ledger,
        summary_periods=periods,
        daily_horizon_days=7,
        older_horizon_days=0,
        weekly_window_days=7,
    )
    # No series_index=0 points in ledger, so planner still needs daily requests.
    assert any(row["chart_mode"] == "rolling_daily" for row in plan.chart_requests)
