#!/usr/bin/env python3
"""z2u.com exhaustive multi-category product search.

Four-state field semantics (OWA-correct):
  - Actual value       = field found and extracted
  - null               = field confirmed absent on this page type
  - "__UNOBSERVABLE__" = page blocked or broken, could not inspect
  - key omitted        = field not checked (different page type)

Workflow:
    python3 search.py plan "google" --filter "ultra" --output results.csv
    python3 search.py plan "chatgpt" --output chatgpt_all.csv

    # Accumulating extraction (persists across navigations via localStorage):
    python3 search.py extract-js --reset                # clear all localStorage
    python3 search.py extract-js --categories            # extract categories from search page
    python3 search.py extract-js --products              # extract products from category page
    python3 search.py extract-js --detail                # extract detail from product page
    python3 search.py extract-js --coverage              # coverage probe: extracted vs declared
    python3 search.py extract-js --dump                  # dump all accumulated results

    # Merge, filter, export:
    python3 search.py merge results.json --filter "ultra" --output results.csv

    # Verify field-level coverage (field triage):
    python3 search.py verify results.json
"""

import argparse
import csv
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent


def derive_output_path(path: str, expected_suffix: str, replacement_suffix: str) -> str:
    source = Path(path)
    name = source.name
    if name.lower().endswith(expected_suffix.lower()):
        name = name[: -len(expected_suffix)]
    return str(source.with_name(f"{name}{replacement_suffix}"))


# --- Field semantics ---
# In extraction JS:
#   value                = found and extracted
#   null                 = confirmed absent on this page/entity type
#   "__UNOBSERVABLE__"   = page blocked or broken, could not inspect
#   key absent           = not checked (entity type doesn't have this field)
#
# In CSV output:
#   value          = found
#   (absent)       = confirmed absent
#   (unobservable) = page was inaccessible
#   (not checked)  = field not applicable to this entity type

ABSENT = "(absent)"
UNOBSERVABLE = "(unobservable)"
NOT_CHECKED = "(not checked)"

# --- JS Extraction Snippets ---

EXTRACT_RESET_JS = r"""
() => {
  localStorage.removeItem('__z2u_categories');
  localStorage.removeItem('__z2u_products');
  localStorage.removeItem('__z2u_details');
  localStorage.removeItem('__z2u_coverage');
  return { reset: true };
}
""".strip()

EXTRACT_SET_PAGE_SIZE_JS = r"""
() => {
  const select = document.querySelector('select');
  if (select) {
    select.value = '400';
    select.dispatchEvent(new Event('change', { bubbles: true }));
    const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.trim() === 'Confirm');
    if (btn) { btn.click(); return { set: true, clicked: true }; }
    return { set: true, clicked: false };
  }
  return { set: false };
}
""".strip()

EXTRACT_CATEGORIES_JS = r"""
() => {
  const stored = localStorage.getItem('__z2u_categories');
  const results = stored ? JSON.parse(stored) : [];
  const existing = new Set(results.map(r => r.url));
  const links = document.querySelectorAll('a[href]');
  let added = 0;
  for (const link of links) {
    const h3 = link.querySelector('h3');
    if (!h3) continue;
    const text = link.textContent || '';
    const offerMatch = text.match(/(\d+)\s*Offers/);
    if (!offerMatch) continue;
    const url = link.href;
    if (existing.has(url)) continue;
    existing.add(url);
    results.push({
      name: h3.textContent.trim(),
      url: url,
      offer_count: parseInt(offerMatch[1]),
      _extracted_from: location.href,
      _extracted_at: new Date().toISOString()
    });
    added++;
  }
  localStorage.setItem('__z2u_categories', JSON.stringify(results));
  // Quota guard: check localStorage has room before reporting success
  try { localStorage.getItem('__z2u_categories'); } catch(e) {
    return { total: results.length, added: added, url: location.href,
             _quota_error: true, _message: 'localStorage quota exceeded — dump now' };
  }
  // Container diagnostic: report whether expected elements exist
  const containers = document.querySelectorAll('a[href] h3');
  const pageHasContainers = containers.length > 0;
  return {
    total: results.length,
    added: added,
    url: location.href,
    containers_found: containers.length,
    suspect: (added === 0 && pageHasContainers)
  };
}
""".strip()

