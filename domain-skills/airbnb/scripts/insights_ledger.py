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
    """
    if max_ds is not None and not isinstance(max_ds, date):
        max_ds = date.fromisoformat(str(max_ds))
    best = None
    for row in ledger_index.values():
        if str(row.get("listing_id")) != str(listing_id):
            continue
        if row.get("route_subroute") != route_subroute:
            continue
        if int(row.get("series_index") or 0) != int(series_index):
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
