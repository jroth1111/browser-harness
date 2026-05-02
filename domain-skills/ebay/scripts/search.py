#!/usr/bin/env python3
"""eBay batch search orchestrator for component searches.

Generates search URLs, fetches pages via curl_cffi + cookie extraction,
extracts results, deduplicates, classifies, and exports to CSV.

Implements the 4-layer iterative discovery loop:
  Pass 1: layers 2-4 → discover products → extract unique product names
  Pass 2: layer 1 queries for each discovered product name → new listings
  Deduplicate across all passes by listing ID

Usage:
    # Full search with 4-layer discovery:
    python3 search.py "Ryzen AI Max+ 395" --output results.csv

    # With extra terms and product names:
    python3 search.py "GB10" --base-terms "Grace Blackwell" --products "DGX Spark"

    # Seller trust verification on results:
    python3 search.py verify results.csv

    # Generate URLs only (no fetching):
    python3 search.py urls "RTX 5090" --products "RTX 5090"

Requires: curl_cffi, browser_cookie3 (auto-installed via uv)
"""

import argparse
import csv
import json
import re
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent

# --- Extraction ---

def extract_search_results(html: str) -> list[dict]:
    if 'Pardon Our Interruption' in html or 'Access Denied' in html or len(html) < 20_000:
        return []
    cards = re.split(r'(?=<li[^>]+data-listingid=)', html)
    results = []
    seen = set()
    for card in cards[1:]:
        lid_m = re.search(r'data-listingid="?(\d+)"?', card)
        if not lid_m:
            continue
        lid = lid_m.group(1)
        if lid in seen:
            continue
        seen.add(lid)

        url_m = re.search(r'href="?(https://(?:www\.)?ebay\.com\.au/itm/(\d+))"?', card)
        title_m = re.search(r's-card__title[^>]*>.*?primary[^>]*>([^<]+)', card, re.DOTALL)
        title = title_m.group(1).strip() if title_m else None
        if not title or title == 'Shop on eBay':
            continue

        price_m = re.search(r'class="[^"]*price[^"]*">[^<]*\$([0-9,\.]+)<', card)
        if not price_m:
            price_m = re.search(r'price">[^<]*\$([0-9,\.]+)<', card)
        price = float(price_m.group(1).replace(',', '')) if price_m else None

        loc_m = re.search(r'from\s+([^<]+?)(?:\s*</)', card)
        location = loc_m.group(1).strip() if loc_m else 'Unknown'

        results.append({
            'listing_id': lid,
            'url': (url_m.group(1).split('?')[0] if url_m else None) or f"https://www.ebay.com.au/itm/{lid}",
            'title': title,
            'price': price,
            'location': location,
        })
    return results


def extract_seller_trust(html: str) -> dict:
    spans = [m.group(1) for m in re.finditer(r'ux-textspans[^>]*>([^<]+)</span>', html)]
    seller_name = None
    feedback_pct = None
    feedback_count = None

    for s in spans:
        if 'positive' in s.lower() and '%' in s:
            feedback_pct = s
        if s.startswith('(') and s.endswith(')'):
            inner = s[1:-1].replace(',', '').replace(' ', '')
            if inner.isdigit():
                feedback_count = int(inner)

    for i, s in enumerate(spans):
        if feedback_count is not None and s == f"({feedback_count})" and i > 0:
            seller_name = spans[i - 1]
            break

    pct_val = None
    if feedback_pct:
        m = re.search(r'(\d+\.?\d*)%', feedback_pct)
        if m:
            pct_val = float(m.group(1))

    count_val = feedback_count if feedback_count is not None else 0
    if count_val < 100 or pct_val is None or pct_val < 95:
        flag = 'HIGH_RISK'
    elif pct_val < 98 or count_val < 500:
        flag = 'MODERATE_RISK'
    else:
        flag = 'OK'

    return {
        'seller': seller_name or 'UNKNOWN',
        'feedback_count': count_val,
        'pct_val': pct_val,
        'flag': flag,
    }


# --- Classification (inline, also available via classify_product_line.py) ---