EXTRACT_PRODUCTS_JS = r"""
(categoryName) => {
  const stored = localStorage.getItem('__z2u_products');
  const results = stored ? JSON.parse(stored) : [];
  const existing = new Set(results.map(r => r.url));
  let added = 0;

  // Product aggregations: /product-{id}/
  // CSS classes: span.title, span.fromCountry, span.fromAttr,
  //   span.numberTxt, span.priceTxt, del (original price)
  document.querySelectorAll('a[href*="/product-"]').forEach(link => {
    const url = link.href.split('?')[0];
    if (existing.has(url)) return;
    existing.add(url);
    const urlMatch = link.href.match(/\/product-(\d+)\//);
    const titleEl = link.querySelector('.title') || link.querySelector('h3');
    const title = titleEl ? titleEl.textContent.trim() : null;
    const countryEl = link.querySelector('.fromCountry');
    const attrEl = link.querySelector('.fromAttr');
    const region = countryEl ? countryEl.textContent.trim() : null;
    const attr = attrEl ? attrEl.textContent.trim() : null;
    const numberEl = link.querySelector('.numberTxt');
    const offerCountMatch = numberEl ? numberEl.textContent.match(/(\d+)/) : null;
    const priceEl = link.querySelector('.priceTxt');
    const price = priceEl ? priceEl.textContent.trim() : null;
    const text = (link.textContent || '');
    const soldOut = text.includes('sold out');
    results.push({
      type: 'product',
      product_id: urlMatch ? urlMatch[1] : null,
      url: url,
      title: title || null,
      category: categoryName,
      region: region,
      attribute: attr,
      price: price,
      offer_count: offerCountMatch ? parseInt(offerCountMatch[1]) : (soldOut ? 0 : null),
      sold_out: soldOut,
      seller: null,
      stock: null,
      delivery: null,
      _extracted_from: location.href,
      _extracted_at: new Date().toISOString()
    });
    added++;
  });

  // Individual seller offers: /items-{id}/
  // CSS classes: span.dayNumber (stock), span.deliveryTimeLabel (delivery),
  //   div.name (seller), span.priceTxt (price)
  document.querySelectorAll('a[href*="/items-"]').forEach(link => {
    const url = link.href.split('?')[0];
    if (!/\/items-\d+\//.test(url)) return;
    if (existing.has(url)) return;
    existing.add(url);
    const title = link.textContent.trim();
    if (!title || title.length < 3) return;
    const parent = link.closest('div, li, tr') || link.parentElement;
    const stockEl = parent ? parent.querySelector('.dayNumber') : null;
    const deliveryEl = parent ? parent.querySelector('.deliveryTimeLabel') : null;
    const sellerEl = parent ? parent.querySelector('.name') : null;
    const priceEl = parent ? parent.querySelector('.priceTxt') : null;
    results.push({
      type: 'offer',
      item_id: (url.match(/\/items-(\d+)\//) || [])[1] || null,
      url: url,
      title: title,
      category: categoryName,
      price: priceEl ? priceEl.textContent.trim() : null,
      seller: sellerEl ? sellerEl.textContent.trim() : null,
      stock: stockEl ? stockEl.textContent.trim() : null,
      delivery: deliveryEl ? deliveryEl.textContent.trim() : null,
      sold_out: false,
      offer_count: 1,
      _extracted_from: location.href,
      _extracted_at: new Date().toISOString()
    });
    added++;
  });

  localStorage.setItem('__z2u_products', JSON.stringify(results));
  // Quota guard: check localStorage has room before reporting success
  try { localStorage.getItem('__z2u_products'); } catch(e) {
    return { total: results.length, added: added, url: location.href,
             containers_found: productContainers.length + offerContainers.length,
             _quota_error: true, _message: 'localStorage quota exceeded — dump now' };
  }
  // Container diagnostic: report whether expected elements exist
  const productContainers = document.querySelectorAll('a[href*="/product-"]');
  const offerContainers = document.querySelectorAll('a[href*="/items-"]');
  const pageHasContainers = productContainers.length > 0 || offerContainers.length > 0;
  return {
    total: results.length,
    added: added,
    url: location.href,
    containers_found: productContainers.length + offerContainers.length,
    suspect: (added === 0 && pageHasContainers)
  };
}
""".strip()

