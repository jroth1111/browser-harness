#!/usr/bin/env python3
"""Batch search orchestrator for AliExpress component searches.

Generates search URLs, provides the browser extraction snippet, then
deduplicates and classifies results against an existing CSV.

Workflow:
    1. Generate URLs:
       python3 search.py generate "Ryzen AI Max+ 395" --base-terms "Strix Halo"

    2. Print extraction JS (paste into browser for each URL):
       python3 search.py extract-js

    3. After extracting all pages, combine and dedup:
       python3 search.py merge results.json --existing .private-data/ryzen-aimax395-aliexpress-2026-05-02.csv

    4. One-shot: generate URLs with inline extraction instructions:
       python3 search.py plan "Ryzen AI Max+ 395"
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent

EXTRACT_JS = r"""
() => {
  const links = document.querySelectorAll('a[href*="/item/"]');
  const results = [];
  const seen = new Set();
  links.forEach(a => {
    const urlMatch = a.href.match(/\/item\/(\d+)\.html/);
    if (!urlMatch) return;
    const pid = urlMatch[1];
    if (seen.has(pid)) return;
    seen.add(pid);
    const h3 = a.querySelector('h3');
    const title = h3?.innerText?.trim() || '';
    if (!title) return;
    const priceEl = a.querySelector('[class*="price"]');
    const price = priceEl?.innerText?.trim() || '';
    results.push({ product_id: pid, title: title.substring(0, 200), price: price.substring(0, 30) });
  });
  return results;
}
""".strip()


def cmd_generate(args):
    gen_args = [
        sys.executable,
        str(SCRIPT_DIR / "generate_search_urls.py"),
        args.chip,
        "--sort", args.sort,
    ]
    if args.base_terms:
        gen_args.extend(["--base-terms"] + args.base_terms)
    if args.form_factors:
        gen_args.extend(["--form-factors"] + args.form_factors)
    if args.products:
        gen_args.extend(["--products"] + args.products)
    if args.spec_terms:
        gen_args.extend(["--spec-terms"] + args.spec_terms)
    if args.urls_only:
        gen_args.append("--urls-only")

    subprocess.run(gen_args)


def cmd_extract_js(args):
    print(EXTRACT_JS)


def cmd_merge(args):
    with open(args.input) as f:
        new_items = json.load(f)

    existing_ids = set()
    if args.existing:
        import csv
        with open(args.existing, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                pid = row.get("product_id", "").strip()
                if pid:
                    existing_ids.add(pid)

    before = len(new_items)
    new_items = [i for i in new_items if i.get("product_id", "") not in existing_ids]

    # Classify
    classify_args = [sys.executable, str(SCRIPT_DIR / "classify_product_line.py"), "--input", "-"]
    proc = subprocess.run(classify_args, input=json.dumps(new_items), capture_output=True, text=True)
    classified = json.loads(proc.stdout)

    # Summary
    print(f"Existing: {len(existing_ids)} | Extracted: {before} | New: {len(new_items)} | Duplicates: {before - len(new_items)}", file=sys.stderr)

    product_lines = {}
    for item in classified:
        pl = item.get("product_line", "unknown")
        if pl not in product_lines:
            product_lines[pl] = 0
        product_lines[pl] += 1

    print(f"\nProduct lines ({len(product_lines)}):", file=sys.stderr)
    for pl, count in sorted(product_lines.items(), key=lambda x: -x[1]):
        print(f"  {pl}: {count}", file=sys.stderr)

    print(json.dumps(classified, indent=2))


def cmd_plan(args):
    print(f"# Search plan for: {args.chip}")
    print()

    gen_args = [
        sys.executable,
        str(SCRIPT_DIR / "generate_search_urls.py"),
        args.chip,
        "--sort", "volume",
    ]
    if args.base_terms:
        gen_args.extend(["--base-terms"] + args.base_terms)

    proc = subprocess.run(gen_args, capture_output=True, text=True)
    lines = proc.stdout.strip().split("\n")

    print(f"## URLs to search ({len(lines)}):")
    for line in lines:
        label, url = line.split("\t", 1)
        print(f"  {label}: {url}")

    print()
    print("## Browser extraction JS:")
    print("```javascript")
    print(EXTRACT_JS)
    print("```")

    print()
    print("## Workflow:")
    print("1. Navigate to each URL above")
    print("2. Run the extraction JS in the browser console")
    print("3. Save all results to a JSON file")
    print("4. Run: python3 search.py merge results.json --existing <csv>")


def main():
    parser = argparse.ArgumentParser(description="AliExpress batch search orchestrator")
    sub = parser.add_subparsers(dest="command")

    # generate
    gen = sub.add_parser("generate", help="Generate search URLs")
    gen.add_argument("chip")
    gen.add_argument("--base-terms", nargs="*")
    gen.add_argument("--form-factors", nargs="*")
    gen.add_argument("--products", nargs="*")
    gen.add_argument("--spec-terms", nargs="*")
    gen.add_argument("--sort", default="volume")
    gen.add_argument("--urls-only", action="store_true")

    # extract-js
    ext = sub.add_parser("extract-js", help="Print browser extraction JS snippet")

    # merge
    mrg = sub.add_parser("merge", help="Merge, dedup, and classify results")
    mrg.add_argument("input", help="JSON file with extracted results")
    mrg.add_argument("--existing", help="Existing CSV to dedup against")

    # plan
    plan = sub.add_parser("plan", help="Generate full search plan")
    plan.add_argument("chip")
    plan.add_argument("--base-terms", nargs="*")

    args = parser.parse_args()
    if args.command == "generate":
        cmd_generate(args)
    elif args.command == "extract-js":
        cmd_extract_js(args)
    elif args.command == "merge":
        cmd_merge(args)
    elif args.command == "plan":
        cmd_plan(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
