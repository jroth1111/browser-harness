"""Collect logged-out Airbnb public competitor snapshots for live host listings.

Role: collector (public, logged out). Captures date-specific search cards
first, then opens the closest deduplicated comp listing pages for richer
attributes.

Reads:
    - Latest complete `airbnb-live-listings-*.json` under
      `.private-data/listing-collections/` (override with
      `AIRBNB_LISTINGS_FILE`).

Produces:
    - Search runs, search-card price rows, target-comp links, comp listing
      snapshots, and price matrix rows under
      `.private-data/public-market-collections/`.
    - `domain-skills/airbnb/.session-store/capability/<run_id>-receipt.json`.

Requires (env, optional unless noted):
    - `AIRBNB_COMP_CHECKIN_DATES`, `AIRBNB_COMP_CHECKIN_OFFSETS`,
      `AIRBNB_COMP_NIGHTS`, `AIRBNB_COMP_TOP_RESULTS`,
      `AIRBNB_COMP_TOP_COMPS_PER_CONTEXT`,
      `AIRBNB_COMP_MAX_LISTING_SNAPSHOTS`,
      `AIRBNB_COMP_MAX_SEARCH_SCROLLS`, `AIRBNB_COMP_LISTING_SCOPE`,
      `AIRBNB_COMP_NAV_DELAY_SEC`, `AIRBNB_COMP_LIMIT_LISTINGS` — see
      public-market.md.

Refuses to run if:
    - Known Airbnb authenticated-session cookies are present (owner login
      personalizes ranking and invalidates rank/visibility analysis).
    - The selected listing inventory is `partial_run: true`. Override with
      `AIRBNB_LISTINGS_FILE` only for an intentionally bounded smoke test.

Run from the browser-harness repo against a fresh logged-out agent Chrome
profile:

    browser-harness --launch-profile domain-skills/airbnb/.session-store/profiles/public-comps \
      --port 52870 --url about:blank --json

    BH_NAME=airbnb-public-comps BH_CDP_WS=http://127.0.0.1:52870 \
      python3 run.py < domain-skills/airbnb/scripts/collect_competitors.py

Private outputs are written under ignored domain-skills/airbnb/.private-data/.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import os
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode, urlsplit, urlunsplit


BASE = "https://www.airbnb.com.au"
LISTINGS_PATH = Path("domain-skills/airbnb/.private-data/listing-collections")
OUTPUT_PATH = Path("domain-skills/airbnb/.private-data/public-market-collections")
SESSION_PATH = Path("domain-skills/airbnb/.session-store/capability")

DEFAULT_CHECKIN_OFFSETS = "14,30,60,90"
DEFAULT_NIGHTS = "3"
DEFAULT_TOP_RESULTS = "12"
DEFAULT_TOP_COMPS_PER_CONTEXT = "8"
DEFAULT_MAX_LISTING_SNAPSHOTS = "120"
DEFAULT_MAX_SEARCH_SCROLLS = "6"
_NAVIGATED = False
AUTH_COOKIE_NAMES = {
    "_aaj",
    "_aat",
    "_airbed_session_id",
    "_iidt",
    "_pt",
    "_vid_t",
    "hli",
    "li",
    "rclu",
}


def _load_local_module(module_filename, module_name):
    path = Path("domain-skills/airbnb/scripts") / module_filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_listing_scope = _load_local_module("listing_scope.py", "airbnb_listing_scope")
_public_scan_planner = _load_local_module("public_scan_planner.py", "airbnb_public_scan_planner")
_surfaces = _load_local_module("surface_capabilities.py", "airbnb_surface_capabilities")
_integrity = _load_local_module("run_integrity.py", "airbnb_run_integrity")
_photo_product = _load_local_module("photo_product_evidence.py", "airbnb_photo_product_evidence")


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def navigate(url):
    """Navigate an agent-owned public collection tab without tab sprawl."""
    global _NAVIGATED
    if not _NAVIGATED:
        new_tab(url)
        _NAVIGATED = True
    else:
        goto_url(url)


def assert_logged_out_public_session():
    cookies = browser_cookies([BASE + "/"])
    names = sorted({cookie.get("name") for cookie in cookies if isinstance(cookie, dict) and cookie.get("name")})
    auth_names = sorted(set(names) & AUTH_COOKIE_NAMES)
    if auth_names:
        raise SystemExit(
            "Refusing public search/rank collection in a logged-in Airbnb session; "
            f"detected authenticated cookie names {auth_names}. Use a fresh logged-out "
            "browser profile because owner-account login biases public ranking."
        )
    return {
        "checked": True,
        "expected_logged_out": True,
        "auth_cookie_names_present": auth_names,
        "cookie_name_count": len(names),
    }


def latest_live_listing_file() -> Path:
    explicit = os.environ.get("AIRBNB_LISTINGS_FILE")
    if explicit:
        return Path(explicit)
    files = sorted(LISTINGS_PATH.glob("airbnb-live-listings-*.json"))
    if not files:
        raise SystemExit(f"No live-listing collection found under {LISTINGS_PATH}")
    complete = [path for path in files if is_complete_live_listing_file(path)]
    if not complete:
        raise SystemExit(
            f"No complete live-listing collection found under {LISTINGS_PATH}; "
            "set AIRBNB_LISTINGS_FILE explicitly for a partial smoke test"
        )
    return complete[-1]


def is_complete_live_listing_file(path: Path) -> bool:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    def safe_int(value):
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    status_counts = data.get("status_counts") if isinstance(data.get("status_counts"), dict) else {}
    active_status_count = safe_int(status_counts.get("ACTIVE"))
    records = data.get("records") or []
    validation = data.get("field_validation") or {}
    return (
        bool(records)
        and len(records) == safe_int(data.get("active_count"))
        and len(records) == active_status_count
        and validation.get("all_active_detail_pages_ok") is True
        and not data.get("partial_run")
    )


def parse_csv_ints(value, default):
    return _public_scan_planner.parse_csv_ints(value, default)


def checkin_dates():
    return _public_scan_planner.resolve_checkin_dates(
        explicit=os.environ.get("AIRBNB_COMP_CHECKIN_DATES"),
        offsets=os.environ.get("AIRBNB_COMP_CHECKIN_OFFSETS"),
        default_offsets=DEFAULT_CHECKIN_OFFSETS,
        checkin_range=os.environ.get("AIRBNB_COMP_CHECKIN_RANGE"),
        step_days=int(os.environ.get("AIRBNB_COMP_CHECKIN_STEP_DAYS", "1")),
    )


def checkout_date(checkin, nights):
    return (date.fromisoformat(checkin) + timedelta(days=int(nights))).isoformat()


def clean_room_url(url):
    if not url:
        return None
    if url.startswith("/"):
        url = BASE + url
    parts = urlsplit(url)
    match = re.search(r"/rooms/(\d+)", parts.path)
    if not match:
        return None
    return urlunsplit((parts.scheme or "https", parts.netloc or "www.airbnb.com.au", f"/rooms/{match.group(1)}", "", ""))


def room_id_from_url(url):
    match = re.search(r"/rooms/(\d+)", url or "")
    return match.group(1) if match else None


def money_to_int(text):
    if not text:
        return None
    match = re.search(r"\$([0-9][0-9,]*)\s*AUD", text)
    return int(match.group(1).replace(",", "")) if match else None


def is_search_card_date_line(line):
    normalized = line.replace("\u2013", " to ").replace("\u2014", " to ")
    normalized = re.sub(r"[\u00a0\u2000-\u200b\u202f]+", " ", normalized)
    month = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|january|february|march|april|june|july|august|september|october|november|december)"
    return bool(
        re.search(rf"\b\d{{1,2}}\s+(?:to|-)\s+\d{{1,2}}\s+{month}\b", normalized, re.I)
        or re.search(rf"\b\d{{1,2}}\s+{month}\s+(?:to|-)\s+\d{{1,2}}(?:\s+{month})?\b", normalized, re.I)
        or re.search(rf"\b{month}\s+\d{{1,2}}\s+(?:to|-)\s+(?:{month}\s+)?\d{{1,2}}\b", normalized, re.I)
    )


def first_match(pattern, text, cast=None):
    match = re.search(pattern, text or "", re.I)
    if not match:
        return None
    value = match.group(1)
    return cast(value) if cast else value


def parse_card_text(text, photo_items=None):
    text = re.sub(r"\n{2,}", "\n", (text or "").strip())
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    total = first_match(r"\$([0-9][0-9,]*)\s*AUD\s+total", text, lambda v: int(v.replace(",", "")))
    nightly = first_match(
        r"\$([0-9][0-9,]*)\s*AUD\s*(?:per\s+night|night)",
        text,
        lambda v: int(v.replace(",", "")),
    )
    rating = first_match(r"([0-5](?:\.\d+)?)\s+out of 5 average rating", text, float)
    if rating is None:
        rating = first_match(r"\b([0-5]\.\d{1,2})\b", text, float)
    review_count = first_match(r"([0-9,]+)\s+reviews?", text, lambda v: int(v.replace(",", "")))
    bedrooms = first_match(r"([0-9]+)\s+bedrooms?", text, int)
    beds = first_match(r"([0-9]+)\s+beds?", text, int)
    bathrooms = first_match(r"([0-9]+(?:\.[0-9]+)?)\s+baths?", text, float)
    title = None
    location = None
    title_candidates = []
    for line in lines:
        if " in " in line and not re.search(r"\$|AUD|rating|reviews?|bedrooms?|beds?|baths?|guests?", line, re.I):
            location = line
            continue
        if is_search_card_date_line(line):
            continue
        if re.search(r"\$|AUD|rating|reviews?|guest favourite|superhost|show price breakdown", line, re.I):
            continue
        if re.search(r"\b\d+(?:\.\d+)?\s*(?:guests?|bedrooms?|beds?|baths?)\b", line, re.I):
            continue
        if re.fullmatch(r"[,.\u00b7\s]+", line):
            continue
        title_candidates.append(line)
    title = title_candidates[0] if title_candidates else None
    photo_evidence = _photo_product.normalize_photo_product_evidence(
        raw_listing_text=text,
        raw_photo_data=photo_items,
        hero_text=(photo_items or [None])[0] if photo_items else title,
    )
    differentiators = [
        value
        for value in photo_evidence.get("amenity_claims_proven_in_photos", [])
        if value in {"parking", "pool_or_spa", "view", "workspace", "family", "pet"}
    ]
    return {
        "visible_title_short": title,
        "visible_location_label": location,
        "visible_price_total": total,
        "visible_price_per_night": nightly,
        "visible_rating": rating,
        "visible_review_count": review_count,
        "bedrooms": bedrooms,
        "beds": beds,
        "bathrooms": bathrooms,
        "visible_badge": "Guest favourite" if re.search(r"guest favourite", text, re.I) else None,
        "top_home_highlight_visible": bool(re.search(r"top\s+\d+%|top home", text, re.I)),
        "hero_photo_subject_tag": photo_evidence.get("hero_photo_subject_tag"),
        "first_five_photo_subjects": photo_evidence.get("first_five_photo_subjects"),
        "obvious_differentiator_tags": differentiators,
        "raw_text": text[:3000],
    }


def listing_review_scope(text):
    return re.split(r"\nMeet your host\n|Meet your host", text or "", maxsplit=1, flags=re.I)[0]


def parse_listing_review_count(scope):
    for line in (scope or "").splitlines():
        if re.search(r"\bhost\b|other places to stay|years of hosting", line, re.I):
            continue
        match = re.search(r"\b([0-9][0-9,]*)\s+reviews?\b", line, re.I)
        if match:
            return int(match.group(1).replace(",", ""))
    if re.search(r"\bNo reviews(?:\s*\(yet\)| yet)\b|\bNew listing\b", scope or "", re.I):
        return 0
    return None


def parse_review_star_distribution(scope, review_count):
    individual_counts = {
        str(stars): len(re.findall(rf"\bRating,\s*{stars}\s+stars?\b", scope or "", re.I))
        for stars in range(1, 6)
    }
    total_visible = sum(individual_counts.values())
    star_distribution = {
        "visible_individual_review_star_count": total_visible,
    }
    for stars, pct in re.findall(r"([1-5])\s+stars?,\s*([0-9]+)%\s+of reviews", scope or "", re.I):
        percent = int(pct)
        count = round((review_count or 0) * percent / 100) if review_count is not None else None
        star_distribution[f"{stars}_star_pct"] = percent
        star_distribution[f"{stars}_star_count_estimate"] = count
    if any(key.endswith("_star_pct") for key in star_distribution):
        star_distribution["star_distribution_source"] = "percentage_widget"
        star_distribution["star_distribution_confidence"] = "percentage_estimate"
        return star_distribution
    if review_count == 0:
        star_distribution["star_distribution_source"] = "not_visible"
        star_distribution["star_distribution_confidence"] = "not_available"
        return star_distribution
    if review_count is None:
        star_distribution["star_distribution_source"] = (
            "partial_visible_individual_review_stars" if total_visible else "not_visible"
        )
        star_distribution["star_distribution_confidence"] = (
            "unknown_review_count" if total_visible else "not_available"
        )
        return star_distribution
    if total_visible != review_count:
        star_distribution["star_distribution_source"] = (
            "partial_visible_individual_review_stars" if total_visible else "not_visible"
        )
        star_distribution["star_distribution_confidence"] = (
            "insufficient_visible_review_rows" if total_visible else "not_available"
        )
        return star_distribution
    for stars, count in individual_counts.items():
        if count:
            star_distribution[f"{stars}_star_pct"] = round(count * 100 / review_count)
            star_distribution[f"{stars}_star_count_estimate"] = count
    star_distribution["star_distribution_source"] = "visible_individual_review_stars"
    star_distribution["star_distribution_confidence"] = "complete_visible_review_rows"
    return star_distribution


def rating_display_state(scope, rating, review_count):
    if review_count == 0:
        return "no_reviews_yet"
    if rating is not None:
        return "average_visible"
    if review_count and re.search(r"Average rating will appear after 3 reviews", scope or "", re.I):
        return "hidden_until_minimum_reviews"
    return "not_visible"


def parse_listing_text(text, photo_items=None):
    text = re.sub(r"\n{2,}", "\n", (text or "").strip())
    review_scope = listing_review_scope(text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    title = None
    for line in lines[:40]:
        if line.lower() in {"share", "save", "photos", "show all photos"}:
            continue
        if len(line) > 8 and not re.search(r"airbnb|start your search|skip to content", line, re.I):
            title = line
            break
    capacity_line = next((line for line in lines if re.search(r"\d+\s+guests?", line, re.I) and re.search(r"bedrooms?|beds?|baths?", line, re.I)), "")
    rating = first_match(r"Rated\s+([0-5](?:\.\d+)?)\s+out of 5(?:\s+stars)?", review_scope, float)
    if rating is None:
        rating = first_match(r"([0-5](?:\.\d+)?)\s+out of 5(?:\s+stars)?\s+from", review_scope, float)
    if rating is None:
        rating = first_match(r"([0-5](?:\.\d+)?)\s+out of 5 average rating", review_scope, float)
    review_count = parse_listing_review_count(review_scope)
    star_distribution = parse_review_star_distribution(review_scope, review_count)
    amenities_text = text.lower()
    photo_evidence = _photo_product.normalize_photo_product_evidence(
        raw_listing_text=text,
        raw_photo_data=photo_items,
        hero_text=(photo_items or [None])[0] if photo_items else title,
    )
    return {
        "title": title,
        "property_type": first_match(r"(Entire [^\n]+)", text),
        "max_guests": first_match(r"([0-9]+)\s+guests?", capacity_line or text, int),
        "bedrooms": first_match(r"([0-9]+)\s+bedrooms?", capacity_line or text, int),
        "beds": first_match(r"([0-9]+)\s+beds?", capacity_line or text, int),
        "bathrooms": first_match(r"([0-9]+(?:\.[0-9]+)?)\s+baths?", capacity_line or text, float),
        "rating": rating,
        "review_count": review_count,
        "rating_display_state": rating_display_state(review_scope, rating, review_count),
        "review_scope_confidence": "listing_section_before_host",
        "parking_flag": bool(re.search(r"\bparking\b|car ?park|garage", amenities_text)),
        "pool_spa_flag": bool(re.search(r"\bpool\b|\bspa\b|hot tub|sauna", amenities_text)),
        "pet_friendly_flag": bool(re.search(r"pets? allowed|pet friendly", amenities_text)),
        "workspace_wifi_flag": bool(re.search(r"wifi|dedicated workspace|work space|ethernet", amenities_text)),
        "family_amenities_flag": bool(re.search(r"cot|high chair|children|baby|family", amenities_text)),
        "accessible_features_flag": bool(re.search(r"step-free|accessible|wheelchair", amenities_text)),
        "photo_count": first_match(r"([0-9]+)\s+photos?", text, int),
        **photo_evidence,
        "visible_amenities_core": sorted(set(re.findall(r"\b(pool|spa|sauna|gym|parking|wifi|washer|dryer|kitchen|balcony|lift|air conditioning)\b", amenities_text))),
        "raw_text": text[:12000],
        **star_distribution,
    }


def target_query(listing):
    address = listing.get("address") or ""
    location = listing.get("location_label") or ""
    if address:
        return address
    return location.replace(", Australia", "")


def destination_from_listing(listing):
    location = listing.get("location_label") or ""
    return location if location else "Melbourne, Victoria, Australia"


def safe_float(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def adult_count(listing):
    guests = safe_float(listing.get("max_guests"), 2)
    return min(max(int(guests or 2), 1), 8)


def search_url(listing, checkin, nights, price_band=None):
    checkout = checkout_date(checkin, nights)
    query = target_query(listing)
    params = {
        "query": query,
        "checkin": checkin,
        "checkout": checkout,
        "adults": adult_count(listing),
        "room_types[]": "Entire home/apt",
    }
    bedrooms = listing.get("bedrooms")
    bedroom_count = safe_float(bedrooms)
    if bedroom_count:
        params["min_bedrooms"] = int(bedroom_count)
    price_band = price_band or {}
    price_min = safe_float(price_band.get("price_min"))
    price_max = safe_float(price_band.get("price_max"))
    if price_min is not None:
        params["price_min"] = int(price_min)
    if price_max is not None:
        params["price_max"] = int(price_max)
    return f"{BASE}/s/{destination_from_listing(listing).replace(' ', '--').replace(',', '')}/homes?{urlencode(params)}"


def listing_url_with_context(room_url, checkin, nights, adults):
    params = {
        "check_in": checkin,
        "check_out": checkout_date(checkin, nights),
        "adults": min(max(int(adults or 2), 1), 8),
    }
    return f"{clean_room_url(room_url)}?{urlencode(params)}"


def page_failure(status):
    title = str(status.get("title") or "").lower()
    text = str(status.get("text") or "").lower()
    block = status.get("block") if isinstance(status.get("block"), dict) else {}
    if block.get("blocked"):
        return block.get("kind") or "blocked"
    if "429" in title or "too many requests" in text:
        return "http_429_or_too_many_requests"
    if "503 service unavailable" in title or "error code: 503" in text or "stay tuned" in text:
        return "http_503_or_airbnb_error"
    if "enable javascript" in text and len(text) < 3000:
        return "no_javascript_shell"
    return None


def extract_search_cards_from_page():
    return js(
        r"""
