#!/usr/bin/env python3
"""Generate eBay search URLs for a component search.

Implements the 4-layer query taxonomy from data-source-exploration.md:
  L1: known product names
  L2: chip/component references
  L3: category + architecture
  L4: spec-level

Usage:
    python3 generate_search_urls.py "Ryzen AI Max+ 395"
    python3 generate_search_urls.py "GB10" --synonyms "Grace Blackwell"
    python3 generate_search_urls.py "RTX 5090" --products "RTX 5090" --modifiers "desktop" "laptop"

Output: TSV of label<TAB>url per line.
"""

import argparse
import sys
from urllib.parse import quote

BASE_URL = "https://www.ebay.com.au/sch/i.html"

FORM_FACTORS = [
    "laptop", "mini PC", "desktop", "workstation", "handheld",
    "tablet", "2-in-1", "gaming", "PC", "computer", "notebook",
]


def build_url(query: str, lh_bin: bool = True, lh_prefloc: str = "",
              sort: str = "", page: int = 1) -> str:
    params = [f"_nkw={quote(query)}"]
    if lh_bin:
        params.append("LH_BIN=1")
    if lh_prefloc:
        params.append(f"LH_PrefLoc={lh_prefloc}")
    if sort:
        params.append(f"_sop={sort}")
    if page > 1:
        params.append(f"_pgn={page}")
    return f"{BASE_URL}?{'&'.join(params)}"


def generate_queries(
    chip: str,
    base_terms: list[str] | None = None,
    form_factors: list[str] | None = None,
    products: list[str] | None = None,
    spec_terms: list[str] | None = None,
    pages: int = 3,
    location: str = "",
) -> list[tuple[str, str]]:
    ffs = form_factors or FORM_FACTORS
    queries = []

    # Layer 1: known product names
    if products:
        for p in products:
            for pg in range(1, pages + 1):
                label = f"L1: {p} {chip}" + (f" p{pg}" if pg > 1 else "")
                queries.append((label, build_url(f"{p} {chip}", page=pg, lh_prefloc=location)))

    # Layer 2: chip references
    terms = [chip] + (base_terms or [])
    for t in terms:
        for pg in range(1, pages + 1):
            label = f"L2: {t}" + (f" p{pg}" if pg > 1 else "")
            queries.append((label, build_url(t, page=pg, lh_prefloc=location)))

    # Layer 3: category + form-factor
    for t in terms:
        for ff in ffs:
            q = f"{t} {ff}"
            label = f"L3: {q}"
            queries.append((label, build_url(q, lh_prefloc=location)))

    # Layer 4: spec-level
    if spec_terms:
        for s in spec_terms:
            label = f"L4: {s}"
            queries.append((label, build_url(s, lh_prefloc=location)))

    return queries


def main():
    parser = argparse.ArgumentParser(description="Generate eBay search URLs")
    parser.add_argument("chip", help="Chip/component name")
    parser.add_argument("--base-terms", nargs="*", dest="base_terms", help="Additional chip reference terms (legacy)")
    parser.add_argument("--synonyms", nargs="*", dest="base_terms", help="Alternative names for the search target")
    parser.add_argument("--form-factors", nargs="*", dest="form_factors", help="Form-factor synonyms (legacy)")
    parser.add_argument("--modifiers", nargs="*", dest="form_factors", help="Category/context words for queries")
    parser.add_argument("--products", nargs="*", help="Known product names for Layer 1")
    parser.add_argument("--spec-terms", nargs="*", help="Spec-level queries for Layer 4")
    parser.add_argument("--pages", type=int, default=3, help="Pages per query (default: 3)")
    parser.add_argument("--location", default="", help="LH_PrefLoc value (1=AU, 2=NA, 99=worldwide)")
    parser.add_argument("--urls-only", action="store_true", help="Output URLs only")
    args = parser.parse_args()

    queries = generate_queries(
        args.chip,
        base_terms=args.base_terms,
        form_factors=args.form_factors,
        products=args.products,
        spec_terms=args.spec_terms,
        pages=args.pages,
        location=args.location,
    )

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
