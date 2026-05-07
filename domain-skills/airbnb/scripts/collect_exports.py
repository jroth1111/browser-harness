"""Parse Airbnb host export files into normalized local collection artifacts.

This is export-first ingestion for surfaces where Airbnb provides downloadable
files. It never logs in and never scrapes UI; point it at a local export file or
directory that the user has already downloaded.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import os
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path


OUTPUT_PATH = Path("domain-skills/airbnb/.private-data/export-collections")
SESSION_PATH = Path("domain-skills/airbnb/.session-store/capability")


def _load_local_module(module_filename, module_name):
    path = Path("domain-skills/airbnb/scripts") / module_filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_integrity = _load_local_module("run_integrity.py", "airbnb_run_integrity")


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_key(value):
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def parse_money(value):
    text = str(value or "").strip()
    if not text:
        return None
    negative = text.startswith("(") and text.endswith(")")
    amount = re.sub(r"[^0-9.-]", "", text)
    if amount in {"", "-", "."}:
        return None
    parsed = round(float(amount), 2)
    return -parsed if negative else parsed


def first_value(row, names):
    normalized = {normalize_key(key): value for key, value in row.items()}
    for name in names:
        if normalize_key(name) in normalized and str(normalized[normalize_key(name)]).strip():
            return str(normalized[normalize_key(name)]).strip()
    return None


def parse_earnings_csv(text, *, observed_at, source_path=None, default_currency="AUD"):
    rows = []
    reader = csv.DictReader(str(text or "").splitlines())
    for index, raw in enumerate(reader, start=1):
        if not any(str(value or "").strip() for value in raw.values()):
            continue
        listing_id = first_value(raw, ["listing id", "listing_id", "room id"])
        reservation_id = first_value(raw, ["reservation id", "confirmation code", "booking id"])
        payout = parse_money(first_value(raw, ["payout", "paid out", "amount paid", "net earnings"]))
        gross = parse_money(first_value(raw, ["gross earnings", "gross", "total paid by guest", "amount"]))
        service_fee = parse_money(first_value(raw, ["host service fee", "service fee", "fees"]))
        currency = first_value(raw, ["currency"]) or default_currency
        rows.append({
            "earning_export_row_id": f"earnings:{Path(source_path or 'inline').name}:{index}",
            "observed_at": observed_at,
            "source_family": "host_export",
            "surface_class": "earnings_export",
            "auth_context": "downloaded_export_file",
            "source_path": str(source_path) if source_path else None,
            "listing_id": listing_id,
            "reservation_id": reservation_id,
            "transaction_date": first_value(raw, ["date", "transaction date", "payout date", "start date"]),
            "guest_name_present": bool(first_value(raw, ["guest", "guest name"])),
            "currency": currency.upper(),
            "gross_earnings": gross,
            "host_service_fee": service_fee,
            "payout_amount": payout,
            "export_row_number": index,
        })
    return rows


def parse_reservation_detail_text(text, *, observed_at, source_path=None):
    normalized = re.sub(r"\r\n?", "\n", str(text or ""))
    fields = {}
    for line in normalized.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = normalize_key(key)
        value = value.strip()
        if key and value:
            fields[key] = value
    reservation_id = (
        fields.get("reservation_id")
        or fields.get("confirmation_code")
        or fields.get("booking_id")
        or first_match(normalized, r"\b(?:HM|HMA)[A-Z0-9]{7,}\b")
    )
    return [{
        "reservation_export_row_id": f"reservation:{Path(source_path or 'inline').name}:{reservation_id or 'unknown'}",
        "observed_at": observed_at,
        "source_family": "host_export",
        "surface_class": "reservation_detail_export",
        "auth_context": "downloaded_export_file",
        "source_path": str(source_path) if source_path else None,
        "reservation_id": reservation_id,
        "listing_id": fields.get("listing_id"),
        "listing_name": fields.get("listing"),
        "guest_name_present": bool(fields.get("guest") or fields.get("guest_name")),
        "check_in_date": fields.get("check_in") or fields.get("checkin"),
        "check_out_date": fields.get("check_out") or fields.get("checkout"),
        "nights": integer_or_none(fields.get("nights")),
        "guest_count": integer_or_none(fields.get("guests")),
        "currency": (fields.get("currency") or "AUD").upper(),
        "total_payout": parse_money(fields.get("payout") or fields.get("total_payout")),
        "raw_field_keys": sorted(fields),
    }]


def first_match(text, pattern):
    match = re.search(pattern, text or "", re.I)
    return match.group(0) if match else None


def integer_or_none(value):
    match = re.search(r"\d+", str(value or ""))
    return int(match.group(0)) if match else None


def classify_export_entry(name):
    lowered = name.lower()
    if "reservation" in lowered or "booking" in lowered:
        return "reservations"
    if "earning" in lowered or "payout" in lowered or "transaction" in lowered:
        return "earnings"
    if "message" in lowered or "thread" in lowered:
        return "messages"
    if "profile" in lowered or "account" in lowered:
        return "profile"
    if "calendar" in lowered or lowered.endswith(".ics"):
        return "calendar"
    return "other"


def parse_personal_data_export_catalog(path, *, observed_at):
    path = Path(path)
    entries = []
    if path.is_dir():
        candidates = [item for item in path.rglob("*") if item.is_file()]
        for item in sorted(candidates):
            rel = item.relative_to(path).as_posix()
            entries.append(catalog_entry(rel, item.stat().st_size, observed_at, source_path=path))
    elif zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            for info in sorted(archive.infolist(), key=lambda row: row.filename):
                if info.is_dir():
                    continue
                entries.append(catalog_entry(info.filename, info.file_size, observed_at, source_path=path))
    else:
        entries.append(catalog_entry(path.name, path.stat().st_size, observed_at, source_path=path))
    return entries


def catalog_entry(name, size, observed_at, *, source_path):
    return {
        "catalog_entry_id": f"personal-data-export:{name}",
        "observed_at": observed_at,
        "source_family": "host_export",
        "surface_class": "personal_data_export_catalog",
        "auth_context": "downloaded_export_file",
        "source_path": str(source_path),
        "entry_path": name,
        "entry_size_bytes": int(size),
        "entry_category": classify_export_entry(name),
    }


def build_export_collection(kind, source, *, observed_at):
    source_path = Path(source)
    if kind == "earnings_csv":
        return "airbnb_earnings_export_row", parse_earnings_csv(source_path.read_text(encoding="utf-8"), observed_at=observed_at, source_path=source_path)
    if kind == "reservation_detail":
        return "airbnb_reservation_export_row", parse_reservation_detail_text(source_path.read_text(encoding="utf-8"), observed_at=observed_at, source_path=source_path)
    if kind == "personal_data_catalog":
        return "airbnb_personal_data_export_catalog_entry", parse_personal_data_export_catalog(source_path, observed_at=observed_at)
    raise ValueError("AIRBNB_EXPORT_KIND must be earnings_csv, reservation_detail, or personal_data_catalog")


def write_csv(path, rows):
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys = []
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def main():
    observed_at = utc_now()
    run_id = os.environ.get("AIRBNB_EXPORT_RUN_ID") or "airbnb-host-export-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    kind = os.environ.get("AIRBNB_EXPORT_KIND")
    source = os.environ.get("AIRBNB_EXPORT_SOURCE")
    if not kind:
        raise SystemExit("AIRBNB_EXPORT_KIND is required")
    if not source:
        raise SystemExit("AIRBNB_EXPORT_SOURCE is required")
    table, rows = build_export_collection(kind, source, observed_at=observed_at)

    OUTPUT_PATH.mkdir(parents=True, exist_ok=True)
    SESSION_PATH.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_PATH / f"{run_id}.json"
    csv_path = OUTPUT_PATH / f"{run_id}.csv"
    receipt_path = SESSION_PATH / f"{run_id}-receipt.json"
    warehouse_exports = _integrity.warehouse_manifest([
        {
            "table": table,
            "path": str(csv_path),
            "row_count": len(rows),
            "grain": next((key for key in rows[0] if key.endswith("_id")), "source_path + row_number") if rows else "source_path + row_number",
            "source_family": "host_export",
            "surface_class": f"{kind}_export",
            "auth_context": "downloaded_export_file",
        }
    ])
    last_good_guard = _integrity.last_good_guard(
        subject=f"{kind}_rows",
        current_count=len(rows),
        prior_positive_count=0,
        allow_empty=os.environ.get("AIRBNB_EXPORT_ALLOW_EMPTY") == "1",
    )
    output = _integrity.stamp_collection_contract(
        {
            "run_id": run_id,
            "observed_at": observed_at,
            "export_kind": kind,
            "source_path": str(source),
            "row_count": len(rows),
            "rows": rows,
        },
        source_family="host_export",
        surface_class=f"{kind}_export",
        auth_context="downloaded_export_file",
        collection_status=_integrity.collection_status(last_good_guard_record=last_good_guard),
        last_good_guard_record=last_good_guard,
        warehouse_exports=warehouse_exports,
    )
    _integrity.write_collection_json(json_path, output)
    write_csv(csv_path, rows)
    receipt = _integrity.stamp_collection_contract(
        {
            "run_id": run_id,
            "observed_at": observed_at,
            "export_kind": kind,
            "row_count": len(rows),
            "json_path": str(json_path),
            "csv_path": str(csv_path),
        },
        source_family="host_export",
        surface_class=f"{kind}_export",
        auth_context="downloaded_export_file",
        collection_status=output["collection_status"],
        last_good_guard_record=last_good_guard,
        warehouse_exports=warehouse_exports,
    )
    _integrity.write_receipt_json(receipt_path, receipt)
    print(json.dumps(receipt, indent=2, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    import sys
    if any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
        print((__doc__ or "").strip())
        raise SystemExit(0)
    main()