(() => {
  const seen = new Set();
  const cards = [];
  const anchors = Array.from(document.querySelectorAll('a[href*="/rooms/"]'));
  for (const anchor of anchors) {
    let href = anchor.href || anchor.getAttribute('href') || '';
    const match = href.match(/\/rooms\/(\d+)/);
    if (!match || seen.has(match[1])) continue;
    seen.add(match[1]);
    let node = anchor;
    let best = anchor.innerText || '';
    for (let i = 0; i < 8 && node && node.parentElement; i++) {
      node = node.parentElement;
      const text = (node.innerText || '').trim();
      if (text.length > best.length && text.length < 3500) best = text;
      if (/AUD\s+total|out of 5 average rating|reviews?/i.test(text) && text.length < 3500) {
        best = text;
        break;
      }
    }
    const photoAltTexts = Array.from((node || anchor).querySelectorAll('img'))
      .map((img) => img.getAttribute('alt') || img.getAttribute('aria-label') || img.getAttribute('title') || '')
      .map((value) => value.trim())
      .filter(Boolean)
      .slice(0, 5);
    cards.push({href, room_id: match[1], text: best, photo_alt_texts: photoAltTexts});
  }
  return cards;
})()
"""
    ) or []


def extract_listing_photo_labels_from_page():
    return js(
        r"""
