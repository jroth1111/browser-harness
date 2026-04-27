"""Collect logged-out Airbnb public competitor snapshots for live host listings.

Run from the browser-harness repo against a fresh logged-out agent Chrome
profile:

    browser-harness --launch-profile domain-skills/airbnb/.session-store/profiles/public-comps \
      --port 52870 --url about:blank --json

    BH_NAME=airbnb-public-comps BH_CDP_WS=http://127.0.0.1:52870 \
      python3 run.py < domain-skills/airbnb/scripts/collect_competitors.py

Private outputs are written under ignored domain-skills/airbnb/.private-data/.
The collector captures date-specific search cards first, then opens the closest
deduplicated comp listing pages for richer attributes.
"""

from __future__ import annotations

import csv
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
    """Navigate an agent-owned public collection tab without tab sprawl."""
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


def parse_csv_ints(value, default):
    raw = value or default
    return [int(part.strip()) for part in raw.split(",") if part.strip()]


def checkin_dates():
    explicit = os.environ.get("AIRBNB_COMP_CHECKIN_DATES")
    if explicit:
        return [part.strip() for part in explicit.split(",") if part.strip()]
    today = date.today()
    return [(today + timedelta(days=offset)).isoformat() for offset in parse_csv_ints(os.environ.get("AIRBNB_COMP_CHECKIN_OFFSETS"), DEFAULT_CHECKIN_OFFSETS)]


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


def parse_card_text(text):
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
        "raw_text": text[:3000],
    }


def listing_review_scope(text):
    return re.split(r"\nMeet your host\n|Meet your host", text or "", maxsplit=1, flags=re.I)[0]


def parse_listing_review_count(scope):
    if re.search(r"\bNo reviews(?:\s*\(yet\)| yet)\b|\bNew listing\b", scope or "", re.I):
        return 0
    matches = re.findall(r"\b([0-9][0-9,]*)\s+reviews?\b", scope or "", re.I)
    if matches:
        return int(matches[0].replace(",", ""))
    return None


def parse_review_star_distribution(scope, review_count):
    star_distribution = {}
    for stars, pct in re.findall(r"([1-5])\s+stars?,\s*([0-9]+)%\s+of reviews", scope or "", re.I):
        percent = int(pct)
        count = round((review_count or 0) * percent / 100) if review_count is not None else None
        star_distribution[f"{stars}_star_pct"] = percent
        star_distribution[f"{stars}_star_count_estimate"] = count
    if star_distribution or not review_count:
        return star_distribution

    counts = {
        str(stars): len(re.findall(rf"\bRating,\s*{stars}\s+stars?\b", scope or "", re.I))
        for stars in range(1, 6)
    }
    total_visible = sum(counts.values())
    if total_visible != review_count:
        return star_distribution
    for stars, count in counts.items():
        if count:
            star_distribution[f"{stars}_star_pct"] = round(count * 100 / review_count)
            star_distribution[f"{stars}_star_count_estimate"] = count
    return star_distribution