EXTRACT_DETAIL_JS = r"""
(categoryName) => {
  const h1 = document.querySelector('h1');
  const title = h1 ? h1.textContent.trim() : '';
  const bodyText = document.body.innerText;
  const region = (bodyText.match(/(Global|United States|Europe|Turkey|Argentina)/) || [])[1] || '';
  const platform = (bodyText.match(/Activate\/redeem\/trade on (.+)/) || [])[1] || '';
  const deliveryMatch = bodyText.match(/Delivery Time:\s*([^\n]+)/);
  const durationMatch = bodyText.match(/Subscription duration:\s*([^\n]+)/);
  const sellerLink = document.querySelector('a[href*="/shop/"]');
  const sellerName = sellerLink ? sellerLink.textContent.trim() : '';
  const ratingMatch = bodyText.match(/(\d+\.\d+)%/);
  const stockText = bodyText.match(/Stock:\s*([^\n]+)/);
  const priceMatch = bodyText.match(/\$\s*([\d,.]+)/);
  const descSection = bodyText.match(/Product Description([\s\S]*?)(?:Looking for more|$)/);
  const sellers = [];
  document.querySelectorAll('a[href*="/shop/"]').forEach(link => {
    const name = link.textContent.trim();
    if (name && !sellers.includes(name)) sellers.push(name);
  });
  return {
    product_name: title || null,
    category: categoryName,
    description: descSection ? descSection[1].trim().substring(0, 500) : null,
    seller: sellerName || null,
    all_sellers: sellers,
    price: priceMatch ? '$' + priceMatch[1] : null,
    url: location.href,
    region: region || null,
    platform: platform || null,
    delivery_time: deliveryMatch ? deliveryMatch[1].trim() : null,
    subscription_duration: durationMatch ? durationMatch[1].trim() : null,
    stock: stockText ? stockText[1].trim() : null,
    seller_rating: ratingMatch ? ratingMatch[1] + '%' : null,
    _extracted_from: location.href,
    _extracted_at: new Date().toISOString()
  };
}
""".strip()

EXTRACT_COVERAGE_JS = r"""
() => {
  const bodyText = document.body.innerText;
  const products = JSON.parse(localStorage.getItem('__z2u_products') || '[]');
  const url = location.href;

  // Category listing page: "N Product Contain M Offers"
  const containMatch = bodyText.match(/(\d+)\s*Product\s*Contain\s*(\d+)\s*Offers/);
  // Search results page: "N Results" and "M records in total"
  const resultsHeader = bodyText.match(/(\d+)\s*Results/);
  const totalRecords = bodyText.match(/(\d+)\s*records?\s*in\s*total/i);

  // Count what we extracted from this page
  const currentBase = location.href.split('?')[0];
  const pageProducts = products.filter(p => {
    const source = p._extracted_from ? p._extracted_from.split('?')[0] : null;
    return source === currentBase;
  });

  const coverage = {
    url: url,
    page_type: 'unknown',
    declared: null,
    extracted: products.length,
    extracted_from_page: pageProducts.length
  };

  if (containMatch) {
    coverage.page_type = 'category';
    coverage.declared = {
      products: parseInt(containMatch[1]),
      offers: parseInt(containMatch[2])
    };
  } else if (resultsHeader) {
    coverage.page_type = 'search';
    coverage.declared = {
      results: parseInt(resultsHeader[1]),
      total_records: totalRecords ? parseInt(totalRecords[1]) : null
    };
  }

  // Field-level coverage: count non-null, non-empty values per field
  const fields = ['title', 'price', 'seller', 'stock', 'delivery', 'region', 'attribute', 'offer_count'];
  const fieldCoverage = {};
  for (const field of fields) {
    let found = 0, absent = 0, unchecked = 0;
    for (const p of products) {
      if (!(field in p)) { unchecked++; continue; }
      if (p[field] === null) { absent++; continue; }
      if (p[field] !== '' && p[field] !== undefined) { found++; }
    }
    fieldCoverage[field] = { found, absent, unchecked, total: products.length };
  }
  coverage.field_coverage = fieldCoverage;

  // Store coverage report
  localStorage.setItem('__z2u_coverage', JSON.stringify(coverage));
  return coverage;
}
""".strip()