def classify_product(title: str) -> str:
    t = title.lower()
    patterns = [
        (r'rog\s+flow\s+z13', 'ASUS ROG Flow Z13'),
        (r'rog\s+flow\s+x13', 'ASUS ROG Flow X13'),
        (r'gpd\s+win\s*5', 'GPD WIN 5'),
        (r'zbook\s+ultra\s+(?:14\s+)?g1a', 'HP ZBook Ultra G1a'),
        (r'hp\s+z2\s+(?:mini\s+)?g1a', 'HP Z2 G1a Mini'),
        (r'z2\s+mini\s+g1a', 'HP Z2 G1a Mini'),
        (r'zbook\s+studio\s+99', 'HP ZBook Studio 99'),
        (r'onexplayer\s+super\s+x', 'OneXPlayer Super X'),
        (r'onexplayer\s+apex', 'OneXPlayer Apex'),
        (r'onexfly\s+apex', 'OneXPlayer Apex'),
        (r'onexstation\s+i1', 'OneXPlayer ONEXStation i1'),
        (r'minisforum\s+ms-?s1\s+max', 'MinisForum MS-S1 Max'),
        (r'ms-?s1\s+max', 'MinisForum MS-S1 Max'),
        (r'minix.*er939', 'MINIX ER939-AI'),
        (r'er939-?ai', 'MINIX ER939-AI'),
        (r'nimo\s+mini\s+pc', 'NIMO Mini PC'),
        (r'evo-?x2', 'EVO-X2 Mini PC'),
        (r'dgx\s+spark', 'DGX Spark'),
        (r'dell\s+pro\s+max', 'Dell Pro Max'),
    ]
    for pattern, name in patterns:
        if re.search(pattern, t):
            return name
    return 'Other'


# --- HTTP session ---

def make_session():
    try:
        import browser_cookie3
        from curl_cffi import requests as cffi_requests
        cj = browser_cookie3.chrome(domain_name="ebay.com.au")
        cookies = {c.name: c.value for c in cj}
    except Exception:
        cookies = {}

    return cookies


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch_page(url: str, cookies: dict, delay: float = 3.0) -> list[dict]:
    from curl_cffi import requests as cffi_requests
    try:
        r = cffi_requests.get(url, headers=HEADERS, cookies=cookies, impersonate="chrome136", timeout=15)
        return extract_search_results(r.text)
    except Exception as e:
        print(f"  ERROR: {e}", file=sys.stderr)
        return []


# --- Relevance filtering ---

def make_relevance_filter(target_chip: str, min_price: float = 500.0) -> callable:
    def is_relevant(item: dict) -> bool:
        t = item['title'].lower()
        if target_chip.lower() not in t:
            return False
        price = item.get('price') or 0
        if price < min_price:
            return False
        system_kw = ['laptop', 'pc', 'desktop', 'workstation', 'gaming', 'handheld',
                     'tablet', 'notebook', 'computer', 'mini pc', 'server', 'console',
                     'supercomputer', 'ai max', 'ryzen', 'pro max', 'flow', 'gpd win',
                     'zbook', 'onexplayer', 'onexfly', 'minisforum', 'minix', 'nimo',
                     'evo-x2', 'hp z2', 'convertible', '2-in-1', '2in1', 'dgx', 'dell']
        return any(kw in t for kw in system_kw)
    return is_relevant


# --- Commands ---

