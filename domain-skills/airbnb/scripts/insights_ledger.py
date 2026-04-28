"""Cross-run ledger utilities for Airbnb Insights chart primitives."""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path


LEDGER_KEY_FIELDS = (
    "listing_id",
    "route_family",
    "route_subroute",
    "series_index",
    "ds",
    "primary_metric_name",
)


def ledger_key(row):
    return tuple(row.get(field) for field in LEDGER_KEY_FIELDS)


def read_ledger_index(path):
    path = Path(path)
    if not path.exists():
        return {}
    index = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            key = ledger_key(row)
            existing = index.get(key)
            if existing is None or str(row.get("observed_at") or "") >= str(existing.get("observed_at") or ""):
                index[key] = row
    return index


def append_ledger_rows(path, rows):
    rows = list(rows or [])
    if not rows:
        return
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
    try:
        payload = "".join(json.dumps(row, separators=(",", ":"), ensure_ascii=False) + "\n" for row in rows)
        os.write(fd, payload.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)


def latest_ds_per(ledger_index, listing_id, route_subroute, series_index=0, max_ds=None):
    """Return the most recent date stored for (listing, route, series).

    max_ds: optional upper bound (date or ISO string) — only rows on or before
    this date are considered. Used by the planner to find the latest date within
    the older-tier boundary without bleeding into the daily tier.

    For repeated lookups against the same ledger_index, prefer
    build_latest_ds_index(ledger_index) once and use latest_ds_lookup(...) for
    O(1) reads.
    """
    if max_ds is not None and not isinstance(max_ds, date):
        max_ds = date.fromisoformat(str(max_ds))
    target_listing = str(listing_id)
    target_series = int(series_index)
    best = None
    for row in ledger_index.values():
        if str(row.get("listing_id")) != target_listing:
            continue
        if row.get("route_subroute") != route_subroute:
            continue
        if int(row.get("series_index") or 0) != target_series:
            continue
        ds = row.get("ds")
        if not ds:
            continue
        ds_date = date.fromisoformat(ds)
        if max_ds is not None and ds_date > max_ds:
            continue
        if best is None or ds_date > best:
            best = ds_date
    return best


_GRANULARITY_SPAN_DAYS = {
    "DAY": 1,
    "WEEK": 7,
    "MONTH": 30,
}


def build_latest_ds_index(ledger_index):
    """Bucket the ledger by (listing_id, route_subroute, series_index) → sorted
    list of date objects covered by each row.

    A row's `series_granularity` determines how many calendar days the row
    represents — DAY=1, WEEK=7, MONTH=30. Each covered date is added to the
    bucket so gap detection treats e.g. a weekly Monday row as covering the
    full Monday–Sunday range.

    O(n × avg_span) one-time scan; subsequent in-range lookups are O(log n).
    """
    from datetime import timedelta

    buckets = {}
    for row in ledger_index.values():
        ds = row.get("ds")
        if not ds:
            continue
        key = (
            str(row.get("listing_id")),
            row.get("route_subroute"),
            int(row.get("series_index") or 0),
        )
        try:
            ds_date = date.fromisoformat(ds)
        except (TypeError, ValueError):
            continue
        gran = (row.get("series_granularity") or "DAY").upper()
        span = _GRANULARITY_SPAN_DAYS.get(gran, 1)
        bucket = buckets.setdefault(key, set())
        for offset in range(span):
            bucket.add(ds_date + timedelta(days=offset))
    # Convert to sorted lists so binary search and bisect work.
    return {key: sorted(dates) for key, dates in buckets.items()}


def latest_ds_lookup(buckets, listing_id, route_subroute, series_index=0, max_ds=None):
    """O(log n) per-bucket lookup of the latest date ≤ max_ds (or unbounded).

    Use after build_latest_ds_index(ledger_index).
    """
    key = (str(listing_id), route_subroute, int(series_index))
    dates = buckets.get(key)
    if not dates:
        return None
    if max_ds is None:
        return dates[-1]
    if not isinstance(max_ds, date):
        max_ds = date.fromisoformat(str(max_ds))
    # Binary search for rightmost date ≤ max_ds
    lo, hi = 0, len(dates)
    while lo < hi:
        mid = (lo + hi) // 2
        if dates[mid] <= max_ds:
            lo = mid + 1
        else:
            hi = mid
    return dates[lo - 1] if lo > 0 else None
