"""Listing status/ID scoping helpers for Airbnb collectors."""

from __future__ import annotations


def normalize_status(value):
    return str(value or "").strip().upper()


def _split_csv(value):
    return [part.strip() for part in str(value or "").split(",") if part.strip()]


def parse_listing_scope(value=None, default="active"):
    """Parse a listing-scope selector.

    Supported forms:
    - active/default/blank: only ACTIVE listings
    - all/*/any: all records from the selected listing artifact
    - status:UNLISTED or statuses:ACTIVE,UNLISTED: selected statuses
    - ids:123,456: selected listing IDs
    - a bare comma list such as ACTIVE,UNLISTED: selected statuses
    """
    raw = str(value or default or "active").strip()
    lowered = raw.lower()
    if lowered in {"", "active", "default", "live"}:
        return {"mode": "statuses", "statuses": {"ACTIVE"}, "label": "active"}
    if lowered in {"all", "any", "*"}:
        return {"mode": "all", "statuses": None, "label": "all"}
    if lowered.startswith(("ids:", "id:")):
        ids = {part for part in _split_csv(raw.split(":", 1)[1])}
        return {"mode": "ids", "listing_ids": ids, "label": "ids:" + ",".join(sorted(ids))}
    if lowered.startswith(("statuses:", "status:")):
        statuses = {normalize_status(part) for part in _split_csv(raw.split(":", 1)[1])}
        return {"mode": "statuses", "statuses": statuses, "label": "statuses:" + ",".join(sorted(statuses))}
    statuses = {normalize_status(part) for part in _split_csv(raw)}
    return {"mode": "statuses", "statuses": statuses, "label": "statuses:" + ",".join(sorted(statuses))}


def select_listings(records, scope_value=None, default="active"):
    scope = parse_listing_scope(scope_value, default=default)
    records = list(records or [])
    if scope["mode"] == "all":
        selected = records
    elif scope["mode"] == "ids":
        ids = {str(value) for value in scope.get("listing_ids") or set()}
        selected = [record for record in records if str(record.get("listing_id")) in ids]
    else:
        statuses = set(scope.get("statuses") or set())
        selected = [record for record in records if normalize_status(record.get("status")) in statuses]
    return selected, scope


def status_counts(records):
    counts = {}
    for record in records or []:
        status = normalize_status(record.get("status")) or "UNKNOWN"
        counts[status] = counts.get(status, 0) + 1
    return counts
