"""Collect logged-out guest-visible audits for the host's own Airbnb listings.

Run from the browser-harness repo against a fresh logged-out agent Chrome
profile:

    browser-harness --launch-profile domain-skills/airbnb/.session-store/profiles/own-public \
      --port 52872 --url about:blank --json

    BH_NAME=airbnb-own-public BH_CDP_WS=http://127.0.0.1:52872 \
      python3 run.py < domain-skills/airbnb/scripts/collect_own_public.py

Private outputs are written under ignored domain-skills/airbnb/.private-data/.
This collector must not use the host auth bundle. It captures how the host's
listings appear to a guest in public search and on public listing pages.
"""

from __future__ import annotations

import csv
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
    names = sorted({cookie.get("name") for cookie in cookies if cookie.get("name")})
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
    active_status_count = int((data.get("status_counts") or {}).get("ACTIVE") or 0)
    records = data.get("records") or []
    validation = data.get("field_validation") or {}
    return (
        bool(records)
        and len(records) == int(data.get("active_count") or 0)
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
    raw = value or default
    return [int(part.strip()) for part in raw.split(",") if part.strip()]


def checkin_dates():
    explicit = os.environ.get("AIRBNB_OWN_PUBLIC_CHECKIN_DATES")
    if explicit:
        return [part.strip() for part in explicit.split(",") if part.strip()]
    today = date.today()
    return [(today + timedelta(days=offset)).isoformat() for offset in parse_csv_ints(os.environ.get("AIRBNB_OWN_PUBLIC_CHECKIN_OFFSETS"), DEFAULT_CHECKIN_OFFSETS)]


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


def parse_card_text(text):
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
    return {
        "visible_title_short": title,
        "visible_location_label": location,
        "visible_price_total": total,
        "visible_price_per_night": nightly,
        "visible_rating": rating,
        "visible_review_count": review_count,
        "visible_badge": "Guest favourite" if re.search(r"guest favourite", text, re.I) else None,
        "top_home_highlight_visible": bool(re.search(r"top\s+\d+%|top home", text, re.I)),
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


def parse_listing_text(text):
    text = re.sub(r"\n{2,}", "\n", (text or "").strip())
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    title = None
    for line in lines[:50]:
        if line.lower() in {"share", "save", "photos", "show all photos", "start your search"}:
            continue
        if len(line) > 8 and not re.search(r"airbnb|skip to content|translation|rating|reviews?", line, re.I):
            title = line
            break
    capacity_line = next((line for line in lines if re.search(r"\d+\s+guests?", line, re.I) and re.search(r"bedrooms?|beds?|baths?", line, re.I)), "")
    rating = first_match(r"Rated\s+([0-5](?:\.\d+)?)\s+out of 5 stars", text, float)
    if rating is None:
        rating = first_match(r"([0-5](?:\.\d+)?)\s+out of 5 stars from", text, float)
    if rating is None:
        rating = first_match(r"([0-5](?:\.\d+)?)\s+out of 5 average rating", text, float)
    review_count = first_match(r"([0-9,]+)\s+reviews?", text, lambda v: int(v.replace(",", "")))
    star_distribution = {}
    for stars, pct in re.findall(r"([1-5])\s+stars?,\s*([0-9]+)%\s+of reviews", text, re.I):
        percent = int(pct)
        count = round((review_count or 0) * percent / 100) if review_count is not None else None
        star_distribution[f"{stars}_star_pct"] = percent
        star_distribution[f"{stars}_star_count_estimate"] = count
    amenities_text = text.lower()
    cancellation = first_match(r"(Flexible|Moderate|Firm|Strict|Non-refundable)[^\n]*(?:cancellation|refund)?", text)
    checkin = first_match(r"(Check-in after[^\n]+)", text)
    checkout = first_match(r"(Checkout before[^\n]+)", text)
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
        "accuracy_rating": parse_rating_category(text, "Accuracy"),
        "checkin_rating": parse_rating_category(text, "Check-in"),
        "cleanliness_rating": parse_rating_category(text, "Cleanliness"),
        "communication_rating": parse_rating_category(text, "Communication"),
        "location_rating": parse_rating_category(text, "Location"),
        "value_rating": parse_rating_category(text, "Value"),
        "guest_favourite_visible": bool(re.search(r"guest favourite", text, re.I)),
        "top_percent_badge_visible": first_match(r"(Top\s+\d+%[^\\n]*)", text),
        "parking_flag": bool(re.search(r"\bparking\b|car ?park|garage", amenities_text)),
        "pool_spa_flag": bool(re.search(r"\bpool\b|\bspa\b|hot tub|sauna", amenities_text)),
        "pet_friendly_flag": bool(re.search(r"pets? allowed|pet friendly", amenities_text)),
        "workspace_wifi_flag": bool(re.search(r"wifi|dedicated workspace|work space|ethernet", amenities_text)),
        "family_amenities_flag": bool(re.search(r"cot|high chair|children|baby|family", amenities_text)),
        "accessible_features_flag": bool(re.search(r"step-free|accessible|wheelchair", amenities_text)),
        "photo_count": first_match(r"([0-9]+)\s+photos?", text, int),
        "visible_amenities_core": sorted(set(re.findall(r"\b(pool|spa|sauna|gym|parking|wifi|washer|dryer|kitchen|balcony|lift|air conditioning)\b", amenities_text))),
        "house_rules_summary_flags": [value for value in [checkin, checkout] if value],
        "cancellation_policy_visible": cancellation,
        "review_theme_tags": review_themes(text),
        "raw_text": text[:15000],
        **star_distribution,
    }


def target_query(listing):
    return (listing.get("address") or listing.get("location_label") or "").replace(", Australia", "")


def destination_from_listing(listing):
    location = listing.get("location_label") or ""
    return location if location else "Melbourne, Victoria, Australia"


def search_url(listing, checkin, nights):
    checkout = checkout_date(checkin, nights)
    params = {
        "query": target_query(listing),
        "checkin": checkin,
        "checkout": checkout,
        "adults": min(max(int(listing.get("max_guests") or 2), 1), 8),
    }
    bedrooms = listing.get("bedrooms")
    if bedrooms:
        params["min_bedrooms"] = int(float(bedrooms))
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
    title = (status.get("title") or "").lower()
    text = (status.get("text") or "").lower()
    if status.get("block", {}).get("blocked"):
        return status.get("block", {}).get("kind") or "blocked"
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
    cards.push({href, room_id: match[1], text: best});
  }
  return cards;
})()
"""
    ) or []


def scroll_public_listing():
    for y in (900, 1800, 3600, 7200, 100000):
        js(f"window.scrollTo(0, {y})")
        wait(0.4)


def write_csv(path, rows):
    if not rows:
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


def main():
    observed_at = utc_now()
    run_id = os.environ.get("AIRBNB_OWN_PUBLIC_RUN_ID") or "airbnb-own-public-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    logged_out_guard = assert_logged_out_public_session()
    listing_file = latest_live_listing_file()
    listing_run = json.loads(listing_file.read_text())
    listings = [row for row in listing_run.get("records") or [] if row.get("status") == "ACTIVE"]
    if os.environ.get("AIRBNB_OWN_PUBLIC_LIMIT_LISTINGS"):
        listings = listings[: int(os.environ["AIRBNB_OWN_PUBLIC_LIMIT_LISTINGS"])]
    dates = checkin_dates()
    nights_values = parse_csv_ints(os.environ.get("AIRBNB_OWN_PUBLIC_NIGHTS"), DEFAULT_NIGHTS)
    top_results = int(os.environ.get("AIRBNB_OWN_PUBLIC_TOP_RESULTS", DEFAULT_TOP_RESULTS))
    pause = float(os.environ.get("AIRBNB_OWN_PUBLIC_NAV_DELAY_SEC", "2.0"))

    OUTPUT_PATH.mkdir(parents=True, exist_ok=True)
    SESSION_PATH.mkdir(parents=True, exist_ok=True)

    content_audits = []
    review_summaries = []
    search_runs = []
    search_appearance = []
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
        failure_kind = page_failure(status)
        if failure_kind:
            failures.append({"listing_id": listing_id, "source_url": url, "source": "public_listing_page", "error": failure_kind, "title": status.get("title")})
            continue
        text = status.get("text") or ""
        parsed = parse_listing_text(text)
        with raw_listing_path.open("a") as handle:
            handle.write(json.dumps({"listing_id": listing_id, "observed_at": utc_now(), "url": url, "text": text}, ensure_ascii=False) + "\n")
        content_audits.append({
            "listing_id": listing_id,
            "observed_at": utc_now(),
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
            "review_theme_tags": parsed.get("review_theme_tags"),
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
                context = {
                    "search_run_id": run_key,
                    "listing_id": listing_id,
                    "observed_at": observed_at,
                    "observer_location_country": "AU",
                    "device_type": "desktop",
                    "logged_in_flag": False,
                    "currency": "AUD",
                    "destination": destination_from_listing(listing),
                    "check_in_date": checkin,
                    "check_out_date": checkout_date(checkin, nights),
                    "nights": nights,
                    "guest_count_adults": min(max(int(listing.get("max_guests") or 2), 1), 8),
                    "guest_count_children": 0,
                    "guest_count_pets": 0,
                    "filters_applied": [f"query={target_query(listing)}", f"min_bedrooms={listing.get('bedrooms')}"],
                    "source_url": url,
                }
                print(json.dumps({"phase": "own_search", "search_run_id": run_key, "url": url}), flush=True)
                navigate(url)
                wait_for_load()
                wait(pause)
                status = page_content_status(text_limit=25000, html_limit=4000)
                failure_kind = page_failure(status)
                if failure_kind:
                    failures.append({**context, "source": "public_search", "error": failure_kind, "title": status.get("title")})
                    search_runs.append({**context, "results_count_visible": 0, "status": "failed", "failure_kind": failure_kind})
                    if failure_kind in {"http_429_or_too_many_requests", "http_503_or_airbnb_error"}:
                        stop_collection = True
                    continue
                cards = extract_search_cards_from_page()
                with raw_search_path.open("a") as handle:
                    handle.write(json.dumps({**context, "cards": cards}, ensure_ascii=False) + "\n")
                parsed_cards = []
                own_card = None
                for position, card in enumerate(cards[:top_results], start=1):
                    room_url = clean_room_url(card.get("href"))
                    room_id = room_id_from_url(room_url)
                    parsed = parse_card_text(card.get("text") or "")
                    row = {**parsed, "listing_url": room_url, "listing_id_if_extractable": room_id, "result_position": position}
                    parsed_cards.append(row)
                    if room_id == listing_id and own_card is None:
                        own_card = row
                search_runs.append({**context, "results_count_visible": len(parsed_cards), "status": "ok"})
                search_appearance.append({
                    **context,
                    "search_appears_flag": own_card is not None,
                    "search_result_position": own_card.get("result_position") if own_card else None,
                    "listing_url": own_card.get("listing_url") if own_card else None,
                    "visible_title_short": own_card.get("visible_title_short") if own_card else None,
                    "visible_location_label": own_card.get("visible_location_label") if own_card else None,
                    "visible_price_total": own_card.get("visible_price_total") if own_card else None,
                    "visible_price_per_night": own_card.get("visible_price_per_night") if own_card else None,
                    "visible_rating": own_card.get("visible_rating") if own_card else None,
                    "visible_review_count": own_card.get("visible_review_count") if own_card else None,
                    "visible_badge": own_card.get("visible_badge") if own_card else None,
                    "top_home_highlight_visible": own_card.get("top_home_highlight_visible") if own_card else None,
                    "available_flag": bool(own_card and own_card.get("visible_price_total")),
                    "rank_observation_confidence": "top_results_card_match" if own_card else "not_seen_in_top_results",
                })

    json_path = OUTPUT_PATH / f"{run_id}.json"
    content_csv = OUTPUT_PATH / f"{run_id}-content-audits.csv"
    reviews_csv = OUTPUT_PATH / f"{run_id}-review-summaries.csv"
    search_runs_csv = OUTPUT_PATH / f"{run_id}-search-runs.csv"
    search_appearance_csv = OUTPUT_PATH / f"{run_id}-search-appearance.csv"
    receipt_path = SESSION_PATH / f"{run_id}-receipt.json"
    output = {
        "run_id": run_id,
        "observed_at": observed_at,
        "auth_context": "logged_out_public_guest_visible",
        "source": {
            "listing_scope": str(listing_file),
            "backend": "headful_chrome_logged_out",
            "collection_strategy": "public room-page content/review audit plus own-listing search appearance",
            "logged_out_guard": logged_out_guard,
        },
        "target_listing_count": len(listings),
        "checkin_dates": dates,
        "nights_values": nights_values,
        "content_audit_count": len(content_audits),
        "review_summary_count": len(review_summaries),
        "search_run_count": len(search_runs),
        "search_appearance_count": len(search_appearance),
        "failures_count": len(failures),
        "content_audits": content_audits,
        "review_summaries": review_summaries,
        "search_runs": search_runs,
        "search_appearance": search_appearance,
        "failures": failures[:100],
    }
    json_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    write_csv(content_csv, content_audits)
    write_csv(reviews_csv, review_summaries)
    write_csv(search_runs_csv, search_runs)
    write_csv(search_appearance_csv, search_appearance)
    expected_search_runs = len(listings) * len(dates) * len(nights_values)
    receipt = {
        "run_id": run_id,
        "observed_at": observed_at,
        "auth_context": output["auth_context"],
        "logged_out_guard": logged_out_guard,
        "target_listing_count": len(listings),
        "checkin_dates": dates,
        "nights_values": nights_values,
        "content_audit_count": len(content_audits),
        "review_summary_count": len(review_summaries),
        "search_run_count": len(search_runs),
        "expected_search_runs": expected_search_runs,
        "search_appearance_count": len(search_appearance),
        "own_search_appeared_count": len([row for row in search_appearance if row.get("search_appears_flag")]),
        "review_rows_with_rating_count": len([row for row in review_summaries if row.get("overall_rating") is not None]),
        "review_rows_with_star_distribution_count": len([row for row in review_summaries if row.get("five_star_pct") is not None]),
        "failures_count": len(failures),
        "all_public_listing_pages_ok": len(content_audits) == len(listings),
        "all_search_contexts_attempted": len(search_runs) == expected_search_runs,
        "all_search_contexts_have_cards": bool(search_runs) and all(row.get("results_count_visible", 0) > 0 for row in search_runs),
        "json_path": str(json_path),
        "content_csv": str(content_csv),
        "reviews_csv": str(reviews_csv),
        "search_runs_csv": str(search_runs_csv),
        "search_appearance_csv": str(search_appearance_csv),
        "failure_sample": failures[:10],
    }
    receipt_path.write_text(json.dumps(receipt, indent=2, ensure_ascii=False))
    print(json.dumps(receipt, indent=2, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
