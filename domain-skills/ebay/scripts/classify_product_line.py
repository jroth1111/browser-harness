#!/usr/bin/env python3
"""Classify eBay listing titles into product lines and form factors.

Usage:
    echo 'ASUS ROG Flow Z13 GZ302EA 13.4 AMD AI Max+ 395 64GB' | python3 classify_product_line.py
    python3 classify_product_line.py --input results.json
    python3 classify_product_line.py --csv data.csv --field title

Output: JSON with product_line, form_factor, ram_gb, storage_tb, condition per listing.
"""

import argparse
import csv
import json
import re
import sys

PRODUCT_PATTERNS: list[tuple[str, str, str]] = [
    # ── GPU product lines (must come before system patterns) ──
    (r"\bRTX\s+5090\b", "NVIDIA RTX 5090", "gpu"),
    (r"\bRTX\s+4090\b", "NVIDIA RTX 4090", "gpu"),
    (r"\bRTX\s+3090\b", "NVIDIA RTX 3090", "gpu"),
    (r"\bL40S\b", "NVIDIA L40S", "gpu"),
    (r"\bRTX\s+A6000\b", "NVIDIA RTX A6000", "gpu"),
    (r"\bRTX\s+6000\s+Ada\b", "NVIDIA RTX 6000 Ada", "gpu"),
    (r"\bRTX\s+PRO\s+6000\b", "NVIDIA RTX PRO 6000 Blackwell", "gpu"),
    (r"\bRTX\s+A5000\b", "NVIDIA RTX A5000", "gpu"),
    # ── System / laptop / handheld patterns ──
    (r"\bROG\s+Flow\s+Z13\b", "ASUS ROG Flow Z13", "tablet"),
    (r"\bROG\s+Flow\s+X13\b", "ASUS ROG Flow X13", "laptop"),
    (r"\bGPD\s+WIN\s*5\b", "GPD WIN 5", "handheld"),
    (r"\bHP\s+ZBook\s+Ultra\s+G1a\b", "HP ZBook Ultra G1a", "laptop"),
    (r"\bZBook\s+Ultra\s+14\s+G1a\b", "HP ZBook Ultra G1a", "laptop"),
    (r"\bHP\s+Z2\s+(?:Mini\s+)?G1a\b", "HP Z2 G1a Mini", "mini_pc"),
    (r"\bZ2\s+Mini\s+G1a\b", "HP Z2 G1a Mini", "mini_pc"),
    (r"\bHP\s+ZBook\s+Studio\s+99\b", "HP ZBook Studio 99", "laptop"),
    (r"\bOneXPlayer\s+Super\s+X\b", "OneXPlayer Super X", "tablet"),
    (r"\bOneXPlayer\s+Apex\b", "OneXPlayer Apex", "handheld"),
    (r"\bOnexfly\s+Apex\b", "OneXPlayer Apex", "handheld"),
    (r"\bONEXFLY\s+Apex\b", "OneXPlayer Apex", "handheld"),
    (r"\bONEXStation\s+i1\b", "OneXPlayer ONEXStation i1", "mini_pc"),
    (r"\bMinisforum\s+MS-?S1\s+Max\b", "MinisForum MS-S1 Max", "mini_pc"),
    (r"\bMS-?S1\s+Max\b", "MinisForum MS-S1 Max", "mini_pc"),
    (r"\bMINIX\b.*\bER939\b", "MINIX ER939-AI", "mini_pc"),
    (r"\bER939-?AI\b", "MINIX ER939-AI", "mini_pc"),
    (r"\bNIMO\s+Mini\s+PC\b", "NIMO Mini PC", "mini_pc"),
    (r"\bEVO-?X2\b", "EVO-X2 Mini PC", "mini_pc"),
    (r"\bDGX\s+Spark\b", "DGX Spark", "mini_pc"),
    (r"\bDell\s+Pro\s+Max\b", "Dell Pro Max", "workstation"),
]