(() => {
  const labels = [];
  const seen = new Set();
  for (const img of Array.from(document.querySelectorAll('img'))) {
    const label = (img.getAttribute('alt') || img.getAttribute('aria-label') || img.getAttribute('title') || '').trim();
    if (!label || seen.has(label)) continue;
    seen.add(label);
    labels.push({alt: label});
    if (labels.length >= 20) break;
  }
  return labels;
})()
"""
    ) or []


def search_card_key(card):
    room_url = clean_room_url(card.get("href"))
    return card.get("room_id") or room_id_from_url(room_url) or room_url or card.get("href")


def merge_search_cards(seen, cards, scroll_depth):
    added = 0
    for card in cards:
        key = search_card_key(card)
        if not key or key in seen:
            continue
        seen[key] = {**card, "page_number_or_scroll_depth": scroll_depth}
        added += 1
    return added


def collect_search_cards_from_page(max_cards, max_scrolls, pause):
    """Collect cards across Airbnb's lazy search result list.

    Rank is the first-seen DOM order in a bounded, logged-out, scrolled result
    window. This is not a claim of global Airbnb rank beyond the collected
    window.
    """
    seen = {}
    scrolls_attempted = 0
    stable_rounds = 0
    for scroll_depth in range(max_scrolls + 1):
        added = merge_search_cards(seen, extract_search_cards_from_page(), scroll_depth)
        scrolls_attempted = scroll_depth
        if len(seen) >= max_cards:
            break
        metrics = js(
            """
