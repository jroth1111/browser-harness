#!/usr/bin/env python3
"""G2G exhaustive product research orchestrator.

4-wave BFS crawl of the G2G marketplace API:
  Wave 1: Discover categories from search page HTML
  Wave 2: Resolve keyword info and service types per category
  Wave 3: Enumerate collections (denominations/regions) per service type
  Wave 4: Paginate offers with dedup, keyword matching, and coverage tracking

Subcommands:
  search     Full exhaustive crawl with CSV export and coverage report
  categories Discover and print categories for a query (Wave 1 only)
  seller     Enrich existing CSV with detailed seller data
  coverage   Generate coverage report from existing CSV

Usage:
    python3 search.py search "google" --output results.csv
    python3 search.py search "google" --output results.csv --target-keywords storage cloud
    python3 search.py categories "google"
    python3 search.py seller results.csv --output seller-results.csv
    python3 search.py coverage results.csv
"""

import argparse
import csv
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlencode
from urllib.error import URLError

from browser_harness.helpers import http_get

# --- Constants ---

API_BASE = "https://sls.g2g.com"
SITE_BASE = "https://www.g2g.com/au"
GLOBAL_REGION_ID = "0f76ac42-3267-4d77-9fba-f9d9d719dac9"
CURRENCY = "AUD"
COUNTRY = "AU"
PAGE_SIZE = 100
DELAY = 1.5  # seconds between API requests

CSV_COLUMNS = [
    "search_query", "target_keywords", "top_level_result_name",
    "top_level_result_type", "category", "subcategory",
    "product_type_tab", "breadcrumb", "product_title", "product_url",
    "product_description", "product_info",
    "delivery_speed", "delivery_method", "activation_region",
    "denomination", "other_denominations",
    "listed_from_price", "listed_currency", "offer_count",
    "warranty_or_support_notes",
    "keyword_match_found", "matched_keywords",
    "seller_name", "seller_level",
    "seller_successful_delivery_rate", "seller_all_time_rating",
    "seller_joined_date", "seller_sold_count",
    "seller_min_quantity", "seller_available_quantity",
    "seller_delivery_speed", "seller_price", "seller_currency",
    "seller_volume_discount", "seller_badges",
    "offer_id", "offer_currency", "original_unit_price",
    "seller_ranking", "satisfaction_rate_raw",
    "is_official", "is_online", "is_bundle",
    "reserved_qty", "cat_id", "ancestor_id",
    "scraped_at", "source_page_type", "discovery_path",
    "coverage_status", "coverage_notes", "notes",
]


# --- G2G API Client ---

