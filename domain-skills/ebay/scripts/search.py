#!/usr/bin/env python3
"""eBay batch search orchestrator for component searches.

Generates search URLs, fetches pages via curl_cffi + cookie extraction,
extracts results, deduplicates, classifies, and exports to CSV.

Implements the 4-layer iterative discovery loop:
  Pass 1: L1 (pre-populated products) + L2-4 → discover + fetch
  Pass 2: L1 (iteratively discovered products) → catch remaining
  Coverage verification: auto-probes gaps and reports confidence

Usage:
    # Full search with 4-layer discovery and coverage verification:
    python3 search.py search "Ryzen AI Max+ 395" --output results.csv

    # With extra terms and product names:
    python3 search.py search "GB10" --synonyms "Grace Blackwell" --products "DGX Spark"

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
from urllib.parse import quote

SCRIPT_DIR = Path(__file__).parent


def derive_output_path(path: str, expected_suffix: str, replacement_suffix: str) -> str:
    source = Path(path)
    name = source.name
    if name.lower().endswith(expected_suffix.lower()):
        name = name[: -len(expected_suffix)]
    return str(source.with_name(f"{name}{replacement_suffix}"))


def append_missing_fields(fieldnames, extra_fields):
    fields = list(fieldnames or [])
    for field in extra_fields:
        if field not in fields:
            fields.append(field)
    return fields


def _run_child(cmd, **kwargs):
    proc = subprocess.run(cmd, **kwargs)
    if proc.returncode != 0:
        stderr = getattr(proc, "stderr", None) or ""
        stdout = getattr(proc, "stdout", None) or ""
        detail = (stderr or stdout).strip()
        message = f"child command failed with exit {proc.returncode}: {' '.join(map(str, cmd))}"
        if detail:
            message += f"\n{detail[-2000:]}"
        raise SystemExit(message)
    return proc

# --- Component-to-product mapping (pre-populates L1) ---

COMPONENT_PRODUCTS = {
    "ryzen ai max+ 395": [
        "ROG Flow Z13", "GPD WIN 5", "HP ZBook Ultra G1a", "HP Z2 G1a Mini",
        "HP ZBook Studio 99", "OneXPlayer Super X", "OneXPlayer Apex",
        "ONEXStation i1", "MinisForum MS-S1 Max", "MINIX ER939-AI",
        "NIMO Mini PC", "EVO-X2", "AYANEO NEXT 2", "Beelink GTR9 Pro",
    ],
    "gb10": [
        "DGX Spark", "Dell Pro Max", "Ascent GX10", "EdgeXpert",
    ],
}


def lookup_products(chip: str) -> list[str]:
    chip_lower = chip.lower()
    for key, products in COMPONENT_PRODUCTS.items():
        if key in chip_lower or chip_lower in key:
            return products
    return []


# --- Extraction ---

# Required fields for search results — field-level acceptance per
# interaction-skills/cross-domain-control-flow.md routing ladder.
# Note: condition is NOT available at search level — detail page required.
SEARCH_REQUIRED_FIELDS = {'listing_id', 'title', 'price'}


def extract_search_results(html: str) -> list[dict]:
    if 'Pardon Our Interruption' in html or 'Access Denied' in html or len(html) < 20_000:
        # Return structured unobservable result instead of empty list
        return [{"_unobservable": True, "_block_reason": "WAF" if 'Pardon Our Interruption' in html else ("access_denied" if 'Access Denied' in html else "empty_page")}]
    cards = re.split(r'(?=<li[^>]+data-listingid=)', html)
    results = []
    seen = set()
    missing_fields = {}
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
        location = loc_m.group(1).strip() if loc_m else None

        row = {
            'listing_id': lid,
            'url': (url_m.group(1).split('?')[0] if url_m else None) or f"https://www.ebay.com.au/itm/{lid}",
            'title': title,
            'price': price,
            'location': location,
        }
        for f in SEARCH_REQUIRED_FIELDS:
            if row.get(f) is None:
                missing_fields[f] = missing_fields.get(f, 0) + 1
        results.append(row)
    if missing_fields:
        print(f"  Field coverage warning: {missing_fields}", file=sys.stderr)
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


# --- Classification ---

def classify_product(title: str) -> str:
    t = title.lower()
    patterns = [
        # GPUs (checked first so GPU matches take priority over system matches)
        (r'rtx\s+5090', 'NVIDIA RTX 5090'),
        (r'rtx\s+4090', 'NVIDIA RTX 4090'),
        (r'rtx\s+3090', 'NVIDIA RTX 3090'),
        (r'l40s', 'NVIDIA L40S'),
        (r'rtx\s+a6000', 'NVIDIA RTX A6000'),
        (r'rtx\s+6000\s+ada', 'NVIDIA RTX 6000 Ada'),
        (r'rtx\s+pro\s+6000', 'NVIDIA RTX PRO 6000 Blackwell'),
        (r'rtx\s+a5000', 'NVIDIA RTX A5000'),
        # Systems
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

class Session:
    """Manages cookies with WAF-aware backoff and automatic refresh."""

    def __init__(self):
        self._cookies = None
        self._refresh_cookies()

    def _refresh_cookies(self):
        try:
            import browser_cookie3
            cj = browser_cookie3.chrome(domain_name="ebay.com.au")
            self._cookies = {c.name: c.value for c in cj}
        except Exception:
            self._cookies = {}

    @property
    def cookies(self):
        return self._cookies

    def refresh(self):
        print("  Refreshing cookies...", file=sys.stderr)
        self._refresh_cookies()

    def fetch_page(self, url: str, retries: int = 2) -> list[dict]:
        from curl_cffi import requests as cffi_requests
        for attempt in range(retries + 1):
            try:
                r = cffi_requests.get(url, headers=HEADERS, cookies=self._cookies,
                                      impersonate="chrome136", timeout=15)
                results = extract_search_results(r.text)
                if not results and len(r.text) > 100_000:
                    # Page loaded but no results — might be WAF captcha
                    if 'captcha' in r.text.lower() or 'Pardon' in r.text:
                        if attempt < retries:
                            wait = 30 * (attempt + 1)
                            print(f"  WAF blocked, waiting {wait}s (attempt {attempt+1}/{retries})...", file=sys.stderr)
                            time.sleep(wait)
                            self.refresh()
                            continue
                return results
            except Exception as e:
                if attempt < retries:
                    print(f"  ERROR: {e}, retrying...", file=sys.stderr)
                    time.sleep(10)
                else:
                    print(f"  ERROR: {e}", file=sys.stderr)
                    return [{"_unobservable": True, "_block_reason": "fetch_error"}]
        return [{"_unobservable": True, "_block_reason": "fetch_error"}]


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


# --- Relevance filtering ---

def make_relevance_filter(target_chip: str, min_price: float = 500.0, mode: str = "system") -> callable:
    chip_lower = target_chip.lower().strip()
    chip_id = re.search(r'(\d{3,})', target_chip)
    chip_id_str = chip_id.group(1) if chip_id else chip_lower

    # Disambiguation: when multiple GPU generations share the same numeric ID,
    # require the distinguishing qualifier adjacent to the number in the title.
    # Build regex patterns that match the chip as it appears in titles.
    ambiguous_ids = {'6000'}
    if chip_id_str in ambiguous_ids:
        # For "RTX A6000"       → require "a6000" or "a 6000" in title
        # For "RTX 6000 Ada"    → require "6000 ada" or "6000ada" in title
        # For "RTX PRO 6000"    → require "pro 6000" or "pro6000" in title
        before_match = re.search(r'(\w+)\s*' + chip_id_str, chip_lower)
        after_match = re.search(chip_id_str + r'\s*(\w+)', chip_lower)
        if before_match and before_match.group(1) != 'rtx':
            prefix = before_match.group(1)
            _pat = re.compile(re.escape(prefix) + r'\s*' + re.escape(chip_id_str))
        elif after_match:
            suffix = after_match.group(1)
            _pat = re.compile(re.escape(chip_id_str) + r'\s*' + re.escape(suffix))
        else:
            _pat = None

        if _pat:
            def match_fn(title_lower, _p=_pat):
                return bool(_p.search(title_lower))
        else:
            def match_fn(title_lower):
                return chip_id_str in title_lower
    else:
        def match_fn(title_lower):
            return chip_id_str in title_lower

    def is_relevant(item: dict) -> bool:
        title = item.get("title") if isinstance(item, dict) else None
        if not isinstance(title, str) or not title:
            return False
        t = title.lower()
        if not match_fn(t):
            return False
        price = item.get('price') or 0
        if not isinstance(price, (int, float)) or isinstance(price, bool):
            return False
        if price < min_price:
            return False
        if mode == "system":
            system_kw = ['laptop', 'pc', 'desktop', 'workstation', 'gaming', 'handheld',
                         'tablet', 'notebook', 'computer', 'mini pc', 'server', 'console',
                         'supercomputer', 'ai max', 'ryzen', 'pro max', 'flow', 'gpd win',
                         'zbook', 'onexplayer', 'onexfly', 'minisforum', 'minix', 'nimo',
                         'evo-x2', 'hp z2', 'convertible', '2-in-1', '2in1', 'dgx', 'dell']
            return any(kw in t for kw in system_kw)
        elif mode == "gpu":
            gpu_kw = ['rtx', 'gtx', 'radeon', 'gpu', 'graphics', 'video card', 'nvidia',
                      'geforce', 'quadro', 'a100', 'a6000', 'l40', 'h100', 'blackwell',
                      'ada', 'ampere', 'founders', 'ti', 'super', 'gb', 'gb', 'a5000']
            return any(kw in t for kw in gpu_kw)
        return True  # mode="any" — just chip_id + price filter
    return is_relevant


# --- Convergence-based pagination ---

def paginate_query(query: str, session: Session, is_relevant: callable,
                   all_listings: dict, delay: float = 3.0,
                   max_pages: int = 50, sort: str = "",
                   source_tag: str = "") -> tuple[int, int, bool]:
    """Fetch pages until convergence (0 new items from a full page).
    Returns (total_fetched, new_count, fully_converged)."""
    new_total = 0
    last_page_new = -1
    zero_streak = 0
    page = 0

    while page < max_pages:
        page += 1
        params = f"_nkw={quote(query)}&LH_BIN=1&_pgn={page}"
        if sort:
            params += f"&_sop={sort}"
        url = f"https://www.ebay.com.au/sch/i.html?{params}"
        items = session.fetch_page(url)
        if not items:
            # Empty response after retries — likely end of results or WAF block
            if zero_streak >= 1:
                break
            zero_streak += 1
            continue

        new_this_page = 0
        for i in items:
            if is_relevant(i) and i['listing_id'] not in all_listings:
                all_listings[i['listing_id']] = i
                i['query_source'] = source_tag or query
                new_this_page += 1
                new_total += 1

        # Convergence: 2 consecutive full pages with 0 new items
        if len(items) >= 50 and new_this_page == 0:
            zero_streak += 1
            if zero_streak >= 2:
                return new_total, page, True
        else:
            zero_streak = 0

        # Short page (last page of results)
        if len(items) < 50:
            return new_total, page, True

        # Same new count as last page = likely repeating (eBay loop)
        if new_this_page == last_page_new and new_this_page > 0:
            next_params = f"_nkw={quote(query)}&LH_BIN=1&_pgn={page+1}"
            if sort:
                next_params += f"&_sop={sort}"
            next_url = f"https://www.ebay.com.au/sch/i.html?{next_params}"
            next_items = session.fetch_page(next_url)
            if next_items:
                next_new = sum(1 for i in next_items if is_relevant(i) and i['listing_id'] not in all_listings)
                if next_new == new_this_page:
                    return new_total, page, True
            break

        last_page_new = new_this_page
        time.sleep(delay)

    return new_total, page, page >= max_pages


# --- Coverage verification ---

def run_coverage_verification(chip: str, session: Session, all_listings: dict,
                              is_relevant: callable, delay: float = 3.0) -> dict:
    """Probe remaining gaps and return coverage report."""
    chip_id = re.search(r'(\d{3,})', chip)
    chip_id_str = chip_id.group(1) if chip_id else chip.lower()

    report = {
        'total_listings': len(all_listings),
        'gaps_probed': 0,
        'new_from_gaps': 0,
        'probe_details': [],
        'coverage': 'UNKNOWN',
    }

    print("\n=== Coverage Verification ===", file=sys.stderr)

    # Gap 1: Sort variations (paginated to recover missing listings)
    for sop, label in [(15, "cheapest"), (16, "most expensive")]:
        new, pages, converged = paginate_query(chip, session, is_relevant,
                                                all_listings, delay=delay,
                                                max_pages=10, sort=str(sop),
                                                source_tag=f"verify:sort_{label}")
        report['gaps_probed'] += 1
        report['new_from_gaps'] += new
        report['probe_details'].append({'probe': f'sort_{label}', 'new': new})
        print(f"  Sort {label}: +{new} new ({pages} pages)", file=sys.stderr)
        time.sleep(delay)

    # Gap 2: Without "Ryzen" prefix
    alt_chip = chip.replace("Ryzen ", "")
    if alt_chip != chip:
        new, _, _ = paginate_query(alt_chip, session, is_relevant,
                                   all_listings, delay=delay, max_pages=3,
                                   source_tag="verify:no_ryzen_prefix")
        report['gaps_probed'] += 1
        report['new_from_gaps'] += new
        report['probe_details'].append({'probe': 'no_ryzen_prefix', 'new': new})
        print(f"  No 'Ryzen' prefix: +{new} new", file=sys.stderr)
        time.sleep(delay)

    # Gap 3: Known products not yet discovered
    known_products = lookup_products(chip)
    discovered_types = {classify_product(item['title']) for item in all_listings.values()}
    undiscovered = [p for p in known_products if p not in discovered_types]
    for product in undiscovered:
        q = f'{product} {chip}'
        new, _, _ = paginate_query(q, session, is_relevant,
                                   all_listings, delay=delay, max_pages=3,
                                   source_tag=f"verify:missing_product_{product}")
        report['gaps_probed'] += 1
        report['new_from_gaps'] += new
        report['probe_details'].append({'probe': f'missing_{product}', 'new': new})
        status = f"+{new}" if new else "0 (confirmed absent)"
        print(f"  Missing product '{product}': {status}", file=sys.stderr)
        time.sleep(delay)

    # Determine coverage confidence based on gap ratio, not absolute count
    total = len(all_listings)
    if total == 0 and report['gaps_probed'] == 0:
        report['coverage'] = 'UNKNOWN'
        print(f"\n  Coverage: UNKNOWN — 0 listings collected, 0 gaps probed", file=sys.stderr)
    elif total == 0:
        report['coverage'] = 'UNKNOWN'
        print(f"\n  Coverage: UNKNOWN — 0 listings but {report['gaps_probed']} gaps probed", file=sys.stderr)
    else:
        gap_ratio = report['new_from_gaps'] / total
        if report['new_from_gaps'] == 0:
            report['coverage'] = 'HIGH'
            print(f"\n  Coverage: HIGH — {report['gaps_probed']} gap probes found 0 new listings", file=sys.stderr)
        elif gap_ratio <= 0.03 or report['new_from_gaps'] <= 5:
            report['coverage'] = 'MEDIUM'
            print(f"\n  Coverage: MEDIUM — {report['new_from_gaps']} new from {report['gaps_probed']} probes ({gap_ratio:.1%} gap ratio)", file=sys.stderr)
        else:
            report['coverage'] = 'LOW'
            print(f"\n  Coverage: LOW — {report['new_from_gaps']} new from {report['gaps_probed']} probes ({gap_ratio:.1%} gap ratio), re-run recommended", file=sys.stderr)

    return report


# --- Commands ---

def cmd_search(args):
    session = Session()
    mode = getattr(args, 'mode', 'system')
    is_relevant = make_relevance_filter(args.chip, min_price=args.min_price, mode=mode)
    all_listings = {}

    # Build chip terms
    chip_terms = [args.chip] + (args.base_terms or [])
    pro_variant = args.chip.replace('+ ', '+ PRO ').replace('Max ', 'Max PRO ')
    if pro_variant != args.chip:
        chip_terms.append(pro_variant)

    layer2_queries = []
    for t in chip_terms:
        layer2_queries.append(f'"{t}"')
        layer2_queries.append(t)

    form_factors = args.form_factors or [
        "laptop", "mini PC", "workstation", "handheld", "desktop",
        "tablet", "2-in-1", "PC", "gaming", "notebook",
    ]
    layer3_queries = []
    for t in chip_terms[:2]:
        for ff in form_factors:
            layer3_queries.append(f'"{t}" {ff}')

    layer4_queries = args.spec_terms or []

    # Pre-populate L1 from component mapping + user-supplied products
    l1_products = set()
    mapped = lookup_products(args.chip)
    if mapped:
        l1_products.update(mapped)
        print(f"Pre-populated {len(mapped)} products from component mapping", file=sys.stderr)
    if args.products:
        l1_products.update(args.products)

    # --- Pass 1: L1 (pre-populated) + L2-4 ---
    print("=== Pass 1: L1 (pre-populated) + L2-4 ===", file=sys.stderr)

    # L1 queries first (pre-populated products)
    for product in sorted(l1_products):
        for q in [f'{product} "{args.chip}"', f'{product} {args.chip}']:
            new, pages, converged = paginate_query(q, session, is_relevant, all_listings, delay=args.delay)
            if new:
                ctag = "" if converged else " (not converged!)"
                print(f"  L1-pre: {q}: +{new} ({pages} pages){ctag}", file=sys.stderr)
            time.sleep(args.delay)

    # L2-4 queries
    pass1_queries = [(f"L2: {q}", q) for q in layer2_queries] + \
                    [(f"L3: {q}", q) for q in layer3_queries] + \
                    [(f"L4: {q}", q) for q in layer4_queries]

    for label, q in pass1_queries:
        new, pages, converged = paginate_query(q, session, is_relevant, all_listings, delay=args.delay)
        if new:
            ctag = "" if converged else " (not converged!)"
            print(f"  {label}: +{new} ({pages} pages){ctag}", file=sys.stderr)
        time.sleep(args.delay)

    print(f"\nPass 1 total: {len(all_listings)} unique listings", file=sys.stderr)

    # --- Discover additional product names ---
    discovered = set()
    for item in all_listings.values():
        pt = classify_product(item['title'])
        if pt != 'Other':
            discovered.add(pt)

    new_products = discovered - l1_products
    if new_products:
        print(f"Discovered {len(new_products)} additional product types: {', '.join(sorted(new_products))}", file=sys.stderr)
    else:
        print("No new product types discovered beyond pre-populated set", file=sys.stderr)

    # --- Pass 2: L1 (iteratively discovered) ---
    if new_products:
        print("\n=== Pass 2: L1 (iteratively discovered) ===", file=sys.stderr)
        for product in sorted(new_products):
            for q in [f'{product} "{args.chip}"', f'{product} {args.chip}']:
                new, pages, converged = paginate_query(q, session, is_relevant, all_listings, delay=args.delay)
                if new:
                    print(f"  L1-iter: {q}: +{new} ({pages} pages)", file=sys.stderr)
                time.sleep(args.delay)

    # --- Coverage verification ---
    report = run_coverage_verification(args.chip, session, all_listings, is_relevant, delay=args.delay)

    # --- Final summary ---
    print(f"\n=== Final: {len(all_listings)} unique listings | Coverage: {report['coverage']} ===", file=sys.stderr)

    product_counts = {}
    for item in all_listings.values():
        pt = classify_product(item['title'])
        product_counts[pt] = product_counts.get(pt, 0) + 1

    for pt, cnt in sorted(product_counts.items(), key=lambda x: -x[1]):
        print(f"  {pt}: {cnt}", file=sys.stderr)

    # --- Export ---
    if args.output:
        fieldnames = ['listing_id', 'title', 'price_aud', 'product_type',
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
                    'seller_location': item['location'],
                    'layer': item.get('layer', ''),
                    'query_source': item.get('query_source', ''),
                    'url': item.get('url', ''),
                })
        print(f"\nExported to {args.output}", file=sys.stderr)

        # Write coverage report alongside CSV
        report_path = derive_output_path(args.output, '.csv', '-coverage.json')
        report['final_count'] = len(all_listings)
        report['product_counts'] = product_counts
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)
        print(f"Coverage report: {report_path}", file=sys.stderr)
    else:
        for item in sorted(all_listings.values(), key=lambda x: x.get('price') or 0):
            item['product_type'] = classify_product(item['title'])
        print(json.dumps(list(all_listings.values()), indent=2))


def cmd_verify(args):
    from curl_cffi import requests as cffi_requests
    session = Session()
    listings = []
    with open(args.input, newline='') as f:
        reader = csv.DictReader(f)
        input_fieldnames = list(reader.fieldnames or [])
        for row in reader:
            listings.append(row)

    print(f"Verifying {len(listings)} listings...", file=sys.stderr)
    results = []
    for i, row in enumerate(listings):
        lid = row['listing_id']
        url = f"https://www.ebay.com.au/itm/{lid}"
        try:
            r = cffi_requests.get(url, headers=HEADERS, cookies=session.cookies, impersonate="chrome136", timeout=15)
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

    output = args.output or derive_output_path(args.input, '.csv', '-verified.csv')
    trust_fields = ['seller_name', 'feedback_pct', 'feedback_count', 'trust_flag']
    fieldnames = list(results[0].keys()) if results else append_missing_fields(input_fieldnames, trust_fields)
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
    _run_child(gen_args)


def main():
    parser = argparse.ArgumentParser(description="eBay batch search orchestrator")
    sub = parser.add_subparsers(dest="command")

    s = sub.add_parser("search", help="Full 4-layer search with fetch and coverage verification")
    s.add_argument("chip", help="Chip/component name")
    s.add_argument("--base-terms", nargs="*", dest="base_terms")
    s.add_argument("--synonyms", nargs="*", dest="base_terms")
    s.add_argument("--form-factors", nargs="*", dest="form_factors")
    s.add_argument("--modifiers", nargs="*", dest="form_factors")
    s.add_argument("--products", nargs="*")
    s.add_argument("--spec-terms", nargs="*")
    s.add_argument("--min-price", type=float, default=500.0, help="Minimum price filter")
    s.add_argument("--mode", choices=["system", "gpu", "any"], default="system",
                   help="Relevance mode: system=systems only, gpu=GPUs only, any=chip_id match only")
    s.add_argument("--delay", type=float, default=3.0, help="Delay between requests (seconds)")
    s.add_argument("--output", "-o", help="Output CSV path")

    v = sub.add_parser("verify", help="Verify seller trust from CSV")
    v.add_argument("input", help="CSV with listing_id column")
    v.add_argument("--output", "-o", help="Output CSV path")

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
