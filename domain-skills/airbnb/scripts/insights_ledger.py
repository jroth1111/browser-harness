"""Cross-run ledger utilities for Airbnb Insights chart primitives."""

from __future__ import annotations

import json
import os
from datetime import date, timedelta
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


def safe_int(value, default=0):
    if isinstance(value, bool):
        return int(default)
    try:
        return int(value if value not in (None, "") else default)
    except (TypeError, ValueError):
        return int(default)


def optional_int(value):
    if value in (None, ""):
        return 0
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def read_ledger_index(path):
    path = Path(path)
    if not path.exists():
        return {}
    index = {}
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                if not line.endswith("\n"):
                    # A previous append may have been interrupted mid-row. Keep
                    # complete durable rows usable; append_ledger_rows truncates
                    # this tail before writing new rows.
                    continue
                raise ValueError(f"Invalid JSON in ledger {path} at line {line_number}") from error
            if not isinstance(row, dict):
                continue
            key = ledger_key(row)
            existing = index.get(key)
            if existing is None or str(row.get("observed_at") or "") >= str(existing.get("observed_at") or ""):
                index[key] = row
    return index


def write_all(fd, data):
    view = memoryview(data)
    written_total = 0
    while written_total < len(view):
        written = os.write(fd, view[written_total:])
        if written <= 0:
            raise OSError("os.write returned 0 while appending ledger rows")
        written_total += written


def truncate_trailing_partial_line(path):
    path = Path(path)
    if not path.exists() or path.stat().st_size == 0:
        return
    with path.open("rb+") as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        handle.seek(size - 1)
        if handle.read(1) == b"\n":
            return
        keep = 0
        position = size
        chunk_size = 8192
        while position > 0:
            read_size = min(chunk_size, position)
            position -= read_size
            handle.seek(position)
            chunk = handle.read(read_size)
            newline_at = chunk.rfind(b"\n")
            if newline_at >= 0:
                keep = position + newline_at + 1
                break
        handle.truncate(keep)


def append_ledger_rows(path, rows):
    rows = list(rows or [])
    if not rows:
        return
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    truncate_trailing_partial_line(path)
    fd = os.open(str(path), os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
    try:
        payload = "".join(json.dumps(row, separators=(",", ":"), ensure_ascii=False) + "\n" for row in rows)
        write_all(fd, payload.encode("utf-8"))
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
    target_series = optional_int(series_index)
    if target_series is None:
        return None
    best = None
    for row in ledger_index.values():
        if not isinstance(row, dict):
            continue
        if str(row.get("listing_id")) != target_listing:
            continue
        if row.get("route_subroute") != route_subroute:
            continue
        row_series = optional_int(row.get("series_index"))
        if row_series is None or row_series != target_series:
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

# Sentinel marker for chart windows that returned HTTP 200 but zero data
# points. Recorded in the ledger so the planner skips re-requesting them.
SENTINEL_GRANULARITY = "ATTEMPT_RANGE"
SENTINEL_PRIMARY_METRIC = "_attempt_sentinel"

# Daily-tier sentinels (ds within last SENTINEL_DAILY_HORIZON_DAYS) expire
# after SENTINEL_DAILY_EXPIRY_DAYS so we retry in case Airbnb backfills.
# Older-tier sentinels never expire because historical records are stable.
SENTINEL_DAILY_HORIZON_DAYS = 90
SENTINEL_DAILY_EXPIRY_DAYS = 7


def _sentinel_is_active(ds_date, observed_at_str, today, span_days=1):
    """Return True if this sentinel should still suppress re-planning.

    Tiered expiry:
    - Older tier (ds older than 90 days from today): never expires.
    - Daily tier (ds within last 90 days): expires after 7 days from observed_at.
    - Span overlap: if a sentinel starting in the older tier has a span that
      extends into the daily tier, apply daily-tier expiry rules instead of
      never-expire, so daily-tier dates can be retried after backfill.

    On malformed observed_at, return False (treat as expired) so we re-attempt
    rather than silently honoring an unverifiable cache entry.
    """
    age_days = (today - ds_date).days
    span_end_age = (today - (ds_date + timedelta(days=max(0, span_days - 1)))).days
    entirely_older = span_end_age > SENTINEL_DAILY_HORIZON_DAYS
    if age_days > SENTINEL_DAILY_HORIZON_DAYS and entirely_older:
        return True
    try:
        observed = date.fromisoformat(str(observed_at_str)[:10])
        return (today - observed).days <= SENTINEL_DAILY_EXPIRY_DAYS
    except (TypeError, ValueError):
        return False


def build_latest_ds_index(ledger_index, today=None, include_granularities=None, include_sentinels=True):
    """Bucket the ledger by (listing_id, route_subroute, series_index) → sorted
    list of date objects covered by each row.

    Row types handled:
    - Regular metric rows: granularity DAY/WEEK/MONTH expands ds over its span.
    - Attempt sentinels (series_granularity=ATTEMPT_RANGE): expand over
      _attempt_span_days. Subject to tiered expiry — daily-tier sentinels
      (ds within last 90 days) expire after 7 days; older-tier sentinels
      (ds > 90 days ago) never expire.

    include_granularities optionally restricts native metric rows to the named
    granularities while still allowing active attempt sentinels by default.

    O(n × avg_span) one-time scan; subsequent in-range lookups are O(log n).
    """
    if today is None:
        today = date.today()
    if include_granularities is not None:
        include_granularities = {str(granularity).upper() for granularity in include_granularities}

    buckets = {}
    for row in ledger_index.values():
        if not isinstance(row, dict):
            continue
        ds = row.get("ds")
        if not ds:
            continue
        row_series = optional_int(row.get("series_index"))
        if row_series is None:
            continue
        key = (
            str(row.get("listing_id")),
            row.get("route_subroute"),
            row_series,
        )
        try:
            ds_date = date.fromisoformat(ds)
        except (TypeError, ValueError):
            continue
        gran = (row.get("series_granularity") or "DAY").upper()
        if gran == SENTINEL_GRANULARITY:
            if not include_sentinels:
                continue
            span = safe_int(row.get("_attempt_span_days"), 1)
            if not _sentinel_is_active(ds_date, row.get("observed_at"), today, span_days=span):
                continue
        else:
            if include_granularities is not None and gran not in include_granularities:
                continue
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