class G2GClient:
    """Wraps the G2G sls API and search-page HTML scraping."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(f"  [client] {msg}", file=sys.stderr)

    def _api_get(self, path: str, params: Optional[dict] = None) -> dict:
        """GET a JSON API endpoint. Returns parsed payload on success, raises on error."""
        url = f"{API_BASE}{path}"
        if params:
            url += "?" + urlencode(params)
        self._log(f"GET {url}")
        try:
            raw = http_get(url, timeout=20.0)
        except (URLError, OSError) as exc:
            raise RuntimeError(f"Connection error for {url}: {exc}") from exc
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            raise RuntimeError(f"Invalid JSON from {url}: {exc}") from exc
        if not isinstance(data, dict):
            raise RuntimeError(f"Unexpected response type from {url}: {type(data)}")
        code = data.get("code")
        if code != 2000:
            msg = data.get("message", data.get("msg", "unknown error"))
            raise RuntimeError(f"API error {code} from {url}: {msg}")
        payload = data.get("payload") or data.get("data") or data
        return payload

    # --- Wave 1: category discovery from categories.json ---

    _CATEGORIES_JSON_URL = "https://assets.g2g.com/offer/categories.json"

    def search_categories(self, query: str) -> list[dict]:
        """Search the G2G categories index for entries matching *query*.

        Uses the static ``categories.json`` asset that G2G preloads on every
        page.  This avoids depending on client-rendered HTML from the search
        page (which is a SPA shell with no server-rendered category content).

        Returns a list of dicts: {name, type_label, seo_term, url, service_id, brand_id}.
        """
        self._log(f"Fetching categories index from {self._CATEGORIES_JSON_URL}")
        try:
            raw = http_get(self._CATEGORIES_JSON_URL, timeout=30.0)
            index = json.loads(raw)
        except (URLError, OSError, json.JSONDecodeError) as exc:
            self._log(f"Failed to fetch categories index: {exc}")
            return []

        query_lower = query.lower()
        categories = []
        seen_seo = set()

        # Two-pass: slug-keyed entries have full data (service_id, brand_id,
        # marketing_title).  UUID-keyed entries are just redirect pointers
        # with only {seo_term: "slug-name"}.  Process slugs first so the
        # rich entries take priority.
        slug_entries = {}
        uuid_redirects = {}
        for key, entry in index.items():
            if not isinstance(entry, dict):
                continue
            # Slug keys contain hyphens and start with a letter.
            # UUID compound keys look like "8f88b6fd-..._67071d4a-...".
            if key and key[0].isalpha() and "-" in key:
                slug_entries[key] = entry
            elif "seo_term" in entry:
                uuid_redirects[entry["seo_term"]] = key

        for seo_term, entry in slug_entries.items():
            # Extract marketing title (English)
            title_obj = entry.get("marketing_title", {})
            if isinstance(title_obj, dict):
                name = title_obj.get("en", "")
            else:
                name = str(title_obj)

            # Match: query appears in marketing title or seo_term
            searchable = f"{name} {seo_term}".lower()
            if query_lower not in searchable:
                continue

            if not name:
                name = seo_term.replace("-", " ").title()

            service_id = entry.get("service_id", "")
            brand_id = entry.get("brand_id", "")

            seen_seo.add(seo_term)
            categories.append({
                "name": name,
                "type_label": "",
                "seo_term": seo_term,
                "url": f"{SITE_BASE}/categories/{seo_term}",
                "service_id": service_id,
                "brand_id": brand_id,
            })

        self._log(f"Discovered {len(categories)} categories matching '{query}'")
        return categories

    def _search_categories_html_fallback(self, query: str) -> list[dict]:
        """Fallback: extract category slugs from the search HTML page."""
        url = f"{SITE_BASE}/search?q={query.replace(' ', '+')}"
        self._log(f"Fallback: fetching search page {url}")
        try:
            html = http_get(url, timeout=20.0)
        except (URLError, OSError) as exc:
            self._log(f"Fallback failed: {exc}")
            return []

        categories = []
        seen = set()
        for match in re.finditer(r'/categories/([a-z0-9][a-z0-9-]+)', html):
            seo_term = match.group(1)
            if seo_term in seen:
                continue
            seen.add(seo_term)
            categories.append({
                "name": seo_term.replace("-", " ").title(),
                "type_label": "",
                "seo_term": seo_term,
                "url": f"{SITE_BASE}/categories/{seo_term}",
                "service_id": "",
                "brand_id": "",
            })
        self._log(f"HTML fallback found {len(categories)} categories")
        return categories

    # --- Wave 2: keyword info and service types ---

    def get_keyword_info(self, seo_term: str) -> dict:
        """Fetch keyword metadata including brand_id."""
        return self._api_get(
            "/offer/keyword_info",
            {"seo_term": seo_term, "include_relation_detail": "1"},
        )

    def get_service_types(self) -> list[dict]:
        """Fetch available service types (e.g. Top Up, Digital Pins)."""
        payload = self._api_get(
            "/offer/keyword_relation/service",
            {"include_settings": "1", "include_gc": "1"},
        )
        if isinstance(payload, list):
            return payload
        # Sometimes wrapped in a dict with a list field
        if isinstance(payload, dict):
            for key in ("services", "data", "items", "results"):
                if key in payload and isinstance(payload[key], list):
                    return payload[key]
        return []

    # --- Wave 3: collections ---

    def get_collections(
        self, brand_id: str, region_id: str, service_id: str
    ) -> list[dict]:
        """Fetch collections (denominations) for a brand/region/service combo."""
        payload = self._api_get(
            "/offer/keyword_relation/collection/",
            {
                "brand_id": brand_id,
                "region_id": region_id,
                "service_id": service_id,
                "include_searchable_only": "0",
            },
        )
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in ("collections", "data", "items", "results"):
                if key in payload and isinstance(payload[key], list):
                    return payload[key]
        return []

    # --- Wave 4: offer search and details ---

    def search_offers(
        self,
        seo_term: str,
        service_id: str = "",
        brand_id: str = "",
        region_id: str = "",
        filter_attr: str = "",
        page: int = 1,
        sort: str = "",
    ) -> tuple[list[dict], int]:
        """Search offers. Returns (offers_list, total_count_from_meta)."""
        params: dict[str, Any] = {
            "seo_term": seo_term,
            "page_size": str(PAGE_SIZE),
            "page": str(page),
            "group": "0",
            "currency": CURRENCY,
            "country": COUNTRY,
        }
        if service_id:
            params["service_id"] = service_id
        if brand_id:
            params["brand_id"] = brand_id
        if region_id:
            params["region_id"] = region_id
        if filter_attr:
            params["filter_attr"] = filter_attr
        if sort:
            params["sort"] = sort

        payload = self._api_get("/offer/search", params)

        # Extract offers list
        offers = []
        if isinstance(payload, dict):
            offers = payload.get("offers", payload.get("results", payload.get("items", [])))
            if not isinstance(offers, list):
                offers = []
            meta = payload.get("meta", payload)
            total = (
                meta.get("total", meta.get("total_offer", 0))
                if isinstance(meta, dict)
                else 0
            )
            return offers, int(total) if total else len(offers)
        return [], 0

    def search_result_count(
        self,
        seo_term: str,
        service_id: str = "",
        brand_id: str = "",
        region_id: str = "",
        filter_attr: str = "",
    ) -> int:
        """Return just the total offer count for the given parameters."""
        _, total = self.search_offers(
            seo_term=seo_term,
            service_id=service_id,
            brand_id=brand_id,
            region_id=region_id,
            filter_attr=filter_attr,
            page=1,
        )
        return total

    def get_offer_detail(self, offer_id: str) -> dict:
        """Fetch full detail for a single offer."""
        return self._api_get(
            f"/offer/{offer_id}",
            {"currency": CURRENCY, "country": COUNTRY, "include_out_of_stock": "1"},
        )

    # --- Seller endpoints ---

    def get_seller_info(self, user_id: str) -> dict:
        """Fetch seller profile info."""
        return self._api_get(f"/user/{user_id}/info")

    def get_seller_rating(self, user_id: str) -> dict:
        """Fetch seller rating summary."""
        return self._api_get(
            f"/rating/user/{user_id}", {"user_type": "all"}
        )

    def get_completion_rate(self, user_id: str) -> dict:
        """Fetch seller order completion rate."""
        return self._api_get(f"/order/seller/{user_id}/completion_rate")


# --- Crawl Frontier ---

class CrawlFrontier:
    """BFS queue tracking 4 waves of discovery."""

    def __init__(self):
        self.categories: list[dict] = []
        self.service_targets: list[dict] = []
        self.collection_targets: list[dict] = []
        self.seen_offer_ids: set[str] = set()
        self.crawl_log: list[dict] = []

    def log(self, entry: dict) -> None:
        self.crawl_log.append(entry)


# --- Coverage Accountant ---

class CoverageAccountant:
    """Track expected vs collected offers per category for coverage reporting."""

    def __init__(self):
        self.expected: dict[str, int] = {}
        self.collected: dict[str, int] = {}
        self.deduped: dict[str, int] = {}
        # Metadata for richer reporting
        self.category_meta: dict[str, dict] = {}

    def record_expected(self, key: str, count: int) -> None:
        self.expected[key] = self.expected.get(key, 0) + count

    def record_collected(self, key: str, count: int) -> None:
        self.collected[key] = self.collected.get(key, 0) + count

    def record_dedup(self, key: str) -> None:
        self.deduped[key] = self.deduped.get(key, 0) + 1

    def set_category_meta(
        self, key: str, name: str, type_label: str,
        service_types: list[str], collections: int,
    ) -> None:
        self.category_meta[key] = {
            "name": name,
            "type": type_label,
            "service_types": service_types,
            "collections": collections,
        }

    def _rating(self, pct: float) -> str:
        if pct >= 97.0:
            return "HIGH"
        if pct >= 90.0:
            return "MEDIUM"
        return "LOW"

    def coverage_report(
        self,
        query: str,
        target_keywords: list[str],
        total_collected: int,
        total_deduped: int,
        keyword_match_counts: dict[str, int],
        crawl_log: list[dict],
    ) -> dict:
        by_category: dict[str, dict] = {}
        worst_rating = "HIGH"

        all_keys = set(self.expected.keys()) | set(self.collected.keys())
        for key in sorted(all_keys):
            exp = self.expected.get(key, 0)
            col = self.collected.get(key, 0)
            ded = self.deduped.get(key, 0)
            if exp == 0 and col == 0:
                pct = 100.0
            elif exp == 0:
                pct = 0.0
            else:
                pct = col / exp * 100
            rating = self._rating(pct)
            if rating == "LOW":
                worst_rating = "LOW"
            elif rating == "MEDIUM" and worst_rating != "LOW":
                worst_rating = "MEDIUM"

            meta = self.category_meta.get(key, {})
            by_category[key] = {
                "name": meta.get("name", key),
                "type": meta.get("type", ""),
                "service_types": meta.get("service_types", []),
                "collections": meta.get("collections", 0),
                "expected_offers": exp,
                "collected_offers": col,
                "deduped_offers": ded,
                "coverage_pct": round(pct, 1),
                "coverage_rating": rating,
            }

        total_expected = sum(self.expected.values())
        overall_pct = (
            total_collected / total_expected * 100 if total_expected > 0 else 0.0
        )

        return {
            "query": query,
            "target_keywords": target_keywords,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "categories_discovered": len(self.categories) if hasattr(self, 'categories') else len(all_keys),
                "categories_inspected": len(all_keys),
                "service_types_discovered": sum(
                    len(m.get("service_types", []))
                    for m in self.category_meta.values()
                ),
                "collections_discovered": sum(
                    m.get("collections", 0) for m in self.category_meta.values()
                ),
                "offers_collected": total_collected,
                "offers_deduplicated": total_deduped,
                "target_keyword_matches": sum(keyword_match_counts.values()),
                "overall_coverage": worst_rating,
            },
            "by_category": by_category,
            "crawl_log": crawl_log,
            "target_keyword_results": keyword_match_counts,
            "coverage_uncertainty": [],
        }


# --- CSV row builder ---

def build_csv_row(
    offer: dict,
    context: dict,
) -> dict:
    """Map an API offer dict plus crawl context into a flat CSV row."""

    target_keywords: list[str] = context.get("target_keywords", [])
    seo_term: str = context.get("seo_term", "")
    service_name: str = context.get("service_name", "")
    type_label: str = context.get("type_label", "")
    brand_name: str = context.get("brand_name", "")
    filter_attr: str = context.get("filter_attr", "")
    region_id: str = context.get("region_id", "")
    collection_label: str = context.get("collection_label", "")
    other_denominations: list[str] = context.get("other_denominations", [])
    total_offers: int = context.get("total_offers", 0)
    min_price: Optional[float] = context.get("min_price")
    display_currency: str = context.get("display_currency", CURRENCY)

    title = str(offer.get("title", ""))
    description = str(offer.get("description", ""))
    desc_truncated = description[:500]

    # Delivery info
    delivery_speed = str(offer.get("delivery_speed", ""))
    delivery_modes = offer.get("delivery_mode", [])
    if isinstance(delivery_modes, list):
        delivery_method = ",".join(str(m) for m in delivery_modes)
    else:
        delivery_method = str(delivery_modes)

    product_info = f"{delivery_speed} {delivery_method}".strip()

    # Activation region
    territory = offer.get("sales_territory_settings", {})
    if isinstance(territory, dict):
        settings_type = territory.get("settings_type", "")
        territory_countries = territory.get("countries", [])
        if isinstance(territory_countries, list):
            country_str = ",".join(str(c) for c in territory_countries)
        else:
            country_str = str(territory_countries)
        activation_region = f"{settings_type}: {country_str}".strip(": ")
    else:
        activation_region = ""

    # Price
    seller_price = offer.get("converted_unit_price")
    if seller_price is not None:
        try:
            seller_price = float(seller_price)
        except (ValueError, TypeError):
            seller_price = ""

    # Volume discount — API returns list of tier dicts
    wholesale = offer.get("wholesale_details")
    volume_discount = ""
    if isinstance(wholesale, list) and wholesale:
        tiers = []
        for tier in wholesale:
            if not isinstance(tier, dict):
                continue
            discount = tier.get("discount")
            min_qty = tier.get("min")
            if discount is not None and min_qty is not None:
                pct = round(float(discount) * 100, 1)
                tiers.append(f"{pct}% off at {min_qty}+")
        volume_discount = "; ".join(tiers)

    # Badges
    badges = "is_official" if offer.get("is_official") else ""

    # Breadcrumb
    breadcrumb_parts = ["Home"]
    if type_label:
        breadcrumb_parts.append(type_label)
    if service_name:
        breadcrumb_parts.append(service_name)
    if brand_name:
        breadcrumb_parts.append(brand_name)
    breadcrumb = " > ".join(breadcrumb_parts)

    # Product URL
    product_url = f"{SITE_BASE}/categories/{seo_term}/offer/group"
    url_params = {}
    if filter_attr:
        url_params["fa"] = filter_attr
    if region_id:
        url_params["region_id"] = region_id
    service_id_url = context.get("service_id", "")
    if service_id_url:
        url_params["sid"] = service_id_url
    if url_params:
        product_url += "?" + urlencode(url_params)

    # Warranty / support extraction from description
    warranty_notes = ""
    desc_lower = description.lower()
    for marker in ("warranty", "support", "notice"):
        idx = desc_lower.find(marker)
        if idx != -1:
            # Grab the sentence containing the marker (up to 200 chars around it)
            start = max(0, idx - 50)
            end = min(len(description), idx + 150)
            warranty_notes = description[start:end].strip()
            break

    # Keyword matching
    match_text = f"{title} {description}".lower()
    matched = [kw for kw in target_keywords if kw.lower() in match_text]
    keyword_match_found = "true" if matched else "false"
    matched_keywords = ",".join(matched)

    # Satisfaction rate as percentage
    satisfaction = offer.get("satisfaction_rate")
    if satisfaction is not None:
        try:
            satisfaction = f"{float(satisfaction)}%"
        except (ValueError, TypeError):
            satisfaction = str(satisfaction)
    else:
        satisfaction = ""

    return {
        "search_query": context.get("search_query", ""),
        "target_keywords": ",".join(target_keywords),
        "top_level_result_name": context.get("category_name", ""),
        "top_level_result_type": type_label,
        "category": service_name,
        "subcategory": seo_term.replace("-", " ").title(),
        "product_type_tab": service_name,
        "breadcrumb": breadcrumb,
        "product_title": title,
        "product_url": product_url,
        "product_description": desc_truncated,
        "product_info": product_info,
        "delivery_speed": delivery_speed,
        "delivery_method": delivery_method,
        "activation_region": activation_region,
        "denomination": collection_label,
        "other_denominations": ",".join(other_denominations),
        "listed_from_price": str(min_price) if min_price is not None else "",
        "listed_currency": display_currency,
        "offer_count": str(total_offers),
        "warranty_or_support_notes": warranty_notes,
        "keyword_match_found": keyword_match_found,
        "matched_keywords": matched_keywords,
        "seller_name": offer.get("username", ""),
        "seller_level": str(offer.get("user_level", "")),
        "seller_successful_delivery_rate": satisfaction,
        "seller_all_time_rating": str(offer.get("total_rating", "")),
        "seller_joined_date": "",
        "seller_sold_count": str(offer.get("total_success_order", "")),
        "seller_min_quantity": str(offer.get("min_qty", "")),
        "seller_available_quantity": str(offer.get("available_qty", "")),
        "seller_delivery_speed": str(offer.get("delivery_speed", "")),
        "seller_price": str(seller_price),
        "seller_currency": offer.get("display_currency", display_currency),
        "seller_volume_discount": volume_discount,
        "seller_badges": badges,
        "offer_id": str(offer.get("offer_id", offer.get("id", ""))),
        "offer_currency": str(offer.get("offer_currency", "")),
        "original_unit_price": str(offer.get("unit_price", "")),
        "seller_ranking": str(offer.get("seller_ranking", "")),
        "satisfaction_rate_raw": str(offer.get("satisfaction_rate", "")),
        "is_official": str(offer.get("is_official", "")),
        "is_online": str(offer.get("is_online", "")),
        "is_bundle": str(offer.get("is_bundle", "")),
        "reserved_qty": str(offer.get("reserved_qty", "")),
        "cat_id": str(offer.get("cat_id", "")),
        "ancestor_id": str(offer.get("ancestor_id", "")),
        "scraped_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_page_type": "api_search",
        "discovery_path": f"wave4:{seo_term}:{context.get('service_id', '')}:{filter_attr}",
        "coverage_status": "inspected",
        "coverage_notes": "",
        "notes": "",
    }


# --- Schema evolution detection ---

_KNOWN_OFFER_FIELDS = frozenset({
    "id", "offer_id", "title", "description", "offer_currency", "unit_price",
    "unit_price_in_usd", "converted_unit_price", "display_currency",
    "display_price", "formatted_unit_price", "delivery_speed",
    "delivery_mode", "delivery_method_ids", "available_qty", "reserved_qty",
    "min_qty", "wholesale_details", "satisfaction_rate", "total_rating",
    "total_success_order", "seller_id", "username", "user_level",
    "seller_ranking", "user_avatar", "is_official", "is_online",
    "service_id", "brand_id", "region_id", "cat_id", "ancestor_id",
    "offer_attributes", "filter_attributes", "offer_group",
    "sales_territory_settings", "status", "is_bundle", "images",
    "updated_at", "created_at", "slug",
})


def log_unknown_fields(offer: dict, verbose: bool) -> list[str]:
    """Return fields in offer not in known schema. Log if verbose."""
    unknown = [k for k in offer if k not in _KNOWN_OFFER_FIELDS]
    if unknown and verbose:
        print(f"  [schema] Unknown offer fields: {', '.join(sorted(unknown))}", file=sys.stderr)
    return unknown


# --- Subcommands ---

def cmd_search(args: argparse.Namespace) -> None:
    """Full exhaustive crawl: 4 waves with CSV export and coverage report."""
    client = G2GClient(verbose=args.verbose)
    frontier = CrawlFrontier()
    accountant = CoverageAccountant()

    query = args.query
    target_keywords = args.target_keywords or []
    max_pages = args.max_pages
    all_rows: list[dict] = []
    keyword_match_counts: dict[str, int] = {kw: 0 for kw in target_keywords}

    def _match_keywords(title: str, description: str) -> None:
        text = f"{title} {description}".lower()
        for kw in target_keywords:
            if kw.lower() in text:
                keyword_match_counts[kw] = keyword_match_counts.get(kw, 0) + 1

    # --- Wave 1: Category discovery ---
    print(f"=== Wave 1: Discovering categories for '{query}' ===", file=sys.stderr)
    categories = client.search_categories(query)
    if not categories:
        print("categories.json returned 0 results, trying HTML fallback...", file=sys.stderr)
        categories = client._search_categories_html_fallback(query)
    if not categories:
        print("No categories found from any source. Exiting.", file=sys.stderr)
        return
    frontier.categories = categories
    frontier.log({
        "wave": 1, "action": "search", "query": query,
        "categories_found": len(categories),
    })
    for cat in categories:
        print(f"  {cat['name']} ({cat['type_label']}) -> {cat['seo_term']}", file=sys.stderr)

    # --- Wave 2-4: Per-category crawl ---
    for cat in categories:
        seo_term = cat["seo_term"]
        cat_name = cat["name"]
        type_label = cat["type_label"]
        cat_key = seo_term

        print(f"\n=== Wave 2: Resolving services for '{cat_name}' ({seo_term}) ===", file=sys.stderr)
        time.sleep(DELAY)

        # Use brand_id / service_id from categories.json (already populated).
        # Fall back to keyword_info only if categories.json lacked them.
        brand_id = cat.get("brand_id", "")
        brand_name = cat_name

        if not brand_id:
            try:
                kw_info = client.get_keyword_info(seo_term)
                if isinstance(kw_info, dict):
                    brand_id = str(kw_info.get("brand_id", kw_info.get("id", "")))
                    if kw_info.get("brand_name"):
                        brand_name = kw_info["brand_name"]
            except RuntimeError as exc:
                print(f"  WARNING: keyword_info failed for {seo_term}: {exc}", file=sys.stderr)

        cat_service_id = cat.get("service_id", "")
        service_types: list[dict] = []

        if cat_service_id:
            # categories.json gave us the exact service — use it directly
            service_types = [{"id": cat_service_id, "name": cat_service_id}]
            print(f"  Using service_id={cat_service_id} from categories.json", file=sys.stderr)
        else:
            # No service_id in categories.json — fetch all and try each
            try:
                service_types = client.get_service_types()
            except RuntimeError as exc:
                print(f"  WARNING: service_types failed: {exc}", file=sys.stderr)

        time.sleep(DELAY)

        # If no services discovered, try a bare search with just seo_term
        if not service_types:
            print(f"  No service types found, probing bare search for {seo_term}", file=sys.stderr)
            try:
                expected_count = client.search_result_count(seo_term=seo_term)
                accountant.record_expected(cat_key, expected_count)
                accountant.set_category_meta(
                    cat_key, cat_name, type_label, [], 0,
                )
                if expected_count > 0:
                    offers, total = client.search_offers(seo_term=seo_term, page=1)
                    collected = 0
                    for offer in offers:
                        oid = str(offer.get("id", offer.get("offer_id", "")))
                        if oid in frontier.seen_offer_ids:
                            accountant.record_dedup(cat_key)
                            continue
                        frontier.seen_offer_ids.add(oid)
                        collected += 1
                        _match_keywords(str(offer.get("title", "")), str(offer.get("description", "")))
                        row = build_csv_row(offer, {
                            "search_query": query,
                            "target_keywords": target_keywords,
                            "category_name": cat_name,
                            "type_label": type_label,
                            "seo_term": seo_term,
                            "brand_name": brand_name,
                        })
                        all_rows.append(row)
                    accountant.record_collected(cat_key, collected)
                    frontier.log({
                        "wave": 4, "action": "offers", "seo_term": seo_term,
                        "pages_fetched": 1, "offers_found": collected, "deduped": 0,
                    })
            except RuntimeError as exc:
                print(f"  WARNING: bare search failed for {seo_term}: {exc}", file=sys.stderr)
            continue

        # Track per-category service type names for metadata
        service_type_names: list[str] = []
        total_collections_for_cat = 0

        for svc in service_types:
            service_id = str(svc.get("id", svc.get("service_id", "")))
            service_name = svc.get("name", svc.get("service_type_name", ""))
            if service_name:
                service_type_names.append(service_name)
            else:
                service_type_names.append(f"service_{service_id}")

            print(f"  Service: {service_name} (id={service_id})", file=sys.stderr)

            # Use global region if no specific region
            region_id = GLOBAL_REGION_ID

            # --- Wave 3: Collections ---
            print(f"    Wave 3: Fetching collections for service {service_id}...", file=sys.stderr)
            time.sleep(DELAY)

            collections: list[dict] = []
            try:
                collections = client.get_collections(brand_id, region_id, service_id)
            except RuntimeError as exc:
                print(f"    WARNING: collections failed: {exc}", file=sys.stderr)

            if not collections:
                print(f"    NOTE: 0 collections for service {service_id}, probing bare search", file=sys.stderr)

            frontier.log({
                "wave": 3, "action": "collections", "seo_term": seo_term,
                "service_id": service_id, "collections_found": len(collections),
            })
            total_collections_for_cat += len(collections)

            # Build collection targets; if none, use bare seo_term+service
            collection_targets: list[dict] = []
            if collections:
                for coll in collections:
                    coll_id = str(coll.get("collection_id", coll.get("id", "")))
                    dataset_id = str(coll.get("dataset_id", coll.get("id", "")))
                    fa = coll.get("filter_attr", coll.get("fa", ""))
                    if not fa and coll_id:
                        fa = coll_id
                    coll_label = coll.get("name", coll.get("label", coll.get("display_name", "")))
                    collection_targets.append({
                        "seo_term": seo_term,
                        "service_id": service_id,
                        "service_name": service_name,
                        "brand_id": brand_id,
                        "region_id": region_id,
                        "collection_id": coll_id,
                        "dataset_id": dataset_id,
                        "filter_attr": fa,
                        "collection_label": coll_label,
                    })
            else:
                # No collections: probe without filter_attr
                collection_targets.append({
                    "seo_term": seo_term,
                    "service_id": service_id,
                    "service_name": service_name,
                    "brand_id": brand_id,
                    "region_id": region_id,
                    "collection_id": "",
                    "dataset_id": "",
                    "filter_attr": "",
                    "collection_label": "",
                })

            # --- Wave 4: Paginate offers per collection ---
            for ct in collection_targets:
                ct_seo = ct["seo_term"]
                ct_svc = ct["service_id"]
                ct_fa = ct["filter_attr"]
                ct_label = ct["collection_label"]

                # Determine expected count
                try:
                    expected = client.search_result_count(
                        seo_term=ct_seo,
                        service_id=ct_svc,
                        brand_id=ct["brand_id"],
                        region_id=ct["region_id"],
                        filter_attr=ct_fa,
                    )
                except RuntimeError:
                    expected = 0

                accountant.record_expected(cat_key, expected)

                if expected == 0:
                    print(f"    Collection '{ct_label}': 0 expected (may be empty or wrong params)", file=sys.stderr)
                    accountant.record_collected(cat_key, 0)
                    continue

                print(f"    Collection '{ct_label}': ~{expected} offers, fetching...", file=sys.stderr)
                time.sleep(DELAY)

                pages_fetched = 0
                collected_here = 0
                deduped_here = 0
                min_price: Optional[float] = None
                other_denoms = [
                    c["collection_label"]
                    for c in collection_targets
                    if c["collection_label"] and c["collection_label"] != ct_label
                ]

                for page_num in range(1, max_pages + 1):
                    try:
                        offers, total = client.search_offers(
                            seo_term=ct_seo,
                            service_id=ct_svc,
                            brand_id=ct["brand_id"],
                            region_id=ct["region_id"],
                            filter_attr=ct_fa,
                            page=page_num,
                        )
                    except RuntimeError as exc:
                        print(f"      Page {page_num} error: {exc}", file=sys.stderr)
                        break

                    pages_fetched += 1
                    if not offers:
                        break

                    # Schema evolution check — first offer of first page only
                    if page_num == 1 and offers:
                        log_unknown_fields(offers[0], args.verbose)

                    for offer in offers:
                        oid = str(offer.get("id", offer.get("offer_id", "")))
                        if oid in frontier.seen_offer_ids:
                            deduped_here += 1
                            accountant.record_dedup(cat_key)
                            continue
                        frontier.seen_offer_ids.add(oid)
                        collected_here += 1

                        # Track minimum price
                        try:
                            price = float(offer.get("converted_unit_price", float("inf")))
                            if min_price is None or price < min_price:
                                min_price = price
                        except (ValueError, TypeError):
                            pass

                        # Keyword matching
                        _match_keywords(
                            str(offer.get("title", "")),
                            str(offer.get("description", "")),
                        )

                        row = build_csv_row(offer, {
                            "search_query": query,
                            "target_keywords": target_keywords,
                            "category_name": cat_name,
                            "type_label": type_label,
                            "seo_term": ct_seo,
                            "service_id": ct_svc,
                            "service_name": ct["service_name"],
                            "brand_name": brand_name,
                            "filter_attr": ct_fa,
                            "region_id": ct["region_id"],
                            "collection_label": ct_label,
                            "other_denominations": other_denoms,
                            "total_offers": total,
                            "min_price": min_price,
                            "display_currency": offer.get("display_currency", CURRENCY),
                        })
                        all_rows.append(row)

                    # Stop if we have collected enough or page was short
                    if len(offers) < PAGE_SIZE:
                        break
                    if collected_here >= expected:
                        break

                    time.sleep(DELAY)

                # Coverage verification: probe with lowest_price sort
                if collected_here > 0 and collected_here < expected:
                    print(f"      Coverage probe: sorting by lowest_price...", file=sys.stderr)
                    time.sleep(DELAY)
                    try:
                        probe_offers, _ = client.search_offers(
                            seo_term=ct_seo,
                            service_id=ct_svc,
                            brand_id=ct["brand_id"],
                            region_id=ct["region_id"],
                            filter_attr=ct_fa,
                            page=1,
                            sort="lowest_price",
                        )
                        for offer in probe_offers:
                            oid = str(offer.get("id", offer.get("offer_id", "")))
                            if oid in frontier.seen_offer_ids:
                                deduped_here += 1
                                accountant.record_dedup(cat_key)
                                continue
                            frontier.seen_offer_ids.add(oid)
                            collected_here += 1
                            _match_keywords(
                                str(offer.get("title", "")),
                                str(offer.get("description", "")),
                            )
                            row = build_csv_row(offer, {
                                "search_query": query,
                                "target_keywords": target_keywords,
                                "category_name": cat_name,
                                "type_label": type_label,
                                "seo_term": ct_seo,
                                "service_id": ct_svc,
                                "service_name": ct["service_name"],
                                "brand_name": brand_name,
                                "filter_attr": ct_fa,
                                "region_id": ct["region_id"],
                                "collection_label": ct_label,
                                "other_denominations": other_denoms,
                                "total_offers": total,
                                "min_price": min_price,
                                "display_currency": offer.get("display_currency", CURRENCY),
                            })
                            all_rows.append(row)
                    except RuntimeError as exc:
                        print(f"      Coverage probe error: {exc}", file=sys.stderr)

                accountant.record_collected(cat_key, collected_here)
                frontier.log({
                    "wave": 4, "action": "offers", "seo_term": ct_seo,
                    "filter_attr": ct_fa,
                    "pages_fetched": pages_fetched,
                    "offers_found": collected_here,
                    "deduped": deduped_here,
                })
                print(f"      Collected {collected_here}, deduped {deduped_here}", file=sys.stderr)

        # Set category metadata after all services processed
        accountant.set_category_meta(
            cat_key, cat_name, type_label, service_type_names,
            total_collections_for_cat,
        )

    # --- Export CSV ---
    output_path = args.output
    if not output_path:
        output_path = f"g2g-{query.replace(' ', '-')}-{datetime.now().strftime('%Y%m%d')}.csv"

    print(f"\n=== Exporting {len(all_rows)} rows to {output_path} ===", file=sys.stderr)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(all_rows)

    # --- Coverage report ---
    total_collected = len(all_rows)
    total_deduped = len(frontier.seen_offer_ids) - total_collected
    report = accountant.coverage_report(
        query=query,
        target_keywords=target_keywords,
        total_collected=total_collected,
        total_deduped=max(0, total_deduped),
        keyword_match_counts=keyword_match_counts,
        crawl_log=frontier.crawl_log,
    )

    report_path = output_path.replace(".csv", "-coverage.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"\n=== Summary ===", file=sys.stderr)
    summary = report.get("summary", {})
    for k, v in summary.items():
        print(f"  {k}: {v}", file=sys.stderr)
    print(f"  CSV: {output_path}", file=sys.stderr)
    print(f"  Coverage report: {report_path}", file=sys.stderr)


def cmd_categories(args: argparse.Namespace) -> None:
    """Discover and print categories for a query (Wave 1 only)."""
    client = G2GClient(verbose=args.verbose)
    categories = client.search_categories(args.query)

    if not categories:
        print("No categories found.", file=sys.stderr)
        return

    print(f"Found {len(categories)} categories for '{args.query}':\n", file=sys.stderr)
    for i, cat in enumerate(categories, 1):
        parts = [f"  {i}. {cat['name']}"]
        if cat["type_label"]:
            parts.append(f" [{cat['type_label']}]")
        parts.append(f" -> {cat['seo_term']}")
        print("".join(parts), file=sys.stderr)

    # Also output as JSON to stdout for piping
    print(json.dumps(categories, indent=2))


def cmd_seller(args: argparse.Namespace) -> None:
    """Enrich existing CSV with detailed seller data."""
    client = G2GClient(verbose=args.verbose)
    input_path = args.input
    output_path = args.output or input_path.replace(".csv", "-seller.csv")

    rows: list[dict] = []
    with open(input_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        input_fieldnames = list(reader.fieldnames or [])
        for row in reader:
            rows.append(row)

    if not rows:
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            if input_fieldnames:
                writer = csv.DictWriter(f, fieldnames=input_fieldnames, quoting=csv.QUOTE_ALL)
                writer.writeheader()
        print(f"No rows in input CSV. Wrote empty seller output to {output_path}", file=sys.stderr)
        return

    # Collect unique seller identifiers
    seller_ids: set[str] = set()
    for row in rows:
        # Try to find seller ID from various possible columns
        sid = row.get("seller_id") or row.get("seller_name") or ""
        if sid:
            seller_ids.add(sid)

    # If no explicit seller_id column, use seller_name as lookup key
    # and enrich by matching name
    seller_cache: dict[str, dict] = {}
    print(f"Enriching {len(rows)} rows for {len(seller_ids)} unique sellers...", file=sys.stderr)

    # The CSV from our own search has seller_name but not seller_id.
    # We look up sellers by name from the offer data; the enrichment
    # uses seller user_id from the offer if available.
    # For now, fetch details for any user_id found in rows.
    user_ids: set[str] = set()
    for row in rows:
        uid = row.get("seller_user_id") or row.get("user_id") or ""
        if uid:
            user_ids.add(uid)

    for i, uid in enumerate(sorted(user_ids), 1):
        print(f"  [{i}/{len(user_ids)}] Fetching seller {uid}...", file=sys.stderr)
        info = {}
        rating = {}
        completion = {}
        try:
            info = client.get_seller_info(uid)
            time.sleep(DELAY)
        except RuntimeError as exc:
            print(f"    seller_info error: {exc}", file=sys.stderr)
        try:
            rating = client.get_seller_rating(uid)
            time.sleep(DELAY)
        except RuntimeError as exc:
            print(f"    seller_rating error: {exc}", file=sys.stderr)
        try:
            completion = client.get_completion_rate(uid)
            time.sleep(DELAY)
        except RuntimeError as exc:
            print(f"    completion_rate error: {exc}", file=sys.stderr)
        seller_cache[uid] = {
            "info": info,
            "rating": rating,
            "completion": completion,
        }

    # Enrich rows
    enriched_rows: list[dict] = []
    for row in rows:
        uid = row.get("seller_user_id") or row.get("user_id") or ""
        cache_entry = seller_cache.get(uid, {})

        info = cache_entry.get("info", {})
        rating_data = cache_entry.get("rating", {})
        completion_data = cache_entry.get("completion", {})

        # Update joined date from seller info
        if info.get("joined_date") or info.get("created_at"):
            row["seller_joined_date"] = str(
                info.get("joined_date") or info.get("created_at", "")
            )

        # Update rating from rating endpoint
        if rating_data.get("average_rating") or rating_data.get("total_rating"):
            row["seller_all_time_rating"] = str(
                rating_data.get("average_rating") or rating_data.get("total_rating", "")
            )

        # Completion rate
        if completion_data.get("completion_rate") is not None:
            row["seller_successful_delivery_rate"] = f"{completion_data['completion_rate']}%"

        enriched_rows.append(row)

    # Write output with all columns (original + any new)
    all_fields = list(rows[0].keys()) if rows else CSV_COLUMNS
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=all_fields, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(enriched_rows)

    print(f"\nExported {len(enriched_rows)} enriched rows to {output_path}", file=sys.stderr)


def cmd_coverage(args: argparse.Namespace) -> None:
    """Generate coverage report from existing CSV."""
    input_path = args.input
    rows: list[dict] = []
    with open(input_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append(row)

    if not rows:
        print("No rows in input CSV.", file=sys.stderr)
        return

    # Group by category (seo_term from discovery_path or subcategory)
    by_category: dict[str, list[dict]] = {}
    query = ""
    target_keywords: list[str] = []
    for row in rows:
        if not query:
            query = row.get("search_query", "")
        tk = row.get("target_keywords", "")
        if tk and not target_keywords:
            target_keywords = [k.strip() for k in tk.split(",") if k.strip()]

        # Extract category key from discovery_path
        dp = row.get("discovery_path", "")
        # wave4:{seo_term}:{service_id}:{filter_attr}
        parts = dp.split(":") if dp else []
        cat_key = parts[1] if len(parts) >= 2 else row.get("subcategory", "unknown")
        by_category.setdefault(cat_key, []).append(row)

    keyword_match_counts: dict[str, int] = {kw: 0 for kw in target_keywords}
    for row in rows:
        if row.get("keyword_match_found") == "true":
            matched = row.get("matched_keywords", "")
            for kw in matched.split(","):
                kw = kw.strip()
                if kw in keyword_match_counts:
                    keyword_match_counts[kw] += 1

    report = {
        "query": query,
        "target_keywords": target_keywords,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "categories_discovered": len(by_category),
            "categories_inspected": len(by_category),
            "offers_collected": len(rows),
            "offers_deduplicated": sum(
                1 for r in rows if r.get("coverage_notes", "").startswith("dedup")
            ),
            "target_keyword_matches": sum(keyword_match_counts.values()),
        },
        "by_category": {},
        "target_keyword_results": keyword_match_counts,
    }

    for cat_key, cat_rows in sorted(by_category.items()):
        # Count keyword matches within this category
        matched_in_cat = sum(
            1 for r in cat_rows if r.get("keyword_match_found") == "true"
        )
        report["by_category"][cat_key] = {
            "name": cat_rows[0].get("top_level_result_name", cat_key) if cat_rows else cat_key,
            "type": cat_rows[0].get("top_level_result_type", "") if cat_rows else "",
            "collected_offers": len(cat_rows),
            "keyword_matched_offers": matched_in_cat,
        }

    report_path = input_path.replace(".csv", "-coverage.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"Coverage report written to {report_path}", file=sys.stderr)
    print(json.dumps(report["summary"], indent=2), file=sys.stderr)


# --- CLI ---

def main() -> None:
    parser = argparse.ArgumentParser(
        description="G2G exhaustive product research orchestrator"
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Print progress to stderr")
    sub = parser.add_subparsers(dest="command")

    # search
    s = sub.add_parser("search", help="Full exhaustive crawl with CSV export")
    s.add_argument("query", help="Search query (e.g. 'google')")
    s.add_argument("--output", "-o", help="Output CSV path")
    s.add_argument(
        "--target-keywords", nargs="*",
        help="Keywords to match in titles/descriptions",
    )
    s.add_argument(
        "--max-pages", type=int, default=20,
        help="Maximum pages to fetch per collection (default: 20)",
    )

    # categories
    c = sub.add_parser("categories", help="Discover categories only (Wave 1)")
    c.add_argument("query", help="Search query")

    # seller
    sl = sub.add_parser("seller", help="Enrich CSV with seller details")
    sl.add_argument("input", help="Input CSV path")
    sl.add_argument("--output", "-o", help="Output CSV path")

    # coverage
    co = sub.add_parser("coverage", help="Generate coverage report from CSV")
    co.add_argument("input", help="Input CSV path")

    args = parser.parse_args()

    if args.command == "search":
        cmd_search(args)
    elif args.command == "categories":
        cmd_categories(args)
    elif args.command == "seller":
        cmd_seller(args)
    elif args.command == "coverage":
        cmd_coverage(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