def parse_listing_text(text):
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
    rating = first_match(r"Rated\s+([0-5](?:\.\d+)?)\s+out of 5 stars", review_scope, float)
    if rating is None:
        rating = first_match(r"([0-5](?:\.\d+)?)\s+out of 5 stars from", review_scope, float)
    if rating is None:
        rating = first_match(r"([0-5](?:\.\d+)?)\s+out of 5 average rating", review_scope, float)
    review_count = parse_listing_review_count(review_scope)
    star_distribution = parse_review_star_distribution(review_scope, review_count)
    amenities_text = text.lower()
    return {
        "title": title,
        "property_type": first_match(r"(Entire [^\n]+)", text),
        "max_guests": first_match(r"([0-9]+)\s+guests?", capacity_line or text, int),
        "bedrooms": first_match(r"([0-9]+)\s+bedrooms?", capacity_line or text, int),
        "beds": first_match(r"([0-9]+)\s+beds?", capacity_line or text, int),
        "bathrooms": first_match(r"([0-9]+(?:\.[0-9]+)?)\s+baths?", capacity_line or text, float),
        "rating": rating,
        "review_count": review_count,
        "parking_flag": bool(re.search(r"\bparking\b|car ?park|garage", amenities_text)),
        "pool_spa_flag": bool(re.search(r"\bpool\b|\bspa\b|hot tub|sauna", amenities_text)),
        "pet_friendly_flag": bool(re.search(r"pets? allowed|pet friendly", amenities_text)),
        "workspace_wifi_flag": bool(re.search(r"wifi|dedicated workspace|work space|ethernet", amenities_text)),
        "family_amenities_flag": bool(re.search(r"cot|high chair|children|baby|family", amenities_text)),
        "accessible_features_flag": bool(re.search(r"step-free|accessible|wheelchair", amenities_text)),
        "photo_count": first_match(r"([0-9]+)\s+photos?", text, int),
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


def search_url(listing, checkin, nights):
    checkout = checkout_date(checkin, nights)
    query = target_query(listing)
    params = {
        "query": query,
        "checkin": checkin,
        "checkout": checkout,
        "adults": min(max(int(listing.get("max_guests") or 2), 1), 8),
    }
    bedrooms = listing.get("bedrooms")
    if bedrooms:
        params["min_bedrooms"] = int(float(bedrooms))
    return f"{BASE}/s/{destination_from_listing(listing).replace(' ', '--').replace(',', '')}/homes?{urlencode(params)}"


def listing_url_with_context(room_url, checkin, nights, adults):
    params = {
        "check_in": checkin,
        "check_out": checkout_date(checkin, nights),
        "adults": min(max(int(adults or 2), 1), 8),
    }
    return f"{clean_room_url(room_url)}?{urlencode(params)}"


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


def search_run_id(target_listing_id, checkin, nights):
    return f"airbnb-public-search-{target_listing_id}-{checkin}-{nights}n"


def score_comp(target, card, result_position):
    score = 1000 - (result_position * 8)
    for field, weight in (("bedrooms", 35), ("bathrooms", 25), ("beds", 10)):
        target_value = target.get(field)
        card_value = card.get(field)
        if target_value is not None and card_value is not None:
            score -= abs(float(target_value) - float(card_value)) * weight
    if card.get("visible_price_total"):
        score += 20
    if card.get("visible_rating"):
        score += min(float(card["visible_rating"]), 5) * 3
    target_location = (target.get("location_label") or "").split(",")[0].lower()
    if target_location and target_location in (card.get("visible_location_label") or "").lower():
        score += 30
    return round(score, 2)


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


def main():
    observed_at = utc_now()
    run_id = os.environ.get("AIRBNB_COMP_RUN_ID") or "airbnb-public-comps-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    logged_out_guard = assert_logged_out_public_session()
    listing_file = latest_live_listing_file()
    listing_run = json.loads(listing_file.read_text())
    listings = [row for row in listing_run.get("records") or [] if row.get("status") == "ACTIVE"]
    if os.environ.get("AIRBNB_COMP_LIMIT_LISTINGS"):
        listings = listings[: int(os.environ["AIRBNB_COMP_LIMIT_LISTINGS"])]
    nights_values = parse_csv_ints(os.environ.get("AIRBNB_COMP_NIGHTS"), DEFAULT_NIGHTS)
    dates = checkin_dates()
    top_results = int(os.environ.get("AIRBNB_COMP_TOP_RESULTS", DEFAULT_TOP_RESULTS))
    top_comps_per_context = int(os.environ.get("AIRBNB_COMP_TOP_COMPS_PER_CONTEXT", DEFAULT_TOP_COMPS_PER_CONTEXT))
    max_listing_snapshots = int(os.environ.get("AIRBNB_COMP_MAX_LISTING_SNAPSHOTS", DEFAULT_MAX_LISTING_SNAPSHOTS))
    pause = float(os.environ.get("AIRBNB_COMP_NAV_DELAY_SEC", "2.0"))
    OUTPUT_PATH.mkdir(parents=True, exist_ok=True)
    SESSION_PATH.mkdir(parents=True, exist_ok=True)

    target_ids = {str(row.get("listing_id")) for row in listings}
    search_runs = []
    search_results = []
    price_matrix = []
    target_comp_links = []
    comp_snapshot_queue = {}
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
                run_key = search_run_id(target_listing_id, checkin, nights)
                url = search_url(listing, checkin, nights)
                context = {
                    "search_run_id": run_key,
                    "target_listing_id": target_listing_id,
                    "observed_at": observed_at,
                    "observer_location_country": "AU",
                    "device_type": "desktop",
                    "logged_in_flag": False,
                    "currency": "AUD",
                    "destination": destination_from_listing(listing),
                    "map_area_bounds_description": None,
                    "check_in_date": checkin,
                    "check_out_date": checkout_date(checkin, nights),
                    "nights": nights,
                    "guest_count_adults": min(max(int(listing.get("max_guests") or 2), 1), 8),
                    "guest_count_children": 0,
                    "guest_count_pets": 0,
                    "filters_applied": [f"query={target_query(listing)}", f"min_bedrooms={listing.get('bedrooms')}"],
                    "source_url": url,
                }
                print(json.dumps({"phase": "search", "search_run_id": run_key, "url": url}), flush=True)
                navigate(url)
                wait_for_load()
                wait(pause)
                status = page_content_status(text_limit=20000, html_limit=4000)
                failure_kind = page_failure(status)
                if failure_kind:
                    failures.append({**context, "error": failure_kind, "title": status.get("title"), "text_sample": (status.get("text") or "")[:500]})
                    search_runs.append({**context, "results_count_visible": 0, "status": "failed", "failure_kind": failure_kind})
                    if failure_kind in {"http_429_or_too_many_requests", "http_503_or_airbnb_error"}:
                        stop_collection = True
                    continue
                cards = extract_search_cards_from_page()
                with raw_search_path.open("a") as handle:
                    handle.write(json.dumps({**context, "cards": cards}, ensure_ascii=False) + "\n")
                parsed_cards = []
                for card in cards:
                    room_url = clean_room_url(card.get("href"))
                    room_id = room_id_from_url(room_url)
                    if not room_url or room_id in target_ids:
                        continue
                    parsed = parse_card_text(card.get("text") or "")
                    if not parsed.get("visible_price_total") and not parsed.get("visible_title_short"):
                        continue
                    parsed_cards.append({**parsed, "listing_url": room_url, "listing_id_if_extractable": room_id})
                ranked = []
                for index, card in enumerate(parsed_cards[:top_results], start=1):
                    score = score_comp(listing, card, index)
                    ranked.append((score, index, card))
                ranked.sort(key=lambda item: item[0], reverse=True)
                search_runs.append({**context, "results_count_visible": len(parsed_cards), "status": "ok"})
                for score, index, card in ranked[:top_results]:
                    result_row = {
                        "search_run_id": run_key,
                        "target_listing_id": target_listing_id,
                        "result_position": index,
                        "page_number_or_scroll_depth": "initial",
                        "listing_url": card["listing_url"],
                        "listing_id_if_extractable": card["listing_id_if_extractable"],
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
                        "hero_photo_subject_tag": None,
                        "available_flag": bool(card.get("visible_price_total")),
                        "instant_book_visible_flag": None,
                        "obvious_differentiator_tags": [],
                        "competitor_score": score,
                        "raw_text": card.get("raw_text"),
                    }
                    search_results.append(result_row)
                    price_matrix.append({
                        "matrix_id": f"{run_key}-{card['listing_id_if_extractable']}",
                        "comp_listing_id": card["listing_id_if_extractable"],
                        "target_listing_id": target_listing_id,
                        "search_run_id": run_key,
                        "check_in_date": checkin,
                        "check_out_date": checkout_date(checkin, nights),
                        "nights": nights,
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
                        "check_in_date": checkin,
                        "nights": nights,
                        "comp_rank_for_target": comp_rank,
                        "search_result_position": index,
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
        parsed = parse_listing_text(status.get("text") or "")
        with raw_listing_path.open("a") as handle:
            handle.write(json.dumps({**item, "observed_at": utc_now(), "text": status.get("text")}, ensure_ascii=False) + "\n")
        comp_listing_snapshots.append({
            "comp_listing_id": item["comp_listing_id"],
            "observed_at": utc_now(),
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
            "hero_photo_subject": None,
            "review_theme_positive_tags": [],
            "review_theme_negative_tags": [],
            "raw_text": parsed.get("raw_text"),
        })

    output = {
        "run_id": run_id,
        "observed_at": observed_at,
        "auth_context": "logged_out_public_guest_visible",
        "source": {
            "listing_scope": str(listing_file),
            "backend": "headful_chrome_logged_out",
            "collection_strategy": "Airbnb public search cards by target listing/date/stay length, then deduplicated public listing snapshots",
            "granularity_strategy": "date-specific search contexts; rerun over time to build time series",
            "logged_out_guard": logged_out_guard,
            "raw_search_path": str(raw_search_path),
            "raw_listing_path": str(raw_listing_path),
        },
        "target_listing_count": len(listings),
        "checkin_dates": dates,
        "nights_values": nights_values,
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
    json_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    write_csv(search_runs_csv, search_runs)
    write_csv(search_results_csv, search_results)
    write_csv(price_matrix_csv, price_matrix)
    write_csv(target_comps_csv, target_comp_links)
    write_csv(comp_snapshots_csv, comp_listing_snapshots)

    expected_search_runs = len(listings) * len(dates) * len(nights_values)
    receipt = {
        "run_id": run_id,
        "observed_at": observed_at,
        "logged_out_guard": logged_out_guard,
        "target_listing_count": len(listings),
        "expected_search_runs": expected_search_runs,
        "search_run_count": len(search_runs),
        "search_result_count": len(search_results),
        "price_matrix_count": len(price_matrix),
        "target_comp_link_count": len(target_comp_links),
        "comp_listing_snapshot_count": len(comp_listing_snapshots),
        "failures_count": len(failures),
        "all_search_contexts_attempted": len(search_runs) == expected_search_runs,
        "all_search_contexts_have_cards": bool(search_runs) and all(row.get("results_count_visible", 0) > 0 for row in search_runs),
        "all_targets_have_comp_links": all(any(link["target_listing_id"] == str(row["listing_id"]) for link in target_comp_links) for row in listings),
        "json_path": str(json_path),
        "search_runs_csv": str(search_runs_csv),
        "search_results_csv": str(search_results_csv),
        "price_matrix_csv": str(price_matrix_csv),
        "target_comps_csv": str(target_comps_csv),
        "comp_snapshots_csv": str(comp_snapshots_csv),
        "failure_sample": failures[:10],
    }
    receipt_path.write_text(json.dumps(receipt, indent=2, ensure_ascii=False))
    print(json.dumps(receipt, indent=2, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
