"""Collect Airbnb calendar export / iCal availability snapshots.

Role: collector (export). Reads a consented Airbnb iCal/export URL or local
`.ics` file and turns VEVENT ranges into daily `airbnb_calendar_snapshot` rows.

Requires:
    - `AIRBNB_ICAL_SOURCE` — HTTPS URL or local path to an `.ics` file.
    - `AIRBNB_ICAL_LISTING_ID` — listing ID the export belongs to.

Optional:
    - `AIRBNB_ICAL_RUN_ID`
    - `AIRBNB_ICAL_ALLOW_EMPTY=1` — allow an empty calendar even when the last
      successful export for this listing had events.
    - `AIRBNB_ICAL_INCLUDE_RAW_TEXT=1` — include raw event summary/description
      in the private JSON/CSV artifact. Receipts never include raw event text.

Outputs:
    - `.private-data/calendar-export-collections/<run_id>.json`
    - event and daily snapshot CSVs in the same directory
    - `.session-store/capability/<run_id>-receipt.json`
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen


OUTPUT_PATH = Path("domain-skills/airbnb/.private-data/calendar-export-collections")
SESSION_PATH = Path("domain-skills/airbnb/.session-store/capability")

BOOKING_CODE_RE = re.compile(r"\b[A-Z][A-Z0-9]{9}\b")


def _load_local_module(module_filename, module_name):
    path = Path("domain-skills/airbnb/scripts") / module_filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_surfaces = _load_local_module("surface_capabilities.py", "airbnb_surface_capabilities")
_integrity = _load_local_module("run_integrity.py", "airbnb_run_integrity")


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def redacted_source(source):
    if not source:
        return None
    parsed = urlsplit(source)
    if parsed.scheme in {"http", "https"}:
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "redacted_query=1" if parsed.query else "", ""))
    return str(source)


def read_ical_source(source):
    parsed = urlsplit(source)
    if parsed.scheme == "webcal":
        source = urlunsplit(("https", parsed.netloc, parsed.path, parsed.query, parsed.fragment))
        parsed = urlsplit(source)
    if parsed.scheme in {"http", "https"}:
        request = Request(
            source,
            headers={
                "Accept": "text/calendar,text/plain;q=0.9,*/*;q=0.5",
                "User-Agent": "browser-harness-airbnb-calendar-export/1",
            },
        )
        with urlopen(request, timeout=float(os.environ.get("AIRBNB_ICAL_FETCH_TIMEOUT_SEC", "20"))) as response:
            return response.read().decode("utf-8", errors="replace")
    return Path(source).read_text(encoding="utf-8")


def unfold_ical_lines(text):
    lines = str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    unfolded = []
    for line in lines:
        if not line:
            continue
        if line[:1] in {" ", "\t"} and unfolded:
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)
    return unfolded


def unescape_ical_value(value):
    return (
        str(value or "")
        .replace("\\n", "\n")
        .replace("\\N", "\n")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\\\", "\\")
        .strip()
    )


def split_property(line):
    if ":" not in line:
        return None, {}, ""
    left, value = line.split(":", 1)
    parts = left.split(";")
    name = parts[0].upper()
    params = {}
    for part in parts[1:]:
        if "=" in part:
            key, raw = part.split("=", 1)
            params[key.upper()] = raw
    return name, params, unescape_ical_value(value)


def parse_ical_events(text):
    events = []
    current = None
    for line in unfold_ical_lines(text):
        upper = line.upper()
        if upper == "BEGIN:VEVENT":
            current = {}
            continue
        if upper == "END:VEVENT":
            if current is not None:
                events.append(current)
            current = None
            continue
        if current is None:
            continue
        name, params, value = split_property(line)
        if not name:
            continue
        current.setdefault(name, []).append({"params": params, "value": value})
    return events


def first_prop(event, name):
    values = event.get(name.upper()) or []
    return values[0] if values else {"params": {}, "value": ""}


def parse_ical_date(prop):
    value = prop.get("value") or ""
    params = prop.get("params") or {}
    if params.get("VALUE", "").upper() == "DATE" or re.fullmatch(r"\d{8}", value):
        return date.fromisoformat(f"{value[0:4]}-{value[4:6]}-{value[6:8]}")
    if re.fullmatch(r"\d{8}T\d{6}Z?", value):
        return date.fromisoformat(f"{value[0:4]}-{value[4:6]}-{value[6:8]}")
    return date.fromisoformat(value[:10])


def uid_hash(uid):
    return hashlib.sha256(str(uid or "").encode("utf-8")).hexdigest()[:16]


def booking_code(summary, description):
    match = BOOKING_CODE_RE.search("\n".join([summary or "", description or ""]))
    return match.group(0) if match else None


def classify_event(summary, description, event_status):
    text = " ".join([summary or "", description or "", event_status or ""]).lower()
    if "cancelled" in text or event_status.upper() == "CANCELLED":
        return "cancelled", "ical_cancelled"
    if any(token in text for token in ("blocked", "not available", "unavailable")):
        return "blocked", "ical_blocked"
    if any(token in text for token in ("reserved", "reservation", "booking")):
        return "booked", "ical_reserved"
    return "busy", "ical_busy"


def normalize_event(event, listing_id, observed_at, source, include_raw_text=False):
    uid = first_prop(event, "UID")["value"]
    summary = first_prop(event, "SUMMARY")["value"]
    description = first_prop(event, "DESCRIPTION")["value"]
    event_status = first_prop(event, "STATUS")["value"]
    start = parse_ical_date(first_prop(event, "DTSTART"))
    end_prop = first_prop(event, "DTEND")
    end = parse_ical_date(end_prop) if end_prop.get("value") else start + timedelta(days=1)
    if end <= start:
        end = start + timedelta(days=1)
    status, status_reason = classify_event(summary, description, event_status)
    record = {
        "event_uid_hash": uid_hash(uid),
        "listing_id": str(listing_id or ""),
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "nights": (end - start).days,
        "status": status,
        "status_reason": status_reason,
        "reservation_id": booking_code(summary, description),
        "summary_kind": "reserved" if "reserved" in summary.lower() else ("blocked" if "block" in summary.lower() else "other"),
        "source_family": "calendar_export",
        "surface_class": "calendar_export",
        "auth_context": "calendar_export_url_or_file",
        "source_url": redacted_source(source),
        "observed_at": observed_at,
    }
    if include_raw_text:
        record["raw_summary"] = summary
        record["raw_description"] = description
    return record


def event_to_snapshots(event):
    start = date.fromisoformat(event["start_date"])
    end = date.fromisoformat(event["end_date"])
    rows = []
    current = start
    while current < end:
        rows.append({
            "listing_id": event["listing_id"],
            "calendar_date": current.isoformat(),
            "status": event["status"],
            "status_reason": event["status_reason"],
            "reservation_id": event["reservation_id"],
            "source_event_uid_hash": event["event_uid_hash"],
            "source_family": event["source_family"],
            "surface_class": event["surface_class"],
            "auth_context": event["auth_context"],
            "observed_at": event["observed_at"],
        })
        current += timedelta(days=1)
    return rows


def build_collection(text, *, listing_id, observed_at, source, include_raw_text=False):
    events = [
        normalize_event(event, listing_id, observed_at, source, include_raw_text=include_raw_text)
        for event in parse_ical_events(text)
    ]
    snapshots = [row for event in events for row in event_to_snapshots(event)]
    return events, snapshots


def latest_prior_event_count(listing_id):
    latest = None
    for path in sorted(OUTPUT_PATH.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if str(payload.get("listing_id") or "") != str(listing_id or ""):
            continue
        if latest is None or str(payload.get("observed_at") or "") > str(latest.get("observed_at") or ""):
            latest = payload
    return int((latest or {}).get("event_count") or 0)


def write_csv(path, rows, fieldnames):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main():
    observed_at = utc_now()
    run_id = os.environ.get("AIRBNB_ICAL_RUN_ID") or "airbnb-calendar-export-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    source = os.environ.get("AIRBNB_ICAL_SOURCE")
    listing_id = os.environ.get("AIRBNB_ICAL_LISTING_ID")
    if not source:
        raise SystemExit("AIRBNB_ICAL_SOURCE is required")
    if not listing_id:
        raise SystemExit("AIRBNB_ICAL_LISTING_ID is required")
    include_raw_text = os.environ.get("AIRBNB_ICAL_INCLUDE_RAW_TEXT") == "1"
    allow_empty = os.environ.get("AIRBNB_ICAL_ALLOW_EMPTY") == "1"

    text = read_ical_source(source)
    events, snapshots = build_collection(
        text,
        listing_id=listing_id,
        observed_at=observed_at,
        source=source,
        include_raw_text=include_raw_text,
    )
    prior_event_count = latest_prior_event_count(listing_id)
    last_good_guard = _integrity.last_good_guard(
        subject="calendar_export_events",
        current_count=len(events),
        prior_positive_count=prior_event_count,
        allow_empty=allow_empty,
    )
    empty_guard = {
        **last_good_guard,
        "prior_event_count": prior_event_count,
        "current_event_count": len(events),
        "refused_empty_after_nonempty": last_good_guard["quarantined_empty_after_prior_nonempty"],
    }

    OUTPUT_PATH.mkdir(parents=True, exist_ok=True)
    SESSION_PATH.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_PATH / f"{run_id}.json"
    events_csv = OUTPUT_PATH / f"{run_id}-events.csv"
    snapshots_csv = OUTPUT_PATH / f"{run_id}-daily-snapshots.csv"
    receipt_path = SESSION_PATH / f"{run_id}-receipt.json"

    capability = _surfaces.capability_record(
        "calendar_export",
        observed_at=observed_at,
        auth_context="calendar_export_url_or_file",
        source_url=source,
        resource_urls=[source],
        status="capability_observed" if events else "capability_not_observed",
        evidence={"event_count": len(events), "snapshot_count": len(snapshots), "empty_feed_guard": empty_guard},
    )
    warehouse_exports = _integrity.warehouse_manifest([
        {
            "table": "airbnb_calendar_export_event",
            "path": str(events_csv),
            "row_count": len(events),
            "grain": "event_uid_hash",
            "source_family": "calendar_export",
            "surface_class": "calendar_export",
            "auth_context": "calendar_export_url_or_file",
        },
        {
            "table": "airbnb_calendar_snapshot",
            "path": str(snapshots_csv),
            "row_count": len(snapshots),
            "grain": "listing_id + calendar_date",
            "source_family": "calendar_export",
            "surface_class": "calendar_export",
            "auth_context": "calendar_export_url_or_file",
        },
    ])
    output = _integrity.stamp_collection_contract({
        "run_id": run_id,
        "observed_at": observed_at,
        "listing_id": str(listing_id),
        "source_url": redacted_source(source),
        "collection_status": (
            "refused_empty_feed_after_prior_nonempty"
            if empty_guard["refused_empty_after_nonempty"]
            else _integrity.collection_status(last_good_guard_record=last_good_guard)
        ),
        "event_count": len(events),
        "snapshot_count": len(snapshots),
        "empty_feed_guard": empty_guard,
        "surface_capabilities": [capability],
        "events": events,
        "daily_snapshots": snapshots,
    },
        source_family="calendar_export",
        surface_class="calendar_export",
        auth_context="calendar_export_url_or_file",
        collection_status=(
            "refused_empty_feed_after_prior_nonempty"
            if empty_guard["refused_empty_after_nonempty"]
            else _integrity.collection_status(last_good_guard_record=last_good_guard)
        ),
        last_good_guard_record=last_good_guard,
        warehouse_exports=warehouse_exports,
    )

    if empty_guard["refused_empty_after_nonempty"]:
        receipt = _integrity.stamp_collection_contract({
            "run_id": run_id,
            "observed_at": observed_at,
            "status": "refused_empty_feed_after_prior_nonempty",
            "event_count": len(events),
            "snapshot_count": len(snapshots),
            "empty_feed_guard": empty_guard,
            "json_path": None,
        },
            source_family="calendar_export",
            surface_class="calendar_export",
            auth_context="calendar_export_url_or_file",
            collection_status="refused_empty_feed_after_prior_nonempty",
            last_good_guard_record=last_good_guard,
            warehouse_exports=[],
        )
        _integrity.write_receipt_json(receipt_path, receipt)
        print(json.dumps(receipt, indent=2, ensure_ascii=False), flush=True)
        raise SystemExit(2)

    _integrity.write_collection_json(json_path, output)
    write_csv(
        events_csv,
        events,
        [
            "event_uid_hash",
            "listing_id",
            "start_date",
            "end_date",
            "nights",
            "status",
            "status_reason",
            "reservation_id",
            "summary_kind",
            "source_family",
            "surface_class",
            "auth_context",
            "source_url",
            "observed_at",
            "raw_summary",
            "raw_description",
        ],
    )
    write_csv(
        snapshots_csv,
        snapshots,
        [
            "listing_id",
            "calendar_date",
            "status",
            "status_reason",
            "reservation_id",
            "source_event_uid_hash",
            "source_family",
            "surface_class",
            "auth_context",
            "observed_at",
        ],
    )
    receipt = _integrity.stamp_collection_contract({
        "run_id": run_id,
        "observed_at": observed_at,
        "status": "ok",
        "event_count": len(events),
        "snapshot_count": len(snapshots),
        "empty_feed_guard": empty_guard,
        "json_path": str(json_path),
        "events_csv": str(events_csv),
        "snapshots_csv": str(snapshots_csv),
        "surface_capabilities": [capability],
    },
        source_family="calendar_export",
        surface_class="calendar_export",
        auth_context="calendar_export_url_or_file",
        collection_status=output["collection_status"],
        last_good_guard_record=last_good_guard,
        warehouse_exports=warehouse_exports,
    )
    _integrity.write_receipt_json(receipt_path, receipt)
    print(json.dumps(receipt, indent=2, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
