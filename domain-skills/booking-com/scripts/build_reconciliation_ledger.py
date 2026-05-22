#!/usr/bin/env python3
"""Build a source-hashed Booking.com booking/finance/payout ledger.

The script intentionally keeps provenance noisy and claims conservative:
Booking.com payout pages often expose transfer summaries without the expanded
booking membership rows. In that case rows are linked only as period candidates
and the reconciliation status records that direct transfer membership is still
unproven.
"""

from __future__ import annotations

import csv
import hashlib
import html
import json
import re
import sqlite3
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

try:
    import xlrd  # type: ignore
except ImportError as exc:  # pragma: no cover - exercised by CLI users.
    raise SystemExit(
        "Missing dependency: xlrd. Run with `uv run --with xlrd python "
        "domain-skills/booking-com/scripts/build_reconciliation_ledger.py <export-root>`."
    ) from exc


SCRIPT_JSON_RE = re.compile(
    r"<script[^>]*type=[\"']application/json[\"'][^>]*>(.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)
TAX_LEVY_RE = re.compile(r"(gst|tax|vat|levy|levies|fee|charge)", re.IGNORECASE)
MONEY_RE = re.compile(r"(-?\d[\d,]*\.\d{2}|-?\d[\d,]*)")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def decimal_text(value: Any) -> str:
    if value in (None, ""):
        return ""
    try:
        return str(Decimal(str(value)).quantize(Decimal("0.01")))
    except (InvalidOperation, ValueError):
        return clean_text(value)


def decimal_value(value: Any) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def money_decimal(value: Any) -> Decimal:
    text = clean_text(value).replace("\u00a0", " ")
    if not text:
        return Decimal("0")
    match = MONEY_RE.search(text)
    if not match:
        return Decimal("0")
    try:
        return Decimal(match.group(1).replace(",", ""))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def money_sum_text(rows: list[dict[str, Any]], key: str) -> str:
    total = sum((money_decimal(row.get(key)) for row in rows), Decimal("0"))
    return str(total.quantize(Decimal("0.01")))


def has_nonzero_money(rows: list[dict[str, Any]], key: str) -> bool:
    return any(money_decimal(row.get(key)) != 0 for row in rows)


def iso_date(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = clean_text(value)
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    return text


def parse_period_key_from_path(path: Path) -> str:
    match = re.search(r"period_(\d{4}-\d{2})", path.name)
    return match.group(1) if match else ""


def classify_source(path: Path, root: Path) -> str:
    rel = path.relative_to(root).as_posix()
    if rel.startswith("reservation_exports/") and path.suffix.lower() == ".xls":
        return "reservation_export_xls"
    if "/statements/" in rel and path.suffix.lower() == ".html":
        return "finance_statement_html"
    if "/finance_surfaces/" in rel and path.suffix.lower() == ".html":
        return "finance_surface_html"
    if path.suffix.lower() == ".pdf":
        return "invoice_pdf"
    if path.suffix.lower() == ".tsv":
        return "manifest_tsv"
    if path.suffix.lower() == ".json":
        return "receipt_json"
    return "source"


def find_source_files(root: Path) -> list[Path]:
    suffixes = {".xls", ".html", ".pdf", ".tsv", ".json", ".csv"}
    out_dir = root / "reconciliation_ledger"
    files = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if out_dir in path.parents:
            continue
        if path.suffix.lower() in suffixes:
            files.append(path)
    return sorted(files)


def read_tsv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def parse_reservation_exports(root: Path, source_hashes: dict[str, str]) -> list[dict[str, Any]]:
    exports_dir = root / "reservation_exports" / "booking_date_monthly"
    rows: list[dict[str, Any]] = []
    if not exports_dir.exists():
        return rows

    for path in sorted(exports_dir.glob("Reservations_BOOKING_*.xls")):
        rel = path.relative_to(root).as_posix()
        book = xlrd.open_workbook(path.as_posix())
        sheet = book.sheet_by_index(0)
        if sheet.nrows < 2:
            continue
        headers = [clean_text(sheet.cell_value(0, col)) for col in range(sheet.ncols)]
        for row_idx in range(1, sheet.nrows):
            raw = {headers[col]: sheet.cell_value(row_idx, col) for col in range(sheet.ncols)}
            booking_number = clean_text(raw.get("Reservation Number"))
            if not booking_number:
                continue
            record = {
                "booking_number": booking_number,
                "property_name": clean_text(raw.get("Property Name")),
                "property_id": "",
                "location": clean_text(raw.get("Location")).replace("\r\n", "\n"),
                "guest_name": clean_text(raw.get("Booker Name")),
                "genius_booker": clean_text(raw.get("Genius Booker")),
                "check_in": iso_date(raw.get("Arrival")),
                "check_out": iso_date(raw.get("Departure")),
                "booked_on": iso_date(raw.get("Booked on")),
                "status": clean_text(raw.get("Status")),
                "export_total_payment": decimal_text(raw.get("Total Payment")),
                "commission_export": decimal_text(raw.get("Commission")),
                "currency": clean_text(raw.get("Currency")),
                "source_file": rel,
                "source_sha256": source_hashes.get(rel, ""),
                "source_row": row_idx + 1,
            }
            rows.append(record)
    return rows


def json_payloads_from_html(path: Path) -> list[dict[str, Any]]:
    text = path.read_text("utf-8", errors="ignore")
    payloads = []
    for match in SCRIPT_JSON_RE.finditer(text):
        raw = html.unescape(match.group(1)).strip()
        if not raw:
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            payloads.append(value)
    return payloads


def collect_tax_levy_fields(value: Any, prefix: str = "") -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if TAX_LEVY_RE.search(str(key)) and not isinstance(child, (dict, list)):
                found.append({"path": path, "value": child})
            found.extend(collect_tax_levy_fields(child, path))
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            found.extend(collect_tax_levy_fields(child, f"{prefix}[{idx}]"))
    return found


def document_details_from_payload(payload: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    vuex = payload.get("vuex")
    if not isinstance(vuex, dict):
        return []
    details = vuex.get("DocumentDetails")
    if not isinstance(details, dict):
        return []
    docs = []
    for key in ("documentDetails", "originalDocumentDetails"):
        value = details.get(key)
        if isinstance(value, dict) and value:
            docs.append((key, value))
    return docs


def parse_finance_items(root: Path, source_hashes: dict[str, str]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    paths = sorted((root / "properties").glob("*/statements/*.html"))
    paths += sorted((root / "properties").glob("*/finance_surfaces/*.html"))
    seen_rows: set[str] = set()

    for path in paths:
        rel = path.relative_to(root).as_posix()
        parts = path.relative_to(root).parts
        property_id = parts[1] if len(parts) > 2 and parts[0] == "properties" else ""
        for payload in json_payloads_from_html(path):
            for doc_slot, doc in document_details_from_payload(payload):
                doc_id = clean_text(doc.get("id") or doc.get("documentId"))
                doc_external_id = clean_text(doc.get("externalId") or doc.get("external_id"))
                doc_type = clean_text(doc.get("type"))
                currency = clean_text(doc.get("currency"))
                invoice_date = iso_date(doc.get("invoiceDate") or doc.get("date"))
                period = clean_text(doc.get("period")) or parse_period_key_from_path(path)
                doc_tax_fields = collect_tax_levy_fields(doc)

                for item_idx, item in enumerate(doc.get("documentDetailsItems") or []):
                    item_booking = clean_text(item.get("bookingNumber") or item.get("reservationNumber"))
                    room_reservations = item.get("roomReservations") or []
                    if not room_reservations:
                        row = {
                            "property_id": property_id,
                            "booking_number": item_booking,
                            "guest_name": clean_text(item.get("guestName")),
                            "check_in": "",
                            "check_out": "",
                            "status": clean_text(item.get("status")),
                            "document_id": doc_id,
                            "document_external_id": doc_external_id,
                            "document_type": doc_type,
                            "document_slot": doc_slot,
                            "invoice_date": invoice_date,
                            "period": period,
                            "currency": currency,
                            "product_code": clean_text(item.get("productCode")),
                            "order_item_id": clean_text(item.get("orderItemId")),
                            "room_nights": clean_text(item.get("roomNights")),
                            "service_amount": decimal_text(item.get("serviceAmount")),
                            "final_service_amount": decimal_text(item.get("finalServiceAmount")),
                            "commission_statement": decimal_text(item.get("amount")),
                            "percent_applied": clean_text(item.get("percentApplied")),
                            "payment_charges": decimal_text(item.get("paymentCharges")),
                            "commission_discount": decimal_text(item.get("commissionDiscount")),
                            "tax_levy_fields_json": stable_json(doc_tax_fields + collect_tax_levy_fields(item)),
                            "source_file": rel,
                            "source_sha256": source_hashes.get(rel, ""),
                            "source_item_index": item_idx,
                            "source_room_index": "",
                        }
                        key = stable_json(row)
                        if key not in seen_rows:
                            seen_rows.add(key)
                            items.append(row)
                        continue

                    for room_idx, room in enumerate(room_reservations):
                        stay = room.get("stayPeriod") or {}
                        row = {
                            "property_id": property_id,
                            "booking_number": clean_text(
                                room.get("bookingNumber")
                                or item_booking
                                or item.get("bookingNumber")
                            ),
                            "guest_name": clean_text(room.get("guestName") or item.get("guestName")),
                            "check_in": iso_date(stay.get("dateFrom") or room.get("dateFrom")),
                            "check_out": iso_date(stay.get("dateUntil") or room.get("dateUntil")),
                            "status": clean_text(room.get("status") or item.get("status")),
                            "document_id": doc_id,
                            "document_external_id": doc_external_id,
                            "document_type": doc_type,
                            "document_slot": doc_slot,
                            "invoice_date": invoice_date,
                            "period": period,
                            "currency": currency,
                            "product_code": clean_text(room.get("productCode") or item.get("productCode")),
                            "order_item_id": clean_text(room.get("orderItemId") or item.get("orderItemId")),
                            "room_nights": clean_text(room.get("roomNights")),
                            "service_amount": decimal_text(room.get("serviceAmount")),
                            "final_service_amount": decimal_text(room.get("finalServiceAmount")),
                            "commission_statement": decimal_text(room.get("amount")),
                            "percent_applied": clean_text(room.get("percentApplied")),
                            "payment_charges": decimal_text(room.get("paymentCharges")),
                            "commission_discount": decimal_text(room.get("commissionDiscount")),
                            "tax_levy_fields_json": stable_json(doc_tax_fields + collect_tax_levy_fields(item) + collect_tax_levy_fields(room)),
                            "source_file": rel,
                            "source_sha256": source_hashes.get(rel, ""),
                            "source_item_index": item_idx,
                            "source_room_index": room_idx,
                        }
                        key = stable_json(row)
                        if key not in seen_rows:
                            seen_rows.add(key)
                            items.append(row)
    return items


def parse_amount_dict(value: Any) -> tuple[str, str]:
    if isinstance(value, dict):
        return decimal_text(value.get("amount")), clean_text(value.get("currency"))
    return decimal_text(value), ""


def amount_formatted(value: Any) -> str:
    if isinstance(value, dict):
        return clean_text(value.get("amountFormatted")) or decimal_text(value.get("amount"))
    return decimal_text(value)


def parse_payouts(root: Path, source_hashes: dict[str, str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    payouts: list[dict[str, Any]] = []
    payout_links: list[dict[str, Any]] = []
    payment_cost_rules: list[dict[str, Any]] = []
    seen_payouts: set[tuple[str, str, str]] = set()

    def add_payout(row: dict[str, Any]) -> None:
        key = (row.get("property_id", ""), row.get("payout_uuid", ""), row.get("source_file", ""))
        if not row.get("payout_uuid") or key in seen_payouts:
            return
        seen_payouts.add(key)
        payouts.append(row)

    for path in sorted((root / "properties").glob("*/finance_surfaces/payouts.html")):
        rel = path.relative_to(root).as_posix()
        parts = path.relative_to(root).parts
        property_id_from_path = parts[1] if len(parts) > 2 and parts[0] == "properties" else ""
        for payload in json_payloads_from_html(path):
            vuex = payload.get("vuex")
            state = vuex.get("Payouts") if isinstance(vuex, dict) else None
            if not isinstance(state, dict):
                continue

            for rule_idx, rule in enumerate(state.get("paymentCosts") or []):
                payment_cost_rules.append(
                    {
                        "property_id": property_id_from_path,
                        "active_from": clean_text(rule.get("activeFrom")),
                        "active_until": clean_text(rule.get("activeUntil")),
                        "percentage": clean_text(rule.get("percentage")),
                        "source_file": rel,
                        "source_sha256": source_hashes.get(rel, ""),
                        "source_rule_index": rule_idx,
                    }
                )

            for month_idx, month in enumerate(state.get("months") or []):
                for payout_idx, payout in enumerate(month.get("payouts") or []):
                    amount, currency = parse_amount_dict(payout.get("amount"))
                    source_amount, source_currency = parse_amount_dict(payout.get("sourceAmount"))
                    row = {
                        "property_id": clean_text(payout.get("assetId")) or property_id_from_path,
                        "payout_uuid": clean_text(payout.get("uuid")),
                        "transfer_reference": clean_text(payout.get("transferReference")),
                        "transfer_status": clean_text(payout.get("transferStatusDescription")),
                        "transfer_issued_date": iso_date(payout.get("transferIssuedDate")),
                        "created": clean_text(payout.get("created")),
                        "date_from": iso_date(payout.get("dateFrom")),
                        "date_until": iso_date(payout.get("dateUntil")),
                        "amount": amount,
                        "currency": currency,
                        "source_amount": source_amount,
                        "source_currency": source_currency,
                        "method": clean_text(payout.get("method")),
                        "is_payment_cost": clean_text(payout.get("isPaymentCost")),
                        "is_post_chargeable": clean_text(payout.get("isPostChargeable")),
                        "source_file": rel,
                        "source_sha256": source_hashes.get(rel, ""),
                        "source_month_index": month_idx,
                        "source_payout_index": payout_idx,
                    }
                    add_payout(row)

            reservations = state.get("reservations")
            if isinstance(reservations, dict):
                iterable = reservations.items()
            elif isinstance(reservations, list):
                iterable = enumerate(reservations)
            else:
                iterable = []
            for key, value in iterable:
                values = value if isinstance(value, list) else [value]
                for idx, reservation in enumerate(values):
                    if not isinstance(reservation, dict):
                        continue
                    booking_number = clean_text(
                        reservation.get("bookingNumber")
                        or reservation.get("reservationNumber")
                        or reservation.get("reservation_id")
                    )
                    payout_uuid = clean_text(
                        reservation.get("payoutUuid")
                        or reservation.get("uuid")
                        or reservation.get("payout_uuid")
                        or key
                    )
                    if booking_number or payout_uuid:
                        payout_links.append(
                            {
                                "property_id": property_id_from_path,
                                "payout_uuid": payout_uuid,
                                "booking_number": booking_number,
                                "raw_key": clean_text(key),
                                "raw_json": stable_json(reservation),
                                "source_file": rel,
                                "source_sha256": source_hashes.get(rel, ""),
                                "source_link_index": idx,
                            }
                        )

    harness_history_root = root / "browser_harness_payout_downloads" / "graphql_payout_history"
    for path in sorted(harness_history_root.glob("*/*.json")):
        rel = path.relative_to(root).as_posix()
        property_id_from_path = path.parent.name
        try:
            payload = json.loads(path.read_text("utf-8"))
        except json.JSONDecodeError:
            continue
        response = payload.get("response") if isinstance(payload, dict) else None
        history = (((response or {}).get("data") or {}).get("payoutHistory") or {})
        for month_idx, month in enumerate(history.get("payoutHistoryMonths") or []):
            for payout_idx, payout in enumerate(month.get("payouts") or []):
                amount, currency = parse_amount_dict(payout.get("amount"))
                source_amount, source_currency = parse_amount_dict(payout.get("sourceAmount"))
                row = {
                    "property_id": property_id_from_path,
                    "payout_uuid": clean_text(payout.get("uuid")),
                    "transfer_reference": clean_text(payout.get("transferReference")),
                    "transfer_status": clean_text(payout.get("transferStatusDescription") or payout.get("withdrawStatusDescription")),
                    "transfer_issued_date": iso_date(payout.get("transferIssuedDatetime")),
                    "created": clean_text(payout.get("created")),
                    "date_from": iso_date(payout.get("dateFrom")),
                    "date_until": iso_date(payout.get("dateUntil")),
                    "amount": amount,
                    "currency": currency,
                    "source_amount": source_amount,
                    "source_currency": source_currency,
                    "method": "browser_harness_graphql",
                    "is_payment_cost": "",
                    "is_post_chargeable": "",
                    "source_file": rel,
                    "source_sha256": source_hashes.get(rel, ""),
                    "source_month_index": month_idx,
                    "source_payout_index": payout_idx,
                }
                add_payout(row)

    return payouts, payout_links, payment_cost_rules


def parse_payout_detail_rows(root: Path, source_hashes: dict[str, str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_memberships: set[tuple[str, str]] = set()
    rows_by_membership: dict[tuple[str, str], dict[str, Any]] = {}

    harness_detail_root = root / "browser_harness_payout_downloads" / "graphql_payout_detail"
    for path in sorted(harness_detail_root.glob("*/*/*.json")):
        rel = path.relative_to(root).as_posix()
        parts = path.relative_to(harness_detail_root).parts
        property_id = parts[0] if len(parts) >= 3 else ""
        year = parts[1] if len(parts) >= 3 else ""
        payout_uuid = path.stem
        try:
            payload = json.loads(path.read_text("utf-8"))
        except json.JSONDecodeError:
            continue
        if payload.get("status") != 200:
            continue
        payout_history_row = payload.get("payout") if isinstance(payload.get("payout"), dict) else {}
        payout = (((payload.get("response") or {}).get("data") or {}).get("payout") or {})
        if not isinstance(payout, dict):
            continue
        for idx, reservation in enumerate(payout.get("reservations") or [], start=1):
            if not isinstance(reservation, dict):
                continue
            booking_number = clean_text(reservation.get("id") or reservation.get("documentNumber"))
            if not booking_number:
                continue
            seen_memberships.add((booking_number, payout_uuid))
            row = {
                "type": clean_text(reservation.get("releaseRequestTypeTranslated") or reservation.get("releaseRequestType")),
                "booking_reference_number": booking_number,
                "booking_number": booking_number,
                "check_in": iso_date(reservation.get("checkinDate")),
                "checkout": iso_date(reservation.get("checkoutDate")),
                "guest_name": clean_text(reservation.get("bookerName")),
                "reservation_status": "",
                "currency": clean_text((reservation.get("reservationAmount") or {}).get("currency")),
                "payment_status": "",
                "amount": amount_formatted(reservation.get("reservationAmount")),
                "commission": amount_formatted(reservation.get("commissionAmount")),
                "payments_service_fee": amount_formatted(reservation.get("costOfPaymentsAmount")),
                "vat": amount_formatted(reservation.get("vatAmount")),
                "short_stay_levy": amount_formatted(reservation.get("cityTaxAmount")),
                "withheld_taxes": amount_formatted(reservation.get("withheldTaxes")),
                "net": amount_formatted(reservation.get("netAmount")),
                "payout_date": iso_date(payout_history_row.get("transferIssuedDatetime")),
                "payout_id": clean_text(payout_history_row.get("transferReference")),
                "payout_uuid": payout_uuid,
                "transfer_reference": clean_text(payout_history_row.get("transferReference")),
                "period_filter": f"BROWSER_HARNESS_GRAPHQL_{year}",
                "source_file": rel,
                "source_sha256": source_hashes.get(rel, ""),
                "source_row": idx,
            }
            rows.append(row)
            rows_by_membership[(booking_number, payout_uuid)] = row

    path = root / "payout_detail_captures" / "live_payout_booking_rows.csv"
    if path.exists():
        rel = path.relative_to(root).as_posix()
        with path.open("r", encoding="utf-8", newline="") as fh:
            for idx, row in enumerate(csv.DictReader(fh), start=2):
                normalized = {key: clean_text(value) for key, value in row.items()}
                booking_number = normalized.get("booking_reference_number", "")
                payout_uuid = normalized.get("payout_uuid", "")
                if not booking_number:
                    continue
                existing = rows_by_membership.get((booking_number, payout_uuid))
                if existing:
                    if money_decimal(existing.get("short_stay_levy")) == 0 and money_decimal(normalized.get("short_stay_levy")) != 0:
                        existing["short_stay_levy"] = normalized.get("short_stay_levy", "")
                        existing["source_file"] = ";".join(filter(None, [existing.get("source_file", ""), rel]))
                        existing["source_sha256"] = ";".join(filter(None, [existing.get("source_sha256", ""), source_hashes.get(rel, "")]))
                    continue
                normalized.update(
                    {
                        "booking_number": booking_number,
                        "source_file": rel,
                        "source_sha256": source_hashes.get(rel, ""),
                        "source_row": idx,
                    }
                )
                rows.append(normalized)
                rows_by_membership[(booking_number, payout_uuid)] = normalized
    return rows


def parse_payout_csv_items(root: Path, source_hashes: dict[str, str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    csv_root = root / "browser_harness_payout_downloads" / "payout_csv"
    for path in sorted(csv_root.glob("*/*/*.csv")):
        rel = path.relative_to(root).as_posix()
        parts = path.relative_to(csv_root).parts
        property_id = parts[0] if len(parts) >= 3 else ""
        payout_year = parts[1] if len(parts) >= 3 else ""
        payout_uuid = path.stem
        with path.open("r", encoding="utf-8", newline="") as fh:
            for idx, row in enumerate(csv.DictReader(fh), start=2):
                item_type = clean_text(row.get("Type"))
                reference_number = clean_text(row.get("Reference number"))
                if not item_type and not reference_number:
                    continue
                rows.append(
                    {
                        "property_id": property_id,
                        "payout_year": payout_year,
                        "payout_uuid": payout_uuid,
                        "item_type": item_type,
                        "is_booking_membership": "true" if item_type == "Reservation" else "false",
                        "reference_number": reference_number,
                        "check_in": iso_date(row.get("Check-in")),
                        "checkout": iso_date(row.get("Checkout")),
                        "guest_name": clean_text(row.get("Guest name")),
                        "reservation_status": clean_text(row.get("Reservation status")),
                        "currency": clean_text(row.get("Currency")),
                        "payment_status": clean_text(row.get("Payment status")),
                        "amount": decimal_text(row.get("Amount")),
                        "commission": decimal_text(row.get("Commission")),
                        "payments_service_fee": decimal_text(row.get("Payments Service Fee")),
                        "vat": decimal_text(row.get("VAT for online platform services")),
                        "net": decimal_text(row.get("Net")),
                        "payout_date": iso_date(row.get("Payout date")),
                        "payout_id": clean_text(row.get("Payout ID")),
                        "source_file": rel,
                        "source_sha256": source_hashes.get(rel, ""),
                        "source_row": idx,
                    }
                )
    return rows


def remaining_transfer_gaps(reconciliation: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for row in reconciliation:
        status = row.get("transfer_link_status", "")
        if status.startswith("direct_booking_membership"):
            continue
        if status == "candidate_only_property_and_stay_period_overlap":
            reason = "one_period_overlap_but_no_booking_membership_in_payout_sources"
        elif status == "ambiguous_candidate_property_and_stay_period_overlap":
            reason = "multiple_period_overlaps_but_no_booking_membership_in_payout_sources"
        else:
            reason = "no_booking_membership_and_no_period_overlap_in_payout_sources"
        rows.append({**row, "remaining_gap_reason": reason})
    return rows


def summarize_remaining_transfer_gaps(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (
            clean_text(row.get("check_in"))[:4],
            clean_text(row.get("status")),
            clean_text(row.get("transfer_link_status")),
            clean_text(row.get("remaining_gap_reason")),
        )
        entry = grouped.setdefault(
            key,
            {
                "check_in_year": key[0],
                "status": key[1],
                "transfer_link_status": key[2],
                "remaining_gap_reason": key[3],
                "booking_count": 0,
                "export_total_payment_total": Decimal("0"),
            },
        )
        entry["booking_count"] += 1
        entry["export_total_payment_total"] += decimal_value(row.get("export_total_payment"))
    summary = []
    for entry in grouped.values():
        summary.append(
            {
                **entry,
                "export_total_payment_total": str(entry["export_total_payment_total"].quantize(Decimal("0.01"))),
            }
        )
    return sorted(
        summary,
        key=lambda r: (
            r["check_in_year"],
            r["status"],
            r["transfer_link_status"],
            r["remaining_gap_reason"],
        ),
    )


def parse_date_or_none(text: str) -> date | None:
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def dates_overlap(a_start: str, a_end: str, b_start: str, b_end: str) -> bool:
    start_a = parse_date_or_none(a_start)
    end_a = parse_date_or_none(a_end)
    start_b = parse_date_or_none(b_start)
    end_b = parse_date_or_none(b_end)
    if not (start_a and end_a and start_b and end_b):
        return False
    return start_a <= end_b and start_b <= end_a


def sum_decimals(rows: list[dict[str, Any]], key: str) -> str:
    total = sum((decimal_value(row.get(key)) for row in rows), Decimal("0"))
    return str(total.quantize(Decimal("0.01")))


def field_name_from_path(path: str) -> str:
    if not path:
        return ""
    last = path.split(".")[-1]
    return re.sub(r"\[\d+\]", "", last).lower()


def is_amount_like(value: Any) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, (int, float, Decimal)):
        return True
    text = clean_text(value)
    if text.lower() in {"true", "false", "yes", "no", "enabled", "disabled"}:
        return False
    try:
        Decimal(text.replace(",", ""))
        return True
    except (InvalidOperation, ValueError):
        return False


def explicit_gst_paths(records: list[dict[str, Any]]) -> list[str]:
    paths = []
    for record in records:
        path = clean_text(record.get("path"))
        key = field_name_from_path(path)
        if any(token in key for token in ("gst", "tax", "vat")) and is_amount_like(record.get("value")):
            paths.append(path)
    return sorted(set(paths))


def explicit_levy_paths(records: list[dict[str, Any]]) -> list[str]:
    paths = []
    for record in records:
        path = clean_text(record.get("path"))
        key = field_name_from_path(path)
        if ("levy" in key or "levies" in key) and is_amount_like(record.get("value")):
            paths.append(path)
    return sorted(set(paths))


def build_reconciliation(
    bookings: list[dict[str, Any]],
    finance_items: list[dict[str, Any]],
    payouts: list[dict[str, Any]],
    payout_links: list[dict[str, Any]],
    payout_csv_items: list[dict[str, Any]],
    payout_detail_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    finance_by_booking: dict[str, list[dict[str, Any]]] = defaultdict(list)
    property_ids_by_booking: dict[str, set[str]] = defaultdict(set)
    for item in finance_items:
        booking = item.get("booking_number", "")
        if not booking:
            continue
        finance_by_booking[booking].append(item)
        if item.get("property_id"):
            property_ids_by_booking[booking].add(item["property_id"])

    name_to_property_ids: dict[str, set[str]] = defaultdict(set)
    booking_property_name: dict[str, str] = {}
    for booking in bookings:
        booking_property_name[booking["booking_number"]] = booking.get("property_name", "")
        for prop_id in property_ids_by_booking.get(booking["booking_number"], set()):
            if booking.get("property_name"):
                name_to_property_ids[booking["property_name"]].add(prop_id)

    direct_transfer_by_booking: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for link in payout_links:
        if link.get("booking_number"):
            direct_transfer_by_booking[link["booking_number"]].append(link)

    payout_details_by_booking: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for detail in payout_detail_rows:
        if detail.get("booking_number"):
            payout_details_by_booking[detail["booking_number"]].append(detail)

    payout_csv_by_booking: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in payout_csv_items:
        booking_number = item.get("reference_number", "")
        if item.get("is_booking_membership") == "true" and booking_number:
            payout_csv_by_booking[booking_number].append(item)

    payouts_by_property: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for payout in payouts:
        if payout.get("property_id"):
            payouts_by_property[payout["property_id"]].append(payout)

    rows: list[dict[str, Any]] = []
    property_mapping_notes: dict[str, list[str]] = {}

    for booking in bookings:
        booking_number = booking["booking_number"]
        finance = finance_by_booking.get(booking_number, [])
        property_ids = set(property_ids_by_booking.get(booking_number, set()))
        prop_name = booking.get("property_name", "")
        if not property_ids and prop_name:
            mapped = name_to_property_ids.get(prop_name, set())
            property_ids.update(mapped)
            if len(mapped) != 1:
                property_mapping_notes[prop_name] = sorted(mapped)
        property_id = sorted(property_ids)[0] if len(property_ids) == 1 else ""
        property_id_status = (
            "direct_finance_booking_match"
            if property_ids_by_booking.get(booking_number)
            else ("name_inferred_unique" if len(property_ids) == 1 else "unmapped_or_ambiguous")
        )

        direct_links = direct_transfer_by_booking.get(booking_number, [])
        payout_detail = payout_details_by_booking.get(booking_number, [])
        payout_csv_direct = payout_csv_by_booking.get(booking_number, [])
        candidate_payouts: list[dict[str, Any]] = []
        if property_id:
            for payout in payouts_by_property.get(property_id, []):
                if dates_overlap(booking.get("check_in", ""), booking.get("check_out", ""), payout.get("date_from", ""), payout.get("date_until", "")):
                    candidate_payouts.append(payout)

        direct_source_parts = []
        if payout_detail:
            direct_source_parts.append("payout_detail")
        if payout_csv_direct:
            direct_source_parts.append("payout_csv")
        if direct_links:
            direct_source_parts.append("payout_source")

        if direct_source_parts:
            transfer_status = "direct_booking_membership_from_" + "_and_".join(direct_source_parts)
            transfer_refs = sorted(
                {
                    *(row.get("payout_uuid", "") for row in payout_detail if row.get("payout_uuid")),
                    *(row.get("payout_uuid", "") for row in payout_csv_direct if row.get("payout_uuid")),
                    *(link.get("payout_uuid") or link.get("raw_key", "") for link in direct_links if link),
                }
            )
        elif len(candidate_payouts) == 1:
            transfer_status = "candidate_only_property_and_stay_period_overlap"
            transfer_refs = [candidate_payouts[0].get("payout_uuid") or candidate_payouts[0].get("transfer_reference", "")]
        elif len(candidate_payouts) > 1:
            transfer_status = "ambiguous_candidate_property_and_stay_period_overlap"
            transfer_refs = [p.get("payout_uuid") or p.get("transfer_reference", "") for p in candidate_payouts]
        else:
            transfer_status = "unlinked_no_direct_membership_or_period_candidate"
            transfer_refs = []

        tax_levy_values = []
        for item in finance:
            try:
                tax_levy_values.extend(json.loads(item.get("tax_levy_fields_json") or "[]"))
            except json.JSONDecodeError:
                pass
        tax_levy_records = [v for v in tax_levy_values if isinstance(v, dict)]
        gst_paths = explicit_gst_paths(tax_levy_records)
        levy_paths = explicit_levy_paths(tax_levy_records)
        payout_vat_present = has_nonzero_money(payout_detail, "vat")
        payout_csv_vat_present = has_nonzero_money(payout_csv_direct, "vat")
        payout_levy_present = has_nonzero_money(payout_detail, "short_stay_levy")

        statement_sources = sorted({item.get("source_file", "") for item in finance if item.get("source_file")})
        payout_sources = sorted({payout.get("source_file", "") for payout in candidate_payouts if payout.get("source_file")})
        direct_payout_sources = sorted({link.get("source_file", "") for link in direct_links if link.get("source_file")})
        payout_detail_sources = sorted({row.get("source_file", "") for row in payout_detail if row.get("source_file")})
        payout_csv_sources = sorted({row.get("source_file", "") for row in payout_csv_direct if row.get("source_file")})
        gst_source_paths = gst_paths[:]
        if payout_vat_present:
            gst_source_paths.append("payout_detail.vat")
        if payout_csv_vat_present:
            gst_source_paths.append("payout_csv.vat")
        gst_status = (
            "present_in_payout_detail_source"
            if payout_vat_present
            else (
                "present_in_payout_csv_source"
                if payout_csv_vat_present
                else ("present_in_finance_source" if gst_paths else "not_present_in_captured_source")
            )
        )

        rows.append(
            {
                "booking_number": booking_number,
                "property_id": property_id,
                "property_id_status": property_id_status,
                "property_name": prop_name,
                "guest_name": booking.get("guest_name", ""),
                "check_in": booking.get("check_in", ""),
                "check_out": booking.get("check_out", ""),
                "booked_on": booking.get("booked_on", ""),
                "status": booking.get("status", ""),
                "currency": booking.get("currency", ""),
                "export_total_payment": booking.get("export_total_payment", ""),
                "commission_export": booking.get("commission_export", ""),
                "statement_revenue": sum_decimals(finance, "final_service_amount") if finance else "",
                "commission_statement": sum_decimals(finance, "commission_statement") if finance else "",
                "payment_charges": sum_decimals(finance, "payment_charges") if finance else "",
                "payout_detail_amount": money_sum_text(payout_detail, "amount") if payout_detail else "",
                "payout_detail_commission": money_sum_text(payout_detail, "commission") if payout_detail else "",
                "payout_detail_vat": money_sum_text(payout_detail, "vat") if payout_detail else "",
                "payout_detail_short_stay_levy": money_sum_text(payout_detail, "short_stay_levy") if payout_detail else "",
                "payout_detail_payments_service_fee": money_sum_text(payout_detail, "payments_service_fee") if payout_detail else "",
                "payout_detail_net": money_sum_text(payout_detail, "net") if payout_detail else "",
                "payout_detail_count": len(payout_detail),
                "payout_csv_amount": sum_decimals(payout_csv_direct, "amount") if payout_csv_direct else "",
                "payout_csv_commission": sum_decimals(payout_csv_direct, "commission") if payout_csv_direct else "",
                "payout_csv_vat": sum_decimals(payout_csv_direct, "vat") if payout_csv_direct else "",
                "payout_csv_payments_service_fee": sum_decimals(payout_csv_direct, "payments_service_fee") if payout_csv_direct else "",
                "payout_csv_net": sum_decimals(payout_csv_direct, "net") if payout_csv_direct else "",
                "payout_csv_count": len(payout_csv_direct),
                "finance_item_count": len(finance),
                "finance_link_status": "direct_booking_number_match" if finance else "no_statement_item_captured",
                "gst_status": gst_status,
                "gst_source_paths": ";".join(gst_source_paths),
                "short_stay_levy_status": "present_in_payout_detail_source" if payout_levy_present else ("present_in_finance_source" if levy_paths else "not_present_in_captured_source"),
                "short_stay_levy_source_paths": ";".join(levy_paths + (["payout_detail.short_stay_levy"] if payout_levy_present else [])),
                "transfer_link_status": transfer_status,
                "candidate_transfer_count": len(candidate_payouts),
                "candidate_transfer_ids": ";".join(transfer_refs),
                "candidate_transfer_references": ";".join(sorted({p.get("transfer_reference", "") for p in candidate_payouts if p.get("transfer_reference")})),
                "source_reservation_file": booking.get("source_file", ""),
                "source_statement_files": ";".join(statement_sources),
                "source_candidate_payout_files": ";".join(payout_sources),
                "source_direct_payout_files": ";".join(direct_payout_sources),
                "source_payout_detail_files": ";".join(payout_detail_sources),
                "source_payout_csv_files": ";".join(payout_csv_sources),
            }
        )

    return rows, {name: ids for name, ids in property_mapping_notes.items() if len(ids) != 1}


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str] | None = None) -> None:
    if columns is None:
        seen: list[str] = []
        for row in rows:
            for key in row:
                if key not in seen:
                    seen.append(key)
        columns = seen
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_sqlite(path: Path, tables: dict[str, list[dict[str, Any]]]) -> None:
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    try:
        for table, rows in tables.items():
            columns: list[str] = []
            for row in rows:
                for key in row:
                    if key not in columns:
                        columns.append(key)
            if not columns:
                columns = ["empty"]
            quoted_cols = ", ".join(f'"{col}" TEXT' for col in columns)
            conn.execute(f'CREATE TABLE "{table}" ({quoted_cols})')
            if rows:
                placeholders = ", ".join("?" for _ in columns)
                col_list = ", ".join(f'"{col}"' for col in columns)
                conn.executemany(
                    f'INSERT INTO "{table}" ({col_list}) VALUES ({placeholders})',
                    [[clean_text(row.get(col)) for col in columns] for row in rows],
                )
        conn.commit()
    finally:
        conn.close()


@dataclass
class LedgerChain:
    rows: list[dict[str, Any]]
    previous_hash: str = "0" * 64

    def append(self, event_type: str, payload: dict[str, Any]) -> None:
        event = {"event_type": event_type, "payload": payload, "prev_hash": self.previous_hash}
        event_hash = hashlib.sha256(stable_json(event).encode("utf-8")).hexdigest()
        event["event_hash"] = event_hash
        self.rows.append(event)
        self.previous_hash = event_hash


def build_chain(
    sources: list[dict[str, Any]],
    bookings: list[dict[str, Any]],
    finance_items: list[dict[str, Any]],
    payouts: list[dict[str, Any]],
    payout_csv_items: list[dict[str, Any]],
    payout_detail_rows: list[dict[str, Any]],
    reconciliation: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str]:
    chain = LedgerChain(rows=[])
    for row in sorted(sources, key=lambda r: r["rel_path"]):
        chain.append("source", row)
    for row in sorted(bookings, key=lambda r: (r.get("booking_number", ""), r.get("source_file", ""))):
        chain.append("booking", row)
    for row in sorted(finance_items, key=lambda r: (r.get("booking_number", ""), r.get("source_file", ""), clean_text(r.get("source_item_index")), clean_text(r.get("source_room_index")))):
        chain.append("finance_item", row)
    for row in sorted(payouts, key=lambda r: (r.get("property_id", ""), r.get("payout_uuid", ""), r.get("source_file", ""))):
        chain.append("payout", row)
    for row in sorted(payout_csv_items, key=lambda r: (r.get("property_id", ""), r.get("payout_uuid", ""), r.get("source_row", ""))):
        chain.append("payout_csv_item", row)
    for row in sorted(payout_detail_rows, key=lambda r: (r.get("booking_number", ""), r.get("payout_uuid", ""), r.get("source_row", ""))):
        chain.append("payout_detail", row)
    for row in sorted(reconciliation, key=lambda r: r.get("booking_number", "")):
        chain.append("reconciliation", row)
    return chain.rows, chain.previous_hash


def output_hashes(out_dir: Path) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(out_dir.iterdir()):
        if path.is_file() and path.name != "output_manifest.csv":
            rows.append(
                {
                    "file": path.name,
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    return rows


def write_report(out_dir: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# Booking.com Reconciliation Ledger",
        "",
        f"Generated UTC: `{summary['generated_at_utc']}`",
        "",
        "## Counts",
        "",
        f"- Source files hashed: `{summary['source_files_hashed']}`",
        f"- Reservation export bookings: `{summary['reservation_export_bookings']}`",
        f"- Finance statement line items: `{summary['finance_statement_items']}`",
        f"- Payout transfer summaries: `{summary['payout_transfers']}`",
        f"- Payout CSV transfer line items: `{summary['payout_csv_items']}`",
        f"- Payout CSV booking membership line items: `{summary['payout_csv_booking_membership_rows']}`",
        f"- Payout CSV non-booking transfer line items: `{summary['payout_csv_non_booking_items']}`",
        f"- Payout booking detail rows: `{summary['payout_booking_detail_rows']}`",
        f"- Legacy Vuex payout booking-link rows: `{summary['payout_booking_links_direct']}`",
        f"- Bookings with direct finance items: `{summary['bookings_with_direct_finance_items']}`",
        f"- Bookings without captured finance items: `{summary['bookings_without_captured_finance_items']}`",
        f"- Bookings with direct bank transfer membership: `{summary['bookings_with_direct_bank_transfer_membership']}`",
        f"- Bookings with one candidate transfer by property/stay-period overlap: `{summary['bookings_with_single_candidate_transfer_period']}`",
        f"- Bookings with ambiguous candidate transfers: `{summary['bookings_with_ambiguous_candidate_transfer_period']}`",
        f"- Remaining bookings without direct transfer membership: `{summary['remaining_bookings_without_direct_transfer_membership']}`",
        f"- Bookings with explicit GST/tax amount fields in captured finance source: `{summary['bookings_with_gst_field_in_captured_finance_source']}`",
        f"- Bookings with explicit short-stay levy amount fields in captured finance source: `{summary['bookings_with_short_stay_levy_field_in_captured_finance_source']}`",
        f"- Expanded payout detail filters captured: `{', '.join(summary['payout_detail_capture_filters']) or 'none'}`",
        "",
        "## Claim Boundary",
        "",
        "- Booking revenue and Booking.com commission/payment-charge lines are direct only where reservation numbers match captured finance statement data.",
        "- Bank transfer membership is direct when expanded payout details or downloaded payout CSV reservation rows expose booking membership.",
        "- Expanded payout detail captures and downloaded payout CSVs in this run cover browser-harness GraphQL payout history/detail downloads across the captured operating years.",
        "- Candidate transfer links are property/date-period overlaps only. They are useful review leads, not immutable proof.",
        "- GST, VAT, tax, short-stay levy, or similar costs are reported only when an explicit amount-like source field exists.",
        "",
        "## Integrity",
        "",
        f"- Ledger final chain hash: `{summary['ledger_final_chain_hash']}`",
        "- `source_manifest.csv` hashes every input source used.",
        "- `output_manifest.csv` hashes every generated output artifact.",
        "- `ledger_chain.jsonl` chains source, booking, finance, payout, payout CSV, payout detail, and reconciliation rows with previous-hash links.",
        "",
        "## Main Artifacts",
        "",
    ]
    for name, path in summary["artifacts"].items():
        lines.append(f"- `{name}`: `{path}`")
    lines.append("")
    (out_dir / "reconciliation_report.md").write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: build_reconciliation_ledger.py <bookingcom-export-root>", file=sys.stderr)
        return 2

    root = Path(argv[1]).expanduser().resolve()
    if not root.exists():
        print(f"Export root does not exist: {root}", file=sys.stderr)
        return 2

    out_dir = root / "reconciliation_ledger"
    out_dir.mkdir(parents=True, exist_ok=True)

    source_files = find_source_files(root)
    sources = []
    source_hashes: dict[str, str] = {}
    for path in source_files:
        rel = path.relative_to(root).as_posix()
        digest = sha256_file(path)
        source_hashes[rel] = digest
        sources.append(
            {
                "rel_path": rel,
                "kind": classify_source(path, root),
                "bytes": path.stat().st_size,
                "sha256": digest,
            }
        )

    bookings = parse_reservation_exports(root, source_hashes)
    finance_items = parse_finance_items(root, source_hashes)
    payouts, payout_links, payment_cost_rules = parse_payouts(root, source_hashes)
    payout_csv_items = parse_payout_csv_items(root, source_hashes)
    payout_detail_rows = parse_payout_detail_rows(root, source_hashes)
    reconciliation, ambiguous_property_names = build_reconciliation(
        bookings, finance_items, payouts, payout_links, payout_csv_items, payout_detail_rows
    )
    remaining_gaps = remaining_transfer_gaps(reconciliation)
    remaining_gap_summary = summarize_remaining_transfer_gaps(remaining_gaps)

    statement_manifest = read_tsv_rows(root / "statement_links.tsv")
    invoice_coverage = read_tsv_rows(root / "all_properties_coverage.tsv")
    chain_rows, final_chain_hash = build_chain(
        sources, bookings, finance_items, payouts, payout_csv_items, payout_detail_rows, reconciliation
    )

    write_csv(out_dir / "source_manifest.csv", sources, ["rel_path", "kind", "bytes", "sha256"])
    write_csv(out_dir / "bookings.csv", bookings)
    write_csv(out_dir / "finance_statement_items.csv", finance_items)
    write_csv(out_dir / "payout_transfers.csv", payouts)
    write_csv(out_dir / "payout_csv_items.csv", payout_csv_items)
    write_csv(out_dir / "payout_non_booking_items.csv", [row for row in payout_csv_items if row.get("is_booking_membership") != "true"])
    write_csv(out_dir / "payout_booking_links.csv", payout_links)
    write_csv(out_dir / "payout_booking_details.csv", payout_detail_rows)
    write_csv(out_dir / "payment_cost_rules.csv", payment_cost_rules)
    write_csv(out_dir / "booking_reconciliation.csv", reconciliation)
    write_csv(out_dir / "remaining_transfer_gaps.csv", remaining_gaps)
    write_csv(out_dir / "remaining_transfer_gap_summary.csv", remaining_gap_summary)
    with (out_dir / "ledger_chain.jsonl").open("w", encoding="utf-8") as fh:
        for row in chain_rows:
            fh.write(stable_json(row) + "\n")

    tables = {
        "sources": sources,
        "bookings": bookings,
        "finance_statement_items": finance_items,
        "payout_transfers": payouts,
        "payout_csv_items": payout_csv_items,
        "payout_non_booking_items": [row for row in payout_csv_items if row.get("is_booking_membership") != "true"],
        "payout_booking_links": payout_links,
        "payout_booking_details": payout_detail_rows,
        "payment_cost_rules": payment_cost_rules,
        "booking_reconciliation": reconciliation,
        "remaining_transfer_gaps": remaining_gaps,
        "remaining_transfer_gap_summary": remaining_gap_summary,
        "invoice_coverage": invoice_coverage,
        "statement_manifest": statement_manifest,
    }
    write_sqlite(out_dir / "booking_ledger.sqlite", tables)

    linked_finance = sum(1 for row in reconciliation if row["finance_link_status"] == "direct_booking_number_match")
    direct_transfer = sum(1 for row in reconciliation if row["transfer_link_status"].startswith("direct_booking_membership"))
    candidate_transfer = sum(1 for row in reconciliation if row["transfer_link_status"].startswith("candidate_only"))
    ambiguous_transfer = sum(1 for row in reconciliation if row["transfer_link_status"].startswith("ambiguous_candidate"))
    unmapped_property = sum(1 for row in reconciliation if row["property_id_status"] == "unmapped_or_ambiguous")
    gst_present = sum(
        1
        for row in reconciliation
        if row["gst_status"] in {"present_in_finance_source", "present_in_payout_detail_source", "present_in_payout_csv_source"}
    )
    levy_present = sum(1 for row in reconciliation if row["short_stay_levy_status"] in {"present_in_finance_source", "present_in_payout_detail_source"})

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "export_root": root.as_posix(),
        "output_dir": out_dir.as_posix(),
        "source_files_hashed": len(sources),
        "reservation_export_bookings": len(bookings),
        "finance_statement_items": len(finance_items),
        "payout_transfers": len(payouts),
        "payout_csv_items": len(payout_csv_items),
        "payout_csv_booking_membership_rows": sum(1 for row in payout_csv_items if row.get("is_booking_membership") == "true"),
        "payout_csv_non_booking_items": sum(1 for row in payout_csv_items if row.get("is_booking_membership") != "true"),
        "payout_booking_links_direct": len(payout_links),
        "payout_booking_detail_rows": len(payout_detail_rows),
        "payout_detail_capture_filters": sorted({row.get("period_filter", "") for row in payout_detail_rows if row.get("period_filter")}),
        "bookings_with_direct_finance_items": linked_finance,
        "bookings_without_captured_finance_items": len(reconciliation) - linked_finance,
        "bookings_with_direct_bank_transfer_membership": direct_transfer,
        "bookings_with_single_candidate_transfer_period": candidate_transfer,
        "bookings_with_ambiguous_candidate_transfer_period": ambiguous_transfer,
        "remaining_bookings_without_direct_transfer_membership": len(remaining_gaps),
        "bookings_with_unmapped_or_ambiguous_property": unmapped_property,
        "bookings_with_gst_field_in_captured_finance_source": gst_present,
        "bookings_with_short_stay_levy_field_in_captured_finance_source": levy_present,
        "ambiguous_property_name_mappings": ambiguous_property_names,
        "ledger_final_chain_hash": final_chain_hash,
        "claim_boundary": {
            "booking_revenue_costs": "Direct where Booking.com reservation export rows match captured finance statement items by booking number.",
            "bank_transfer_membership": "Direct when payout detail captures or downloaded payout CSV reservation rows expose booking membership. Otherwise candidate links are property/date-period overlap only and not immutable proof.",
            "gst_and_short_stay_levies": "Reported only when captured Booking.com finance source exposes explicit matching fields; absent fields are not inferred.",
        },
        "artifacts": {
            "sqlite": (out_dir / "booking_ledger.sqlite").as_posix(),
            "booking_reconciliation_csv": (out_dir / "booking_reconciliation.csv").as_posix(),
            "bookings_csv": (out_dir / "bookings.csv").as_posix(),
            "finance_statement_items_csv": (out_dir / "finance_statement_items.csv").as_posix(),
            "payout_transfers_csv": (out_dir / "payout_transfers.csv").as_posix(),
            "payout_csv_items_csv": (out_dir / "payout_csv_items.csv").as_posix(),
            "payout_non_booking_items_csv": (out_dir / "payout_non_booking_items.csv").as_posix(),
            "payout_booking_details_csv": (out_dir / "payout_booking_details.csv").as_posix(),
            "remaining_transfer_gaps_csv": (out_dir / "remaining_transfer_gaps.csv").as_posix(),
            "remaining_transfer_gap_summary_csv": (out_dir / "remaining_transfer_gap_summary.csv").as_posix(),
            "source_manifest_csv": (out_dir / "source_manifest.csv").as_posix(),
            "ledger_chain_jsonl": (out_dir / "ledger_chain.jsonl").as_posix(),
        },
    }
    (out_dir / "reconciliation_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    write_report(out_dir, summary)
    write_csv(out_dir / "output_manifest.csv", output_hashes(out_dir), ["file", "bytes", "sha256"])

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