EXTRACT_DUMP_JS = r"""
() => {
  return {
    categories: JSON.parse(localStorage.getItem('__z2u_categories') || '[]'),
    products: JSON.parse(localStorage.getItem('__z2u_products') || '[]'),
    coverage: JSON.parse(localStorage.getItem('__z2u_coverage') || 'null'),
  };
}
""".strip()

EXTRACT_COUNT_JS = r"""
() => {
  const pageText = document.body.innerText;
  const totalMatch = pageText.match(/(\d+)\s*records?\s*in\s*total/i);
  const cats = JSON.parse(localStorage.getItem('__z2u_categories') || '[]');
  return {
    total_records: totalMatch ? parseInt(totalMatch[1]) : null,
    categories_found: cats.length,
    url: location.href
  };
}
""".strip()


# --- CSV Schema ---

CSV_FIELDNAMES = [
    'product_name',
    'category',
    'description',
    'seller',
    'price',
    'url',
    'region',
    'platform',
    'delivery_time',
    'stock',
    'sold_out',
    'type',
]


# --- Relevance Filter ---

def make_relevance_filter(filter_term: str):
    term_lower = filter_term.lower().strip()
    if not term_lower:
        return lambda item: True

    def is_relevant(item: dict) -> bool:
        searchable = ' '.join([
            item.get('product_name', '') or item.get('title', ''),
            item.get('description', ''),
            item.get('category', ''),
        ]).lower()
        return term_lower in searchable

    return is_relevant


# --- Field value normalisation for CSV ---

def field_to_csv(value):
    """Convert four-state field value to CSV string.

    value                -> value (found)
    None                 -> (absent) (confirmed missing on page)
    "__UNOBSERVABLE__"   -> (unobservable) (page blocked/broken)
    key absent           -> handled by caller
    ''                   -> (absent) (legacy empty string = not found)
    """
    if value == '__UNOBSERVABLE__':
        return UNOBSERVABLE
    if value is None:
        return ABSENT
    if value == '':
        return ABSENT
    return str(value)


# --- Commands ---

