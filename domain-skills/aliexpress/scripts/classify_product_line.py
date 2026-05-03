#!/usr/bin/env python3
"""Classify AliExpress listing titles into product lines and form factors.

Usage:
    echo 'GMKtec EVO-X2 AI Mini PC AMD Ryzen AI Max+ 395 128GB' | python3 classify_product_line.py
    python3 classify_product_line.py --input results.json
    python3 classify_product_line.py --csv .private-data/ryzen-aimax395-aliexpress-2026-05-02.csv --field title

Output: JSON with product_line, form_factor, ram_gb, storage_tb per listing.
"""

import argparse
import csv
import json
import re
import sys

# Product line patterns ordered by specificity (most specific first).
# Each tuple: (pattern, product_line, form_factor)
PRODUCT_PATTERNS: list[tuple[str, str, str]] = [
    # GPU patterns — standalone graphics cards (most specific first)
    (r"\bRTX\s*PRO\s*6000\b", "RTX PRO 6000 Blackwell", "standalone_gpu"),
    (r"\bRTX\s*6000\s+Ada\b", "RTX 6000 Ada", "standalone_gpu"),
    (r"\bRTX\s*A6000\b", "RTX A6000", "standalone_gpu"),
    (r"\bRTX\s*A5000\b", "RTX A5000", "standalone_gpu"),
    (r"\bRTX\s*A4500\b", "RTX A4500", "standalone_gpu"),
    (r"\bRTX\s*A4000\b", "RTX A4000", "standalone_gpu"),
    (r"\bRTX\s*A3000\b", "RTX A3000", "standalone_gpu"),
    (r"\bRTX\s*5090\b", "RTX 5090", "standalone_gpu"),
    (r"\bRTX\s*5080\b", "RTX 5080", "standalone_gpu"),
    (r"\bRTX\s*5070\b", "RTX 5070", "standalone_gpu"),
    (r"\bRTX\s*4090\b", "RTX 4090", "standalone_gpu"),
    (r"\bRTX\s*4080\b", "RTX 4080", "standalone_gpu"),
    (r"\bRTX\s*4070\b", "RTX 4070", "standalone_gpu"),
    (r"\bRTX\s*3090\b", "RTX 3090", "standalone_gpu"),
    (r"\bRTX\s*3080\b", "RTX 3080", "standalone_gpu"),
    (r"\bL40S\b.*\b(?:GPU|graphics|GDDR|accelerator|AI\s+training|deep\s+learning|tensor|rendering)\b", "NVIDIA L40S", "standalone_gpu"),
    # GPU server/system patterns
    (r"\b(?:AI\s+Server|GPU\s+Server|4U\s+Server)\b", "GPU Server", "server"),
    (r"\bGaming\s+(?:Desktop|PC|Computer)\b", "Gaming PC", "desktop"),
    # Mini-PC / system patterns
    (r"\bGMKtec\s+EVO-?X2\b", "GMKtec EVO-X2", "mini_pc"),
    (r"\bEVO-?X2\b", "GMKtec EVO-X2", "mini_pc"),
    (r"\bBosgame\s+M5\b", "Bosgame M5", "mini_pc"),
    (r"\bFEVM\s+FAEX9\b", "FEVM FAEX9", "mini_pc"),
    (r"\bFAEX9\b", "FEVM FAEX9", "mini_pc"),
    (r"\bFEVM\s+FAEX1\b", "FEVM FAEX1", "mini_pc"),
    (r"\bFAEX1\b", "FEVM FAEX1", "mini_pc"),
    (r"\bBeelink\s+GTR9\s+Pro\b", "Beelink GTR9 Pro", "mini_pc"),
    (r"\bGTR9\s+Pro\b", "Beelink GTR9 Pro", "mini_pc"),
    (r"\bOpenClaw\b", "OpenClaw", "mini_pc"),
    (r"\bMinisforum\s+MS-?S1\s+MAX\b", "Minisforum MS-S1 MAX", "mini_pc"),
    (r"\bMS-?S1\s+MAX\b", "Minisforum MS-S1 MAX", "mini_pc"),
    (r"\bSZBOX\b", "SZBOX", "mini_pc"),
    (r"\bVO-?X2\b", "VO-X2", "mini_pc"),
    (r"\bZ2\s+Mini\s+G1a\b", "Z2 Mini G1a", "mini_pc"),
    (r"\bLCFC-?H02\b", "LCFC-H02", "barebones"),
    (r"\bGPD\s+WIN\s*5\b", "GPD WIN 5", "handheld"),
    (r"\bOneXPlayer\s+Apex\s+MAX\+?\b", "OneXPlayer Apex MAX+", "handheld"),
    (r"\bOneXPlayer\s+Super\s+X\b", "OneXPlayer Super X", "tablet"),
    (r"\bOnexfly\s+Apex\b", "Onexfly Apex", "handheld"),
    (r"\bOneXFly\s+Apex\b", "Onexfly Apex", "handheld"),
    (r"\bAYANEO\s+NEXT\s*2\b", "AYANEO NEXT 2", "handheld"),
    (r"\bDGX\s+Spark\b", "DGX Spark", "mini_pc"),
    (r"\bDell\s+Pro\s+Max\b", "Dell Pro Max", "workstation"),
    (r"\b(?:CPU\s+)?(?:main\s*board|motherboard)\b", "Motherboard", "motherboard"),
    (r"\bJetson\s+AGX\s+Thor\b", "Jetson AGX Thor", "dev_board"),
]

