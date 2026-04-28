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