FORM_FACTOR_OVERRIDES = [
    (r"\bgpu\b", "gpu"),
    (r"\bgraphics\s+card\b", "gpu"),
    (r"\bvideo\s+card\b", "gpu"),
    (r"\bhandheld\b", "handheld"),
    (r"\bgaming\s+console\b", "handheld"),
    (r"\btablet\b", "tablet"),
    (r"\b2-in-1\b", "tablet"),
    (r"\b2in1\b", "tablet"),
    (r"\bworkstation\b", "workstation"),
    (r"\bmini\s+pc\b", "mini_pc"),
    (r"\bdesktop\b", "desktop"),
    (r"\blaptop\b", "laptop"),
    (r"\bnotebook\b", "laptop"),
]

CONDITION_MAP = {
    "new": "New",
    "used": "Used",
    "refurbished": "Refurbished",
    "open box": "Open Box",
    "for parts": "For Parts",
    "excellent": "Excellent",
    "very good": "Very Good",
    "good": "Good",
}


def classify(title: str) -> dict:
    result = {"product_line": "Unknown", "form_factor": "unknown", "ram_gb": None, "storage_tb": None, "condition": None}

    # Product line
    for pattern, product_line, form_factor in PRODUCT_PATTERNS:
        if re.search(pattern, title, re.IGNORECASE):
            result["product_line"] = product_line
            result["form_factor"] = form_factor
            break

    # Form factor override from keywords
    if result["form_factor"] == "unknown":
        for pattern, ff in FORM_FACTOR_OVERRIDES:
            if re.search(pattern, title, re.IGNORECASE):
                result["form_factor"] = ff
                break

    # RAM
    ram_match = re.search(r"(\d+)\s*GB", title, re.IGNORECASE)
    if ram_match:
        result["ram_gb"] = int(ram_match.group(1))

    # Storage
    storage_match = re.search(r"(\d+)\s*TB", title, re.IGNORECASE)
    if storage_match:
        result["storage_tb"] = int(storage_match.group(1))

    # Condition keywords in title
    t = title.lower()
    if "open box" in t:
        result["condition"] = "Open Box"
    elif "for parts" in t or "not working" in t:
        result["condition"] = "For Parts"
    elif "cracked" in t or "frame split" in t or "odor" in t or "defect" in t:
        result["condition"] = "Defective"
    elif "refurbished" in t:
        result["condition"] = "Refurbished"
    elif "used" in t:
        result["condition"] = "Used"

    return result


def main():
    parser = argparse.ArgumentParser(description="Classify product lines from titles")
    parser.add_argument("--input", "-i", default="-", help="Input: stdin, JSON file, or CSV file")
    parser.add_argument("--field", default="title", help="Field name containing title (for CSV input)")
    parser.add_argument("--output", "-o", default="-", help="Output file")
    args = parser.parse_args()

    if args.input == "-":
        lines = [line.strip() for line in sys.stdin if line.strip()]
        if not lines:
            return
        raw = "\n".join(lines)
        try:
            items = json.loads(raw)
            if isinstance(items, dict):
                items = [items]
        except json.JSONDecodeError:
            items = [{"title": line} for line in lines]
    else:
        with open(args.input) as f:
            raw = f.read().strip()
        if raw.startswith("[") or raw.startswith("{"):
            items = json.loads(raw)
            if isinstance(items, dict):
                items = [items]
        else:
            items = []
            with open(args.input, newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    items.append(row)

    results = []
    for item in items:
        title = item.get(args.field, item.get("title", ""))
        if not title:
            continue
        cls = classify(title)
        results.append({**item, **cls})

    out = sys.stdout
    if args.output != "-":
        out = open(args.output, "w")
    try:
        json.dump(results, out, indent=2)
        out.write("\n")
    finally:
        if args.output != "-":
            out.close()


if __name__ == "__main__":
    main()