def cmd_plan(args):
    print(f"# z2u.com Exhaustive Search Plan")
    print(f"# Query: {args.query}")
    print(f"# Filter: {args.filter or '(none)'}")
    print(f"# Output: {args.output or 'stdout'}")
    print()

    print("## Phase 0: Initialize")
    print("Execute RESET_JS via js() to clear localStorage.")
    print("```javascript")
    print(EXTRACT_RESET_JS)
    print("```")
    print()

    print("## Phase 1: Discover Categories")
    print(f"Navigate to: https://www.z2u.com/searchAllGame?search={args.query}")
    print("After navigation: wait_for_content(min_text=200)")
    print("If result.block is True or result.ok is False: page is blocked, skip and report.")
    print("Execute SET_PAGE_SIZE_JS to set 400 items per page.")
    print("After page reload: wait_for_content(min_text=200) again.")
    print("Execute CATEGORIES_JS via CDP.")
    print("If result.suspect is True: containers exist but 0 items extracted — selectors may be wrong or content not yet rendered. Wait 2s and retry once.")
    print("Validate first page: check that category results have non-null 'name' fields.")
    print("If all names are null: selectors broken — stop and redo discovery.")
    print(f"Paginate: ?search={args.query}&page=2, page=3, ...")
    print("Stop when 0 new categories extracted (convergence).")
    print("If result.suspect on convergence page: investigate before stopping — may be structure change, not end of results.")
    print("Execute COUNT_JS to check total records vs categories found.")
    print()

    print("## Phase 2: Extract Products per Category")
    print("Execute DUMP_JS to get category list.")
    print("For each category with > 0 offers:")
    print("  1. Navigate to category URL")
    print("  2. wait_for_content(min_text=200)")
    print("  3. If blocked: mark all fields __UNOBSERVABLE__, continue to next category")
    print("  4. Execute PRODUCTS_JS with category name as argument")
    print("  5. If result.suspect is True: containers exist but 0 extracted — retry after 2s")
    print("  6. After first category: validate primary key (title) has non-null values")
    print("  6. Execute COVERAGE_JS to verify extracted vs declared counts")
    print("  7. Paginate: ?page=2, ?page=3, ... until 0 new products")
    print(f"  8. Wait {args.delay}s between pages")
    print("  9. After each category, report progress")
    print()

    print("## Phase 3: Coverage Verification")
    print("After all categories are extracted, run COVERAGE_JS on each.")
    print("Compare field_coverage to identify systematic gaps.")
    print("If any field has found=0 across all items, the selector may be wrong.")
    print("Report fraction of pages that were __UNOBSERVABLE__ (blocked).")
    print()

    print("## Phase 4: Filter and Export")
    print("Execute DUMP_JS to get all products.")
    print("Save to JSON file, then run merge:")
    filter_arg = f" --filter '{args.filter}'" if args.filter else ""
    output_arg = f" --output {args.output}" if args.output else ""
    print(f"  python3 {SCRIPT_DIR}/search.py merge products.json{filter_arg}{output_arg}")
    print()

    print("## JS Snippets")
    for name, js in [
        ("SET_PAGE_SIZE_JS", EXTRACT_SET_PAGE_SIZE_JS),
        ("CATEGORIES_JS", EXTRACT_CATEGORIES_JS),
        ("PRODUCTS_JS", EXTRACT_PRODUCTS_JS),
        ("DETAIL_JS", EXTRACT_DETAIL_JS),
        ("COVERAGE_JS", EXTRACT_COVERAGE_JS),
        ("DUMP_JS", EXTRACT_DUMP_JS),
        ("COUNT_JS", EXTRACT_COUNT_JS),
    ]:
        print(f"### {name}")
        print("```javascript")
        print(js)
        print("```")
        print()


def cmd_extract_js(args):
    snippets = {
        'reset': EXTRACT_RESET_JS,
        'categories': EXTRACT_CATEGORIES_JS,
        'products': EXTRACT_PRODUCTS_JS,
        'detail': EXTRACT_DETAIL_JS,
        'coverage': EXTRACT_COVERAGE_JS,
        'dump': EXTRACT_DUMP_JS,
        'page_size': EXTRACT_SET_PAGE_SIZE_JS,
        'count': EXTRACT_COUNT_JS,
    }
    for flag, js in snippets.items():
        if getattr(args, flag, False):
            print(js)
            return
    print(EXTRACT_CATEGORIES_JS)


def _report_field_triage(items, label=""):
    """Report per-field fill rates and flag systematic gaps."""
    fields = CSV_FIELDNAMES
    total = len(items)
    if total == 0:
        return

    header = f"Field-level triage{label} ({total} items):"
    print(f"\n{header}", file=sys.stderr)

    # Separate unobservable items from checkable items for fill-rate calculation
    unobservable_count = sum(1 for item in items
                            if any(field_to_csv(item.get(f)) == UNOBSERVABLE for f in fields))
    checkable = total - unobservable_count

    flagged = []
    for field in fields:
        found = 0
        absent = 0
        not_checked = 0
        unobservable = 0
        for item in items:
            val = item.get(field)
            csv_val = field_to_csv(val)
            if csv_val == UNOBSERVABLE:
                unobservable += 1
            elif csv_val == ABSENT:
                absent += 1
            elif csv_val == NOT_CHECKED:
                not_checked += 1
            elif val is not None and val != '':
                found += 1
            else:
                absent += 1

        # Fill rate excludes unobservable items — they represent pages never inspected
        fill_rate = found / checkable if checkable > 0 else 0
        status = "OK" if fill_rate > 0.5 else ("LOW" if fill_rate > 0 else "EMPTY")
        if fill_rate == 0 and not_checked < checkable:
            status = "BROKEN"
            flagged.append(field)
        if unobservable > 0 and unobservable == total:
            status = "BLOCKED"

        print(f"  {field:20s}  found={found:4d}  absent={absent:4d}  "
              f"unobservable={unobservable:4d}  fill={fill_rate:.0%}  [{status}]",
              file=sys.stderr)

    if flagged:
        print(f"\n  FLAGGED: {', '.join(flagged)} — 0% fill rate across all items.", file=sys.stderr)
        print("  These fields exist on the page but the extractor returns empty.", file=sys.stderr)
        print("  Likely cause: wrong CSS selector or extraction not attempted.", file=sys.stderr)

    return flagged


