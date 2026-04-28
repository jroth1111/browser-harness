"""Tiered request planner for Airbnb Insights collection."""

from __future__ import annotations
import importlib.util
from datetime import date, timedelta
from pathlib import Path


def _load_ledger_module():
    path = Path(__file__).parent / "insights_ledger.py"
    spec = importlib.util.spec_from_file_location("airbnb_insights_ledger", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_ledger = _load_ledger_module()


class RequestPlan:
    def __init__(self, summary_requests, chart_requests):
        self.summary_requests = summary_requests
        self.chart_requests = chart_requests

    @property
    def empty(self):
        return not self.summary_requests and not self.chart_requests


def _parse_ds(value):
    if not value:
        return None
    return date.fromisoformat(str(value))


def _relative(today, ds):
    return (ds - today).days


def _rolling_daily_windows(start_ds, end_ds, window_days=7):
    if start_ds > end_ds:
        return []
    windows = []
    current = start_ds
    while current <= end_ds:
        window_end = min(current + timedelta(days=window_days - 1), end_ds)
        windows.append((current, window_end))
        current = window_end + timedelta(days=1)
    return windows


def _single_windows(start_ds, end_ds, window_days):
    return _rolling_daily_windows(start_ds, end_ds, window_days=window_days)


def plan_requests(
    listings,
    routes,
    today,
    ledger_index,
    summary_periods,
    daily_horizon_days=90,
    older_horizon_days=275,
    weekly_window_days=56,
):
    chart_requests = []
    summary_requests = []
    today = _parse_ds(today) if not isinstance(today, date) else today

    daily_start = today - timedelta(days=daily_horizon_days)
    # Airbnb daily data lags by at least one day; a window ending on today (relative 0)
    # produces a malformed-input error from ChartQuery.
    daily_end = today - timedelta(days=1)
    older_start = today - timedelta(days=(daily_horizon_days + older_horizon_days))
    older_end = daily_start - timedelta(days=1)

    for listing in listings:
        listing_id = str(listing["listing_id"])
        for route in routes:
            route_subroute = route["subroute"]
            route_family = route["family"]

            for period in summary_periods:
                summary_requests.append(
                    {
                        "request_kind": "summary",
                        "listing_id": listing_id,
                        "route_family": route_family,
                        "route_subroute": route_subroute,
                        "period_label": period["label"],
                        "relative_ds_start": int(period["ds_start"]),
                        "relative_ds_end": int(period["ds_end"]),
                    }
                )

            latest_daily = _ledger.latest_ds_per(
                ledger_index,
                listing_id=listing_id,
                route_subroute=route_subroute,
                series_index=0,
            )
            missing_daily_start = daily_start if latest_daily is None else max(latest_daily + timedelta(days=1), daily_start)
            for start_ds, end_ds in _rolling_daily_windows(missing_daily_start, daily_end, window_days=7):
                chart_requests.append(
                    {
                        "request_kind": "daily_chart",
                        "chart_mode": "rolling_daily",
                        "listing_id": listing_id,
                        "route_family": route_family,
                        "route_subroute": route_subroute,
                        "relative_ds_start": _relative(today, start_ds),
                        "relative_ds_end": _relative(today, end_ds),
                    }
                )

            latest_older = _ledger.latest_ds_per(
                ledger_index,
                listing_id=listing_id,
                route_subroute=route_subroute,
                series_index=0,
                max_ds=older_end,
            )
            missing_older_start = older_start if latest_older is None else max(latest_older + timedelta(days=1), older_start)
            for start_ds, end_ds in _single_windows(missing_older_start, older_end, window_days=weekly_window_days):
                chart_requests.append(
                    {
                        "request_kind": "daily_chart",
                        "chart_mode": "single_window",
                        "listing_id": listing_id,
                        "route_family": route_family,
                        "route_subroute": route_subroute,
                        "relative_ds_start": _relative(today, start_ds),
                        "relative_ds_end": _relative(today, end_ds),
                    }
                )

    return RequestPlan(summary_requests=summary_requests, chart_requests=chart_requests)
