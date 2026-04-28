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
    """Generate windows covering [start_ds, end_ds].

    Empirical Airbnb constraint (probe_single_day_windows.py): ChartQuery rejects
    any window where relative_ds_start == relative_ds_end with
    ServiceBadRequestError/malformed_input, regardless of position. So every
    emitted window must satisfy `end - start >= 1` (≥ 2 calendar days).

    Strategy: emit non-overlapping window_days-sized windows from start_ds
    forward; if a partial trailing window would be < 2 days, right-align it to
    end_ds with the full window_days width. The overlap with the previous
    window is harmless because the ledger dedupes by (listing, route, series,
    ds, primary_metric_name).
    """
    if start_ds > end_ds:
        return []
    span = (end_ds - start_ds).days + 1
    if span < 2:
        # Pad single-day gap to a full window anchored at end_ds.
        return [(end_ds - timedelta(days=window_days - 1), end_ds)]
    windows = []
    current = start_ds
    while current + timedelta(days=window_days - 1) <= end_ds:
        windows.append((current, current + timedelta(days=window_days - 1)))
        current = current + timedelta(days=window_days)
    if current <= end_ds:
        partial_span = (end_ds - current).days + 1
        if partial_span >= 2:
            windows.append((current, end_ds))
        else:
            # Trailing partial of length 1 — right-align to end_ds with full width.
            windows.append((end_ds - timedelta(days=window_days - 1), end_ds))
    return windows


def _single_windows(start_ds, end_ds, window_days):
    return _rolling_daily_windows(start_ds, end_ds, window_days=window_days)


def _missing_date_ranges_from_dates(start_ds, end_ds, covered_dates):
    """Given a set/sorted-iterable of covered date objects, return contiguous
    [missing_start, missing_end] ranges in [start_ds, end_ds] with no coverage.
    """
    if start_ds > end_ds:
        return []
    covered = covered_dates if isinstance(covered_dates, set) else set(covered_dates)
    ranges = []
    current = start_ds
    while current <= end_ds:
        if current in covered:
            current += timedelta(days=1)
            continue
        missing_start = current
        while current <= end_ds and current not in covered:
            current += timedelta(days=1)
        ranges.append((missing_start, current - timedelta(days=1)))
    return ranges


def _bucket_dates_in_range(buckets, listing_id, route_subroute, series_index, start_ds, end_ds):
    """Pull the date list out of a precomputed bucket and slice to [start_ds, end_ds]."""
    key = (str(listing_id), route_subroute, int(series_index))
    dates = buckets.get(key) or []
    if not dates:
        return set()
    # Binary search the inclusive range [start_ds, end_ds]
    import bisect

    lo = bisect.bisect_left(dates, start_ds)
    hi = bisect.bisect_right(dates, end_ds)
    return set(dates[lo:hi])


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
    # Airbnb daily data lags by at least one day; relative_ds_end=0 maps to today
    # which produces a malformed-input error from ChartQuery.
    daily_end = today - timedelta(days=1)
    older_start = today - timedelta(days=(daily_horizon_days + older_horizon_days))
    older_end = daily_start - timedelta(days=1)

    # One-time O(n) bucketing of the ledger by (listing, route, series); each
    # subsequent in-range slice is O(log n + k) instead of O(n).
    buckets = _ledger.build_latest_ds_index(ledger_index)

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

            covered_daily = _bucket_dates_in_range(
                buckets, listing_id, route_subroute, 0, daily_start, daily_end
            )
            for missing_start, missing_end in _missing_date_ranges_from_dates(daily_start, daily_end, covered_daily):
                for start_ds, end_ds in _rolling_daily_windows(missing_start, missing_end, window_days=7):
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

            # Older tier: same gap-driven approach. The previous "skip any window
            # that overlaps any covered date" was incorrect because a single
            # covered date in the middle of a 56-day window caused the entire
            # window's other 55 days to be dropped.
            covered_older = _bucket_dates_in_range(
                buckets, listing_id, route_subroute, 0, older_start, older_end
            )
            for missing_start, missing_end in _missing_date_ranges_from_dates(older_start, older_end, covered_older):
                for start_ds, end_ds in _single_windows(missing_start, missing_end, window_days=weekly_window_days):
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