def cmd_merge(args):
    with open(args.input) as f:
        data = json.load(f)

    # Collect items
    items = []
    products = data if isinstance(data, list) else data.get('products', [])
    for p in products:
        item = {
            'product_name': p.get('title', p.get('product_name', '')),
            'category': p.get('category', ''),
            'description': p.get('description', ''),
            'seller': p.get('seller', ''),
            'price': p.get('price', ''),
            'url': p.get('url', ''),
            'region': p.get('region', p.get('region_attr', '')),
            'platform': p.get('platform', ''),
            'delivery_time': p.get('delivery_time', ''),
            'stock': p.get('stock', ''),
            'sold_out': str(p.get('sold_out', False)).lower(),
            'type': p.get('type', 'product'),
        }
        items.append(item)

    # Apply relevance filter
    if args.filter:
        is_relevant = make_relevance_filter(args.filter)
        before = len(items)
        items = [i for i in items if is_relevant(i)]
        filtered = before - len(items)
        print(f"Filter '{args.filter}': {before} -> {len(items)} ({filtered} removed)", file=sys.stderr)

    # Sort by product_name
    items.sort(key=lambda x: x.get('product_name', '').lower())

    # Field triage report (pre-export)
    _report_field_triage(items, label=" (pre-filter)" if args.filter else "")

    # Export CSV with tri-state normalisation
    output_path = args.output or derive_output_path(args.input, '.json', '.csv')
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES, extrasaction='ignore')
        writer.writeheader()
        for item in items:
            row = {}
            for field in CSV_FIELDNAMES:
                val = item.get(field)
                row[field] = field_to_csv(val)
            writer.writerow(row)

    print(f"\nExported {len(items)} items to {output_path}", file=sys.stderr)

    # Category summary
    categories = {}
    for item in items:
        cat = item.get('category', 'Unknown')
        categories[cat] = categories.get(cat, 0) + 1

    print(f"\nCategories ({len(categories)}):", file=sys.stderr)
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}", file=sys.stderr)

    # Coverage report if available
    coverage = data.get('coverage') if isinstance(data, dict) else None
    if coverage:
        declared = coverage.get('declared')
        if declared:
            print(f"\nCoverage verification:", file=sys.stderr)
            for key, val in declared.items():
                print(f"  Declared {key}: {val}", file=sys.stderr)


