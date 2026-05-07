"""Collect logged-out guest-visible audits for the host's own Airbnb listings.

Role: collector (public, logged out). Captures how the host's listings appear
to a guest in public search and on public listing pages. Must not use the host
auth bundle.

Reads:
    - Latest complete `airbnb-live-listings-*.json` under
      `.private-data/listing-collections/` (override with
      `AIRBNB_LISTINGS_FILE`).

Produces:
    - Public listing-page content audits, review summaries, individual
      review snapshots, and search-appearance rows under
      `.private-data/own-public-collections/`.
    - `domain-skills/airbnb/.session-store/capability/<run_id>-receipt.json`.

Requires (env, optional unless noted):
    - `AIRBNB_OWN_PUBLIC_CHECKIN_DATES`, `AIRBNB_OWN_PUBLIC_CHECKIN_OFFSETS`,
      `AIRBNB_OWN_PUBLIC_NIGHTS`, `AIRBNB_OWN_PUBLIC_TOP_RESULTS`,
      `AIRBNB_OWN_PUBLIC_MAX_SEARCH_SCROLLS`,
      `AIRBNB_OWN_PUBLIC_LISTING_SCOPE`, `AIRBNB_OWN_PUBLIC_NAV_DELAY_SEC`,
      `AIRBNB_OWN_PUBLIC_LIMIT_LISTINGS` — see public-market.md.

Refuses to run if:
    - Known Airbnb authenticated-session cookies are present (own-listing
      rank must not be observed from the owner's account).
    - The selected listing inventory is `partial_run: true`. Override with
      `AIRBNB_LISTINGS_FILE` only for an intentionally bounded smoke test.

Run from the browser-harness repo against a fresh logged-out agent Chrome
profile:

    browser-harness --launch-profile domain-skills/airbnb/.session-store/profiles/own-public \
      --port 52872 --url about:blank --json

    BH_NAME=airbnb-own-public BH_CDP_WS=http://127.0.0.1:52872 \
      python3 run.py < domain-skills/airbnb/scripts/collect_own_public.py

Private outputs are written under ignored domain-skills/airbnb/.private-data/.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode, urlsplit, urlunsplit


BASE = "https://www.airbnb.com.au"
LISTINGS_PATH = Path("domain-skills/airbnb/.private-data/listing-collections")
OUTPUT_PATH = Path("domain-skills/airbnb/.private-data/own-public-collections")
SESSION_PATH = Path("domain-skills/airbnb/.session-store/capability")

DEFAULT_CHECKIN_OFFSETS = "30"
DEFAULT_NIGHTS = "3"
DEFAULT_TOP_RESULTS = "30"
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
            "Refusing own public search/rank collection in a logged-in Airbnb session; "
            f"detected authenticated cookie names {auth_names}. Use a fresh logged-out "
            "browser profile because owner-account login biases public ranking."
        )
    return {
        "checked": True,
        "expected_logged_out": True,
        "auth_cookie_names_present": auth_names,
        "cookie_name_count": len(names),
    }


def is_complete_live_listing_file(path: Path) -> bool:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    def safe_int(value):
        if isinstance(value, bool):
            return 0
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


def parse_csv_ints(value, default):
    return _public_scan_planner.parse_csv_ints(value, default)


def checkin_dates():
    return _public_scan_planner.resolve_checkin_dates(
        explicit=os.environ.get("AIRBNB_OWN_PUBLIC_CHECKIN_DATES"),
        offsets=os.environ.get("AIRBNB_OWN_PUBLIC_CHECKIN_OFFSETS"),
        default_offsets=DEFAULT_CHECKIN_OFFSETS,
        checkin_range=os.environ.get("AIRBNB_OWN_PUBLIC_CHECKIN_RANGE"),
        step_days=int(os.environ.get("AIRBNB_OWN_PUBLIC_CHECKIN_STEP_DAYS", "1")),
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


def first_match(pattern, text, cast=None):
    match = re.search(pattern, text or "", re.I)
    if not match:
        return None
    value = match.group(1)
    return cast(value) if cast else value


def money_to_int(value):
    return int(value.replace(",", "")) if value else None


def is_search_card_date_line(line):
    normalized = line.replace("\u2013", " to ").replace("\u2014", " to ")
    normalized = re.sub(r"[\u00a0\u2000-\u200b\u202f]+", " ", normalized)
    month = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|january|february|march|april|june|july|august|september|october|november|december)"
    return bool(
        re.search(rf"\b\d{{1,2}}\s+(?:to|-)\s+\d{{1,2}}\s+{month}\b", normalized, re.I)
        or re.search(rf"\b\d{{1,2}}\s+{month}\s+(?:to|-)\s+\d{{1,2}}(?:\s+{month})?\b", normalized, re.I)
        or re.search(rf"\b{month}\s+\d{{1,2}}\s+(?:to|-)\s+(?:{month}\s+)?\d{{1,2}}\b", normalized, re.I)
    )


def parse_card_text(text, photo_items=None):
    text = re.sub(r"\n{2,}", "\n", (text or "").strip())
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    total = first_match(r"\$([0-9][0-9,]*)\s*AUD\s+total", text, money_to_int)
    nightly = first_match(r"\$([0-9][0-9,]*)\s*AUD\s*(?:per\s+night|night)", text, money_to_int)
    rating = first_match(r"([0-5](?:\.\d+)?)\s+out of 5 average rating", text, float)
    if rating is None:
        rating = first_match(r"\b([0-5]\.\d{1,2})\b", text, float)
    review_count = first_match(r"([0-9,]+)\s+reviews?", text, lambda v: int(v.replace(",", "")))
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
        "visible_badge": "Guest favourite" if re.search(r"guest favourite", text, re.I) else None,
        "top_home_highlight_visible": bool(re.search(r"top\s+\d+%|top home", text, re.I)),
        "hero_photo_subject_tag": photo_evidence.get("hero_photo_subject_tag"),
        "first_five_photo_subjects": photo_evidence.get("first_five_photo_subjects"),
        "obvious_differentiator_tags": differentiators,
        "raw_text": text[:3000],
    }


def parse_rating_category(text, label):
    patterns = [
        rf"{label}\s*\n\s*([0-5](?:\.\d+)?)",
        rf"{label}\s+([0-5](?:\.\d+)?)",
    ]
    for pattern in patterns:
        value = first_match(pattern, text, float)
        if value is not None:
            return value
    return None


def review_themes(text):
    lowered = (text or "").lower()
    theme_patterns = {
        "cleanliness": r"clean|spotless|dirty|dust|mould|mold",
        "accuracy": r"accurate|as described|not as described|misleading",
        "checkin": r"check[- ]?in|key|lockbox|arrival",
        "communication": r"communicat|responsive|reply|message",
        "noise": r"noise|noisy|quiet",
        "beds_sleep": r"bed|mattress|sleep|pillow",
        "wifi_work": r"wifi|wi-fi|internet|workspace|work",
        "parking": r"parking|car park|garage",
        "location": r"location|walk|tram|train|cbd|central",
        "value": r"value|worth|expensive|price",
    }
    return [name for name, pattern in theme_patterns.items() if re.search(pattern, lowered)]


MONTH_PATTERN = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4}"


def review_noise_line(line):
    return bool(re.fullmatch(
        r"Show more|Show less|Translate(?: to English)?|Helpful|Report|Response from .+|Host response",
        line or "",
        re.I,
    ))


def visible_review_id(listing_id, row):
    material = "|".join(str(row.get(key) or "") for key in (
        "reviewer_name_visible", "review_rating", "review_date_label", "review_text",
    ))
    digest = hashlib.sha256(f"{listing_id}|{material}".encode("utf-8")).hexdigest()[:16]
    return f"public-review-{listing_id}-{digest}"


def parse_visible_public_reviews(scope):
    """Extract review rows that Airbnb rendered in public listing text.

    This captures visible public rows only. It is not a complete historical
    review export unless every public review row is visible in the source text.
    """
    lines = [line.strip() for line in (scope or "").splitlines() if line.strip()]
    reviews = []
    rating_pattern = re.compile(r"\bRating,\s*([1-5])\s+stars?\b", re.I)
    stop_labels = {
        "cleanliness", "accuracy", "check-in", "communication", "location", "value",
        "where you'll sleep", "what this place offers", "meet your host",
    }
    for index, line in enumerate(lines):
        rating_match = rating_pattern.search(line)
        if not rating_match:
            continue
        reviewer = None
        if index > 0:
            previous = lines[index - 1]
            if not review_noise_line(previous) and not re.fullmatch(MONTH_PATTERN, previous, re.I):
                reviewer = previous[:120]
        review_date = None
        text_lines = []
        cursor = index + 1
        while cursor < len(lines):
            current = lines[cursor]
            lowered = current.lower()
            if rating_pattern.search(current) or lowered in stop_labels:
                break
            if cursor + 1 < len(lines) and rating_pattern.search(lines[cursor + 1]):
                break
            if review_noise_line(current):
                cursor += 1
                continue
            if review_date is None and re.fullmatch(MONTH_PATTERN, current, re.I):
                review_date = current
                cursor += 1
                continue
            if current == reviewer:
                cursor += 1
                continue
            text_lines.append(current)
            cursor += 1
        review_text = " ".join(text_lines).strip()
        reviews.append({
            "review_position_visible": len(reviews) + 1,
            "reviewer_name_visible": reviewer,
            "review_rating": int(rating_match.group(1)),
            "review_date_label": review_date,
            "review_text": review_text[:4000],
            "review_theme_tags": review_themes(review_text),
            "review_row_source": "public_listing_visible_review_row",
            "review_row_confidence": "visible_review_row_with_text" if review_text else "visible_review_star_only",
        })
    return reviews


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


def rating_category_source(category_ratings):
    if any(value is not None for value in category_ratings.values()):
        return "category_widget"
    return "not_visible"


def parse_listing_text(text, photo_items=None):
    text = re.sub(r"\n{2,}", "\n", (text or "").strip())
    review_scope = listing_review_scope(text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    title = None
    for line in lines[:50]:
        if line.lower() in {"share", "save", "photos", "show all photos", "start your search"}:
            continue
        if len(line) > 8 and not re.search(r"airbnb|skip to content|translation|rating|reviews?", line, re.I):
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
    category_ratings = {
        "accuracy_rating": parse_rating_category(review_scope, "Accuracy"),
        "checkin_rating": parse_rating_category(review_scope, "Check-in"),
        "cleanliness_rating": parse_rating_category(review_scope, "Cleanliness"),
        "communication_rating": parse_rating_category(review_scope, "Communication"),
        "location_rating": parse_rating_category(review_scope, "Location"),
        "value_rating": parse_rating_category(review_scope, "Value"),
    }
    amenities_text = text.lower()
    cancellation = first_match(r"(Flexible|Moderate|Firm|Strict|Non-refundable)[^\n]*(?:cancellation|refund)?", text)
    checkin = first_match(r"(Check-in after[^\n]+)", text)
    checkout = first_match(r"(Checkout before[^\n]+)", text)
    photo_evidence = _photo_product.normalize_photo_product_evidence(
        raw_listing_text=text,
        raw_photo_data=photo_items,
        hero_text=(photo_items or [None])[0] if photo_items else title,
    )
    return {
        "title_text": title,
        "title_length": len(title or ""),
        "property_type": first_match(r"(Entire [^\n]+)", text),
        "max_guests": first_match(r"([0-9]+)\s+guests?", capacity_line or text, int),
        "bedrooms": first_match(r"([0-9]+)\s+bedrooms?\b", capacity_line or text, int),
        "beds": first_match(r"([0-9]+)\s+beds?\b", capacity_line or text, int),
        "bathrooms": first_match(r"([0-9]+(?:\.[0-9]+)?)\s+baths?\b", capacity_line or text, float),
        "overall_rating": rating,
        "review_count": review_count,
        "rating_display_state": rating_display_state(review_scope, rating, review_count),
        "review_scope_confidence": "listing_section_before_host",
        "rating_category_source": rating_category_source(category_ratings),
        **category_ratings,
        "guest_favourite_visible": bool(re.search(r"guest favourite", text, re.I)),
        "top_percent_badge_visible": first_match(r"(Top\s+\d+%[^\\n]*)", text),
        "parking_flag": bool(re.search(r"\bparking\b|car ?park|garage", amenities_text)),
        "pool_spa_flag": bool(re.search(r"\bpool\b|\bspa\b|hot tub|sauna", amenities_text)),
        "pet_friendly_flag": bool(re.search(r"pets? allowed|pet friendly", amenities_text)),
        "workspace_wifi_flag": bool(re.search(r"wifi|dedicated workspace|work space|ethernet", amenities_text)),
        "family_amenities_flag": bool(re.search(r"cot|high chair|children|baby|family", amenities_text)),
        "accessible_features_flag": bool(re.search(r"step-free|accessible|wheelchair", amenities_text)),
        "photo_count": first_match(r"([0-9]+)\s+photos?", text, int),
        **photo_evidence,
        "visible_amenities_core": sorted(set(re.findall(r"\b(pool|spa|sauna|gym|parking|wifi|washer|dryer|kitchen|balcony|lift|air conditioning)\b", amenities_text))),
        "house_rules_summary_flags": [value for value in [checkin, checkout] if value],
        "cancellation_policy_visible": cancellation,
        "review_theme_tags": review_themes(review_scope),
        "visible_review_rows": parse_visible_public_reviews(review_scope),
        "raw_text": text[:15000],
        **star_distribution,
    }


def target_query(listing):
    return (listing.get("address") or listing.get("location_label") or "").replace(", Australia", "")


def destination_from_listing(listing):
    location = listing.get("location_label") or ""
    return location if location else "Melbourne, Victoria, Australia"


def safe_float(value, default=None):
    if isinstance(value, bool):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def adult_count(listing):
    guests = safe_float(listing.get("max_guests"), 2)
    return min(max(int(guests or 2), 1), 8)


def search_url(listing, checkin, nights):
    checkout = checkout_date(checkin, nights)
    params = {
        "query": target_query(listing),
        "checkin": checkin,
        "checkout": checkout,
        "adults": adult_count(listing),
        "room_types[]": "Entire home/apt",
    }
    bedrooms = listing.get("bedrooms")
    bedroom_count = safe_float(bedrooms)
    if bedroom_count:
        params["min_bedrooms"] = int(bedroom_count)
    return f"{BASE}/s/{destination_from_listing(listing).replace(' ', '--').replace(',', '')}/homes?{urlencode(params)}"


def listing_url_with_context(room_url, checkin=None, nights=None, adults=None):
    room_url = clean_room_url(room_url)
    if not checkin:
        return room_url
    params = {
        "check_in": checkin,
        "check_out": checkout_date(checkin, nights or 3),
        "adults": min(max(int(adults or 2), 1), 8),
    }
    return f"{room_url}?{urlencode(params)}"


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

    Airbnb search does not always expose all relevant cards after the first
    load. Scroll the result window and keep first-seen DOM order as the rank
    order. This still records a bounded rank window, not global rank.
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


def rank_observation_confidence(own_card):
    if own_card:
        return "matched_in_bounded_result_window"
    return "not_seen_in_bounded_result_window"


def scroll_public_listing():
    for y in (900, 1800, 3600, 7200, 100000):
        js(f"window.scrollTo(0, {y})")
        wait(0.4)


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


def search_run_id(listing_id, checkin, nights):
    return f"airbnb-own-public-search-{listing_id}-{checkin}-{nights}n"


def record_own_public_capability(records, resource_urls, source_url, observed_at, evidence):
    record = _surfaces.capability_record(
        "own_public_audit",
        observed_at=observed_at,
        auth_context="logged_out_public_guest_visible",
        source_url=source_url,
        resource_urls=resource_urls,
        evidence=evidence,
    )
    _surfaces.upsert_best_capability(records, record)


def main():
    observed_at = utc_now()
    run_id = os.environ.get("AIRBNB_OWN_PUBLIC_RUN_ID") or "airbnb-own-public-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    logged_out_guard = assert_logged_out_public_session()
    listing_file = latest_live_listing_file()
    listing_run = json.loads(listing_file.read_text())
    all_listings = listing_run.get("records") or []
    listings, listing_scope = _listing_scope.select_listings(
        all_listings,
        os.environ.get("AIRBNB_OWN_PUBLIC_LISTING_SCOPE"),
    )
    total_scope_listings = len(listings)
    if not listings:
        raise SystemExit(
            f"Listing source file {listing_file} produced zero listings for scope {listing_scope['label']}"
        )
    if os.environ.get("AIRBNB_OWN_PUBLIC_LIMIT_LISTINGS"):
        listings = listings[: int(os.environ["AIRBNB_OWN_PUBLIC_LIMIT_LISTINGS"])]
    dates = checkin_dates()
    nights_values = _public_scan_planner.resolve_nights_values(
        explicit=os.environ.get("AIRBNB_OWN_PUBLIC_NIGHTS"),
        night_range=os.environ.get("AIRBNB_OWN_PUBLIC_STAY_LENGTH_RANGE"),
        default=DEFAULT_NIGHTS,
    )
    top_results = int(os.environ.get("AIRBNB_OWN_PUBLIC_TOP_RESULTS", DEFAULT_TOP_RESULTS))
    max_search_scrolls = int(os.environ.get("AIRBNB_OWN_PUBLIC_MAX_SEARCH_SCROLLS", DEFAULT_MAX_SEARCH_SCROLLS))
    validation = _public_scan_planner.validate_public_market_options(
        checkin_dates=dates,
        nights_values=nights_values,
        price_bands=None,
        top_results=top_results,
        max_search_scrolls=max_search_scrolls,
        currency="AUD",
    )
    pause = float(os.environ.get("AIRBNB_OWN_PUBLIC_NAV_DELAY_SEC", "2.0"))

    OUTPUT_PATH.mkdir(parents=True, exist_ok=True)
    SESSION_PATH.mkdir(parents=True, exist_ok=True)

    content_audits = []
    review_summaries = []
    visible_review_snapshots = []
    search_runs = []
    search_appearance = []
    surface_capabilities = []
    failures = []
    raw_listing_path = OUTPUT_PATH / f"{run_id}-listing-raw.jsonl"
    raw_search_path = OUTPUT_PATH / f"{run_id}-search-raw.jsonl"

    for index, listing in enumerate(listings, start=1):
        listing_id = str(listing["listing_id"])
        url = listing_url_with_context(listing.get("public_listing_url") or f"{BASE}/rooms/{listing_id}")
        print(json.dumps({"phase": "own_listing_page", "progress": index, "total": len(listings), "listing_id": listing_id, "url": url}), flush=True)
        navigate(url)
        wait_for_load()
        wait(pause)
        scroll_public_listing()
        status = page_content_status(text_limit=45000, html_limit=4000)
        record_own_public_capability(
            surface_capabilities,
            _surfaces.page_api_resource_urls(js),
            url,
            observed_at,
            {"listing_id": listing_id, "phase": "public_listing_page"},
        )
        failure_kind = page_failure(status)
        if failure_kind:
            failures.append({"listing_id": listing_id, "source_url": url, "source": "public_listing_page", "error": failure_kind, "title": status.get("title")})
            continue
        text = status.get("text") or ""
        photo_labels = extract_listing_photo_labels_from_page()
        parsed = parse_listing_text(text, photo_labels)
        with raw_listing_path.open("a") as handle:
            handle.write(json.dumps({"listing_id": listing_id, "observed_at": utc_now(), "url": url, "text": text, "photo_labels": photo_labels}, ensure_ascii=False) + "\n")
        content_audits.append({
            "listing_id": listing_id,
            "observed_at": utc_now(),
            "source_family": "own_public",
            "surface_class": "own_public",
            "auth_context": "logged_out_public_guest_visible",
            "logged_in_flag": False,
            "source_url": url,
            "public_listing_url": clean_room_url(url),
            "title_text": parsed.get("title_text"),
            "title_length": parsed.get("title_length"),
            "property_type": parsed.get("property_type"),
            "max_guests": parsed.get("max_guests"),
            "bedrooms": parsed.get("bedrooms"),
            "beds": parsed.get("beds"),
            "bathrooms": parsed.get("bathrooms"),
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
            "visible_amenities_core": parsed.get("visible_amenities_core"),
            "parking_flag": parsed.get("parking_flag"),
            "pool_spa_flag": parsed.get("pool_spa_flag"),
            "pet_friendly_flag": parsed.get("pet_friendly_flag"),
            "workspace_wifi_flag": parsed.get("workspace_wifi_flag"),
            "family_amenities_flag": parsed.get("family_amenities_flag"),
            "accessible_features_flag": parsed.get("accessible_features_flag"),
            "house_rules_summary_flags": parsed.get("house_rules_summary_flags"),
            "cancellation_policy_visible": parsed.get("cancellation_policy_visible"),
            "guest_favourite_visible": parsed.get("guest_favourite_visible"),
            "top_percent_badge_visible": parsed.get("top_percent_badge_visible"),
            "content_confidence": "public_listing_text",
            "raw_text": parsed.get("raw_text"),
        })
        review_summaries.append({
            "listing_id": listing_id,
            "observed_at": utc_now(),
            "source_family": "own_public",
            "surface_class": "own_public",
            "auth_context": "logged_out_public_guest_visible",
            "logged_in_flag": False,
            "source_url": url,
            "overall_rating": parsed.get("overall_rating"),
            "review_count": parsed.get("review_count"),
            "accuracy_rating": parsed.get("accuracy_rating"),
            "checkin_rating": parsed.get("checkin_rating"),
            "cleanliness_rating": parsed.get("cleanliness_rating"),
            "communication_rating": parsed.get("communication_rating"),
            "location_rating": parsed.get("location_rating"),
            "value_rating": parsed.get("value_rating"),
            "rating_category_source": parsed.get("rating_category_source"),
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
            "review_theme_tags": parsed.get("review_theme_tags"),
        })
        for review_row in parsed.get("visible_review_rows") or []:
            visible_review_snapshots.append({
                "public_review_row_id": visible_review_id(listing_id, review_row),
                "listing_id": listing_id,
                "observed_at": utc_now(),
                "source_family": "own_public",
                "surface_class": "own_public",
                "auth_context": "logged_out_public_guest_visible",
                "logged_in_flag": False,
                "source_url": url,
                **review_row,
            })

    stop_collection = False
    for listing in listings:
        if stop_collection:
            break
        listing_id = str(listing["listing_id"])
        for checkin in dates:
            if stop_collection:
                break
            for nights in nights_values:
                run_key = search_run_id(listing_id, checkin, nights)
                url = search_url(listing, checkin, nights)
                filters_applied = [
                    f"query={target_query(listing)}",
                    "room_types[]=Entire home/apt",
                    f"min_bedrooms={listing.get('bedrooms')}",
                ]
                context_validation = _public_scan_planner.validate_public_search_context(
                    destination=destination_from_listing(listing),
                    checkin=checkin,
                    checkout=checkout_date(checkin, nights),
                    nights=nights,
                    adults=adult_count(listing),
                    currency="AUD",
                    filters=filters_applied,
                    url=url,
                )
                context = {
                    "search_run_id": run_key,
                    "listing_id": listing_id,
                    "observed_at": observed_at,
                    "source_family": "own_public",
                    "surface_class": "own_public",
                    "auth_context": "logged_out_public_guest_visible",
                    "observer_location_country": "AU",
                    "device_type": "desktop",
                    "logged_in_flag": False,
                    "currency": "AUD",
                    "destination": destination_from_listing(listing),
                    "check_in_date": checkin,
                    "check_out_date": checkout_date(checkin, nights),
                    "nights": nights,
                    "guest_count_adults": adult_count(listing),
                    "guest_count_children": 0,
                    "guest_count_pets": 0,
                    "filters_applied": filters_applied,
                    "search_context_validation": context_validation,
                    "source_url": url,
                    "results_limit_requested": top_results,
                    "max_search_scrolls_requested": max_search_scrolls,
                }
                print(json.dumps({"phase": "own_search", "search_run_id": run_key, "url": url}), flush=True)
                navigate(url)
                wait_for_load()
                wait(pause)
                status = page_content_status(text_limit=25000, html_limit=4000)
                record_own_public_capability(
                    surface_capabilities,
                    _surfaces.page_api_resource_urls(js),
                    url,
                    observed_at,
                    {"listing_id": listing_id, "search_run_id": run_key, "phase": "public_search"},
                )
                failure_kind = page_failure(status)
                if failure_kind:
                    failures.append({**context, "source": "public_search", "error": failure_kind, "title": status.get("title")})
                    search_runs.append({**context, "results_count_visible": 0, "status": "failed", "failure_kind": failure_kind})
                    if failure_kind in {"http_429_or_too_many_requests", "http_503_or_airbnb_error"}:
                        stop_collection = True
                    continue
                cards, card_collection = collect_search_cards_from_page(top_results, max_search_scrolls, pause)
                with raw_search_path.open("a") as handle:
                    handle.write(json.dumps({**context, **card_collection, "cards": cards}, ensure_ascii=False) + "\n")
                parsed_cards = []
                own_card = None
                for position, card in enumerate(cards[:top_results], start=1):
                    room_url = clean_room_url(card.get("href"))
                    room_id = room_id_from_url(room_url)
                    parsed = parse_card_text(card.get("text") or "", card.get("photo_alt_texts"))
                    row = {
                        **parsed,
                        "listing_url": room_url,
                        "listing_id_if_extractable": room_id,
                        "result_position": position,
                        "page_number_or_scroll_depth": card.get("page_number_or_scroll_depth"),
                    }
                    parsed_cards.append(row)
                    if room_id == listing_id and own_card is None:
                        own_card = row
                search_runs.append({**context, **card_collection, "results_count_visible": len(parsed_cards), "status": "ok"})
                search_appearance.append({
                    **context,
                    **card_collection,
                    "search_appears_flag": own_card is not None,
                    "search_result_position": own_card.get("result_position") if own_card else None,
                    "page_number_or_scroll_depth": own_card.get("page_number_or_scroll_depth") if own_card else None,
                    "listing_url": own_card.get("listing_url") if own_card else None,
                    "visible_title_short": own_card.get("visible_title_short") if own_card else None,
                    "visible_location_label": own_card.get("visible_location_label") if own_card else None,
                    "visible_price_total": own_card.get("visible_price_total") if own_card else None,
                    "visible_price_per_night": own_card.get("visible_price_per_night") if own_card else None,
                    "visible_rating": own_card.get("visible_rating") if own_card else None,
                    "visible_review_count": own_card.get("visible_review_count") if own_card else None,
                    "visible_badge": own_card.get("visible_badge") if own_card else None,
                    "top_home_highlight_visible": own_card.get("top_home_highlight_visible") if own_card else None,
                    "hero_photo_subject_tag": own_card.get("hero_photo_subject_tag") if own_card else None,
                    "first_five_photo_subjects": own_card.get("first_five_photo_subjects") if own_card else None,
                    "obvious_differentiator_tags": own_card.get("obvious_differentiator_tags") if own_card else [],
                    "available_flag": bool(own_card and own_card.get("visible_price_total")),
                    "rank_observation_confidence": rank_observation_confidence(own_card),
                })

    json_path = OUTPUT_PATH / f"{run_id}.json"
    content_csv = OUTPUT_PATH / f"{run_id}-content-audits.csv"
    reviews_csv = OUTPUT_PATH / f"{run_id}-review-summaries.csv"
    visible_reviews_csv = OUTPUT_PATH / f"{run_id}-visible-review-snapshots.csv"
    search_runs_csv = OUTPUT_PATH / f"{run_id}-search-runs.csv"
    search_appearance_csv = OUTPUT_PATH / f"{run_id}-search-appearance.csv"
    receipt_path = SESSION_PATH / f"{run_id}-receipt.json"
    prior_counts = _integrity.latest_prior_count(
        OUTPUT_PATH,
        count_keys=("review_summary_count",),
        current_run_id=run_id,
    )
    last_good_guard = _integrity.last_good_guard(
        subject="own_public_review_summaries",
        current_count=len(review_summaries),
        prior_positive_count=prior_counts["prior_positive_count"],
        allow_empty=os.environ.get("AIRBNB_OWN_PUBLIC_ALLOW_EMPTY_REVIEWS") == "1",
    )
    warehouse_exports = _integrity.warehouse_manifest([
        {
            "table": "airbnb_own_public_listing_audit",
            "path": str(content_csv),
            "row_count": len(content_audits),
            "grain": "listing_id + observed_at",
            "source_family": "own_public",
            "surface_class": "own_public",
            "auth_context": "logged_out_public_guest_visible",
        },
        {
            "table": "airbnb_own_public_review_summary",
            "path": str(reviews_csv),
            "row_count": len(review_summaries),
            "grain": "listing_id + observed_at",
            "source_family": "own_public",
            "surface_class": "own_public",
            "auth_context": "logged_out_public_guest_visible",
        },
        {
            "table": "airbnb_own_public_search_appearance",
            "path": str(search_appearance_csv),
            "row_count": len(search_appearance),
            "grain": "listing_id + search_run_id",
            "source_family": "own_public",
            "surface_class": "own_public",
            "auth_context": "logged_out_public_guest_visible",
        },
    ])
    output = _integrity.stamp_collection_contract({
        "run_id": run_id,
        "observed_at": observed_at,
        "auth_context": "logged_out_public_guest_visible",
        "source_family": "own_public",
        "surface_class": "own_public",
        "collection_status": _integrity.collection_status(
            last_good_guard_record=last_good_guard,
            failures_count=len(failures),
            complete=len(content_audits) == len(listings),
        ),
        "source": {
            "listing_scope": str(listing_file),
            "backend": "headful_chrome_logged_out",
            "collection_strategy": "public room-page content/review audit plus own-listing search appearance",
            "logged_out_guard": logged_out_guard,
            "max_search_scrolls": max_search_scrolls,
            "validation": validation,
            "surface_capabilities": surface_capabilities,
        },
        "last_good_guard": last_good_guard,
        "warehouse_exports": warehouse_exports,
        "target_listing_count": len(listings),
        "listing_status_scope": listing_scope["label"],
        "total_source_listings": len(all_listings),
        "total_scope_listings": total_scope_listings,
        "listing_scope_complete": len(listings) == total_scope_listings,
        "checkin_dates": dates,
        "nights_values": nights_values,
        "public_input_validation": validation,
        "top_results": top_results,
        "max_search_scrolls": max_search_scrolls,
        "content_audit_count": len(content_audits),
        "review_summary_count": len(review_summaries),
        "visible_review_snapshot_count": len(visible_review_snapshots),
        "search_run_count": len(search_runs),
        "search_appearance_count": len(search_appearance),
        "failures_count": len(failures),
        "content_audits": content_audits,
        "review_summaries": review_summaries,
        "visible_review_snapshots": visible_review_snapshots,
        "search_runs": search_runs,
        "search_appearance": search_appearance,
        "failures": failures[:100],
    },
        source_family="own_public",
        surface_class="own_public",
        auth_context="logged_out_public_guest_visible",
        collection_status=_integrity.collection_status(
            last_good_guard_record=last_good_guard,
            failures_count=len(failures),
            complete=len(content_audits) == len(listings),
        ),
        last_good_guard_record=last_good_guard,
        warehouse_exports=warehouse_exports,
    )
    _integrity.write_collection_json(json_path, output)
    write_csv(content_csv, content_audits)
    write_csv(reviews_csv, review_summaries)
    write_csv(visible_reviews_csv, visible_review_snapshots)
    write_csv(search_runs_csv, search_runs)
    write_csv(search_appearance_csv, search_appearance)
    expected_search_runs = len(listings) * len(dates) * len(nights_values)
    receipt = _integrity.stamp_collection_contract({
        "run_id": run_id,
        "observed_at": observed_at,
        "auth_context": output["auth_context"],
        "source_family": output["source_family"],
        "surface_class": output["surface_class"],
        "collection_status": output["collection_status"],
        "last_good_guard": last_good_guard,
        "warehouse_exports": warehouse_exports,
        "logged_out_guard": logged_out_guard,
        "target_listing_count": len(listings),
        "listing_status_scope": listing_scope["label"],
        "total_source_listings": len(all_listings),
        "total_scope_listings": total_scope_listings,
        "listing_scope_complete": len(listings) == total_scope_listings,
        "checkin_dates": dates,
        "nights_values": nights_values,
        "public_input_validation": validation,
        "top_results": top_results,
        "max_search_scrolls": max_search_scrolls,
        "content_audit_count": len(content_audits),
        "review_summary_count": len(review_summaries),
        "visible_review_snapshot_count": len(visible_review_snapshots),
        "visible_review_snapshot_listing_count": len({row.get("listing_id") for row in visible_review_snapshots}),
        "search_run_count": len(search_runs),
        "expected_search_runs": expected_search_runs,
        "search_appearance_count": len(search_appearance),
        "own_search_appeared_count": len([row for row in search_appearance if row.get("search_appears_flag")]),
        "review_rows_with_review_count_count": len([row for row in review_summaries if row.get("review_count") is not None]),
        "review_rows_with_rating_count": len([row for row in review_summaries if row.get("overall_rating") is not None]),
        "review_rows_with_star_distribution_count": len([row for row in review_summaries if row.get("five_star_pct") is not None]),
        "review_rows_with_rating_category_count": len([
            row for row in review_summaries
            if any(row.get(key) is not None for key in (
                "accuracy_rating", "checkin_rating", "cleanliness_rating",
                "communication_rating", "location_rating", "value_rating",
            ))
        ]),
        "review_rows_no_reviews_yet_count": len([row for row in review_summaries if row.get("rating_display_state") == "no_reviews_yet"]),
        "review_rows_hidden_until_minimum_reviews_count": len([row for row in review_summaries if row.get("rating_display_state") == "hidden_until_minimum_reviews"]),
        "review_rows_rating_category_not_visible_count": len([row for row in review_summaries if row.get("rating_category_source") == "not_visible"]),
        "review_rows_partial_visible_individual_stars_count": len([row for row in review_summaries if row.get("star_distribution_source") == "partial_visible_individual_review_stars"]),
        "failures_count": len(failures),
        "all_public_listing_pages_ok": len(content_audits) == len(listings),
        "all_search_contexts_attempted": len(search_runs) == expected_search_runs,
        "all_search_contexts_have_cards": bool(search_runs) and all(row.get("results_count_visible", 0) > 0 for row in search_runs),
        "json_path": str(json_path),
        "content_csv": str(content_csv),
        "reviews_csv": str(reviews_csv),
        "visible_reviews_csv": str(visible_reviews_csv),
        "search_runs_csv": str(search_runs_csv),
        "search_appearance_csv": str(search_appearance_csv),
        "surface_capabilities": surface_capabilities,
        "failure_sample": failures[:10],
    },
        source_family="own_public",
        surface_class="own_public",
        auth_context=output["auth_context"],
        collection_status=output["collection_status"],
        last_good_guard_record=last_good_guard,
        warehouse_exports=warehouse_exports,
    )
    _integrity.write_receipt_json(receipt_path, receipt)
    print(json.dumps(receipt, indent=2, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    import sys
    if any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
        print((__doc__ or "").strip())
        raise SystemExit(0)
    main()