def cmd_search(args):
    from curl_cffi import requests as cffi_requests

    cookies = make_session()
    is_relevant = make_relevance_filter(args.chip, min_price=args.min_price)
    all_listings = {}
    query_stats = []

    # Layer 2: chip references
    chip_terms = [args.chip] + (args.base_terms or [])
    # Add PRO variant
    pro_variant = args.chip.replace('+ ', '+ PRO ').replace('Max ', 'Max PRO ')
    if pro_variant != args.chip:
        chip_terms.append(pro_variant)

    layer2_queries = []
    for t in chip_terms:
        layer2_queries.append(f'"{t}"')
        layer2_queries.append(t)  # unquoted version

    # Layer 3: category + architecture
    form_factors = args.form_factors or [
        "laptop", "mini PC", "workstation", "handheld", "desktop",
        "tablet", "2-in-1", "PC", "gaming", "notebook",
    ]
    layer3_queries = []
    for t in chip_terms[:2]:  # Only use primary chip terms for layer 3
        for ff in form_factors:
            layer3_queries.append(f'"{t}" {ff}')

    # Layer 4: spec-level
    layer4_queries = args.spec_terms or []

    # --- Pass 1: Layers 2-4 ---
    print("=== Pass 1: Layers 2-4 ===", file=sys.stderr)
    pass1_queries = [(f"L2: {q}", q) for q in layer2_queries] + \
                    [(f"L3: {q}", q) for q in layer3_queries] + \
                    [(f"L4: {q}", q) for q in layer4_queries]

    for label, q in pass1_queries:
        new = 0
        for page in range(1, args.pages + 1):
            from urllib.parse import quote
            url = f"https://www.ebay.com.au/sch/i.html?_nkw={quote(q)}&LH_BIN=1&_pgn={page}"
            items = fetch_page(url, cookies)
            if not items:
                break
            for i in items:
                if is_relevant(i) and i['listing_id'] not in all_listings:
                    all_listings[i['listing_id']] = i
                    i['query_source'] = q
                    i['layer'] = label.split(':')[0].strip()
                    new += 1
            if len(items) < 50:
                break
            time.sleep(args.delay)

        query_stats.append((label, new))
        tag = f" (+{new})" if new else ""
        print(f"  {label}: {new} new{tag}", file=sys.stderr)
        time.sleep(args.delay)

    print(f"\nPass 1 total: {len(all_listings)} unique listings", file=sys.stderr)

    # --- Discover product names ---
    discovered = set()
    for item in all_listings.values():
        pt = classify_product(item['title'])
        if pt != 'Other':
            discovered.add(pt)
    print(f"Discovered {len(discovered)} product types", file=sys.stderr)

    # --- Pass 2: Layer 1 ---
    print("\n=== Pass 2: Layer 1 (product names) ===", file=sys.stderr)
    for product in sorted(discovered):
        for q in [f'{product} "{args.chip}"', f'{product} {args.chip}']:
            new = 0
            for page in range(1, args.pages + 1):
                from urllib.parse import quote
                url = f"https://www.ebay.com.au/sch/i.html?_nkw={quote(q)}&LH_BIN=1&_pgn={page}"
                items = fetch_page(url, cookies)
                if not items:
                    break
                for i in items:
                    if is_relevant(i) and i['listing_id'] not in all_listings:
                        all_listings[i['listing_id']] = i
                        i['query_source'] = q
                        i['layer'] = 'L1'
                        new += 1
                if len(items) < 50:
                    break
                time.sleep(args.delay)

            if new:
                print(f"  L1: {q}: +{new} new", file=sys.stderr)
            time.sleep(args.delay)

    # --- Classify and export ---
    print(f"\n=== Final: {len(all_listings)} unique listings ===", file=sys.stderr)

    product_counts = {}
    for item in all_listings.values():
        pt = classify_product(item['title'])
        product_counts[pt] = product_counts.get(pt, 0) + 1

    for pt, cnt in sorted(product_counts.items(), key=lambda x: -x[1]):
        print(f"  {pt}: {cnt}", file=sys.stderr)

    if args.output:
        fieldnames = ['listing_id', 'title', 'price_aud', 'product_type', 'form_factor',
                      'seller_location', 'layer', 'query_source', 'url']
        with open(args.output, 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for item in sorted(all_listings.values(), key=lambda x: x.get('price') or 0):
                pt = classify_product(item['title'])
                w.writerow({
                    'listing_id': item['listing_id'],
                    'title': item['title'],
                    'price_aud': item.get('price', ''),
                    'product_type': pt,
                    'form_factor': item.get('layer', ''),
                    'seller_location': item['location'],
                    'layer': item.get('layer', ''),
                    'query_source': item.get('query_source', ''),
                    'url': item.get('url', ''),
                })
        print(f"\nExported to {args.output}", file=sys.stderr)
    else:
        # Output JSON to stdout
        for item in sorted(all_listings.values(), key=lambda x: x.get('price') or 0):
            item['product_type'] = classify_product(item['title'])
        print(json.dumps(list(all_listings.values()), indent=2))


def cmd_verify(args):
    """Verify seller trust for listings in a CSV."""
    from curl_cffi import requests as cffi_requests

    cookies = make_session()
    listings = []
    with open(args.input, newline='') as f:
        for row in csv.DictReader(f):
            listings.append(row)

    print(f"Verifying {len(listings)} listings...", file=sys.stderr)
    results = []
    for i, row in enumerate(listings):
        lid = row['listing_id']
        url = f"https://www.ebay.com.au/itm/{lid}"
        try:
            r = cffi_requests.get(url, headers=HEADERS, cookies=cookies, impersonate="chrome136", timeout=15)
            trust = extract_seller_trust(r.text)
            row['seller_name'] = trust['seller']
            row['feedback_pct'] = trust['pct_val'] or ''
            row['feedback_count'] = trust['feedback_count']
            row['trust_flag'] = trust['flag']
            results.append(row)
            print(f"  [{i+1}/{len(listings)}] {lid} | {trust['seller']:20s} | {trust['pct_val']}% {trust['feedback_count']}fb | {trust['flag']}", file=sys.stderr)
        except Exception as e:
            print(f"  [{i+1}/{len(listings)}] {lid} | ERROR: {e}", file=sys.stderr)
            row['seller_name'] = ''
            row['feedback_pct'] = ''
            row['feedback_count'] = ''
            row['trust_flag'] = 'ERROR'
            results.append(row)
        time.sleep(2)

    output = args.output or args.input.replace('.csv', '-verified.csv')
    fieldnames = list(results[0].keys()) if results else []
    with open(output, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(results)
    print(f"\nExported {len(results)} verified listings to {output}", file=sys.stderr)


def cmd_urls(args):
    gen_args = [
        sys.executable,
        str(SCRIPT_DIR / "generate_search_urls.py"),
        args.chip,
        "--pages", str(args.pages),
    ]
    if args.base_terms:
        gen_args.extend(["--base-terms"] + args.base_terms)
    if args.products:
        gen_args.extend(["--products"] + args.products)
    if args.form_factors:
        gen_args.extend(["--form-factors"] + args.form_factors)
    if args.spec_terms:
        gen_args.extend(["--spec-terms"] + args.spec_terms)
    if args.location:
        gen_args.extend(["--location", args.location])
    subprocess.run(gen_args)


def main():
    parser = argparse.ArgumentParser(description="eBay batch search orchestrator")
    sub = parser.add_subparsers(dest="command")

    # search (default)
    s = sub.add_parser("search", help="Full 4-layer search with fetch")
    s.add_argument("chip", help="Chip/component name")
    s.add_argument("--base-terms", nargs="*")
    s.add_argument("--form-factors", nargs="*")
    s.add_argument("--products", nargs="*")
    s.add_argument("--spec-terms", nargs="*")
    s.add_argument("--pages", type=int, default=3)
    s.add_argument("--min-price", type=float, default=500.0, help="Minimum price filter")
    s.add_argument("--delay", type=float, default=3.0, help="Delay between requests (seconds)")
    s.add_argument("--output", "-o", help="Output CSV path")

    # verify
    v = sub.add_parser("verify", help="Verify seller trust from CSV")
    v.add_argument("input", help="CSV with listing_id column")
    v.add_argument("--output", "-o", help="Output CSV path")

    # urls
    u = sub.add_parser("urls", help="Generate search URLs only")
    u.add_argument("chip")
    u.add_argument("--base-terms", nargs="*")
    u.add_argument("--form-factors", nargs="*")
    u.add_argument("--products", nargs="*")
    u.add_argument("--spec-terms", nargs="*")
    u.add_argument("--pages", type=int, default=3)
    u.add_argument("--location", default="")

    args = parser.parse_args()
    if args.command == "search" or args.command is None:
        if hasattr(args, 'chip'):
            cmd_search(args)
        else:
            parser.print_help()
    elif args.command == "verify":
        cmd_verify(args)
    elif args.command == "urls":
        cmd_urls(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