def cmd_verify(args):
    """Field-level coverage verification and triage report."""
    with open(args.input) as f:
        data = json.load(f)

    products = data if isinstance(data, list) else data.get('products', [])
    coverage = data.get('coverage') if isinstance(data, dict) else None

    if not products:
        print("No products found in input.", file=sys.stderr)
        return

    print(f"=== z2u.com Coverage Verification ===\n", file=sys.stderr)
    print(f"Total items: {len(products)}", file=sys.stderr)

    # Type breakdown
    types = {}
    for p in products:
        t = p.get('type', 'unknown')
        types[t] = types.get(t, 0) + 1
    print(f"Entity types:", file=sys.stderr)
    for t, count in sorted(types.items(), key=lambda x: -x[1]):
        print(f"  {t}: {count}", file=sys.stderr)

    # Per-type field triage
    all_flagged = []
    for entity_type in types:
        type_items = [p for p in products if p.get('type') == entity_type]
        # Build CSV-format items for triage
        csv_items = []
        for p in type_items:
            csv_items.append({
                'product_name': p.get('title', p.get('product_name', '')),
                'category': p.get('category', ''),
                'description': p.get('description', ''),
                'seller': p.get('seller', ''),
                'price': p.get('price', ''),
                'url': p.get('url', ''),
                'region': p.get('region', p.get('region_attr', '')),
                'platform': p.get('platform', ''),
                'delivery_time': p.get('delivery_time', ''),
                'stock': p.get('stock', ''),
                'sold_out': str(p.get('sold_out', False)).lower(),
                'type': p.get('type', 'product'),
            })
        flagged = _report_field_triage(csv_items, label=f" type={entity_type}")
        if flagged:
            all_flagged.extend(flagged)

    # Overall triage
    csv_items_all = []
    for p in products:
        csv_items_all.append({
            'product_name': p.get('title', p.get('product_name', '')),
            'category': p.get('category', ''),
            'description': p.get('description', ''),
            'seller': p.get('seller', ''),
            'price': p.get('price', ''),
            'url': p.get('url', ''),
            'region': p.get('region', p.get('region_attr', '')),
            'platform': p.get('platform', ''),
            'delivery_time': p.get('delivery_time', ''),
            'stock': p.get('stock', ''),
            'sold_out': str(p.get('sold_out', False)).lower(),
            'type': p.get('type', 'product'),
        })
    _report_field_triage(csv_items_all, label=" (overall)")

    # Coverage probe results
    if coverage:
        print(f"\n=== Coverage Probe ===", file=sys.stderr)
        declared = coverage.get('declared')
        if declared:
            for key, val in declared.items():
                print(f"  Declared {key}: {val}", file=sys.stderr)
        fc = coverage.get('field_coverage')
        if fc:
            print(f"\n  JS field coverage:", file=sys.stderr)
            for field, stats in fc.items():
                print(f"    {field}: found={stats['found']} absent={stats['absent']} "
                      f"unchecked={stats['unchecked']}", file=sys.stderr)

    # Summary
    if all_flagged:
        unique_flagged = list(set(all_flagged))
        print(f"\n*** ACTION REQUIRED ***", file=sys.stderr)
        print(f"Fields with 0% fill: {', '.join(unique_flagged)}", file=sys.stderr)
        print("These fields likely have broken selectors or need Phase 3 (detail page) extraction.", file=sys.stderr)
    else:
        print(f"\nAll fields have >0% fill rate.", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="z2u.com exhaustive search orchestrator")
    sub = parser.add_subparsers(dest="command")

    # plan
    p = sub.add_parser("plan", help="Generate exhaustive search plan with JS snippets")
    p.add_argument("query", help="Broad search query (e.g., 'google')")
    p.add_argument("--filter", help="Relevance filter term (e.g., 'ultra')")
    p.add_argument("--output", "-o", help="Output CSV path")
    p.add_argument("--delay", type=float, default=3.0, help="Delay between pages (seconds)")
    p.add_argument("--max-pages", type=int, default=200, help="Max pages per category")

    # extract-js
    e = sub.add_parser("extract-js", help="Print browser extraction JS snippet")
    e.add_argument("--reset", action="store_true", help="Clear all localStorage")
    e.add_argument("--categories", action="store_true", help="Extract categories from search page")
    e.add_argument("--products", action="store_true", help="Extract products from category page")
    e.add_argument("--detail", action="store_true", help="Extract detail from product page")
    e.add_argument("--coverage", action="store_true", help="Coverage probe: extracted vs declared")
    e.add_argument("--dump", action="store_true", help="Dump all accumulated results")
    e.add_argument("--page-size", action="store_true", help="Set items per page to 400")
    e.add_argument("--count", action="store_true", help="Get page record count")

    # merge
    m = sub.add_parser("merge", help="Merge extracted JSON, filter, export CSV")
    m.add_argument("input", help="JSON file with extracted results")
    m.add_argument("--filter", help="Relevance filter term")
    m.add_argument("--output", "-o", help="Output CSV path")

    # verify
    v = sub.add_parser("verify", help="Field-level coverage verification and triage")
    v.add_argument("input", help="JSON file with extracted results")

    args = parser.parse_args()
    if args.command == "plan":
        cmd_plan(args)
    elif args.command == "extract-js":
        cmd_extract_js(args)
    elif args.command == "merge":
        cmd_merge(args)
    elif args.command == "verify":
        cmd_verify(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
