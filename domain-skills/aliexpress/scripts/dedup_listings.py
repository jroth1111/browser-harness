#!/usr/bin/env python3
"""Compare extracted search results against an existing CSV.

Takes JSON from stdin (browser extraction output) and a CSV file path.
Outputs only listings whose product_id is not already in the CSV.

Usage:
    # Agent pipes browser extraction output:
    echo '[{"product_id":"123","title":"...","price":"AU$100"}]' | \
        python3 dedup_listings.py .private-data/ryzen-aimax395-aliexpress-2026-05-02.csv

    # Or from a file:
    python3 dedup_listings.py --input results.csv .private-data/existing.csv

The input can be JSON (array of objects) or CSV (must have product_id column).
"""

import argparse
import csv
import json
import sys


def load_existing_ids(csv_path: str) -> set[str]:
    ids = set()
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pid = row.get("product_id", "").strip()
            if pid:
                ids.add(pid)
    return ids


def load_input(input_source: str) -> list[dict]:
    """Load from stdin (JSON) or file path (CSV or JSON)."""
    if input_source == "-":
        raw = sys.stdin.read().strip()
        return json.loads(raw)

    with open(input_source) as f:
        raw = f.read().strip()

    if raw.startswith("[") or raw.startswith("{"):
        return json.loads(raw)

    results = []
    with open(input_source, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            results.append(dict(row))
    return results


def main():
    parser = argparse.ArgumentParser(description="Deduplicate listings against existing CSV")
    parser.add_argument("existing_csv", help="Path to existing CSV with product_id column")
    parser.add_argument(
        "--input", "-i",
        default="-",
        help="Input file (JSON or CSV). Default: stdin",
    )
    parser.add_argument(
        "--output", "-o",
        default="-",
        help="Output file. Default: stdout",
    )
    parser.add_argument(
        "--format",
        choices=["json", "csv"],
        default="json",
        help="Output format (default: json)",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Print stats to stderr",
    )
    parser.add_argument(
        "--require",
        nargs="*",
        help="Title must contain at least one of these keywords (case-insensitive)",
    )
    parser.add_argument(
        "--exclude",
        nargs="*",
        help="Exclude titles containing any of these keywords (case-insensitive)",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append new listings to the existing CSV instead of printing to stdout",
    )
    args = parser.parse_args()

    existing_ids = load_existing_ids(args.existing_csv)
    new_items = load_input(args.input)

    total_input = len(new_items)
    after_dedup = [item for item in new_items if item.get("product_id", "") not in existing_ids]
    duplicates_removed = total_input - len(after_dedup)

    # Relevance filter
    filtered_items = after_dedup
    if args.require:
        keywords = [k.lower() for k in args.require]
        filtered_items = [
            item for item in filtered_items
            if any(k in item.get("title", "").lower() for k in keywords)
        ]

    # Exclusion filter
    if args.exclude:
        exclude_kw = [k.lower() for k in args.exclude]
        filtered_items = [
            item for item in filtered_items
            if not any(k in item.get("title", "").lower() for k in exclude_kw)
        ]

    relevance_filtered = len(after_dedup) - len(filtered_items)
    new_items = filtered_items
    after = len(new_items)

    if args.stats:
        print(f"Existing: {len(existing_ids)} | Input: {total_input} | Duplicates: {duplicates_removed} | Relevance filtered: {relevance_filtered} | New: {after}", file=sys.stderr)

    if args.append and args.existing_csv and new_items:
        with open(args.existing_csv, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=new_items[0].keys())
            writer.writerows(new_items)
        if args.stats:
            print(f"Appended {len(new_items)} rows to {args.existing_csv}", file=sys.stderr)
        return

    out = sys.stdout
    if args.output != "-":
        out = open(args.output, "w", newline="")

    try:
        if args.format == "json":
            json.dump(new_items, out, indent=2)
            out.write("\n")
        else:
            if new_items:
                writer = csv.DictWriter(out, fieldnames=new_items[0].keys())
                writer.writeheader()
                writer.writerows(new_items)
    finally:
        if args.output != "-":
            out.close()


if __name__ == "__main__":
    main()