FORM_FACTOR_OVERRIDES = [
    (r"\bhandheld\b", "handheld"),
    (r"\bgaming\s+console\b", "handheld"),
    (r"\btablet\b", "tablet"),
    (r"\b2-in-1\b", "tablet"),
    (r"\bworkstation\b", "mini_pc"),
    (r"\bmini\s+pc\b", "mini_pc"),
    (r"\bmini\s+host\b", "mini_pc"),
]


def classify(title: str) -> dict:
    t = title.lower()

    # Try product line patterns
    for pattern, product_line, form_factor in PRODUCT_PATTERNS:
        if re.search(pattern, title, re.IGNORECASE):
            result = {"product_line": product_line, "form_factor": form_factor}

            # Extract RAM
            ram_match = re.search(r"(\d+)\s*GB\s*(?:LPDDR|RAM|DDR)", title, re.IGNORECASE)
            if ram_match:
                result["ram_gb"] = int(ram_match.group(1))
            else:
                # Multi-RAM like "32/64/128"
                multi_ram = re.search(r"(\d+(?:/\d+)+)\s*GB", title)
                if multi_ram:
                    result["ram_gb"] = multi_ram.group(1)

            # Extract storage
            storage_match = re.search(r"(\d+)\s*(?:TB|T)\b", title, re.IGNORECASE)
            if storage_match:
                result["storage_tb"] = int(storage_match.group(1))

            return result

    # Fallback: generic classification from title keywords
    result = {"product_line": "Unknown", "form_factor": "unknown"}
    for pattern, ff in FORM_FACTOR_OVERRIDES:
        if re.search(pattern, title, re.IGNORECASE):
            result["form_factor"] = ff
            break

    if "ryzen" in t and ("ai max" in t or "max+ 395" in t or "max + 395" in t):
        result["product_line"] = "Generic Ryzen AI Max"
        result["form_factor"] = result["form_factor"] if result["form_factor"] != "unknown" else "mini_pc"

    return result


def main():
    parser = argparse.ArgumentParser(description="Classify product lines from titles")
    parser.add_argument("--input", "-i", default="-", help="Input: stdin, JSON file, or CSV file")
    parser.add_argument("--field", default="title", help="Field name containing title (for CSV input)")
    parser.add_argument("--output", "-o", default="-", help="Output file")
    args = parser.parse_args()

    # Load input
    if args.input == "-":
        lines = [line.strip() for line in sys.stdin if line.strip()]
        if not lines:
            return
        # Try JSON first
        raw = "\n".join(lines)
        try:
            items = json.loads(raw)
            if isinstance(items, dict):
                items = [items]
        except json.JSONDecodeError:
            # Plain titles, one per line
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

    # Classify
    results = []
    for item in items:
        title = item.get(args.field, item.get("title", ""))
        if not title:
            continue
        cls = classify(title)
        merged = {**item, **cls}
        results.append(merged)

    # Output
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
