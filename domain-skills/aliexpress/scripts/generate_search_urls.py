#!/usr/bin/env python3
"""Generate AliExpress search URLs for a component search.

Usage:
    python3 generate_search_urls.py "Ryzen AI Max+ 395"
    python3 generate_search_urls.py "GB10" --base-terms "Grace Blackwell"
    python3 generate_search_urls.py "RTX 5090" --form-factors "desktop" "laptop"

Output: one URL per line, ready for browser navigation.
"""

import argparse
import sys
from urllib.parse import quote

BASE_URL = "https://www.aliexpress.com/w/wholesale-{query}.html"
SORTS = {
    "volume": "SortType=total_volume",
    "price_desc": "SortType=price_desc",
    "best": None,
}

# Form-factor synonyms that produce non-overlapping results on AliExpress.
# Each must be a separate query.
DEFAULT_FORM_FACTORS = [
    "mini PC",
    "desktop",
    "workstation",
    "server",
    "host",
    "gaming computer",
]

# 4-layer query taxonomy
# Layer 1: known product names (user-supplied via --products)
# Layer 2: chip/component references (the main term + --base-terms)
# Layer 3: category + architecture (chip + form-factor synonyms)
# Layer 4: spec-level (--spec-terms)


def build_url(query: str, sort: str = "volume") -> str:
    encoded = quote(query)
    url = BASE_URL.format(query=encoded)
    sort_param = SORTS.get(sort)
    if sort_param:
        url += "?" + sort_param
    return url


def generate_queries(
    chip: str,
    base_terms: list[str] | None = None,
    form_factors: list[str] | None = None,
    products: list[str] | None = None,
    spec_terms: list[str] | None = None,
) -> list[tuple[str, str]]:
    """Return (query, url) pairs for all layers."""
    ffs = form_factors or DEFAULT_FORM_FACTORS
    queries = []

    # Layer 1: known product names
    if products:
        for p in products:
            q = f"{p} {chip}"
            queries.append((f"L1: {q}", build_url(q)))

    # Layer 2: chip references
    terms = [chip] + (base_terms or [])
    for t in terms:
        queries.append((f"L2: {t}", build_url(t)))

    # Layer 3: category + form-factor
    for t in terms:
        for ff in ffs:
            q = f"{t} {ff}"
            queries.append((f"L3: {q}", build_url(q)))

    # Layer 4: spec-level
    if spec_terms:
        for s in spec_terms:
            queries.append((f"L4: {s}", build_url(s)))

    return queries


def main():
    parser = argparse.ArgumentParser(description="Generate AliExpress search URLs")
    parser.add_argument("chip", help="Chip/component name (e.g. 'Ryzen AI Max+ 395')")
    parser.add_argument(
        "--base-terms",
        nargs="*",
        help="Additional chip reference terms (e.g. 'Strix Halo')",
    )
    parser.add_argument(
        "--form-factors",
        nargs="*",
        help="Form-factor synonyms (default: built-in list)",
    )
    parser.add_argument(
        "--products",
        nargs="*",
        help="Known product names for Layer 1 (e.g. 'DGX Spark')",
    )
    parser.add_argument(
        "--spec-terms",
        nargs="*",
        help="Spec-level queries for Layer 4 (e.g. '128GB LPDDR5X Blackwell')",
    )
    parser.add_argument(
        "--sort",
        choices=list(SORTS.keys()),
        default="volume",
        help="Sort order (default: volume)",
    )
    parser.add_argument(
        "--urls-only",
        action="store_true",
        help="Output URLs only (no labels)",
    )
    args = parser.parse_args()

    queries = generate_queries(
        args.chip,
        base_terms=args.base_terms,
        form_factors=args.form_factors,
        products=args.products,
        spec_terms=args.spec_terms,
    )

    # Deduplicate by URL
    seen = set()
    for label, url in queries:
        if url in seen:
            continue
        seen.add(url)
        if args.urls_only:
            print(url)
        else:
            print(f"{label}\t{url}")


if __name__ == "__main__":
    main()
