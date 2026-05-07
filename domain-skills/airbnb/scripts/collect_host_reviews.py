"""Collect authenticated Airbnb host review rows.

Role: collector (private). Captures host-visible review rows per listing.

Reads:
    - Latest complete `airbnb-live-listings-*.json` under
      `.private-data/listing-collections/` (override with
      `AIRBNB_LISTINGS_FILE`).
    - Authenticated Performance > Quality review page and discovered review
      API resources from inside the browser context.

Produces:
    - `airbnb_review`-shaped rows under `.private-data/review-collections/`.
    - `domain-skills/airbnb/.session-store/capability/<run_id>-receipt.json`.

Requires (env, optional unless noted):
    - `AIRBNB_HOST_REVIEWS_LISTING_SCOPE` — `all`, `statuses:ACTIVE,UNLISTED`,
      `ids:<listing_id>,<listing_id>`. Default scope is `ACTIVE`.
    - `AIRBNB_LISTINGS_FILE` — alternative listing artifact (smoke runs only).

Refuses to run if:
    - No complete `airbnb-live-listings-*.json` artifact exists and
      `AIRBNB_LISTINGS_FILE` is not set.
    - Authenticated Airbnb host cookies are missing from the browser context.

Run from the browser-harness repo against an authenticated Airbnb host browser
context:

    BH_NAME=airbnb-host-reviews BH_CDP_WS=http://127.0.0.1:52862 \
      python3 run.py < domain-skills/airbnb/scripts/collect_host_reviews.py

Private outputs are written under ignored domain-skills/airbnb/.private-data/.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from browser_harness import login_session


BASE = "https://www.airbnb.com.au"
HOST_REVIEWS_URL = BASE + "/performance/quality/overall"
LISTINGS_PATH = Path("domain-skills/airbnb/.private-data/listing-collections")
OUTPUT_PATH = Path("domain-skills/airbnb/.private-data/review-collections")
SESSION_PATH = Path("domain-skills/airbnb/.session-store/capability")

DEFAULT_PAGE_LIMIT = 50
DEFAULT_MAX_PAGES = 50
_NAVIGATED = False

REVIEW_TEXT_KEYS = (
    "reviewText",
    "publicReview",
    "publicReviewText",
    "guestReview",
    "guestReviewText",
    "comments",
    "comment",
    "body",
)
DATE_KEYS = ("reviewDate", "submittedAt", "createdAt", "date")
RATING_KEYS = ("overallRating", "rating", "starRating")
CATEGORY_LABELS = {
    "accuracy": ("accuracy",),
    "checkin": ("checkin", "checkIn", "check-in"),
    "cleanliness": ("cleanliness",),
    "communication": ("communication",),
    "location": ("location",),
    "value": ("value",),
}


def _load_local_module(module_filename, module_name):
    path = Path("domain-skills/airbnb/scripts") / module_filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_listing_scope = _load_local_module("listing_scope.py", "airbnb_listing_scope")
_surfaces = _load_local_module("surface_capabilities.py", "airbnb_surface_capabilities")
_integrity = _load_local_module("run_integrity.py", "airbnb_run_integrity")


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def navigate(url):
    global _NAVIGATED
    if not _NAVIGATED:
        new_tab(url)
        _NAVIGATED = True
    else:
        goto_url(url)


def read_response_text(response):
    data = response.read()
    return data.decode("utf-8", errors="replace")


def stringify(value):
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, (int, float, bool)):
        return str(value)
    return None


def as_number(value):
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        match = re.search(r"-?\d+(?:\.\d+)?", value)
        if match:
            parsed = float(match.group(0))
            return int(parsed) if parsed.is_integer() else parsed
    return None


def direct_value(obj, names):
    if not isinstance(obj, dict):
        return None
    lowered = {str(key).lower(): key for key in obj}
    for name in names:
        key = lowered.get(str(name).lower())
        if key is not None:
            return obj.get(key)
    return None


def recursive_value(obj, names, max_depth=5):
    direct = direct_value(obj, names)
    if direct is not None:
        return direct
    if max_depth <= 0:
        return None
    if isinstance(obj, dict):
        for value in obj.values():
            found = recursive_value(value, names, max_depth=max_depth - 1)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = recursive_value(value, names, max_depth=max_depth - 1)
            if found is not None:
                return found
    return None


def review_themes(text):
    lowered = (text or "").lower()
    theme_patterns = {
        "cleanliness": r"clean|spotless|dirty|dust|mould|mold",
        "accuracy": r"accurate|as described|not as described|misleading",
        "checkin": r"check[- ]?in|key|lockbox|arrival",
        "noise": r"noise|noisy|quiet",
        "beds_sleep": r"bed|mattress|sleep|pillow",
        "wifi_work": r"wifi|wi-fi|internet|workspace|work",
        "value": r"value|worth|expensive|price",
    }
    return [name for name, pattern in theme_patterns.items() if re.search(pattern, lowered)]


def stable_review_id(listing_id, row):
    material = "|".join(str(row.get(key) or "") for key in (
        "reservation_id", "review_date", "stay_month", "overall_rating", "review_text"
    ))
    digest = hashlib.sha256(f"{listing_id}|{material}".encode("utf-8")).hexdigest()[:16]
    return f"host-review-{listing_id}-{digest}"


def normalize_date(value):
    text = stringify(value)
    if not text:
        return None
    iso = re.match(r"(\d{4}-\d{2}-\d{2})", text)
    return iso.group(1) if iso else text[:80]


def normalize_category_ratings(candidate):
    source = (
        direct_value(candidate, ("categoryRatings", "category_ratings", "subratings"))
        or recursive_value(candidate, ("categoryRatings", "category_ratings", "subratings"), max_depth=3)
    )
    ratings = {}
    if isinstance(source, dict):
        for canonical, labels in CATEGORY_LABELS.items():
            value = recursive_value(source, labels, max_depth=3)
            number = as_number(value)
            if number is not None:
                ratings[canonical] = number
    elif isinstance(source, list):
        for item in source:
            label = stringify(direct_value(item, ("label", "name", "category", "key")))
            value = as_number(direct_value(item, ("rating", "value", "score")))
            if not label or value is None:
                continue
            lowered = label.lower().replace("-", "").replace(" ", "")
            for canonical, labels in CATEGORY_LABELS.items():
                if any(lowered == label_name.lower().replace("-", "").replace(" ", "") for label_name in labels):
                    ratings[canonical] = value
                    break
    return ratings or None


def normalize_host_response(candidate):
    response = direct_value(candidate, ("hostResponse", "host_response", "response", "reply"))
    if response is None:
        response = recursive_value(candidate, ("hostResponse", "host_response"), max_depth=3)
    if isinstance(response, dict):
        text = stringify(recursive_value(response, ("responseText", "text", "body", "comment"), max_depth=3))
        response_date = normalize_date(recursive_value(response, DATE_KEYS, max_depth=3))
    else:
        text = stringify(response)
        response_date = None
    return text, response_date


def normalize_review_text(candidate):
    value = direct_value(candidate, REVIEW_TEXT_KEYS)
    if isinstance(value, dict):
        return stringify(direct_value(value, ("reviewText", "text", "body", "comment")))
    text = stringify(value)
    if text:
        return text
    review_obj = direct_value(candidate, ("review", "guestReview", "publicReview"))
    if isinstance(review_obj, dict):
        return stringify(direct_value(review_obj, ("reviewText", "text", "body", "comment")))
    return stringify(review_obj)


def normalize_review_candidate(candidate, default_listing_id, observed_at, source_url, source_kind):
    if not isinstance(candidate, dict):
        return None
    candidate_keys = {str(key).lower() for key in candidate}
    reviewish_keys = {
        "reviewid", "review_id", "reviewtext", "publicreview", "publicreviewtext",
        "guestreview", "guestreviewtext", "reservationid", "reservation_id",
        "overallrating", "starrating", "categoryratings", "hostresponse",
    }
    if not candidate_keys & reviewish_keys:
        return None
    listing_id = (
        stringify(direct_value(candidate, ("listingId", "listing_id", "roomId", "room_id")))
        or str(default_listing_id)
    )
    review_text = normalize_review_text(candidate)
    host_response_text, host_response_date = normalize_host_response(candidate)
    overall_rating = as_number(recursive_value(candidate, RATING_KEYS, max_depth=3))
    if not any([review_text, host_response_text, overall_rating is not None]):
        return None
    row = {
        "review_id": stringify(direct_value(candidate, ("reviewId", "review_id", "id"))),
        "listing_id": listing_id,
        "reservation_id": stringify(recursive_value(candidate, ("reservationId", "reservation_id", "confirmationCode"), max_depth=4)),
        "review_date": normalize_date(recursive_value(candidate, DATE_KEYS, max_depth=3)),
        "stay_month": stringify(recursive_value(candidate, ("stayMonth", "stay_month"), max_depth=4)),
        "length_of_stay_band": stringify(recursive_value(candidate, ("lengthOfStayBand", "length_of_stay_band"), max_depth=4)),
        "trip_type": stringify(recursive_value(candidate, ("tripType", "trip_type"), max_depth=4)),
        "overall_rating": overall_rating,
        "category_ratings": normalize_category_ratings(candidate),
        "review_text": review_text,
        "review_theme_tags": review_themes(review_text),
        "host_response_present": bool(host_response_text),
        "host_response_date": host_response_date,
        "host_response_text": host_response_text,
        "observed_at": observed_at,
        "source_family": "host_private",
        "surface_class": "host_private",
        "auth_context": "host_private_browser_session",
        "source_url": source_url,
        "review_row_source": source_kind,
        "review_row_confidence": "host_private_review_row",
    }
    if not row["review_id"]:
        row["review_id"] = stable_review_id(listing_id, row)
    return row


def walk_review_rows(obj, listing_id, observed_at, source_url, source_kind):
    rows = []
    if isinstance(obj, dict):
        row = normalize_review_candidate(obj, listing_id, observed_at, source_url, source_kind)
        if row:
            rows.append(row)
        for value in obj.values():
            rows.extend(walk_review_rows(value, listing_id, observed_at, source_url, source_kind))
    elif isinstance(obj, list):
        for value in obj:
            rows.extend(walk_review_rows(value, listing_id, observed_at, source_url, source_kind))
    return rows


def parse_total_count(obj):
    if isinstance(obj, dict):
        for key, value in obj.items():
            if str(key).lower() in {"totalcount", "total_count", "reviewcount", "review_count"}:
                number = as_number(value)
                if number is not None:
                    return int(number)
        for value in obj.values():
            found = parse_total_count(value)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = parse_total_count(value)
            if found is not None:
                return found
    return None


def dedupe_reviews(rows):
    out = {}
    for row in rows:
        key = (str(row.get("listing_id")), str(row.get("review_id")))
        current = out.get(key, {})
        merged = {**current, **{k: v for k, v in row.items() if v not in (None, "", [])}}
        out[key] = merged
    return list(out.values())


def parse_host_review_json(data, listing_id, observed_at, source_url):
    rows = walk_review_rows(data, listing_id, observed_at, source_url, "host_reviews_api")
    return dedupe_reviews(rows), parse_total_count(data)


MONTH_PATTERN = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4}"


def parse_host_review_text(text, listing_id, observed_at, source_url):
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    rows = []
    rating_pattern = re.compile(r"\bRating,\s*([1-5])\s+stars?\b|\b([1-5])\s+stars?\b", re.I)
    for index, line in enumerate(lines):
        rating_match = rating_pattern.search(line)
        if not rating_match:
            continue
        rating = int(rating_match.group(1) or rating_match.group(2))
        date_label = None
        text_lines = []
        cursor = index + 1
        while cursor < len(lines):
            current = lines[cursor]
            if rating_pattern.search(current):
                break
            if date_label is None and re.fullmatch(MONTH_PATTERN, current, re.I):
                date_label = current
                cursor += 1
                continue
            if re.search(r"show more|show less|translate|helpful|report", current, re.I):
                cursor += 1
                continue
            text_lines.append(current)
            cursor += 1
        review_text = " ".join(text_lines).strip()
        row = {
            "review_id": None,
            "listing_id": str(listing_id),
            "reservation_id": None,
            "review_date": None,
            "stay_month": date_label,
            "length_of_stay_band": None,
            "trip_type": None,
            "overall_rating": rating,
            "category_ratings": None,
            "review_text": review_text,
            "review_theme_tags": review_themes(review_text),
            "host_response_present": False,
            "host_response_date": None,
            "host_response_text": None,
            "observed_at": observed_at,
            "source_family": "host_private",
            "surface_class": "host_private",
            "auth_context": "host_private_browser_session",
            "source_url": source_url,
            "review_row_source": "host_reviews_rendered_text",
            "review_row_confidence": "host_rendered_review_row",
        }
        row["review_id"] = stable_review_id(listing_id, row)
        rows.append(row)
    return dedupe_reviews(rows)


def latest_listing_file() -> Path:
    explicit = os.environ.get("AIRBNB_LISTINGS_FILE")
    if explicit:
        return Path(explicit)
    files = sorted(LISTINGS_PATH.glob("airbnb-live-listings-*.json"))
    if not files:
        raise SystemExit(f"No listing collection found under {LISTINGS_PATH}")
    complete = [path for path in files if is_complete_active_listing_file(path)]
    if not complete:
        raise SystemExit(
            f"No complete active listing collection found under {LISTINGS_PATH}; "
            "set AIRBNB_LISTINGS_FILE explicitly for a non-canonical scope"
        )
    return complete[-1]


def is_complete_active_listing_file(path: Path) -> bool:
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


def maybe_restore_auth(verification_url):
    state_path = os.environ.get("AIRBNB_AUTH_STATE_PATH")
    if not state_path:
        return None
    state = json.loads(Path(state_path).read_text())
    verification = login_session.restore_session_state_and_verify(
        cdp,
        state,
        [verification_url],
        include_session_storage=True,
        min_text=int(os.environ.get("AIRBNB_HOST_REVIEWS_AUTH_MIN_TEXT", "500")),
        timeout=float(os.environ.get("AIRBNB_HOST_REVIEWS_AUTH_TIMEOUT_SEC", "45")),
    )
    if not verification.get("ok"):
        raise SystemExit(f"Airbnb auth restore failed: {json.dumps(verification, ensure_ascii=False)}")
    return {
        "state_path": state_path,
        "cookie_restore": verification.get("restore", {}).get("cookies", {}),
        "resources_checked": verification.get("resources_checked", []),
    }


def fetch_json(url, base_headers):
    headers = {
        **base_headers,
        "Accept": "application/json",
        "Accept-Encoding": "identity",
        "X-Airbnb-GraphQL-Platform": "web",
        "X-CSRF-Without-Token": "1",
    }
    api_key = os.environ.get("AIRBNB_API_KEY")
    if api_key:
        headers["X-Airbnb-API-Key"] = api_key
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=float(os.environ.get("AIRBNB_HOST_REVIEWS_FETCH_TIMEOUT_SEC", "25"))) as response:
            text = read_response_text(response)
            return {"ok": 200 <= response.status < 300, "status": response.status, "data": json.loads(text)}
    except HTTPError as error:
        text = read_response_text(error)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = {"text": text[:500]}
        return {"ok": False, "status": error.code, "data": data}
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        return {"ok": False, "status": None, "error": str(error)}


def host_reviews_url(listing_id):
    template = os.environ.get("AIRBNB_HOST_REVIEWS_URL_TEMPLATE")
    if template:
        return template.format(listing_id=listing_id)
    return f"{HOST_REVIEWS_URL}/listing/{listing_id}"


def api_url_from_template(listing_id, offset, limit):
    template = os.environ.get("AIRBNB_HOST_REVIEWS_API_URL_TEMPLATE")
    if not template:
        return None
    return template.format(listing_id=listing_id, offset=offset, limit=limit)


def review_api_resource_urls(listing_id):
    return js(f"""(() => {{
  const listingId = {json.dumps(str(listing_id))};
  return Array.from(performance.getEntriesByType('resource') || [])
    .map(entry => entry.name || '')
    .filter(url => /\\/api\\//i.test(url) && /review/i.test(url))
    .filter(url => !listingId || url.includes(listingId))
    .slice(-20);
}})()""") or []


def scroll_host_reviews(max_scrolls, pause):
    last_height = 0
    stable = 0
    for _ in range(max_scrolls):
        height = js("Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)") or 0
        js("window.scrollTo(0, Math.max(document.body.scrollHeight, document.documentElement.scrollHeight))")
        wait(pause)
        if height == last_height:
            stable += 1
            if stable >= 2:
                break
        else:
            stable = 0
        last_height = height


def review_export_confidence(row_count, expected_count):
    if expected_count == 0 and row_count == 0:
        return "complete_no_reviews"
    if expected_count is not None and row_count >= expected_count:
        return "complete_against_host_total"
    if expected_count is not None:
        return "partial_against_host_total"
    if row_count:
        return "rows_collected_without_known_total"
    return "no_rows_without_known_total"


def collect_api_template_reviews(listing_id, base_headers, observed_at, raw_handle):
    rows = []
    expected_total = None
    limit = int(os.environ.get("AIRBNB_HOST_REVIEWS_PAGE_LIMIT", DEFAULT_PAGE_LIMIT))
    max_pages = int(os.environ.get("AIRBNB_HOST_REVIEWS_MAX_PAGES", DEFAULT_MAX_PAGES))
    for page in range(max_pages):
        offset = page * limit
        url = api_url_from_template(listing_id, offset, limit)
        if not url:
            break
        result = fetch_json(url, base_headers)
        raw_handle.write(json.dumps({
            "listing_id": str(listing_id),
            "offset": offset,
            "limit": limit,
            "url": url,
            "result": result,
        }, ensure_ascii=False) + "\n")
        if not result.get("ok"):
            break
        parsed, total = parse_host_review_json(result.get("data"), listing_id, observed_at, url)
        rows.extend(parsed)
        expected_total = total if total is not None else expected_total
        rows = dedupe_reviews(rows)
        if not parsed:
            break
        if expected_total is not None and len(rows) >= expected_total:
            break
    return rows, expected_total


def collect_listing_reviews(listing, base_headers, observed_at, raw_handle):
    listing_id = str(listing["listing_id"])
    rows, expected_total = collect_api_template_reviews(listing_id, base_headers, observed_at, raw_handle)
    source_url = host_reviews_url(listing_id)
    api_resource_urls = []
    if not rows:
        navigate(source_url)
        wait_for_load()
        wait(float(os.environ.get("AIRBNB_HOST_REVIEWS_NAV_DELAY_SEC", "2.0")))
        scroll_host_reviews(
            int(os.environ.get("AIRBNB_HOST_REVIEWS_MAX_SCROLLS", "20")),
            float(os.environ.get("AIRBNB_HOST_REVIEWS_SCROLL_PAUSE_SEC", "0.6")),
        )
        text = js("document.body ? document.body.innerText : ''") or ""
        api_resource_urls = review_api_resource_urls(listing_id)
        raw_handle.write(json.dumps({
            "listing_id": listing_id,
            "url": source_url,
            "text": text,
            "api_resource_urls": api_resource_urls,
        }, ensure_ascii=False) + "\n")
        for url in api_resource_urls:
            result = fetch_json(url, base_headers)
            raw_handle.write(json.dumps({"listing_id": listing_id, "url": url, "result": result}, ensure_ascii=False) + "\n")
            if not result.get("ok"):
                continue
            parsed, total = parse_host_review_json(result.get("data"), listing_id, observed_at, url)
            rows.extend(parsed)
            expected_total = total if total is not None else expected_total
        rows = dedupe_reviews(rows)
        if not rows:
            rows = parse_host_review_text(text, listing_id, observed_at, source_url)
    return rows, {
        "listing_id": listing_id,
        "observed_at": observed_at,
        "source_url": source_url,
        "expected_review_count": expected_total,
        "collected_review_count": len(rows),
        "review_export_confidence": review_export_confidence(len(rows), expected_total),
        "api_resource_count": len(api_resource_urls),
        "api_resource_sample": [_surfaces.redact_url(url) for url in api_resource_urls[:5]],
        "_capability_resource_urls": api_resource_urls,
    }


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
    run_id = os.environ.get("AIRBNB_HOST_REVIEWS_RUN_ID") or "airbnb-host-reviews-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    listing_file = latest_listing_file()
    listing_run = json.loads(listing_file.read_text())
    all_listings = listing_run.get("records") or []
    listings, listing_scope = _listing_scope.select_listings(
        all_listings,
        os.environ.get("AIRBNB_HOST_REVIEWS_LISTING_SCOPE"),
    )
    total_scope_listings = len(listings)
    if not listings:
        raise SystemExit(
            f"Listing source file {listing_file} produced zero listings for scope {listing_scope['label']}"
        )
    if os.environ.get("AIRBNB_HOST_REVIEWS_LIMIT_LISTINGS"):
        listings = listings[: int(os.environ["AIRBNB_HOST_REVIEWS_LIMIT_LISTINGS"])]

    OUTPUT_PATH.mkdir(parents=True, exist_ok=True)
    SESSION_PATH.mkdir(parents=True, exist_ok=True)

    bootstrap_url = host_reviews_url(listings[0]["listing_id"])
    auth_restore = maybe_restore_auth(bootstrap_url)
    navigate(bootstrap_url)
    wait_for_load()
    wait(float(os.environ.get("AIRBNB_HOST_REVIEWS_NAV_DELAY_SEC", "2.0")))
    base_headers = login_session.browser_session_headers(
        cdp,
        BASE + "/api/",
        cookie_urls=[BASE + "/"],
    )
    surface_capabilities = []
    _surfaces.upsert_best_capability(
        surface_capabilities,
        _surfaces.capability_record(
            "host_reviews",
            observed_at=observed_at,
            auth_context=(
                "restored_private_host_session_in_fresh_agent_chrome_profile"
                if auth_restore else "caller_provided_authenticated_browser_context"
            ),
            source_url=bootstrap_url,
            resource_urls=_surfaces.page_api_resource_urls(js),
            evidence={"phase": "host_reviews_landing"},
        ),
    )

    raw_path = OUTPUT_PATH / f"{run_id}-raw.jsonl"
    reviews = []
    summaries = []
    failures = []
    with raw_path.open("a") as raw_handle:
        for index, listing in enumerate(listings, start=1):
            listing_id = str(listing["listing_id"])
            print(json.dumps({"phase": "host_reviews", "progress": index, "total": len(listings), "listing_id": listing_id}), flush=True)
            try:
                rows, summary = collect_listing_reviews(listing, base_headers, observed_at, raw_handle)
            except Exception as error:
                failures.append({"listing_id": listing_id, "error": repr(error)})
                continue
            reviews.extend(rows)
            capability_urls = summary.pop("_capability_resource_urls", [])
            _surfaces.upsert_best_capability(
                surface_capabilities,
                _surfaces.capability_record(
                    "host_reviews",
                    observed_at=observed_at,
                    auth_context=(
                        "restored_private_host_session_in_fresh_agent_chrome_profile"
                        if auth_restore else "caller_provided_authenticated_browser_context"
                    ),
                    source_url=summary.get("source_url"),
                    resource_urls=capability_urls,
                    evidence={"listing_id": listing_id, "phase": "listing_reviews"},
                ),
            )
            summaries.append(summary)
    reviews = dedupe_reviews(reviews)

    json_path = OUTPUT_PATH / f"{run_id}.json"
    reviews_csv = OUTPUT_PATH / f"{run_id}-reviews.csv"
    summaries_csv = OUTPUT_PATH / f"{run_id}-listing-summaries.csv"
    receipt_path = SESSION_PATH / f"{run_id}-receipt.json"
    complete_states = {"complete_against_host_total", "complete_no_reviews"}
    all_target_listing_reviews_complete = bool(summaries) and all(
        row.get("review_export_confidence") in complete_states for row in summaries
    ) and not failures
    empty_reviews_explained = bool(summaries) and all(
        row.get("review_export_confidence") == "complete_no_reviews" for row in summaries
    )
    prior_counts = _integrity.latest_prior_count(
        OUTPUT_PATH,
        count_keys=("review_count",),
        current_run_id=run_id,
    )
    last_good_guard = _integrity.last_good_guard(
        subject="host_private_review_rows",
        current_count=len(reviews),
        prior_positive_count=prior_counts["prior_positive_count"],
        allow_empty=empty_reviews_explained or os.environ.get("AIRBNB_HOST_REVIEWS_ALLOW_EMPTY") == "1",
    )
    warehouse_exports = _integrity.warehouse_manifest([
        {
            "table": "airbnb_review",
            "path": str(reviews_csv),
            "row_count": len(reviews),
            "grain": "review_id",
            "source_family": "host_private",
            "surface_class": "host_private",
            "auth_context": (
                "restored_private_host_session_in_fresh_agent_chrome_profile"
                if auth_restore else "caller_provided_authenticated_browser_context"
            ),
        },
        {
            "table": "airbnb_review_listing_summary",
            "path": str(summaries_csv),
            "row_count": len(summaries),
            "grain": "listing_id + observed_at",
            "source_family": "host_private",
            "surface_class": "host_private",
            "auth_context": (
                "restored_private_host_session_in_fresh_agent_chrome_profile"
                if auth_restore else "caller_provided_authenticated_browser_context"
            ),
        },
    ])
    output = _integrity.stamp_collection_contract({
        "run_id": run_id,
        "observed_at": observed_at,
        "auth_context": (
            "restored_private_host_session_in_fresh_agent_chrome_profile"
            if auth_restore else "caller_provided_authenticated_browser_context"
        ),
        "source_family": "host_private",
        "surface_class": "host_private",
        "collection_status": _integrity.collection_status(
            last_good_guard_record=last_good_guard,
            failures_count=len(failures),
            complete=all_target_listing_reviews_complete,
        ),
        "source": {
            "listing_scope": str(listing_file),
            "backend": "headful_chrome_authenticated_host",
            "collection_strategy": "host reviews API/template when configured, discovered review API resources, then rendered host-review text fallback",
            "raw_path": str(raw_path),
            "surface_capabilities": surface_capabilities,
        },
        "last_good_guard": last_good_guard,
        "warehouse_exports": warehouse_exports,
        "listing_status_scope": listing_scope["label"],
        "total_source_listings": len(all_listings),
        "total_scope_listings": total_scope_listings,
        "target_listing_count": len(listings),
        "listing_scope_complete": len(listings) == total_scope_listings,
        "review_count": len(reviews),
        "listing_summary_count": len(summaries),
        "all_target_listing_reviews_complete": all_target_listing_reviews_complete,
        "reviews": reviews,
        "listing_summaries": summaries,
        "failures_count": len(failures),
        "failures": failures[:100],
    },
        source_family="host_private",
        surface_class="host_private",
        auth_context=(
            "restored_private_host_session_in_fresh_agent_chrome_profile"
            if auth_restore else "caller_provided_authenticated_browser_context"
        ),
        collection_status=_integrity.collection_status(
            last_good_guard_record=last_good_guard,
            failures_count=len(failures),
            complete=all_target_listing_reviews_complete,
        ),
        last_good_guard_record=last_good_guard,
        warehouse_exports=warehouse_exports,
    )
    _integrity.write_collection_json(json_path, output)
    write_csv(reviews_csv, reviews)
    write_csv(summaries_csv, summaries)
    receipt = _integrity.stamp_collection_contract({
        "run_id": run_id,
        "observed_at": observed_at,
        "auth_context": output["auth_context"],
        "source_family": output["source_family"],
        "surface_class": output["surface_class"],
        "collection_status": output["collection_status"],
        "last_good_guard": last_good_guard,
        "warehouse_exports": warehouse_exports,
        "listing_status_scope": output["listing_status_scope"],
        "total_source_listings": output["total_source_listings"],
        "total_scope_listings": output["total_scope_listings"],
        "target_listing_count": output["target_listing_count"],
        "listing_scope_complete": output["listing_scope_complete"],
        "review_count": output["review_count"],
        "listing_summary_count": output["listing_summary_count"],
        "all_target_listing_reviews_complete": output["all_target_listing_reviews_complete"],
        "failures_count": output["failures_count"],
        "json_path": str(json_path),
        "reviews_csv": str(reviews_csv),
        "summaries_csv": str(summaries_csv),
        "raw_path": str(raw_path),
        "surface_capabilities": surface_capabilities,
    },
        source_family="host_private",
        surface_class="host_private",
        auth_context=output["auth_context"],
        collection_status=output["collection_status"],
        last_good_guard_record=last_good_guard,
        warehouse_exports=warehouse_exports,
    )
    if auth_restore:
        receipt["auth_restore"] = auth_restore
    _integrity.write_receipt_json(receipt_path, receipt)
    print(json.dumps(receipt, indent=2, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    import sys
    if any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
        print((__doc__ or "").strip())
        raise SystemExit(0)
    main()