(() => ({
  y: window.scrollY,
  h: window.innerHeight,
  page: Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)
}))()
"""
        ) or {}
        if metrics.get("y", 0) + metrics.get("h", 0) >= metrics.get("page", 0) - 10:
            break
        js("window.scrollBy(0, Math.floor(window.innerHeight * 0.85))")
        wait(pause)
        next_metrics = js("(() => ({ y: window.scrollY }))()") or {}
        if added == 0 and next_metrics.get("y") == metrics.get("y"):
            stable_rounds += 1
            if stable_rounds >= 2:
                break
        else:
            stable_rounds = 0
    return list(seen.values()), {
        "results_limit_requested": max_cards,
        "max_search_scrolls_requested": max_scrolls,
        "search_scrolls_attempted": scrolls_attempted,
        "rank_collection_scope": "scrolled_result_window" if scrolls_attempted else "initial_viewport",
    }


def search_run_id(target_listing_id, checkin, nights, price_band_label="all_prices"):
    suffix = "" if price_band_label == "all_prices" else f"-price-{price_band_label}"
    return f"airbnb-public-search-{target_listing_id}-{checkin}-{nights}n{suffix}"


def record_search_surface_capabilities(records, resource_urls, source_url, search_run_id_value, observed_at):
    for surface_id in ("public_comp_search", "market_research_scan"):
        record = _surfaces.capability_record(
            surface_id,
            observed_at=observed_at,
            auth_context="logged_out_public_guest_visible",
            source_url=source_url,
            resource_urls=resource_urls,
            evidence={"search_run_id": search_run_id_value},
        )
        _surfaces.upsert_best_capability(records, record)


def score_comp(target, card, result_position):
    def numeric(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    score = 1000 - (result_position * 8)
    for field, weight in (("bedrooms", 35), ("bathrooms", 25), ("beds", 10)):
        target_value = numeric(target.get(field))
        card_value = numeric(card.get(field))
        if target_value is not None and card_value is not None:
            score -= abs(target_value - card_value) * weight
    if card.get("visible_price_total"):
        score += 20
    rating = numeric(card.get("visible_rating"))
    if rating is not None:
        score += min(rating, 5) * 3
    target_location = str(target.get("location_label") or "").split(",")[0].lower()
    if target_location and target_location in str(card.get("visible_location_label") or "").lower():
        score += 30
    return round(score, 2)


def write_csv(path, rows):
    if not rows:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
        return
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    observed_at = utc_now()
    run_id = os.environ.get("AIRBNB_COMP_RUN_ID") or "airbnb-public-comps-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    logged_out_guard = assert_logged_out_public_session()
    listing_file = latest_live_listing_file()
    listing_run = json.loads(listing_file.read_text())
    all_listings = listing_run.get("records") or []
    listings, listing_scope = _listing_scope.select_listings(
        all_listings,
        os.environ.get("AIRBNB_COMP_LISTING_SCOPE"),
    )
    total_scope_listings = len(listings)
    if not listings:
        raise SystemExit(
            f"Listing source file {listing_file} produced zero listings for scope {listing_scope['label']}"
        )
    if os.environ.get("AIRBNB_COMP_LIMIT_LISTINGS"):
        listings = listings[: int(os.environ["AIRBNB_COMP_LIMIT_LISTINGS"])]
    nights_values = _public_scan_planner.resolve_nights_values(
        explicit=os.environ.get("AIRBNB_COMP_NIGHTS"),
        night_range=os.environ.get("AIRBNB_COMP_STAY_LENGTH_RANGE"),
        default=DEFAULT_NIGHTS,
    )
    dates = checkin_dates()
    price_bands = _public_scan_planner.initial_price_bands(
        os.environ.get("AIRBNB_COMP_PRICE_BANDS"),
        auto_min=os.environ.get("AIRBNB_COMP_AUTO_PRICE_MIN"),
        auto_max=os.environ.get("AIRBNB_COMP_AUTO_PRICE_MAX"),
    )
    top_results = int(os.environ.get("AIRBNB_COMP_TOP_RESULTS", DEFAULT_TOP_RESULTS))
    top_comps_per_context = int(os.environ.get("AIRBNB_COMP_TOP_COMPS_PER_CONTEXT", DEFAULT_TOP_COMPS_PER_CONTEXT))
    max_listing_snapshots = int(os.environ.get("AIRBNB_COMP_MAX_LISTING_SNAPSHOTS", DEFAULT_MAX_LISTING_SNAPSHOTS))
    max_search_scrolls = int(os.environ.get("AIRBNB_COMP_MAX_SEARCH_SCROLLS", DEFAULT_MAX_SEARCH_SCROLLS))
    validation = _public_scan_planner.validate_public_market_options(
        checkin_dates=dates,
        nights_values=nights_values,
        price_bands=price_bands,
        top_results=top_results,
        max_search_scrolls=max_search_scrolls,
        currency="AUD",
    )
    auto_price_partition = _public_scan_planner.parse_bool(os.environ.get("AIRBNB_COMP_AUTO_PRICE_PARTITION"), default=False)
    partition_threshold = int(os.environ.get("AIRBNB_COMP_PARTITION_TRIGGER_VISIBLE_RESULTS", str(top_results)))
    max_partition_depth = int(os.environ.get("AIRBNB_COMP_PARTITION_MAX_DEPTH", "0"))
    pause = float(os.environ.get("AIRBNB_COMP_NAV_DELAY_SEC", "2.0"))
    OUTPUT_PATH.mkdir(parents=True, exist_ok=True)
    SESSION_PATH.mkdir(parents=True, exist_ok=True)

    target_ids = {str(row.get("listing_id")) for row in listings}
    search_runs = []
    search_results = []
    price_matrix = []
    target_comp_links = []
    comp_snapshot_queue = {}
    surface_capabilities = []
    failures = []
    stop_collection = False
    raw_search_path = OUTPUT_PATH / f"{run_id}-search-raw.jsonl"
    raw_listing_path = OUTPUT_PATH / f"{run_id}-listing-raw.jsonl"

    for listing in listings:
        if stop_collection:
            break
        target_listing_id = str(listing["listing_id"])
        for checkin in dates:
            if stop_collection:
                break
            for nights in nights_values:
                if stop_collection:
                    break
                pending_price_bands = list(price_bands)
                while pending_price_bands:
                    price_band = pending_price_bands.pop(0)
                    if stop_collection:
                        break
                    price_band_label = price_band.get("label") or "all_prices"
                    run_key = search_run_id(target_listing_id, checkin, nights, price_band_label)
                    url = search_url(listing, checkin, nights, price_band=price_band)
                    filters_applied = [
                        f"query={target_query(listing)}",
                        "room_types[]=Entire home/apt",
                        f"min_bedrooms={listing.get('bedrooms')}",
                    ]
                    if price_band.get("price_min") is not None:
                        filters_applied.append(f"price_min={price_band['price_min']}")
                    if price_band.get("price_max") is not None:
                        filters_applied.append(f"price_max={price_band['price_max']}")
                    context_validation = _public_scan_planner.validate_public_search_context(
                        destination=destination_from_listing(listing),
                        checkin=checkin,
                        checkout=checkout_date(checkin, nights),
                        nights=nights,
                        adults=adult_count(listing),
                        currency="AUD",
                        filters=filters_applied,
                        price_band=price_band,
                        url=url,
                    )
                    context = {
                        "search_run_id": run_key,
                        "target_listing_id": target_listing_id,
                        "observed_at": observed_at,
                        "source_family": "public_market",
                        "surface_class": "public_market",
                        "auth_context": "logged_out_public_guest_visible",
                        "observer_location_country": "AU",
                        "device_type": "desktop",
                        "logged_in_flag": False,
                        "currency": "AUD",
                        "destination": destination_from_listing(listing),
                        "map_area_bounds_description": None,
                        "check_in_date": checkin,
                        "check_out_date": checkout_date(checkin, nights),
                        "nights": nights,
                        "price_band_label": price_band_label,
                        "price_min": price_band.get("price_min"),
                        "price_max": price_band.get("price_max"),
                        "partition_key": _public_scan_planner.partition_key(target_listing_id, checkin, nights, price_band),
                        "partition_depth": int(price_band.get("partition_depth") or 0),
                        "parent_price_band_label": price_band.get("parent_price_band_label"),
                        "guest_count_adults": adult_count(listing),
                        "guest_count_children": 0,
                        "guest_count_pets": 0,
                        "filters_applied": filters_applied,
                        "search_context_validation": context_validation,
                        "source_url": url,
                        "results_limit_requested": top_results,
                        "max_search_scrolls_requested": max_search_scrolls,
                    }
                    print(json.dumps({"phase": "search", "search_run_id": run_key, "url": url}), flush=True)
                    navigate(url)
                    wait_for_load()
                    wait(pause)
                    status = page_content_status(text_limit=20000, html_limit=4000)
                    record_search_surface_capabilities(
                        surface_capabilities,
                        _surfaces.page_api_resource_urls(js),
                        url,
                        run_key,
                        observed_at,
                    )
                    failure_kind = page_failure(status)
                    if failure_kind:
                        failures.append({**context, "error": failure_kind, "title": status.get("title"), "text_sample": (status.get("text") or "")[:500]})
                        search_runs.append({**context, "results_count_visible": 0, "status": "failed", "failure_kind": failure_kind})
                        if failure_kind in {"http_429_or_too_many_requests", "http_503_or_airbnb_error"}:
                            stop_collection = True
                        continue
                    cards, card_collection = collect_search_cards_from_page(top_results, max_search_scrolls, pause)
                    with raw_search_path.open("a") as handle:
                        handle.write(json.dumps({**context, **card_collection, "cards": cards}, ensure_ascii=False) + "\n")
                    parsed_cards = []
                    for card in cards:
                        room_url = clean_room_url(card.get("href"))
                        room_id = room_id_from_url(room_url)
                        if not room_url or room_id in target_ids:
                            continue
                        parsed = parse_card_text(card.get("text") or "", card.get("photo_alt_texts"))
                        if not parsed.get("visible_price_total") and not parsed.get("visible_title_short"):
                            continue
                        parsed_cards.append({
                            **parsed,
                            "listing_url": room_url,
                            "listing_id_if_extractable": room_id,
                            "page_number_or_scroll_depth": card.get("page_number_or_scroll_depth"),
                        })
                    ranked = []
                    for index, card in enumerate(parsed_cards[:top_results], start=1):
                        score = score_comp(listing, card, index)
                        ranked.append((score, index, card))
                    ranked.sort(key=lambda item: item[0], reverse=True)
                    search_run_row = {
                        **context,
                        **card_collection,
                        "results_count_visible": len(parsed_cards),
                        "status": "ok",
                    }
                    if auto_price_partition and _public_scan_planner.should_partition_price_band(
                        len(parsed_cards),
                        partition_threshold,
                        price_band,
                        max_partition_depth,
                    ):
                        child_bands = _public_scan_planner.split_price_band(price_band)
                        pending_price_bands.extend(child_bands)
                        search_run_row["partition_triggered"] = True
                        search_run_row["partition_child_labels"] = [band["label"] for band in child_bands]
                    else:
                        search_run_row["partition_triggered"] = False
                        search_run_row["partition_child_labels"] = []
                    search_runs.append(search_run_row)
                    for score, index, card in ranked[:top_results]:
                        result_row = {
                            "search_run_id": run_key,
                            "target_listing_id": target_listing_id,
                            "result_position": index,
                            "page_number_or_scroll_depth": card.get("page_number_or_scroll_depth"),
                            "listing_url": card["listing_url"],
                            "listing_id_if_extractable": card["listing_id_if_extractable"],
                            "source_family": "public_market",
                            "surface_class": "public_market",
                            "auth_context": "logged_out_public_guest_visible",
                            "partition_key": context["partition_key"],
                            "price_band_label": price_band_label,
                            "visible_title_short": card.get("visible_title_short"),
                            "visible_location_label": card.get("visible_location_label"),
                            "visible_rating": card.get("visible_rating"),
                            "visible_review_count": card.get("visible_review_count"),
                            "visible_badge": card.get("visible_badge"),
                            "top_home_highlight_visible": card.get("top_home_highlight_visible"),
                            "top_percent_label": None,
                            "visible_price_total": card.get("visible_price_total"),
                            "visible_price_per_night": card.get("visible_price_per_night"),
                            "fees_included_flag": None,
                            "hero_photo_subject_tag": card.get("hero_photo_subject_tag"),
                            "available_flag": bool(card.get("visible_price_total")),
                            "instant_book_visible_flag": None,
                            "first_five_photo_subjects": card.get("first_five_photo_subjects"),
                            "obvious_differentiator_tags": card.get("obvious_differentiator_tags") or [],
                            "competitor_score": score,
                            "raw_text": card.get("raw_text"),
                        }
                        search_results.append(result_row)
                        price_matrix.append({
                            "matrix_id": f"{run_key}-{card['listing_id_if_extractable']}",
                            "comp_listing_id": card["listing_id_if_extractable"],
                            "target_listing_id": target_listing_id,
                            "search_run_id": run_key,
                            "source_family": "public_market",
                            "surface_class": "public_market",
                            "auth_context": "logged_out_public_guest_visible",
                            "partition_key": context["partition_key"],
                            "check_in_date": checkin,
                            "check_out_date": checkout_date(checkin, nights),
                            "nights": nights,
                            "price_band_label": price_band_label,
                            "price_min": price_band.get("price_min"),
                            "price_max": price_band.get("price_max"),
                            "guest_count": context["guest_count_adults"],
                            "available_flag": bool(card.get("visible_price_total")),
                            "visible_total_guest_price": card.get("visible_price_total"),
                            "visible_nightly_component": card.get("visible_price_per_night"),
                            "visible_fees_or_taxes_component": None,
                            "minimum_stay_observed": None,
                            "cancellation_policy_visible": None,
                            "price_observation_confidence": "search_card_total_price" if card.get("visible_price_total") else "missing_price",
                        })
                    for comp_rank, (score, index, card) in enumerate(ranked[:top_comps_per_context], start=1):
                        target_comp_links.append({
                            "target_listing_id": target_listing_id,
                            "comp_listing_id": card["listing_id_if_extractable"],
                            "search_run_id": run_key,
                            "source_family": "public_market",
                            "surface_class": "public_market",
                            "auth_context": "logged_out_public_guest_visible",
                            "partition_key": context["partition_key"],
                            "check_in_date": checkin,
                            "nights": nights,
                            "price_band_label": price_band_label,
                            "comp_rank_for_target": comp_rank,
                            "search_result_position": index,
                            "page_number_or_scroll_depth": card.get("page_number_or_scroll_depth"),
                            "competitor_score": score,
                            "reason_codes": ["same_search_context", "similar_capacity_filter", "logged_out_guest_visible"],
                        })
                        comp_snapshot_queue.setdefault(card["listing_url"], {
                            "comp_listing_id": card["listing_id_if_extractable"],
                            "listing_url": card["listing_url"],
                            "checkin": checkin,
                            "nights": nights,
                            "adults": context["guest_count_adults"],
                        })

    comp_listing_snapshots = []
    for item in list(comp_snapshot_queue.values())[:max_listing_snapshots]:
        url = listing_url_with_context(item["listing_url"], item["checkin"], item["nights"], item["adults"])
        print(json.dumps({"phase": "listing_snapshot", "comp_listing_id": item["comp_listing_id"], "url": url}), flush=True)
        navigate(url)
        wait_for_load()
        wait(pause)
        status = page_content_status(text_limit=30000, html_limit=4000)
        failure_kind = page_failure(status)
        if failure_kind:
            failures.append({"comp_listing_id": item["comp_listing_id"], "listing_url": item["listing_url"], "error": failure_kind, "title": status.get("title")})
            if failure_kind in {"http_429_or_too_many_requests", "http_503_or_airbnb_error"}:
                break
            continue
        photo_labels = extract_listing_photo_labels_from_page()
        parsed = parse_listing_text(status.get("text") or "", photo_labels)
        with raw_listing_path.open("a") as handle:
            handle.write(json.dumps({**item, "observed_at": utc_now(), "text": status.get("text"), "photo_labels": photo_labels}, ensure_ascii=False) + "\n")
        comp_listing_snapshots.append({
            "comp_listing_id": item["comp_listing_id"],
            "observed_at": utc_now(),
            "source_family": "public_market",
            "surface_class": "public_market",
            "auth_context": "logged_out_public_guest_visible",
            "listing_url": item["listing_url"],
            "market": None,
            "property_type": parsed.get("property_type"),
            "room_type": parsed.get("property_type"),
            "max_guests": parsed.get("max_guests"),
            "bedrooms": parsed.get("bedrooms"),
            "beds": parsed.get("beds"),
            "bathrooms": parsed.get("bathrooms"),
            "rating": parsed.get("rating"),
            "review_count": parsed.get("review_count"),
            "five_star_pct": parsed.get("5_star_pct"),
            "five_star_count_estimate": parsed.get("5_star_count_estimate"),
            "four_star_pct": parsed.get("4_star_pct"),
            "four_star_count_estimate": parsed.get("4_star_count_estimate"),
            "three_star_pct": parsed.get("3_star_pct"),
            "three_star_count_estimate": parsed.get("3_star_count_estimate"),
            "two_star_pct": parsed.get("2_star_pct"),
            "two_star_count_estimate": parsed.get("2_star_count_estimate"),
            "one_star_pct": parsed.get("1_star_pct"),
            "one_star_count_estimate": parsed.get("1_star_count_estimate"),
            "star_distribution_source": parsed.get("star_distribution_source"),
            "star_distribution_confidence": parsed.get("star_distribution_confidence"),
            "visible_individual_review_star_count": parsed.get("visible_individual_review_star_count"),
            "rating_display_state": parsed.get("rating_display_state"),
            "review_scope_confidence": parsed.get("review_scope_confidence"),
            "public_badges": [],
            "top_home_highlight_visible": None,
            "bottom_percent_warning_visible": None,
            "visible_amenities_core": parsed.get("visible_amenities_core"),
            "parking_flag": parsed.get("parking_flag"),
            "pool_spa_flag": parsed.get("pool_spa_flag"),
            "pet_friendly_flag": parsed.get("pet_friendly_flag"),
            "workspace_wifi_flag": parsed.get("workspace_wifi_flag"),
            "family_amenities_flag": parsed.get("family_amenities_flag"),
            "accessible_features_flag": parsed.get("accessible_features_flag"),
            "house_rules_summary_flags": [],
            "cancellation_policy_visible": None,
            "photo_count": parsed.get("photo_count"),
            "hero_photo_subject": parsed.get("hero_photo_subject"),
            "first_five_photo_subjects": parsed.get("first_five_photo_subjects"),
            "bedroom_proof_flag": parsed.get("bedroom_proof_flag"),
            "bathroom_proof_flag": parsed.get("bathroom_proof_flag"),
            "kitchen_proof_flag": parsed.get("kitchen_proof_flag"),
            "living_area_proof_flag": parsed.get("living_area_proof_flag"),
            "workspace_proof_flag": parsed.get("workspace_proof_flag"),
            "parking_proof_flag": parsed.get("parking_proof_flag"),
            "pool_or_spa_proof_flag": parsed.get("pool_or_spa_proof_flag"),
            "view_proof_flag": parsed.get("view_proof_flag"),
            "family_proof_flag": parsed.get("family_proof_flag"),
            "pet_proof_flag": parsed.get("pet_proof_flag"),
            "self_checkin_proof_flag": parsed.get("self_checkin_proof_flag"),
            "amenity_claims_visible": parsed.get("amenity_claims_visible"),
            "amenity_claims_proven_in_photos": parsed.get("amenity_claims_proven_in_photos"),
            "missing_photo_proof": parsed.get("missing_photo_proof"),
            "design_gap_flags": parsed.get("design_gap_flags"),
            "photo_product_score": parsed.get("photo_product_score"),
            "photo_product_evidence_source": parsed.get("photo_product_evidence_source"),
            "review_theme_positive_tags": [],
            "review_theme_negative_tags": [],
            "raw_text": parsed.get("raw_text"),
        })

    prior_counts = _integrity.latest_prior_count(
        OUTPUT_PATH,
        count_keys=("search_result_count",),
        current_run_id=run_id,
    )
    last_good_guard = _integrity.last_good_guard(
        subject="public_comp_search_results",
        current_count=len(search_results),
        prior_positive_count=prior_counts["prior_positive_count"],
        allow_empty=os.environ.get("AIRBNB_COMP_ALLOW_EMPTY") == "1",
    )
    deduped_comp_listing_ids = _public_scan_planner.dedupe_listing_ids(search_results)
    partition_manifest = _public_scan_planner.build_partition_manifest(
        search_runs,
        search_results,
        trigger_threshold=partition_threshold,
        max_depth=max_partition_depth,
    )
    warehouse_exports = _integrity.warehouse_manifest([
        {
            "table": "airbnb_public_search_run",
            "path": f"{OUTPUT_PATH / (run_id + '-search-runs.csv')}",
            "row_count": len(search_runs),
            "grain": "search_run_id",
            "source_family": "public_market",
            "surface_class": "public_market",
            "auth_context": "logged_out_public_guest_visible",
        },
        {
            "table": "airbnb_public_search_result_snapshot",
            "path": f"{OUTPUT_PATH / (run_id + '-search-results.csv')}",
            "row_count": len(search_results),
            "grain": "search_run_id + result_position",
            "source_family": "public_market",
            "surface_class": "public_market",
            "auth_context": "logged_out_public_guest_visible",
        },
        {
            "table": "airbnb_public_price_availability_matrix",
            "path": f"{OUTPUT_PATH / (run_id + '-price-matrix.csv')}",
            "row_count": len(price_matrix),
            "grain": "target listing + comp listing + date + stay length + partition",
            "source_family": "public_market",
            "surface_class": "public_market",
            "auth_context": "logged_out_public_guest_visible",
        },
        {
            "table": "airbnb_public_comp_listing_snapshot",
            "path": f"{OUTPUT_PATH / (run_id + '-comp-listings.csv')}",
            "row_count": len(comp_listing_snapshots),
            "grain": "comp_listing_id + observed_at",
            "source_family": "public_market",
            "surface_class": "public_market",
            "auth_context": "logged_out_public_guest_visible",
        },
    ])
    output = {
        "run_id": run_id,
        "observed_at": observed_at,
        "auth_context": "logged_out_public_guest_visible",
        "source_family": "public_market",
        "surface_class": "public_market",
        "collection_status": _integrity.collection_status(
            last_good_guard_record=last_good_guard,
            failures_count=len(failures),
            complete=not stop_collection,
        ),
        "source": {
            "listing_scope": str(listing_file),
            "backend": "headful_chrome_logged_out",
            "collection_strategy": "Airbnb public search cards by target listing/date/stay length, then deduplicated public listing snapshots",
            "partition_strategy": "optional logged-out price bands via AIRBNB_COMP_PRICE_BANDS",
            "granularity_strategy": "date-specific search contexts; rerun over time to build time series",
            "logged_out_guard": logged_out_guard,
            "max_search_scrolls": max_search_scrolls,
            "validation": validation,
            "price_bands": price_bands,
            "auto_price_partition": {
                "enabled": auto_price_partition,
                "trigger_visible_results": partition_threshold,
                "max_depth": max_partition_depth,
            },
            "raw_search_path": str(raw_search_path),
            "raw_listing_path": str(raw_listing_path),
            "surface_capabilities": surface_capabilities,
        },
        "last_good_guard": last_good_guard,
        "warehouse_exports": warehouse_exports,
        "partition_manifest": partition_manifest,
        "target_listing_count": len(listings),
        "listing_status_scope": listing_scope["label"],
        "total_source_listings": len(all_listings),
        "total_scope_listings": total_scope_listings,
        "listing_scope_complete": len(listings) == total_scope_listings,
        "checkin_dates": dates,
        "nights_values": nights_values,
        "price_bands": price_bands,
        "public_input_validation": validation,
        "auto_price_partition_enabled": auto_price_partition,
        "partitioned_search_run_count": len([row for row in search_runs if row.get("partition_triggered")]),
        "deduped_comp_listing_count": len(deduped_comp_listing_ids),
        "deduped_comp_listing_ids": deduped_comp_listing_ids,
        "top_results": top_results,
        "max_search_scrolls": max_search_scrolls,
        "search_run_count": len(search_runs),
        "search_result_count": len(search_results),
        "price_matrix_count": len(price_matrix),
        "target_comp_link_count": len(target_comp_links),
        "comp_listing_snapshot_count": len(comp_listing_snapshots),
        "failures_count": len(failures),
        "search_runs": search_runs,
        "search_results": search_results,
        "price_matrix": price_matrix,
        "target_comp_links": target_comp_links,
        "comp_listing_snapshots": comp_listing_snapshots,
        "failures": failures[:100],
    }

    json_path = OUTPUT_PATH / f"{run_id}.json"
    search_runs_csv = OUTPUT_PATH / f"{run_id}-search-runs.csv"
    search_results_csv = OUTPUT_PATH / f"{run_id}-search-results.csv"
    price_matrix_csv = OUTPUT_PATH / f"{run_id}-price-matrix.csv"
    target_comps_csv = OUTPUT_PATH / f"{run_id}-target-comps.csv"
    comp_snapshots_csv = OUTPUT_PATH / f"{run_id}-comp-listings.csv"
    receipt_path = SESSION_PATH / f"{run_id}-receipt.json"
    output = _integrity.stamp_collection_contract(
        output,
        source_family="public_market",
        surface_class="public_market",
        auth_context="logged_out_public_guest_visible",
        collection_status=output["collection_status"],
        last_good_guard_record=last_good_guard,
        warehouse_exports=warehouse_exports,
        partition_manifest=partition_manifest,
    )
    _integrity.write_collection_json(json_path, output)
    write_csv(search_runs_csv, search_runs)
    write_csv(search_results_csv, search_results)
    write_csv(price_matrix_csv, price_matrix)
    write_csv(target_comps_csv, target_comp_links)
    write_csv(comp_snapshots_csv, comp_listing_snapshots)

    expected_search_runs = len(listings) * len(dates) * len(nights_values) * len(price_bands)
    receipt = {
        "run_id": run_id,
        "observed_at": observed_at,
        "logged_out_guard": logged_out_guard,
        "source_family": output["source_family"],
        "surface_class": output["surface_class"],
        "auth_context": output["auth_context"],
        "collection_status": output["collection_status"],
        "last_good_guard": last_good_guard,
        "warehouse_exports": warehouse_exports,
        "partition_manifest": partition_manifest,
        "target_listing_count": len(listings),
        "listing_status_scope": listing_scope["label"],
        "total_source_listings": len(all_listings),
        "total_scope_listings": total_scope_listings,
        "listing_scope_complete": len(listings) == total_scope_listings,
        "checkin_dates": dates,
        "nights_values": nights_values,
        "price_bands": price_bands,
        "public_input_validation": validation,
        "auto_price_partition": {
            "enabled": auto_price_partition,
            "trigger_visible_results": partition_threshold,
            "max_depth": max_partition_depth,
        },
        "top_results": top_results,
        "max_search_scrolls": max_search_scrolls,
        "expected_search_runs": expected_search_runs,
        "search_run_count": len(search_runs),
        "partitioned_search_run_count": len([row for row in search_runs if row.get("partition_triggered")]),
        "deduped_comp_listing_count": len(deduped_comp_listing_ids),
        "search_result_count": len(search_results),
        "price_matrix_count": len(price_matrix),
        "target_comp_link_count": len(target_comp_links),
        "comp_listing_snapshot_count": len(comp_listing_snapshots),
        "failures_count": len(failures),
        "all_search_contexts_attempted": len(search_runs) >= expected_search_runs if auto_price_partition else len(search_runs) == expected_search_runs,
        "all_search_contexts_have_cards": bool(search_runs) and all(row.get("results_count_visible", 0) > 0 for row in search_runs),
        "all_targets_have_comp_links": all(any(link["target_listing_id"] == str(row["listing_id"]) for link in target_comp_links) for row in listings),
        "json_path": str(json_path),
        "search_runs_csv": str(search_runs_csv),
        "search_results_csv": str(search_results_csv),
        "price_matrix_csv": str(price_matrix_csv),
        "target_comps_csv": str(target_comps_csv),
        "comp_snapshots_csv": str(comp_snapshots_csv),
        "surface_capabilities": surface_capabilities,
        "failure_sample": failures[:10],
    }
    receipt = _integrity.stamp_collection_contract(
        receipt,
        source_family="public_market",
        surface_class="public_market",
        auth_context="logged_out_public_guest_visible",
        collection_status=output["collection_status"],
        last_good_guard_record=last_good_guard,
        warehouse_exports=warehouse_exports,
        partition_manifest=partition_manifest,
    )
    _integrity.write_receipt_json(receipt_path, receipt)
    print(json.dumps(receipt, indent=2, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    import sys
    if any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
        print((__doc__ or "").strip())
        raise SystemExit(0)
    main()
