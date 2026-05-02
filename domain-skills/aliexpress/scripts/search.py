#!/usr/bin/env python3
"""Batch search orchestrator for AliExpress component searches.

Workflow:
    # Layered search with early termination:
    python3 search.py plan "Ryzen AI Max+ 395" --base-terms "Strix Halo"
    python3 search.py plan "RTX 5090" --layers 2       # chip-only
    python3 search.py plan "RTX 5090" --layers 3       # + form-factor synonyms

    # Accumulating extraction (persists across navigations via localStorage):
    python3 search.py extract-js --reset                # clear accumulated results
    python3 search.py extract-js                        # extract current page
    python3 search.py extract-js --dump                 # dump accumulated results

    # Merge, dedup, filter, classify:
    python3 search.py merge results.json --existing data.csv \\
        --require "ryzen ai max" "395" --min-price 500
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent

# Extraction JS that accumulates across navigations via localStorage.
# Uses localStorage (key: __ae_results) to persist across page loads on the same origin.
# On each call, appends new results (deduped by product_id).
# Use --dump to output the combined array. Use --reset to clear.
EXTRACT_JS = r"""
() => {
  const stored = localStorage.getItem('__ae_results');
  const results = stored ? JSON.parse(stored) : [];
  const existing = new Set(results.map(r => r.product_id));
  const cards = document.querySelectorAll('a[class*="search-card-item"]');
  let added = 0;
  for (let card of cards) {
    const urlMatch = card.href?.match(/\/item\/(\d+)\.html/);
    if (!urlMatch) continue;
    const pid = urlMatch[1];
    if (existing.has(pid)) continue;
    existing.add(pid);
    const h3 = card.querySelector('h3');
    const title = h3?.innerText?.trim() || '';
    if (!title) continue;
    const cardText = card.innerText || '';
    const priceMatch = cardText.match(/AU\$([\d,]+\.?\d*)/);
    const price = priceMatch ? priceMatch[0] : '';
    results.push({ product_id: pid, title, price });
    added++;
  }
  localStorage.setItem('__ae_results', JSON.stringify(results));
  return { total: results.length, added, url: location.href };
}
""".strip()

EXTRACT_DUMP_JS = r"""
() => {
  const stored = localStorage.getItem('__ae_results');
  const results = stored ? JSON.parse(stored) : [];
  return { count: results.length, items: results };
}
""".strip()

EXTRACT_RESET_JS = r"""
() => {
  localStorage.removeItem('__ae_results');
  return { reset: true };
}
""".strip()


def parse_aud_price(price_str: str) -> float | None:
    """Extract numeric value from 'AU$X,XXX.XX' format."""
    if not price_str:
        return None
    import re
    m = re.search(r'([\d,]+\.?\d*)', price_str)
    if not m:
        return None
    try:
        return float(m.group(1).replace(',', ''))
    except ValueError:
        return None


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
    if args.dump:
        print(EXTRACT_DUMP_JS)
    elif args.reset:
        print(EXTRACT_RESET_JS)
    else:
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

    total_input = len(new_items)
    after_dedup = [i for i in new_items if i.get("product_id", "") not in existing_ids]
    duplicates_removed = total_input - len(after_dedup)

    # Price filter
    filtered_items = after_dedup
    if args.min_price is not None or args.max_price is not None:
        before_price = len(filtered_items)
        kept = []
        for item in filtered_items:
            price = parse_aud_price(item.get("price", ""))
            if price is None:
                kept.append(item)  # keep if price can't be parsed
                continue
            if args.min_price is not None and price < args.min_price:
                continue
            if args.max_price is not None and price > args.max_price:
                continue
            kept.append(item)
        filtered_items = kept
    price_filtered = len(after_dedup) - len(filtered_items)

    # Relevance filter
    before_relevance = len(filtered_items)
    if args.require:
        keywords = [k.lower() for k in args.require]
        filtered_items = [
            i for i in filtered_items
            if any(k in i.get("title", "").lower() for k in keywords)
        ]

    # Exclusion filter
    if args.exclude:
        exclude_kw = [k.lower() for k in args.exclude]
        filtered_items = [
            i for i in filtered_items
            if not any(k in i.get("title", "").lower() for k in exclude_kw)
        ]

    relevance_filtered = before_relevance - len(filtered_items)
    new_items = filtered_items

    # Classify
    classify_args = [sys.executable, str(SCRIPT_DIR / "classify_product_line.py"), "--input", "-"]
    proc = subprocess.run(classify_args, input=json.dumps(new_items), capture_output=True, text=True)
    classified = json.loads(proc.stdout)

    # Summary
    print(f"Existing: {len(existing_ids)} | Input: {total_input} | Duplicates: {duplicates_removed} | Price filtered: {price_filtered} | Title filtered: {relevance_filtered} | New: {len(new_items)}", file=sys.stderr)

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
    if args.products:
        gen_args.extend(["--products"] + args.products)

    proc = subprocess.run(gen_args, capture_output=True, text=True)
    all_lines = proc.stdout.strip().split("\n")
    all_queries = []
    for line in all_lines:
        if "\t" in line:
            label, url = line.split("\t", 1)
            all_queries.append((label, url))

    # Split into layers
    layers = {2: [], 3: [], 4: []}
    for label, url in all_queries:
        if label.startswith("L1:"):
            layers.setdefault(1, []).append((label, url))
        elif label.startswith("L2:"):
            layers[2].append((label, url))
        elif label.startswith("L3:"):
            layers[3].append((label, url))
        elif label.startswith("L4:"):
            layers[4].append((label, url))

    max_layer = args.layers

    # Layer 2: chip/component references (always run)
    l2 = layers.get(2, [])
    print(f"## Layer 2 — chip references ({len(l2)} URLs)")
    print("Run these first. If coverage is sufficient, stop here.")
    for label, url in l2:
        print(f"  {label}")
        print(f"  {url}")
        print()

    # Layer 3: form-factor synonyms (run if Layer 2 coverage is insufficient)
    l3 = layers.get(3, [])
    if max_layer >= 3 and l3:
        print(f"## Layer 3 — form-factor synonyms ({len(l3)} URLs)")
        print("Run if Layer 2 missed expected products. Each form-factor keyword")
        print("reaches a different slice of AliExpress's search index.")
        for label, url in l3:
            print(f"  {label}")
            print(f"  {url}")
            print()

    # Layer 4: spec-level
    l4 = layers.get(4, [])
    if max_layer >= 4 and l4:
        print(f"## Layer 4 — spec-level ({len(l4)} URLs)")
        for label, url in l4:
            print(f"  {label}")
            print(f"  {url}")
            print()

    # Early termination guidance
    total = len(l2) + (len(l3) if max_layer >= 3 else 0) + (len(l4) if max_layer >= 4 else 0)
    print(f"## Strategy ({total} URLs total)")
    print("1. Run Layer 2 queries, extract results")
    print("2. Check: did Layer 2 find all expected product lines?")
    print("   If yes → stop, skip Layer 3")
    print("   If no  → run Layer 3 form-factor synonyms for the chip terms that underperformed")
    print("3. Layer 4 is rarely needed — only for components with unusual specs")
    print()
    print("## Reset accumulated results (run first):")
    print("```javascript")
    print(EXTRACT_RESET_JS)
    print("```")
    print()
    print("## Extraction JS (accumulates across navigations via localStorage):")
    print("```javascript")
    print(EXTRACT_JS)
    print("```")
    print()
    print("## After all pages, dump accumulated results:")
    print("```javascript")
    print(EXTRACT_DUMP_JS)
    print("```")
    print()
    print("## Then merge:")
    print(f"python3 search.py merge results.json --existing <csv> \\")
    print(f"  --require <keywords> --min-price <floor>")


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
    ext.add_argument("--dump", action="store_true", help="Print dump JS (returns accumulated results)")
    ext.add_argument("--reset", action="store_true", help="Print reset JS (clears localStorage)")

    # merge
    mrg = sub.add_parser("merge", help="Merge, dedup, and classify results")
    mrg.add_argument("input", help="JSON file with extracted results")
    mrg.add_argument("--existing", help="Existing CSV to dedup against")
    mrg.add_argument("--require", nargs="*", help="Title must contain at least one keyword")
    mrg.add_argument("--exclude", nargs="*", help="Exclude titles containing any of these keywords")
    mrg.add_argument("--min-price", type=float, default=None, help="Minimum price in AUD (excludes noise below threshold)")
    mrg.add_argument("--max-price", type=float, default=None, help="Maximum price in AUD")

    # plan
    plan = sub.add_parser("plan", help="Generate layered search plan")
    plan.add_argument("chip")
    plan.add_argument("--base-terms", nargs="*")
    plan.add_argument("--products", nargs="*")
    plan.add_argument("--layers", type=int, default=3, choices=[2, 3, 4],
                      help="Max layer depth: 2=chip-only, 3=+form-factors (default), 4=+spec-level")

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
