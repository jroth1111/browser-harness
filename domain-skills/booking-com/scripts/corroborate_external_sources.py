#!/usr/bin/env python3
"""Corroborate Booking.com ledger rows with local email and WhatsApp stores.

This script does not upgrade candidate payout overlaps into direct bank-transfer
proof. It records exact booking-number matches from independent communications
so the reconciliation can distinguish Booking.com-source proof from external
operational corroboration.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BOOKING_NUMBER_RE = re.compile(r"\b\d{9,10}\b")


def clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def file_identity(path: Path, conn: sqlite3.Connection) -> dict[str, Any]:
    stat = path.stat()
    schema_rows = conn.execute(
        "select type, name, tbl_name, sql from sqlite_master order by type, name"
    ).fetchall()
    return {
        "path": path.as_posix(),
        "bytes": stat.st_size,
        "mtime_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        "schema_sha256": sha256_text(stable_json(schema_rows)),
    }


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str] | None = None) -> None:
    if columns is None:
        columns = []
        for row in rows:
            for key in row:
                if key not in columns:
                    columns.append(key)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def output_manifest(paths: list[Path]) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(paths):
        rows.append(
            {
                "file": path.name,
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return rows


def matching_fields(booking_number: str, fields: dict[str, str]) -> str:
    return ";".join(name for name, value in fields.items() if booking_number in value)


def scan_email(
    db_path: Path,
    booking_numbers: set[str],
    source_id: dict[str, Any],
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    conn = sqlite3.connect(db_path)
    try:
        query = """
            select
                m.id,
                m.thread_key,
                m.date_utc,
                m.subject,
                m.from_email,
                coalesce(m.snippet, ''),
                coalesce(b.body_markdown, ''),
                coalesce(b.body_sha256, '')
            from messages as m
            left join message_bodies as b on b.message_id = m.id
            where lower(m.subject) like '%booking%'
               or lower(m.from_email) like '%booking%'
               or lower(coalesce(m.snippet, '')) like '%booking%'
        """
        for row in conn.execute(query):
            message_id, thread_key, date_utc, subject, from_email, snippet, body, body_sha256 = row
            fields = {
                "subject": clean(subject),
                "from_email": clean(from_email),
                "snippet": clean(snippet),
                "body": clean(body),
            }
            hits = sorted(booking_numbers & set(BOOKING_NUMBER_RE.findall(" ".join(fields.values()))))
            for booking_number in hits:
                evidence_payload = {
                    "source_type": "email",
                    "booking_number": booking_number,
                    "message_id": clean(message_id),
                    "thread_key": clean(thread_key),
                    "date_utc": clean(date_utc),
                    "subject": clean(subject),
                    "from_email": clean(from_email),
                    "body_sha256": clean(body_sha256),
                    "matching_fields": matching_fields(booking_number, fields),
                    "source_schema_sha256": source_id["schema_sha256"],
                    "source_bytes": source_id["bytes"],
                    "source_mtime_utc": source_id["mtime_utc"],
                }
                events.append(
                    {
                        **evidence_payload,
                        "source_type": "email",
                        "source_db_path": source_id["path"],
                        "source_record_id": clean(message_id),
                        "evidence_basis": "exact_booking_number_match",
                        "evidence_sha256": sha256_text(stable_json(evidence_payload)),
                    }
                )
    finally:
        conn.close()
    return events


def scan_whatsapp(
    db_path: Path,
    booking_numbers: set[str],
    source_id: dict[str, Any],
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    conn = sqlite3.connect(db_path)
    try:
        thread_names = {
            row[0]: row[1]
            for row in conn.execute("select thread_id, thread_name from threads")
        }
        query = """
            select
                message_id,
                thread_id,
                message_date,
                sender_name,
                coalesce(text, ''),
                coalesce(attachment_name, ''),
                coalesce(attachment_info, '')
            from messages
        """
        for row in conn.execute(query):
            message_id, thread_id, message_date, sender_name, text, attachment_name, attachment_info = row
            fields = {
                "text": clean(text),
                "attachment_name": clean(attachment_name),
                "attachment_info": clean(attachment_info),
            }
            hits = sorted(booking_numbers & set(BOOKING_NUMBER_RE.findall(" ".join(fields.values()))))
            for booking_number in hits:
                evidence_payload = {
                    "source_type": "whatsapp",
                    "booking_number": booking_number,
                    "message_id": clean(message_id),
                    "thread_id": clean(thread_id),
                    "thread_name": clean(thread_names.get(thread_id, "")),
                    "message_date": clean(message_date),
                    "sender_name": clean(sender_name),
                    "message_content_sha256": sha256_text(stable_json(fields)),
                    "matching_fields": matching_fields(booking_number, fields),
                    "source_schema_sha256": source_id["schema_sha256"],
                    "source_bytes": source_id["bytes"],
                    "source_mtime_utc": source_id["mtime_utc"],
                }
                events.append(
                    {
                        **evidence_payload,
                        "source_db_path": source_id["path"],
                        "source_record_id": clean(message_id),
                        "evidence_basis": "exact_booking_number_match",
                        "evidence_sha256": sha256_text(stable_json(evidence_payload)),
                    }
                )
    finally:
        conn.close()
    return events


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print(
            "Usage: corroborate_external_sources.py <reconciliation-ledger-dir> <email-sqlite> <whatsapp-sqlite>",
            file=sys.stderr,
        )
        return 2

    ledger_dir = Path(argv[1]).expanduser().resolve()
    email_db = Path(argv[2]).expanduser().resolve()
    whatsapp_db = Path(argv[3]).expanduser().resolve()
    reconciliation_path = ledger_dir / "booking_reconciliation.csv"
    remaining_path = ledger_dir / "remaining_transfer_gaps.csv"
    if not reconciliation_path.exists():
        print(f"Missing booking reconciliation CSV: {reconciliation_path}", file=sys.stderr)
        return 2
    if not remaining_path.exists():
        print(f"Missing remaining transfer gaps CSV: {remaining_path}", file=sys.stderr)
        return 2
    for path in (email_db, whatsapp_db):
        if not path.exists():
            print(f"Missing external source database: {path}", file=sys.stderr)
            return 2

    reconciliation = read_csv(reconciliation_path)
    remaining = read_csv(remaining_path)
    booking_numbers = {row["booking_number"] for row in reconciliation if row.get("booking_number")}
    remaining_numbers = {row["booking_number"] for row in remaining if row.get("booking_number")}

    with sqlite3.connect(email_db) as conn:
        email_source = file_identity(email_db, conn)
    with sqlite3.connect(whatsapp_db) as conn:
        whatsapp_source = file_identity(whatsapp_db, conn)

    events = scan_email(email_db, booking_numbers, email_source)
    events.extend(scan_whatsapp(whatsapp_db, booking_numbers, whatsapp_source))

    events_by_booking: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        events_by_booking[event["booking_number"]].append(event)

    remaining_reason = {row["booking_number"]: row.get("remaining_gap_reason", "") for row in remaining}
    booking_rows: list[dict[str, Any]] = []
    for row in reconciliation:
        booking_number = row["booking_number"]
        evidence = events_by_booking.get(booking_number, [])
        email_events = [event for event in evidence if event["source_type"] == "email"]
        whatsapp_events = [event for event in evidence if event["source_type"] == "whatsapp"]
        booking_rows.append(
            {
                "booking_number": booking_number,
                "property_id": row.get("property_id", ""),
                "property_name": row.get("property_name", ""),
                "guest_name": row.get("guest_name", ""),
                "check_in": row.get("check_in", ""),
                "check_out": row.get("check_out", ""),
                "status": row.get("status", ""),
                "export_total_payment": row.get("export_total_payment", ""),
                "transfer_link_status": row.get("transfer_link_status", ""),
                "remaining_gap_reason": remaining_reason.get(booking_number, ""),
                "email_exact_booking_number_messages": len(email_events),
                "whatsapp_exact_booking_number_messages": len(whatsapp_events),
                "external_exact_booking_number_sources": ";".join(
                    source
                    for source, count in (
                        ("email", len(email_events)),
                        ("whatsapp", len(whatsapp_events)),
                    )
                    if count
                ),
                "external_exact_booking_number_status": "corroborated" if evidence else "not_found",
                "email_message_ids": ";".join(event["source_record_id"] for event in email_events[:20]),
                "whatsapp_message_ids": ";".join(event["source_record_id"] for event in whatsapp_events[:20]),
                "external_evidence_count": len(evidence),
            }
        )

    gap_rows = [row for row in booking_rows if row["booking_number"] in remaining_numbers]

    status_counts = Counter(row["external_exact_booking_number_status"] for row in booking_rows)
    source_counts = Counter()
    for row in booking_rows:
        if row["email_exact_booking_number_messages"]:
            source_counts["email"] += 1
        if row["whatsapp_exact_booking_number_messages"]:
            source_counts["whatsapp"] += 1
    gap_status_counts = Counter(row["external_exact_booking_number_status"] for row in gap_rows)
    gap_reason_counts = Counter(row["remaining_gap_reason"] for row in gap_rows)

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "claim_boundary": {
            "external_corroboration": "Exact booking-number matches in email or WhatsApp corroborate booking existence/operations only.",
            "bank_transfer_membership": "External messages do not upgrade transfer candidates to direct bank-transfer proof unless they contain a direct transfer membership source, which this script does not infer.",
        },
        "ledger_dir": ledger_dir.as_posix(),
        "email_source": email_source,
        "whatsapp_source": whatsapp_source,
        "booking_rows": len(booking_rows),
        "external_evidence_events": len(events),
        "bookings_corroborated_by_any_external_source": status_counts["corroborated"],
        "bookings_not_found_in_external_sources": status_counts["not_found"],
        "bookings_corroborated_by_email": source_counts["email"],
        "bookings_corroborated_by_whatsapp": source_counts["whatsapp"],
        "remaining_gap_rows": len(gap_rows),
        "remaining_gap_rows_corroborated_by_any_external_source": gap_status_counts["corroborated"],
        "remaining_gap_rows_not_found_in_external_sources": gap_status_counts["not_found"],
        "remaining_gap_reason_counts": dict(sorted(gap_reason_counts.items())),
    }

    events_path = ledger_dir / "external_corroboration_events.csv"
    booking_path = ledger_dir / "booking_external_corroboration.csv"
    gaps_path = ledger_dir / "remaining_transfer_gap_corroboration.csv"
    summary_path = ledger_dir / "external_corroboration_summary.json"
    manifest_path = ledger_dir / "external_corroboration_manifest.csv"

    write_csv(events_path, events)
    write_csv(booking_path, booking_rows)
    write_csv(gaps_path, gap_rows)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    write_csv(manifest_path, output_manifest([events_path, booking_path, gaps_path, summary_path]))

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
