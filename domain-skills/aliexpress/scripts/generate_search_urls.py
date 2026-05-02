#!/usr/bin/env python3
"""Generate AliExpress search URLs for any product search.

Usage:
    # GPU with specificity variants:
    python3 generate_search_urls.py "RTX 4090" --specs "24GB" "48GB" --modifiers "graphics card" "GPU"

    # System containing a chip:
    python3 generate_search_urls.py "Ryzen AI Max+ 395" --synonyms "Strix Halo" --modifiers "mini PC" "desktop"

    # Simple product:
    python3 generate_search_urls.py "mechanical keyboard"

Output: tab-separated label and URL per line.
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


def build_url(query: str, sort: str = "volume") -> str:
    encoded = quote(query)
    url = BASE_URL.format(query=encoded)
    sort_param = SORTS.get(sort)
    if sort_param:
        url += "?" + sort_param
    return url


def generate_queries(
    query: str,
    synonyms: list[str] | None = None,
    specs: list[str] | None = None,
    modifiers: list[str] | None = None,
    products: list[str] | None = None,
    spec_terms: list[str] | None = None,
) -> list[tuple[str, str]]:
    """Return (label, url) pairs for all layers."""
    terms = [query] + (synonyms or [])
    queries = []

    # Layer 1: known product names
    if products:
        for p in products:
            q = f"{p} {query}"
            queries.append((f"L1: {q}", build_url(q)))

    # Layer 2: bare terms (always generated)
    for t in terms:
        queries.append((f"L2: {t}", build_url(t)))

    # Layer 2: term × spec specificity variants
    if specs:
        for t in terms:
            for s in specs:
                q = f"{t} {s}"
                queries.append((f"L2: {q}", build_url(q)))

    # Layer 3: term × modifier breadth expansion
    if modifiers:
        for t in terms:
            for m in modifiers:
                q = f"{t} {m}"
                queries.append((f"L3: {q}", build_url(q)))

    # Layer 4: spec-level
    if spec_terms:
        for s in spec_terms:
            queries.append((f"L4: {s}", build_url(s)))

    return queries


def main():
    parser = argparse.ArgumentParser(description="Generate AliExpress search URLs")
    parser.add_argument("query", help="Main search term (e.g. 'RTX 4090')")
    parser.add_argument(
        "--synonyms",
        nargs="*",
        help="Alternative names for the same product (e.g. 'Strix Halo')",
    )
    parser.add_argument(
        "--specs",
        nargs="*",
        help="Specificity tokens that change search results (e.g. '24GB' '48GB')",
    )
    parser.add_argument(
        "--modifiers",
        nargs="*",
        help="Category/context words to append (e.g. 'graphics card' 'GPU')",
    )
    parser.add_argument(
        "--products",
        nargs="*",
        help="Known product names for Layer 1 (e.g. 'DGX Spark')",
    )
    parser.add_argument(
        "--spec-terms",
        nargs="*",
        help="Full spec-level queries for Layer 4",
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
        args.query,
        synonyms=args.synonyms,
        specs=args.specs,
        modifiers=args.modifiers,
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
