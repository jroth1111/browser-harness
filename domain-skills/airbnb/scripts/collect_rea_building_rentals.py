"""Track realestate.com.au rental listings for buildings in the Airbnb portfolio.

Role: collector (external public rental market). It discovers rental listings
for the street addresses where current Airbnb listings are located by searching
realestate.com.au suburb rental result pages directly, paginating through the
full result set, revisiting previously-seen REA listing URLs, and updating
time-series ledgers so price and availability changes are visible across runs.

Reads:
    - Latest complete `airbnb-live-listings-*.json` under
      `.private-data/listing-collections/` (override with
      `REA_BUILDING_RENTALS_LISTINGS_FILE`).
    - Prior REA rental observation ledger under
      `.private-data/realestate-rental-collections/` when present.

Produces:
    - Run snapshot JSON + observations/events/building-prices/search-runs CSVs under
      `.private-data/realestate-rental-collections/`.
    - Idempotent observation, event, and building-price JSONL ledgers in the
      same directory.
    - `domain-skills/airbnb/.session-store/capability/<run_id>-receipt.json`.

Requires:
    - A real, persistent headful Chrome profile for REA pages. REA commonly
      serves Kasada/KPSDK challenge shells to direct HTTP, fresh headless Chrome,
      and Lightpanda. Run through `browser-harness`, not as plain Python.

Run from the browser-harness repo:

    BH_NAME=rea-building-rentals BH_CDP_WS=http://127.0.0.1:<port> \
      python3 run.py < domain-skills/airbnb/scripts/collect_rea_building_rentals.py

Useful env:
    - `REA_BUILDING_RENTALS_LISTING_SCOPE` default `active`
    - `REA_BUILDING_RENTALS_LIMIT_BUILDINGS` for smoke tests
    - `REA_BUILDING_RENTALS_MAX_SEARCH_PAGES` optional smoke-test cap; default
      is every result page reported by REA
    - `REA_BUILDING_RENTALS_OPEN_MATCHED_LISTINGS` default `1`
    - `REA_BUILDING_RENTALS_REVISIT_KNOWN` default `1`
    - `REA_BUILDING_RENTALS_SEED_URLS` comma/newline separated manual URLs
    - `REA_BUILDING_RENTALS_SEED_URLS_FILE` one URL per line
    - `REA_BUILDING_RENTALS_RUN_ID` to retry a run idempotently
    - `REA_BUILDING_RENTALS_RETRY_MAX_ATTEMPTS` default `4` for 429 retries
    - `REA_BUILDING_RENTALS_RETRY_BASE_DELAY_SEC` default `15`
    - `REA_BUILDING_RENTALS_RETRY_MAX_DELAY_SEC` default `180`

Private outputs are written under ignored domain-skills/airbnb/.private-data/.
"""

from __future__ import annotations

import csv
import hashlib
import io
import importlib.util
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus, unquote, urlsplit, urlunsplit


AIRBNB_DIR = Path("domain-skills/airbnb")
LISTINGS_PATH = AIRBNB_DIR / ".private-data" / "listing-collections"
OUTPUT_PATH = AIRBNB_DIR / ".private-data" / "realestate-rental-collections"
SESSION_PATH = AIRBNB_DIR / ".session-store" / "capability"
OBSERVATION_LEDGER = OUTPUT_PATH / "rea-building-rental-observations.jsonl"
EVENT_LEDGER = OUTPUT_PATH / "rea-building-rental-events.jsonl"
BUILDING_PRICE_LEDGER = OUTPUT_PATH / "rea-building-rental-building-prices.jsonl"
RUN_STATE_PATH = OUTPUT_PATH / ".run-state"

REA_BASE = "https://www.realestate.com.au"

DEFAULT_NAV_DELAY_SEC = "3.5"
DEFAULT_RETRY_MAX_ATTEMPTS = "4"
DEFAULT_RETRY_BASE_DELAY_SEC = "15"
DEFAULT_RETRY_MAX_DELAY_SEC = "180"

_NAVIGATED = False

STREET_SUFFIX_ALIASES = {
    "avenue": "ave",
    "ave": "ave",
    "boulevard": "blvd",
    "blvd": "blvd",
    "close": "cl",
    "cl": "cl",
    "court": "ct",
    "ct": "ct",
    "crescent": "cres",
    "cres": "cres",
    "drive": "dr",
    "dr": "dr",
    "highway": "hwy",
    "hwy": "hwy",
    "lane": "ln",
    "ln": "ln",
    "parade": "pde",
    "pde": "pde",
    "place": "pl",
    "pl": "pl",
    "road": "rd",
    "rd": "rd",
    "square": "sq",
    "sq": "sq",
    "street": "st",
    "st": "st",
    "terrace": "tce",
    "tce": "tce",
    "way": "way",
}

DISPLAY_SUFFIX = {
    "ave": "Ave",
    "blvd": "Blvd",
    "cl": "Cl",
    "ct": "Ct",
    "cres": "Cres",
    "dr": "Dr",
    "hwy": "Hwy",
    "ln": "Ln",
    "pde": "Pde",
    "pl": "Pl",
    "rd": "Rd",
    "sq": "Sq",
    "st": "St",
    "tce": "Tce",
    "way": "Way",
}

STREET_SUFFIX_PATTERN = "|".join(sorted(STREET_SUFFIX_ALIASES, key=len, reverse=True))
STATE_PATTERN = r"ACT|NSW|NT|QLD|SA|TAS|VIC|WA"

OBSERVATION_CONTENT_FIELDS = [
    "building_key",
    "rea_listing_id",
    "rea_listing_url",
    "listing_key",
    "listing_state",
    "listing_lifecycle_evidence",
    "listing_lifecycle_confidence",
    "unavailable_reason",
    "available_flag",
    "rent_per_week_aud",
    "bond_aud",
    "availability_text",
    "annual_rent_aud",
    "last_known_rent_per_week_aud",
    "last_known_listing_state",
    "removed_detection_failure_kind",
    "listing_address",
    "listing_building_key",
    "unit_identifier",
    "property_type",
    "bedrooms",
    "bathrooms",
    "car_spaces",
    "furnishing_status",
    "pets_policy_text",
    "inspection_times",
    "application_text",
    "property_features",
    "agency_or_contact_lines",
    "match_confidence",
    "parse_confidence",
]

EVENT_IDENTITY_FIELDS = [
    "run_id",
    "event_type",
    "listing_key",
    "old_listing_state",
    "new_listing_state",
    "old_listing_lifecycle_evidence",
    "new_listing_lifecycle_evidence",
    "old_listing_lifecycle_confidence",
    "new_listing_lifecycle_confidence",
    "old_unavailable_reason",
    "new_unavailable_reason",
    "old_rent_basis",
    "old_rent_per_week_aud",
    "new_rent_per_week_aud",
    "rent_delta_aud",
]

UNAVAILABLE_SIGNAL_PATTERNS = [
    ("leased", r"\bleased\b"),
    ("deposit_taken", r"\bdeposit taken\b"),
    ("application_approved", r"\bapplication approved\b"),
    ("rented", r"\brented\b"),
    ("no_longer_available", r"\bno longer available\b"),
    ("not_currently_available", r"\bnot currently available\b"),
]

UNRELATED_UNAVAILABLE_CONTEXT_PATTERNS = [
    r"^(similar|other|nearby) properties\b",
    r"^recently leased(?: nearby)? (?:apartments|properties|rentals|homes|units)\b",
    r"^leased properties\b",
    r"^property history\b",
    r"^market trends\b",
    r"^suburb profile\b",
]

BUILDING_PRICE_CONTENT_FIELDS = [
    "building_key",
    "observed_listing_count",
    "active_listing_count",
    "unavailable_listing_count",
    "unknown_listing_count",
    "rent_count",
    "rent_min_per_week_aud",
    "rent_median_per_week_aud",
    "rent_mean_per_week_aud",
    "rent_max_per_week_aud",
    "active_rents_per_week_aud",
    "bedroom_rent_summary",
    "active_listing_keys",
]

COMMON_PROPERTY_FEATURES = {
    "air_conditioning": [r"\bair conditioning\b", r"\bsplit system\b"],
    "balcony": [r"\bbalcony\b", r"\bterrace\b"],
    "built_in_wardrobes": [r"\bbuilt[- ]?in wardrobes?\b", r"\bBIRs?\b"],
    "dishwasher": [r"\bdishwasher\b"],
    "floorboards": [r"\bfloorboards?\b"],
    "gym": [r"\bgym\b", r"\bfitness\b"],
    "heating": [r"\bheating\b", r"\bheater\b"],
    "intercom": [r"\bintercom\b"],
    "internal_laundry": [r"\binternal laundry\b", r"\blaundry\b"],
    "pool": [r"\bpool\b", r"\bswimming pool\b"],
    "secure_parking": [r"\bsecure parking\b", r"\bcar space\b", r"\bgarage\b"],
    "study": [r"\bstudy\b", r"\bhome office\b"],
}


def _load_local_module(module_filename, module_name):
    path = Path("domain-skills/airbnb/scripts") / module_filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_listing_scope = _load_local_module("listing_scope.py", "airbnb_listing_scope")
_integrity = _load_local_module("run_integrity.py", "airbnb_run_integrity")


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def truthy_env(name, default=True):
    raw = os.environ.get(name)
    if raw is None:
        return bool(default)
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def int_env(name, default):
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return int(default)
    return int(raw)


def float_env(name, default):
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return float(default)
    return float(raw)


def retry_max_attempts():
    return max(1, int_env("REA_BUILDING_RENTALS_RETRY_MAX_ATTEMPTS", DEFAULT_RETRY_MAX_ATTEMPTS))


def retry_backoff_seconds(retry_number):
    base = max(0.0, float_env("REA_BUILDING_RENTALS_RETRY_BASE_DELAY_SEC", DEFAULT_RETRY_BASE_DELAY_SEC))
    cap = max(base, float_env("REA_BUILDING_RENTALS_RETRY_MAX_DELAY_SEC", DEFAULT_RETRY_MAX_DELAY_SEC))
    return min(cap, base * (2 ** max(0, int(retry_number) - 1)))


def retryable_failure_kind(failure_kind):
    return failure_kind == "http_429_or_too_many_requests"


def wait_retry_delay(seconds):
    if seconds <= 0:
        return
    if "wait" in globals():
        wait(seconds)
    else:
        time.sleep(seconds)


def navigate(url):
    """Navigate one collection tab instead of opening one tab per listing."""
    global _NAVIGATED
    if not _NAVIGATED:
        new_tab(url)
        _NAVIGATED = True
    else:
        goto_url(url)


def normalize_space(value):
    return re.sub(r"\s+", " ", str(value or "").replace("\u00a0", " ")).strip()


def title_keep_abbrev(value):
    words = []
    for word in normalize_space(value).split(" "):
        lowered = word.lower()
        words.append(DISPLAY_SUFFIX.get(lowered, word if word.isupper() else word.capitalize()))
    return " ".join(words)


def canonical_street_name(value):
    text = normalize_space(value).lower().replace(".", "")
    words = re.sub(r"[^a-z0-9\s-]", " ", text).split()
    if words:
        words[-1] = STREET_SUFFIX_ALIASES.get(words[-1], words[-1])
    return " ".join(words)


def suffix_aliases_for_display(street_address):
    text = normalize_space(street_address)
    match = re.search(rf"\b({STREET_SUFFIX_PATTERN})\b\.?$", text, re.I)
    if not match:
        return [text]
    suffix = STREET_SUFFIX_ALIASES.get(match.group(1).lower(), match.group(1).lower())
    variants = [text]
    full = next((key for key, value in STREET_SUFFIX_ALIASES.items() if value == suffix and len(key) > len(value)), None)
    if full:
        variants.append(re.sub(rf"\b{re.escape(match.group(1))}\b\.?$", title_keep_abbrev(full), text, flags=re.I))
    short = DISPLAY_SUFFIX.get(suffix)
    if short:
        variants.append(re.sub(rf"\b{re.escape(match.group(1))}\b\.?$", short, text, flags=re.I))
    out = []
    for variant in variants:
        if variant not in out:
            out.append(variant)
    return out


def parse_locality(text):
    match = re.search(rf"^(?P<suburb>.+?)\s*,?\s+(?P<state>{STATE_PATTERN})\s+(?P<postcode>\d{{4}})$", normalize_space(text), re.I)
    if not match:
        return None
    suburb = normalize_space(match.group("suburb"))
    if re.search(r"\d", suburb):
        return None
    return {
        "suburb": title_keep_abbrev(suburb),
        "state": match.group("state").upper(),
        "postcode": match.group("postcode"),
    }


def parse_street_component(text):
    raw = normalize_space(text)
    raw = re.sub(r"^image:\s*", "", raw, flags=re.I)
    raw = re.sub(r"^(?:unit|apartment|apt|flat|suite)\s+", "", raw, flags=re.I)
    unit_identifier = None

    unit_match = re.match(
        rf"(?P<unit>[A-Za-z]?\d+[A-Za-z]?(?:-\d+[A-Za-z]?)?)\s*/\s*(?P<street>\d+[A-Za-z]?(?:-\d+[A-Za-z]?)?\s+.+\b(?:{STREET_SUFFIX_PATTERN})\.?)$",
        raw,
        re.I,
    )
    if unit_match:
        unit_identifier = unit_match.group("unit")
        raw = unit_match.group("street")

    named_unit_match = re.search(
        rf"(?:unit|apartment|apt|flat|suite)\s+(?P<unit>[A-Za-z]?\d+[A-Za-z]?)\s*,?\s+(?P<street>\d+[A-Za-z]?(?:-\d+[A-Za-z]?)?\s+.+\b(?:{STREET_SUFFIX_PATTERN})\.?)",
        raw,
        re.I,
    )
    if named_unit_match:
        unit_identifier = unit_identifier or named_unit_match.group("unit")
        raw = named_unit_match.group("street")

    street_match = re.search(
        rf"(?P<number>\d+[A-Za-z]?(?:-\d+[A-Za-z]?)?)\s+(?P<name>.+)\s+\b(?P<suffix>{STREET_SUFFIX_PATTERN})\.?\s*$",
        raw,
        re.I,
    )
    if not street_match:
        # Fallback: try non-anchored match for inputs with trailing content
        street_match = re.search(
            rf"(?P<number>\d+[A-Za-z]?(?:-\d+[A-Za-z]?)?)\s+(?P<name>.+?\b(?P<suffix>{STREET_SUFFIX_PATTERN})\.?)\b",
            raw,
            re.I,
        )
    if not street_match:
        return None

    street_number = street_match.group("number")
    name_raw = normalize_space(street_match.group("name")).replace(".", "")
    matched_suffix = street_match.group("suffix") or ""
    suffix_alias = STREET_SUFFIX_ALIASES.get(matched_suffix.lower().rstrip("."), matched_suffix.lower().rstrip("."))
    display_suffix = DISPLAY_SUFFIX.get(suffix_alias, title_keep_abbrev(matched_suffix))
    name_words = name_raw.split()
    # The fallback regex includes the suffix inside the name group — strip it.
    if name_words and name_words[-1].lower().rstrip(".") == matched_suffix.lower().rstrip("."):
        name_words = name_words[:-1]
    if name_words:
        last = name_words[-1].lower().rstrip(".")
        if last in STREET_SUFFIX_ALIASES:
            last_alias = STREET_SUFFIX_ALIASES[last]
            name_words[-1] = DISPLAY_SUFFIX.get(last_alias, title_keep_abbrev(name_words[-1]))
    street_name_display = title_keep_abbrev(" ".join(name_words)) + " " + display_suffix
    street_address_display = f"{street_number} {street_name_display}"
    street_key = f"{street_number.lower()} {canonical_street_name(street_name_display)}"
    return {
        "unit_identifier": unit_identifier,
        "street_number": street_number,
        "street_name": street_name_display,
        "street_address": street_address_display,
        "street_key": street_key,
    }


def parse_australian_address(value):
    text = normalize_space(value)
    if not text:
        return None
    text = re.sub(r",?\s*Australia\s*$", "", text, flags=re.I)
    parts = [part.strip() for part in text.split(",") if part.strip()]
    locality = None
    locality_start = None
    locality_end = None
    for index, part in enumerate(parts):
        locality = parse_locality(part)
        if locality:
            locality_start = locality_end = index
            break
        if index + 1 < len(parts) and not re.search(rf"\d|\b(?:{STREET_SUFFIX_PATTERN})\b", part, re.I):
            locality = parse_locality(part + " " + parts[index + 1])
            if locality:
                locality_start = index
                locality_end = index + 1
                break
    if locality is None:
        locality = parse_locality(text)
        locality_start = len(parts)
        locality_end = len(parts)
    if locality is None:
        return None

    street_candidates = parts[:locality_start] if parts else [text]
    street = None
    for candidate in reversed(street_candidates):
        street = parse_street_component(candidate)
        if street:
            break
    if street is None and locality_start is not None:
        prefix = ", ".join(parts[: locality_end + 1])
        street = parse_street_component(prefix)
    if street is None:
        return None

    building_key = "|".join(
        [
            street["street_key"],
            locality["suburb"].lower(),
            locality["state"],
            locality["postcode"],
        ]
    )
    return {
        **street,
        **locality,
        "building_key": building_key,
        "building_address": f"{street['street_address']}, {locality['suburb']} {locality['state']} {locality['postcode']}",
        "address_display": (
            f"{street['unit_identifier'] + '/' if street.get('unit_identifier') else ''}"
            f"{street['street_address']}, {locality['suburb']} {locality['state']} {locality['postcode']}"
        ),
        "raw_address": value,
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
    explicit = os.environ.get("REA_BUILDING_RENTALS_LISTINGS_FILE") or os.environ.get("AIRBNB_LISTINGS_FILE")
    if explicit:
        return Path(explicit)
    files = sorted(LISTINGS_PATH.glob("airbnb-live-listings-*.json"))
    if not files:
        raise SystemExit(f"No live-listing collection found under {LISTINGS_PATH}")
    complete = [path for path in files if is_complete_live_listing_file(path)]
    if not complete:
        raise SystemExit(
            f"No complete live-listing collection found under {LISTINGS_PATH}; "
            "set REA_BUILDING_RENTALS_LISTINGS_FILE explicitly for a partial smoke test"
        )
    return complete[-1]


def building_targets_from_airbnb_records(records):
    targets = {}
    dropped = []
    for record in records or []:
        parsed = parse_australian_address(record.get("address"))
        if not parsed:
            dropped.append(record)
            continue
        target = targets.setdefault(
            parsed["building_key"],
            {
                "building_key": parsed["building_key"],
                "building_address": parsed["building_address"],
                "street_address": parsed["street_address"],
                "street_key": parsed["street_key"],
                "suburb": parsed["suburb"],
                "state": parsed["state"],
                "postcode": parsed["postcode"],
                "source_airbnb_listing_ids": [],
                "source_airbnb_nicknames": [],
                "source_airbnb_addresses": [],
                "source_airbnb_bedrooms": [],
            },
        )
        listing_id = str(record.get("listing_id") or "")
        if listing_id and listing_id not in target["source_airbnb_listing_ids"]:
            target["source_airbnb_listing_ids"].append(listing_id)
        nickname = normalize_space(record.get("nickname"))
        if nickname and nickname not in target["source_airbnb_nicknames"]:
            target["source_airbnb_nicknames"].append(nickname)
        address = normalize_space(record.get("address"))
        if address and address not in target["source_airbnb_addresses"]:
            target["source_airbnb_addresses"].append(address)
        bedrooms = record.get("bedrooms")
        if bedrooms is not None and bedrooms not in target["source_airbnb_bedrooms"]:
            target["source_airbnb_bedrooms"].append(bedrooms)
    for target in targets.values():
        target["source_airbnb_listing_count"] = len(target["source_airbnb_listing_ids"])
        target["source_airbnb_bedrooms"] = sorted(target["source_airbnb_bedrooms"])
    if dropped:
        print(json.dumps({
            "warning": "listings_dropped_unparseable_address",
            "dropped_count": len(dropped),
            "total_records": len(records or []),
            "sample_addresses": [r.get("address") for r in dropped[:5]],
        }), flush=True)
    return sorted(targets.values(), key=lambda row: row["building_address"])


def rea_listing_id_from_url(url):
    match = re.search(r"-(\d{7,})(?:/)?$", urlsplit(url or "").path)
    return match.group(1) if match else None


def clean_rea_candidate_url(raw_url):
    if not raw_url:
        return None
    url = unquote(str(raw_url))
    parts = urlsplit(url)
    if not parts.scheme:
        return None
    if not parts.netloc.endswith("realestate.com.au"):
        return None
    if "/property-" not in parts.path:
        return None
    listing_id = rea_listing_id_from_url(urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", "")))
    if not listing_id:
        return None
    return urlunsplit(("https", "www.realestate.com.au", parts.path.rstrip("/"), "", ""))


def full_suffix_street_address(street_address):
    variants = suffix_aliases_for_display(street_address)
    return max(variants, key=len) if variants else street_address


def rea_suburb_search_location_query(target):
    return f"{target['suburb']} {target['state']} {target['postcode']}"


def rea_building_match_query(target):
    street = full_suffix_street_address(target["street_address"])
    return f"{street}, {target['suburb']} {target['state']} {target['postcode']}"


def rea_search_location_query(target):
    return rea_suburb_search_location_query(target)


def rea_rent_search_url(target, page_number=1):
    slug = quote_plus(rea_search_location_query(target).lower())
    return f"{REA_BASE}/rent/in-{slug}/list-{int(page_number)}"


def parse_search_result_count(text):
    match = re.search(r"Showing\s+([0-9,]+)\s*[–-]\s*([0-9,]+)\s+of\s+([0-9,]+)\s+properties", text or "", re.I)
    if match:
        start = int(match.group(1).replace(",", ""))
        end = int(match.group(2).replace(",", ""))
        total = int(match.group(3).replace(",", ""))
        page_size = max(1, end - start + 1)
        total_pages = (total + page_size - 1) // page_size
        return {"start": start, "end": end, "total": total, "page_size": page_size, "total_pages": total_pages}
    if re.search(r"\bNo exact matches\b|\b0 properties\b|\bNo properties found\b", text or "", re.I):
        return {"start": 0, "end": 0, "total": 0, "page_size": 0, "total_pages": 0}
    return {"start": None, "end": None, "total": None, "page_size": None, "total_pages": None}


def extract_rea_search_cards_from_page():
    cards = js(
        r"""
(() => {
  const seen = new Set();
  const cards = [];
  const anchors = Array.from(document.querySelectorAll('a[href*="/property-"]'));
  for (const anchor of anchors) {
    const href = anchor.href || anchor.getAttribute('href') || '';
    const match = href.match(/-(\d{7,})(?:\/)?(?:[?#].*)?$/);
    if (!match || seen.has(match[1])) continue;
    seen.add(match[1]);
    let node = anchor;
    let best = anchor.innerText || '';
    for (let i = 0; i < 8 && node && node.parentElement; i++) {
      node = node.parentElement;
      const text = (node.innerText || '').trim();
      const propertyLinkCount = node.querySelectorAll ? node.querySelectorAll('a[href*="/property-"]').length : 1;
      if (propertyLinkCount <= 3 && text.length > best.length && text.length < 2500) best = text;
      if (
        propertyLinkCount <= 3 &&
        /\$[0-9][0-9,]*\s*(per\s+week|pw|p\/w|\/week)/i.test(text) &&
        /vic\s+\d{4}/i.test(text)
      ) {
        best = text;
        break;
      }
    }
    cards.push({href, rea_listing_id: match[1], text: best});
  }
  return cards;
})()
"""
    ) or []
    out = []
    for card in cards:
        cleaned = clean_rea_candidate_url(card.get("href"))
        if not cleaned:
            continue
        out.append({**card, "href": cleaned, "rea_listing_id": rea_listing_id_from_url(cleaned) or card.get("rea_listing_id")})
    return out


def seed_urls_from_env():
    raw_values = []
    if os.environ.get("REA_BUILDING_RENTALS_SEED_URLS"):
        raw_values.extend(re.split(r"[\n,]+", os.environ["REA_BUILDING_RENTALS_SEED_URLS"]))
    file_path = os.environ.get("REA_BUILDING_RENTALS_SEED_URLS_FILE")
    if file_path:
        raw_values.extend(Path(file_path).read_text().splitlines())
    out = []
    for raw in raw_values:
        cleaned = clean_rea_candidate_url(raw.strip())
        if cleaned and cleaned not in out:
            out.append(cleaned)
    return out


def read_jsonl(path):
    rows = []
    if not path.exists():
        return rows
    with path.open() as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def known_listing_urls_by_building(path=OBSERVATION_LEDGER):
    known = {}
    for row in read_jsonl(path):
        building_key = row.get("building_key")
        url = clean_rea_candidate_url(row.get("rea_listing_url"))
        if building_key and url:
            known.setdefault(building_key, [])
            if url not in known[building_key]:
                known[building_key].append(url)
    return known


def latest_observations_by_listing(path=OBSERVATION_LEDGER, exclude_run_id=None):
    latest = {}
    for row in read_jsonl(path):
        if exclude_run_id is not None and row.get("run_id") == exclude_run_id:
            continue
        key = row.get("listing_key")
        observed_at = row.get("observed_at") or ""
        if not key:
            continue
        if key not in latest or observed_at >= (latest[key].get("observed_at") or ""):
            latest[key] = row
    return latest


def latest_observations_by_url(previous_by_listing):
    latest = {}
    for row in previous_by_listing.values():
        url = clean_rea_candidate_url(row.get("rea_listing_url"))
        if url:
            latest[url] = row
    return latest


def unit_alias_key(row):
    building_key = row.get("building_key")
    unit = row.get("unit_identifier")
    if not building_key or not unit:
        return None
    normalized_unit = re.sub(r"\s+", "", str(unit)).lower()
    if not normalized_unit:
        return None
    return f"{building_key}|unit:{normalized_unit}"


def latest_observations_by_unit_alias(previous_by_listing):
    latest = {}
    for row in previous_by_listing.values():
        alias = unit_alias_key(row)
        if not alias:
            continue
        observed_at = row.get("observed_at") or ""
        existing = latest.get(alias)
        if not existing or observed_at >= (existing.get("observed_at") or ""):
            latest[alias] = row
    return latest


def first_int(pattern, text):
    match = re.search(pattern, text or "", re.I)
    return int(match.group(1).replace(",", "")) if match else None


def find_address_in_listing_text(text):
    lines = [normalize_space(line) for line in (text or "").splitlines() if normalize_space(line)]
    for window in (1, 2, 3):
        for index in range(0, min(len(lines), 120)):
            candidate = ", ".join(lines[index : index + window])
            if len(candidate) > 220 or re.search(r"Property ID|Statement of Information|realestate", candidate, re.I):
                continue
            parsed = parse_australian_address(candidate)
            if parsed:
                return parsed
    return None


def parse_price_per_week(text):
    for line in (text or "").splitlines():
        if re.search(r"\bbond\b|\bdeposit\b", line, re.I):
            continue
        match = re.search(r"\$([0-9][0-9,]*)\s*(?:per\s+week|pw|p/w|/week|weekly)", line, re.I)
        if match:
            return int(match.group(1).replace(",", ""))
    match = re.search(r"\$([0-9][0-9,]*)\s*(?:per\s+week|pw|p/w|/week|weekly)", text or "", re.I)
    return int(match.group(1).replace(",", "")) if match else None


def parse_availability_text(text):
    patterns = [
        r"Available\s+now",
        r"Available\s+from\s+[^\n]+",
        r"Availability\s*:?\s*[^\n]+",
    ]
    for pattern in patterns:
        match = re.search(pattern, text or "", re.I)
        if match:
            return normalize_space(match.group(0))
    return None


def property_type_from_url_or_text(text, url=None):
    path = (urlsplit(url or "").path or "").lower()
    for property_type in ("apartment", "unit", "studio", "townhouse", "house", "villa", "duplex", "terrace"):
        if f"property-{property_type}" in path:
            return property_type
    match = re.search(r"\b(apartment|unit|studio|townhouse|house|villa|duplex|terrace)\b", text or "", re.I)
    return match.group(1).lower() if match else None


def parse_furnishing_status(text):
    lower = (text or "").lower()
    if re.search(r"\b(partly|partially|semi)[ -]?furnished\b", lower):
        return "partly_furnished"
    if re.search(r"\bunfurnished\b|\bnot furnished\b", lower):
        return "unfurnished"
    if re.search(r"\bfully furnished\b|\bfurnished\b", lower):
        return "furnished"
    return None


def parse_pets_policy_text(text):
    lines = [normalize_space(line) for line in (text or "").splitlines() if normalize_space(line)]
    for line in lines:
        if re.search(r"\bpets?\b", line, re.I) and len(line) <= 180:
            return line
    return None


def extract_relevant_lines(text, pattern, limit=8):
    lines = [normalize_space(line) for line in (text or "").splitlines() if normalize_space(line)]
    out = []
    for line in lines:
        if len(line) > 220:
            continue
        if re.search(pattern, line, re.I) and line not in out:
            out.append(line)
        if len(out) >= limit:
            break
    return out


def extract_property_features(text):
    features = []
    lower = text or ""
    for feature, patterns in COMMON_PROPERTY_FEATURES.items():
        if any(re.search(pattern, lower, re.I) for pattern in patterns):
            features.append(feature)
    return features


def rent_derived_fields(rent_per_week, bond):
    annual_rent = int(rent_per_week) * 52 if rent_per_week is not None else None
    bond_weeks = None
    if rent_per_week:
        bond_weeks = round(float(bond) / float(rent_per_week), 2) if bond is not None else None
    return annual_rent, bond_weeks


def unavailable_reason_from_text(text):
    lines = [normalize_space(line) for line in (text or "").splitlines() if normalize_space(line)]
    for line in lines:
        if len(line) > 220:
            continue
        if any(re.search(pattern, line, re.I) for pattern in UNRELATED_UNAVAILABLE_CONTEXT_PATTERNS):
            break
        for reason, pattern in UNAVAILABLE_SIGNAL_PATTERNS:
            if re.search(pattern, line, re.I):
                return reason
    return None


def missing_page_reason_from_text(text):
    if re.search(
        r"\b(page not found|sorry,.*not found|property could not be found|http error 404|404 not found|not found 404)\b",
        text or "",
        re.I,
    ):
        return "page_not_found_or_removed"
    return None


def listing_lifecycle_from_signals(rent_per_week, unavailable_reason, missing_page_reason):
    if rent_per_week and not unavailable_reason and not missing_page_reason:
        return {
            "listing_state": "active",
            "available_flag": True,
            "unavailable_reason": None,
            "listing_lifecycle_evidence": "active_price_visible",
            "listing_lifecycle_confidence": "high",
        }
    if unavailable_reason:
        confidence = "high" if unavailable_reason in {"leased", "deposit_taken", "application_approved", "rented"} else "medium"
        return {
            "listing_state": "leased_or_unavailable",
            "available_flag": False,
            "unavailable_reason": unavailable_reason,
            "listing_lifecycle_evidence": f"explicit_{unavailable_reason}",
            "listing_lifecycle_confidence": confidence,
        }
    if missing_page_reason:
        return {
            "listing_state": "removed_or_unknown",
            "available_flag": False,
            "unavailable_reason": missing_page_reason,
            "listing_lifecycle_evidence": "page_not_found_or_removed",
            "listing_lifecycle_confidence": "medium",
        }
    return {
        "listing_state": "unknown",
        "available_flag": False,
        "unavailable_reason": None,
        "listing_lifecycle_evidence": "no_price_or_unavailable_signal",
        "listing_lifecycle_confidence": "low",
    }


def parse_rea_rental_listing_text(text, url=None):
    normalized = re.sub(r"\n{2,}", "\n", text or "").strip()
    address = find_address_in_listing_text(normalized)
    rent_per_week = parse_price_per_week(normalized)
    bond = first_int(r"\bBond\s*\$([0-9][0-9,]*)", normalized)
    annual_rent, bond_weeks = rent_derived_fields(rent_per_week, bond)
    furnishing_status = parse_furnishing_status(normalized)
    unavailable_reason = unavailable_reason_from_text(normalized)
    missing_page_reason = missing_page_reason_from_text(normalized)
    lifecycle = listing_lifecycle_from_signals(rent_per_week, unavailable_reason, missing_page_reason)
    bedrooms = first_int(r"\b([0-9]+)\s*(?:beds?|bedrooms?)\b", normalized)
    bathrooms_match = re.search(r"\b([0-9]+(?:\.[0-9]+)?)\s*(?:baths?|bathrooms?)\b", normalized, re.I)
    bathrooms = float(bathrooms_match.group(1)) if bathrooms_match else None
    car_spaces = first_int(r"\b([0-9]+)\s*(?:cars?|car spaces?|parking spaces?|garage)\b", normalized)
    property_id = first_int(r"\bProperty ID[:\s]+([0-9][0-9,]*)", normalized) or first_int(r"-(\d{7,})(?:/)?$", urlsplit(url or "").path)
    return {
        "rea_listing_id": str(property_id) if property_id is not None else rea_listing_id_from_url(url or ""),
        "listing_address": address["address_display"] if address else None,
        "listing_building_key": address["building_key"] if address else None,
        "unit_identifier": address.get("unit_identifier") if address else None,
        "rent_per_week_aud": rent_per_week,
        "annual_rent_aud": annual_rent,
        "bond_aud": bond,
        "bond_weeks_equivalent": bond_weeks,
        "availability_text": parse_availability_text(normalized),
        **lifecycle,
        "property_type": property_type_from_url_or_text(normalized, url=url),
        "bedrooms": bedrooms,
        "bathrooms": bathrooms,
        "car_spaces": car_spaces,
        "furnishing_status": furnishing_status,
        "furnished_flag": furnishing_status in {"furnished", "partly_furnished"},
        "pets_policy_text": parse_pets_policy_text(normalized),
        "inspection_times": extract_relevant_lines(normalized, r"\b(open for inspection|inspection|open home|inspect)\b"),
        "application_text": extract_relevant_lines(normalized, r"\b(apply|application|ignite)\b", limit=4),
        "property_features": extract_property_features(normalized),
        "agency_or_contact_lines": extract_relevant_lines(
            normalized,
            r"\b(listed by|contact agent|property manager|leasing|real estate|ray white|belle property|mcgrath|barry plant|jellis craig|micm|dingle partners)\b",
            limit=6,
        ),
        "parse_confidence": "address_and_rent" if address and rent_per_week else "address_only" if address else "low",
        "raw_text_sample": normalized[:2000],
    }


def page_failure(status):
    if status.get("block", {}).get("blocked"):
        return status.get("block", {}).get("kind") or "blocked"
    text = (status.get("text") or "").lower()
    title = (status.get("title") or "").lower()
    if "too many requests" in text or "http error 429" in text or "429" in title:
        return "http_429_or_too_many_requests"
    if re.search(r"\b(page not found|sorry,.*not found|property could not be found|http error 404|404 not found|not found 404)\b", text, re.I):
        return "page_not_found_or_removed"
    if re.search(r"\b(page not found|not found|http error 404|404 not found)\b", title, re.I):
        return "page_not_found_or_removed"
    if "access denied" in text:
        return "access_denied"
    return None


def text_contains_building_terms(text, target):
    haystack = canonical_street_name(text)
    street = canonical_street_name(target["street_address"])
    suburb = target["suburb"].lower()
    return bool(street and street in haystack and suburb in (text or "").lower())


def match_listing_to_target(parsed, target, text):
    if parsed.get("listing_building_key") == target["building_key"]:
        return "parsed_address_key"
    if not parsed.get("listing_building_key") and text_contains_building_terms(text or "", target):
        return "text_contains_building_terms"
    return None


def listing_key_for_observation(row):
    if row.get("rea_listing_id"):
        return f"rea:{row['rea_listing_id']}"
    return f"url:{row['rea_listing_url']}"


def stable_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def stable_hash(*parts):
    digest = hashlib.sha256()
    for part in parts:
        digest.update(stable_json(part).encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def observation_content_hash(row):
    return stable_hash(
        "rea_observation_content",
        {field: row.get(field) for field in OBSERVATION_CONTENT_FIELDS},
    )


def with_observation_identity(row):
    out = dict(row)
    out["listing_key"] = out.get("listing_key") or listing_key_for_observation(out)
    out["content_hash"] = observation_content_hash(out)
    out["observation_id"] = stable_hash(
        "rea_observation",
        out.get("run_id"),
        out.get("building_key"),
        out.get("listing_key"),
    )
    return out


def with_event_identity(row):
    out = dict(row)
    out["event_id"] = stable_hash("rea_event", {field: out.get(field) for field in EVENT_IDENTITY_FIELDS})
    return out


def atomic_write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}-{time.time_ns()}")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def atomic_write_json(path, value, *, indent=2):
    atomic_write_text(path, json.dumps(value, indent=indent, ensure_ascii=False) + "\n")


def upsert_jsonl_by_key(path, rows, key_field):
    if not rows:
        return
    merged = {}
    order = []
    for row in read_jsonl(path):
        key = row.get(key_field)
        if not key:
            continue
        if key not in merged:
            order.append(key)
        merged[key] = row
    for row in rows:
        key = row.get(key_field)
        if not key:
            raise ValueError(f"Cannot upsert row without {key_field}: {row}")
        if key not in merged:
            order.append(key)
        merged[key] = row
    payload = "".join(json.dumps(merged[key], ensure_ascii=False, sort_keys=True) + "\n" for key in order)
    atomic_write_text(path, payload)


def checkpoint_path_for_run(run_id):
    return RUN_STATE_PATH / f"{run_id}.json"


def load_checkpoint(path):
    if not path.exists():
        return {"schema_version": 1, "search_pages": [], "listing_pages": []}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {"schema_version": 1, "search_pages": [], "listing_pages": []}
    data.setdefault("schema_version", 1)
    data.setdefault("search_pages", [])
    data.setdefault("listing_pages", [])
    return data


def mark_checkpoint(path, section, entry):
    checkpoint = load_checkpoint(path)
    rows = checkpoint.setdefault(section, [])
    key = entry.get("checkpoint_key") or stable_hash("checkpoint", section, entry)
    existing = {row.get("checkpoint_key"): row for row in rows if row.get("checkpoint_key")}
    if key in existing:
        old_status = existing[key].get("status")
        new_status = entry.get("status")
        if old_status in {"ok", "observed"} and new_status == "failed":
            existing[key]["last_retry_failure_kind"] = entry.get("failure_kind")
            existing[key]["last_retry_failed_at"] = utc_now()
        else:
            existing[key].update({k: v for k, v in entry.items() if k != "checkpointed_at"})
            existing[key]["checkpoint_key"] = key
    else:
        rows.append({**entry, "checkpoint_key": key, "checkpointed_at": utc_now()})
    atomic_write_json(path, checkpoint)


def raw_listing_row_id(run_id, building_key, rea_listing_url):
    return stable_hash("rea_raw_listing", run_id, building_key, clean_rea_candidate_url(rea_listing_url) or rea_listing_url)


def complete_run_snapshot_exists(path):
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    return data.get("run_complete") is True or data.get("collection_status") == "complete"


def known_listing_gone_failure(failure):
    return (failure or {}).get("failure_kind") == "page_not_found_or_removed"


def removed_observation_from_previous(target, previous, observed_at, run_id, candidate, failure):
    if not previous or not known_listing_gone_failure(failure):
        return None
    previous_was_synthetic = previous.get("listing_state") == "removed_or_unknown"
    last_known_rent = (
        previous.get("last_known_rent_per_week_aud")
        if previous_was_synthetic
        else previous.get("rent_per_week_aud")
    )
    last_known_state = (
        previous.get("last_known_listing_state")
        if previous_was_synthetic
        else previous.get("listing_state")
    )
    last_known_observed_at = (
        previous.get("last_known_observed_at")
        if previous_was_synthetic
        else previous.get("observed_at")
    )
    last_known_content_hash = (
        previous.get("last_known_content_hash")
        if previous_was_synthetic
        else previous.get("content_hash")
    )
    row = {
        **previous,
        "run_id": run_id,
        "observed_at": observed_at,
        "building_key": target["building_key"],
        "building_address": target["building_address"],
        "street_address": target["street_address"],
        "suburb": target["suburb"],
        "state": target["state"],
        "postcode": target["postcode"],
        "source_airbnb_listing_ids": target["source_airbnb_listing_ids"],
        "source_airbnb_nicknames": target["source_airbnb_nicknames"],
        "source_airbnb_listing_count": target["source_airbnb_listing_count"],
        "rea_listing_url": candidate["url"],
        "discovery_source": "known_previous_listing_removed_revisit",
        "discovery_query": candidate.get("query"),
        "building_match_query": rea_building_match_query(target),
        "listing_state": "removed_or_unknown",
        "available_flag": False,
        "unavailable_reason": "page_not_found_or_removed",
        "listing_lifecycle_evidence": "known_url_page_not_found_from_previous_observation",
        "listing_lifecycle_confidence": "medium",
        "rent_per_week_aud": None,
        "annual_rent_aud": None,
        "bond_aud": None,
        "bond_weeks_equivalent": None,
        "availability_text": "Previously observed listing URL is no longer reachable",
        "last_known_rent_per_week_aud": last_known_rent,
        "last_known_listing_state": last_known_state,
        "last_known_observed_at": last_known_observed_at,
        "last_known_content_hash": last_known_content_hash,
        "removed_detection_failure_kind": failure.get("failure_kind"),
        "page_title": failure.get("title"),
        "text_length": 0,
        "match_confidence": "previous_observation_same_building",
        "parse_confidence": "synthetic_from_previous_observation",
        "raw_text_sample": failure.get("text_sample"),
    }
    row.pop("observation_id", None)
    row.pop("content_hash", None)
    return with_observation_identity(row)


def observation_from_page(target, url, observed_at, run_id, discovery_source, discovery_query=None):
    attempts = retry_max_attempts()
    retry_delays = []
    status = {}
    failure_kind = None
    attempt = 1
    for attempt in range(1, attempts + 1):
        navigate(url)
        wait_for_load()
        wait(float(os.environ.get("REA_BUILDING_RENTALS_NAV_DELAY_SEC", DEFAULT_NAV_DELAY_SEC)))
        status = wait_for_content(min_text=300, timeout=20)
        failure_kind = page_failure(status)
        if not retryable_failure_kind(failure_kind) or attempt >= attempts:
            break
        delay = retry_backoff_seconds(attempt)
        retry_delays.append(delay)
        print(
            json.dumps({
                "phase": "listing_retry",
                "url": url,
                "failure_kind": failure_kind,
                "attempt": attempt,
                "next_attempt": attempt + 1,
                "sleep_seconds": delay,
            }),
            flush=True,
        )
        wait_retry_delay(delay)
    if failure_kind:
        return None, {
            "building_key": target["building_key"],
            "building_address": target["building_address"],
            "rea_listing_url": url,
            "discovery_source": discovery_source,
            "discovery_query": discovery_query,
            "failure_kind": failure_kind,
            "retry_attempts": attempt,
            "retry_delays_seconds": retry_delays,
            "retry_exhausted": retryable_failure_kind(failure_kind) and attempt >= attempts,
            "title": status.get("title"),
            "text_sample": (status.get("text") or "")[:500],
        }, status
    text = status.get("text") or ""
    parsed = parse_rea_rental_listing_text(text, url=url)
    if parsed.get("listing_state") == "removed_or_unknown":
        return None, {
            "building_key": target["building_key"],
            "building_address": target["building_address"],
            "rea_listing_url": url,
            "discovery_source": discovery_source,
            "discovery_query": discovery_query,
            "failure_kind": "page_not_found_or_removed",
            "retry_attempts": attempt,
            "retry_delays_seconds": retry_delays,
            "parsed_listing_state": parsed.get("listing_state"),
            "title": status.get("title"),
            "text_sample": (status.get("text") or "")[:500],
        }, status
    match_confidence = match_listing_to_target(parsed, target, text)
    if not match_confidence:
        return None, {
            "building_key": target["building_key"],
            "building_address": target["building_address"],
            "rea_listing_url": url,
            "discovery_source": discovery_source,
            "discovery_query": discovery_query,
            "failure_kind": "listing_address_not_in_target_building",
            "parsed_listing_address": parsed.get("listing_address"),
            "parsed_listing_building_key": parsed.get("listing_building_key"),
            "title": status.get("title"),
        }, status
    row = {
        "run_id": run_id,
        "observed_at": observed_at,
        "building_key": target["building_key"],
        "building_address": target["building_address"],
        "street_address": target["street_address"],
        "suburb": target["suburb"],
        "state": target["state"],
        "postcode": target["postcode"],
        "source_airbnb_listing_ids": target["source_airbnb_listing_ids"],
        "source_airbnb_nicknames": target["source_airbnb_nicknames"],
        "source_airbnb_listing_count": target["source_airbnb_listing_count"],
        "rea_listing_url": url,
        "discovery_source": discovery_source,
        "discovery_query": discovery_query,
        "building_match_query": rea_building_match_query(target),
        "page_title": status.get("title"),
        "text_length": status.get("textLength"),
        "retry_attempts": attempt,
        "retry_delays_seconds": retry_delays,
        "match_confidence": match_confidence,
        **parsed,
    }
    return with_observation_identity(row), None, status


def write_csv(path, rows):
    output = io.StringIO()
    if not rows:
        atomic_write_text(path, "")
        return
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    atomic_write_text(path, output.getvalue())


def dedupe_observations(rows):
    best = {}
    for row in rows:
        key = row.get("listing_key")
        if not key:
            continue
        score = (
            10 if row.get("listing_state") == "active" else 0,
            5 if row.get("rent_per_week_aud") is not None else 0,
            3 if row.get("match_confidence") == "parsed_address_key" else 0,
            1 if row.get("discovery_source") != "rea_search_page" else 0,
            int(row.get("text_length") or 0),
        )
        current = best.get(key)
        if not current or score > current[0]:
            best[key] = (score, row)
    return [item[1] for item in best.values()]


def filter_detail_rejected_observations(observations, failures):
    rejected = set()
    for failure in failures:
        if failure.get("failure_kind") != "listing_address_not_in_target_building":
            continue
        parsed_key = failure.get("parsed_listing_building_key")
        if not parsed_key:
            continue
        url = clean_rea_candidate_url(failure.get("rea_listing_url"))
        building_key = failure.get("building_key")
        if url and building_key:
            rejected.add((url, building_key))
            listing_id = rea_listing_id_from_url(url)
            if listing_id:
                rejected.add((f"rea:{listing_id}", building_key))
    return [
        row
        for row in observations
        if (row.get("rea_listing_url"), row.get("building_key")) not in rejected
        and (row.get("listing_key"), row.get("building_key")) not in rejected
    ]


def unavailable_event_type(row):
    if row.get("listing_state") == "leased_or_unavailable":
        reason = row.get("unavailable_reason")
        if reason == "leased":
            return "leased_confirmed"
        if reason in {"deposit_taken", "application_approved", "rented"}:
            return "rented_or_application_confirmed"
        return "unavailable_confirmed"
    if row.get("listing_state") == "removed_or_unknown":
        return "listing_removed_or_unreachable"
    return "availability_state_changed"


def first_seen_event_type(row):
    state = row.get("listing_state")
    if state == "active":
        return "first_seen_active"
    if state == "unknown":
        return "first_seen_unknown"
    return "first_seen_unavailable"


def active_transition_event_type(previous, row):
    old_state = previous.get("listing_state")
    new_state = row.get("listing_state")
    if new_state == "active" and old_state in {"leased_or_unavailable", "removed_or_unknown"}:
        return "relisted"
    if new_state == "active" and old_state == "unknown":
        return "active_confirmed"
    if old_state == "active" and new_state == "unknown":
        return "active_signal_lost"
    return "availability_state_changed"


def lifecycle_evidence_changed(previous, row):
    return any(
        (previous.get(field) != row.get(field))
        for field in (
            "unavailable_reason",
            "listing_lifecycle_evidence",
            "listing_lifecycle_confidence",
        )
    )


def previous_rent_for_change(previous):
    if previous.get("rent_per_week_aud") is not None:
        return previous.get("rent_per_week_aud"), "previous_rent_per_week_aud"
    if previous.get("last_known_rent_per_week_aud") is not None:
        return previous.get("last_known_rent_per_week_aud"), "previous_last_known_rent_per_week_aud"
    return None, None


def event_rows_for_observations(observations, previous_by_listing, observed_at, run_id, previous_by_alias=None):
    events = []
    previous_by_alias = previous_by_alias or {}
    for row in observations:
        key = row.get("listing_key")
        previous = previous_by_listing.get(key)
        previous_match_basis = "listing_key" if previous else None
        if not previous:
            alias = unit_alias_key(row)
            alias_previous = previous_by_alias.get(alias) if alias else None
            if (
                alias_previous
                and alias_previous.get("listing_key") != key
                and alias_previous.get("listing_state") in {"leased_or_unavailable", "removed_or_unknown"}
            ):
                previous = alias_previous
                previous_match_basis = "building_unit_alias"
        event_base = {
            "run_id": run_id,
            "observed_at": observed_at,
            "listing_key": key,
            "rea_listing_id": row.get("rea_listing_id"),
            "rea_listing_url": row.get("rea_listing_url"),
            "building_key": row.get("building_key"),
            "building_address": row.get("building_address"),
            "unit_identifier": row.get("unit_identifier"),
            "new_listing_lifecycle_evidence": row.get("listing_lifecycle_evidence"),
            "new_listing_lifecycle_confidence": row.get("listing_lifecycle_confidence"),
            "new_unavailable_reason": row.get("unavailable_reason"),
        }
        if previous_match_basis == "building_unit_alias":
            event_base["previous_match_basis"] = "building_unit_alias"
            event_base["previous_listing_key"] = previous.get("listing_key")
            event_base["previous_rea_listing_url"] = previous.get("rea_listing_url")
        if not previous:
            events.append(with_event_identity({
                **event_base,
                "event_type": first_seen_event_type(row),
                "old_listing_state": None,
                "new_listing_state": row.get("listing_state"),
                "old_listing_lifecycle_evidence": None,
                "old_listing_lifecycle_confidence": None,
                "old_unavailable_reason": None,
                "old_rent_basis": None,
                "old_rent_per_week_aud": None,
                "new_rent_per_week_aud": row.get("rent_per_week_aud"),
            }))
            continue
        old_state = previous.get("listing_state")
        new_state = row.get("listing_state")
        old_rent, old_rent_basis = previous_rent_for_change(previous)
        new_rent = row.get("rent_per_week_aud")
        if old_state != new_state:
            if new_state == "active" or (old_state == "active" and new_state == "unknown"):
                event_type = active_transition_event_type(previous, row)
            else:
                event_type = unavailable_event_type(row)
            events.append(with_event_identity({
                **event_base,
                "event_type": event_type,
                "old_listing_state": old_state,
                "new_listing_state": new_state,
                "old_listing_lifecycle_evidence": previous.get("listing_lifecycle_evidence"),
                "old_listing_lifecycle_confidence": previous.get("listing_lifecycle_confidence"),
                "old_unavailable_reason": previous.get("unavailable_reason"),
                "old_rent_basis": old_rent_basis,
                "old_rent_per_week_aud": old_rent,
                "new_rent_per_week_aud": new_rent,
            }))
        elif new_state != "active" and lifecycle_evidence_changed(previous, row):
            events.append(with_event_identity({
                **event_base,
                "event_type": unavailable_event_type(row),
                "old_listing_state": old_state,
                "new_listing_state": new_state,
                "old_listing_lifecycle_evidence": previous.get("listing_lifecycle_evidence"),
                "old_listing_lifecycle_confidence": previous.get("listing_lifecycle_confidence"),
                "old_unavailable_reason": previous.get("unavailable_reason"),
                "old_rent_basis": old_rent_basis,
                "old_rent_per_week_aud": old_rent,
                "new_rent_per_week_aud": new_rent,
            }))
        if old_rent is not None and new_rent is not None and int(old_rent) != int(new_rent):
            events.append(with_event_identity({
                **event_base,
                "event_type": "price_changed",
                "old_listing_state": old_state,
                "new_listing_state": new_state,
                "old_listing_lifecycle_evidence": previous.get("listing_lifecycle_evidence"),
                "old_listing_lifecycle_confidence": previous.get("listing_lifecycle_confidence"),
                "old_unavailable_reason": previous.get("unavailable_reason"),
                "old_rent_basis": old_rent_basis,
                "old_rent_per_week_aud": old_rent,
                "new_rent_per_week_aud": new_rent,
                "rent_delta_aud": int(new_rent) - int(old_rent),
            }))
    return events


def median_number(values):
    ordered = sorted(values)
    if not ordered:
        return None
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    value = (ordered[mid - 1] + ordered[mid]) / 2
    return int(value) if value.is_integer() else value


def rent_summary(values):
    rents = sorted(int(value) for value in values if value is not None)
    if not rents:
        return {
            "rent_count": 0,
            "rent_min_per_week_aud": None,
            "rent_median_per_week_aud": None,
            "rent_mean_per_week_aud": None,
            "rent_max_per_week_aud": None,
        }
    return {
        "rent_count": len(rents),
        "rent_min_per_week_aud": rents[0],
        "rent_median_per_week_aud": median_number(rents),
        "rent_mean_per_week_aud": round(sum(rents) / len(rents), 2),
        "rent_max_per_week_aud": rents[-1],
    }


def bedroom_rent_summary(active_rows):
    buckets = {}
    for row in active_rows:
        key = str(row.get("bedrooms")) if row.get("bedrooms") is not None else "unknown"
        buckets.setdefault(key, []).append(row.get("rent_per_week_aud"))
    return {key: rent_summary(values) for key, values in sorted(buckets.items())}


def building_price_snapshot_rows(targets, observations, observed_at, run_id):
    by_building = {}
    for row in observations:
        by_building.setdefault(row.get("building_key"), []).append(row)

    snapshots = []
    for target in targets:
        rows = by_building.get(target["building_key"], [])
        active_rows = [
            row
            for row in rows
            if row.get("listing_state") == "active" and row.get("rent_per_week_aud") is not None
        ]
        unavailable_rows = [row for row in rows if row.get("listing_state") in {"leased_or_unavailable", "removed_or_unknown"}]
        unknown_rows = [row for row in rows if row.get("listing_state") not in {"active", "leased_or_unavailable", "removed_or_unknown"}]
        active_rents = sorted(int(row["rent_per_week_aud"]) for row in active_rows)
        snapshot = {
            "run_id": run_id,
            "observed_at": observed_at,
            "building_key": target["building_key"],
            "building_address": target["building_address"],
            "street_address": target["street_address"],
            "suburb": target["suburb"],
            "state": target["state"],
            "postcode": target["postcode"],
            "source_airbnb_listing_ids": target["source_airbnb_listing_ids"],
            "source_airbnb_nicknames": target["source_airbnb_nicknames"],
            "source_airbnb_listing_count": target["source_airbnb_listing_count"],
            "observed_listing_count": len(rows),
            "active_listing_count": len(active_rows),
            "unavailable_listing_count": len(unavailable_rows),
            "unknown_listing_count": len(unknown_rows),
            "active_rents_per_week_aud": active_rents,
            "bedroom_rent_summary": bedroom_rent_summary(active_rows),
            "observed_listing_keys": sorted(row.get("listing_key") for row in rows if row.get("listing_key")),
            "active_listing_keys": sorted(row.get("listing_key") for row in active_rows if row.get("listing_key")),
            "source_observation_ids": sorted(row.get("observation_id") for row in rows if row.get("observation_id")),
            "snapshot_status": "observed_active_rents" if active_rows else "no_active_rent_observed",
            **rent_summary(active_rents),
        }
        snapshot["building_price_snapshot_id"] = stable_hash(
            "rea_building_price_snapshot",
            run_id,
            target["building_key"],
        )
        snapshot["building_price_content_hash"] = stable_hash(
            "rea_building_price_content",
            {field: snapshot.get(field) for field in BUILDING_PRICE_CONTENT_FIELDS},
        )
        snapshots.append(snapshot)
    return snapshots


def observation_from_search_card(target, card, observed_at, run_id, search_url, page_number):
    url = clean_rea_candidate_url(card.get("href"))
    if not url:
        return None, {
            "building_key": target["building_key"],
            "building_address": target["building_address"],
            "discovery_source": "rea_search_page",
            "source_url": search_url,
            "page_number": page_number,
            "failure_kind": "invalid_rea_listing_url",
            "raw_href": card.get("href"),
        }
    text = card.get("text") or ""
    parsed = parse_rea_rental_listing_text(text, url=url)
    parsed["rea_listing_id"] = parsed.get("rea_listing_id") or card.get("rea_listing_id") or rea_listing_id_from_url(url)
    match_confidence = match_listing_to_target(parsed, target, text)
    if not match_confidence:
        return None, None
    row = {
        "run_id": run_id,
        "observed_at": observed_at,
        "building_key": target["building_key"],
        "building_address": target["building_address"],
        "street_address": target["street_address"],
        "suburb": target["suburb"],
        "state": target["state"],
        "postcode": target["postcode"],
        "source_airbnb_listing_ids": target["source_airbnb_listing_ids"],
        "source_airbnb_nicknames": target["source_airbnb_nicknames"],
        "source_airbnb_listing_count": target["source_airbnb_listing_count"],
        "rea_listing_url": url,
        "discovery_source": "rea_search_page",
        "discovery_query": rea_search_location_query(target),
        "building_match_query": rea_building_match_query(target),
        "search_page_url": search_url,
        "search_page_number": page_number,
        "page_title": None,
        "text_length": len(text),
        "match_confidence": match_confidence,
        **parsed,
    }
    return with_observation_identity(row), None


def collect_search_page_observations(target, observed_at, run_id, checkpoint_path=None):
    search_runs = []
    observations = []
    failures = []
    max_pages = int(os.environ.get("REA_BUILDING_RENTALS_MAX_SEARCH_PAGES", "0") or "0")
    page_number = 1
    total_pages = None
    while True:
        url = rea_rent_search_url(target, page_number)
        print(json.dumps({"phase": "rea_search_page", "building": target["building_address"], "page": page_number, "url": url}), flush=True)
        attempts = retry_max_attempts()
        retry_delays = []
        status = {}
        failure_kind = None
        attempt = 1
        for attempt in range(1, attempts + 1):
            navigate(url)
            wait_for_load()
            wait(float(os.environ.get("REA_BUILDING_RENTALS_NAV_DELAY_SEC", DEFAULT_NAV_DELAY_SEC)))
            status = page_content_status(text_limit=4000, html_limit=4000)
            failure_kind = page_failure(status)
            if not retryable_failure_kind(failure_kind) or attempt >= attempts:
                break
            delay = retry_backoff_seconds(attempt)
            retry_delays.append(delay)
            print(
                json.dumps({
                    "phase": "rea_search_page_retry",
                    "building": target["building_address"],
                    "page": page_number,
                    "url": url,
                    "failure_kind": failure_kind,
                    "attempt": attempt,
                    "next_attempt": attempt + 1,
                    "sleep_seconds": delay,
                }),
                flush=True,
            )
            wait_retry_delay(delay)
        result_count = parse_search_result_count(status.get("text") or "")
        if total_pages is None and result_count.get("total_pages") is not None:
            total_pages = result_count["total_pages"]
        cards = [] if failure_kind else extract_rea_search_cards_from_page()
        matched_count = 0
        if failure_kind:
            failures.append({
                "building_key": target["building_key"],
                "building_address": target["building_address"],
                "discovery_source": "rea_search_page",
                "source_url": url,
                "page_number": page_number,
                "failure_kind": failure_kind,
                "retry_attempts": attempt,
                "retry_delays_seconds": retry_delays,
                "retry_exhausted": retryable_failure_kind(failure_kind) and attempt >= attempts,
                "title": status.get("title"),
                "text_sample": (status.get("text") or "")[:500],
            })
        for card in cards:
            observation, failure = observation_from_search_card(target, card, observed_at, run_id, url, page_number)
            if observation:
                matched_count += 1
                observations.append(observation)
            if failure:
                failures.append(failure)
        search_run = {
            "building_key": target["building_key"],
            "building_address": target["building_address"],
            "observed_at": observed_at,
            "search_source": "realestate.com.au",
            "query": rea_search_location_query(target),
            "building_match_query": rea_building_match_query(target),
            "page_number": page_number,
            "source_url": url,
            "status": "failed" if failure_kind else "ok",
            "failure_kind": failure_kind,
            "retry_attempts": attempt,
            "retry_delays_seconds": retry_delays,
            "retry_exhausted": retryable_failure_kind(failure_kind) and attempt >= attempts,
            "result_start": result_count.get("start"),
            "result_end": result_count.get("end"),
            "result_total": result_count.get("total"),
            "result_page_size": result_count.get("page_size"),
            "total_pages_reported": total_pages,
            "card_count": len(cards),
            "matched_card_count": matched_count,
            "result_urls": [card.get("href") for card in cards],
        }
        search_runs.append(search_run)
        if checkpoint_path:
            mark_checkpoint(
                checkpoint_path,
                "search_pages",
                {
                    "checkpoint_key": stable_hash("rea_search_page", run_id, target["building_key"], page_number),
                    "run_id": run_id,
                    "building_key": target["building_key"],
                    "building_address": target["building_address"],
                    "page_number": page_number,
                    "source_url": url,
                    "status": search_run["status"],
                    "failure_kind": failure_kind,
                    "retry_attempts": attempt,
                    "retry_delays_seconds": retry_delays,
                    "retry_exhausted": retryable_failure_kind(failure_kind) and attempt >= attempts,
                    "card_count": len(cards),
                    "matched_card_count": matched_count,
                },
            )
        if failure_kind:
            break
        if total_pages == 0:
            break
        if max_pages and page_number >= max_pages:
            break
        if total_pages is not None and page_number >= total_pages:
            break
        if total_pages is None and not cards:
            break
        page_number += 1
    return observations, search_runs, failures


def candidate_urls_for_target(target, known_by_building, seed_urls):
    rows = []
    if truthy_env("REA_BUILDING_RENTALS_REVISIT_KNOWN", True):
        for url in known_by_building.get(target["building_key"], []):
            rows.append({"url": url, "source": "known_previous_listing", "query": None})
    for url in seed_urls:
        rows.append({"url": url, "source": "manual_seed", "query": None})
    deduped = []
    for row in rows:
        if row["url"] not in {item["url"] for item in deduped}:
            deduped.append(row)
    return deduped


def main():
    observed_at = utc_now()
    run_id = os.environ.get("REA_BUILDING_RENTALS_RUN_ID") or "rea-building-rentals-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    listing_file = latest_live_listing_file()
    listing_run = json.loads(listing_file.read_text())
    all_records = listing_run.get("records") or []
    records, listing_scope = _listing_scope.select_listings(
        all_records,
        os.environ.get("REA_BUILDING_RENTALS_LISTING_SCOPE"),
    )
    if not records:
        raise SystemExit(f"Listing source file {listing_file} produced zero records for scope {listing_scope['label']}")
    targets = building_targets_from_airbnb_records(records)
    if os.environ.get("REA_BUILDING_RENTALS_LIMIT_BUILDINGS"):
        targets = targets[: int(os.environ["REA_BUILDING_RENTALS_LIMIT_BUILDINGS"])]
    if not targets:
        raise SystemExit("No parseable building addresses found in selected Airbnb listing records")

    OUTPUT_PATH.mkdir(parents=True, exist_ok=True)
    SESSION_PATH.mkdir(parents=True, exist_ok=True)

    known_by_building = known_listing_urls_by_building()
    previous_by_listing = latest_observations_by_listing(exclude_run_id=run_id)
    previous_by_url = latest_observations_by_url(previous_by_listing)
    previous_by_alias = latest_observations_by_unit_alias(previous_by_listing)
    seed_urls = seed_urls_from_env()
    search_runs = []
    observations = []
    failures = []
    raw_rows = []
    raw_path = OUTPUT_PATH / f"{run_id}-raw-listings.jsonl"
    checkpoint_path = checkpoint_path_for_run(run_id)
    stop_collection = False
    stop_reason = None

    for target in targets:
        if stop_collection:
            break
        candidates = candidate_urls_for_target(target, known_by_building, seed_urls)
        search_observations, target_search_runs, search_failures = collect_search_page_observations(
            target,
            observed_at,
            run_id,
            checkpoint_path=checkpoint_path,
        )
        search_runs.extend(target_search_runs)
        failures.extend(search_failures)
        observations.extend(search_observations)
        if any(failure.get("failure_kind") == "http_429_or_too_many_requests" for failure in search_failures):
            stop_collection = True
            stop_reason = "http_429_or_too_many_requests"
            continue
        if truthy_env("REA_BUILDING_RENTALS_OPEN_MATCHED_LISTINGS", True):
            for row in search_observations:
                candidates.append({"url": row["rea_listing_url"], "source": "rea_search_page_detail", "query": row.get("discovery_query")})
        deduped = []
        for row in candidates:
            cleaned = clean_rea_candidate_url(row["url"])
            if not cleaned:
                continue
            if cleaned not in {item["url"] for item in deduped}:
                deduped.append({**row, "url": cleaned})

        for candidate in deduped:
            print(json.dumps({"phase": "listing", "building": target["building_address"], "url": candidate["url"]}), flush=True)
            try:
                observation, failure, status = observation_from_page(
                    target,
                    candidate["url"],
                    observed_at,
                    run_id,
                    candidate["source"],
                    candidate.get("query"),
                )
            except Exception as exc:
                failure = {
                    "building_key": target["building_key"],
                    "building_address": target["building_address"],
                    "rea_listing_url": candidate["url"],
                    "discovery_source": candidate["source"],
                    "failure_kind": "collector_exception",
                    "error": repr(exc),
                }
                failures.append(failure)
                mark_checkpoint(
                    checkpoint_path,
                    "listing_pages",
                    {
                        "checkpoint_key": stable_hash("rea_listing_page", run_id, target["building_key"], candidate["url"]),
                        "run_id": run_id,
                        "building_key": target["building_key"],
                        "building_address": target["building_address"],
                        "rea_listing_url": candidate["url"],
                        "discovery_source": candidate["source"],
                        "status": "failed",
                        "failure_kind": failure["failure_kind"],
                    },
                )
                continue
            if observation:
                observations.append(observation)
                raw_row = {
                    "raw_record_id": raw_listing_row_id(run_id, target["building_key"], candidate["url"]),
                    "run_id": run_id,
                    "observed_at": observed_at,
                    "building_key": target["building_key"],
                    "rea_listing_url": candidate["url"],
                    "text": status.get("text") or "",
                }
                raw_rows.append(raw_row)
            if failure:
                previous = previous_by_url.get(candidate["url"]) if candidate.get("source") == "known_previous_listing" else None
                removed_observation = removed_observation_from_previous(
                    target,
                    previous,
                    observed_at,
                    run_id,
                    candidate,
                    failure,
                )
                if removed_observation:
                    observation = removed_observation
                    observations.append(observation)
                    failure["synthesized_removed_observation_id"] = observation.get("observation_id")
                failures.append(failure)
            mark_checkpoint(
                checkpoint_path,
                "listing_pages",
                {
                    "checkpoint_key": stable_hash("rea_listing_page", run_id, target["building_key"], candidate["url"]),
                    "run_id": run_id,
                    "building_key": target["building_key"],
                    "building_address": target["building_address"],
                    "rea_listing_url": candidate["url"],
                    "discovery_source": candidate["source"],
                    "status": "observed" if observation else "failed" if failure else "unknown",
                    "failure_kind": failure.get("failure_kind") if failure else None,
                    "listing_key": observation.get("listing_key") if observation else None,
                    "content_hash": observation.get("content_hash") if observation else None,
                },
            )

    observations = filter_detail_rejected_observations(observations, failures)
    observations = dedupe_observations(observations)
    events = event_rows_for_observations(
        observations,
        previous_by_listing,
        observed_at,
        run_id,
        previous_by_alias=previous_by_alias,
    )
    building_price_snapshots = building_price_snapshot_rows(targets, observations, observed_at, run_id)

    canonical_json_path = OUTPUT_PATH / f"{run_id}.json"
    run_complete = not stop_collection
    protect_complete_snapshot = not run_complete and complete_run_snapshot_exists(canonical_json_path)
    output_prefix = f"{run_id}-failed-attempt" if protect_complete_snapshot else run_id
    json_path = OUTPUT_PATH / f"{output_prefix}.json"
    observations_csv = OUTPUT_PATH / f"{output_prefix}-observations.csv"
    events_csv = OUTPUT_PATH / f"{output_prefix}-events.csv"
    building_prices_csv = OUTPUT_PATH / f"{output_prefix}-building-prices.csv"
    search_runs_csv = OUTPUT_PATH / f"{output_prefix}-search-runs.csv"
    failures_csv = OUTPUT_PATH / f"{output_prefix}-failures.csv"
    receipt_path = SESSION_PATH / f"{output_prefix}-receipt.json"
    prior_counts = _integrity.latest_prior_count(
        OUTPUT_PATH,
        count_keys=("observation_count", "building_price_snapshot_count"),
        current_run_id=run_id,
    )
    last_good_guard = _integrity.last_good_guard(
        subject="rea_building_rental_observations",
        current_count=len(observations) + len(building_price_snapshots),
        prior_positive_count=prior_counts["prior_positive_count"],
        allow_empty=os.environ.get("REA_BUILDING_RENTALS_ALLOW_EMPTY") == "1",
    )
    collection_status = _integrity.collection_status(
        last_good_guard_record=last_good_guard,
        failures_count=len(failures),
        complete=run_complete,
    )
    warehouse_exports = _integrity.warehouse_manifest([
        {
            "table": "external_rea_rental_observation",
            "path": str(observations_csv),
            "row_count": len(observations),
            "grain": "observation_id",
            "source_family": "external_public_market",
            "surface_class": "external_public_market",
            "auth_context": "persistent_headful_chrome_public_web",
        },
        {
            "table": "external_rea_rental_event",
            "path": str(events_csv),
            "row_count": len(events),
            "grain": "event_id",
            "source_family": "external_public_market",
            "surface_class": "external_public_market",
            "auth_context": "persistent_headful_chrome_public_web",
        },
        {
            "table": "external_rea_building_price_snapshot",
            "path": str(building_prices_csv),
            "row_count": len(building_price_snapshots),
            "grain": "building_key + run_id",
            "source_family": "external_public_market",
            "surface_class": "external_public_market",
            "auth_context": "persistent_headful_chrome_public_web",
        },
        {
            "table": "external_rea_search_run",
            "path": str(search_runs_csv),
            "row_count": len(search_runs),
            "grain": "building_key + page_number + run_id",
            "source_family": "external_public_market",
            "surface_class": "external_public_market",
            "auth_context": "persistent_headful_chrome_public_web",
        },
    ])

    output = _integrity.stamp_collection_contract({
        "run_id": run_id,
        "observed_at": observed_at,
        "source": {
            "airbnb_listing_file": str(listing_file),
            "listing_scope": listing_scope["label"],
            "backend": "persistent_headful_chrome",
            "discovery_strategy": "realestate.com.au suburb rental search pages with full pagination, strict building-address post-filtering, plus known REA listing URL revisits",
            "observation_ledger": str(OBSERVATION_LEDGER),
            "event_ledger": str(EVENT_LEDGER),
            "building_price_ledger": str(BUILDING_PRICE_LEDGER),
            "raw_listing_path": str(raw_path),
            "checkpoint_path": str(checkpoint_path),
            "idempotency": {
                "observation_key": "sha256(run_id, building_key, listing_key)",
                "observation_content_hash": OBSERVATION_CONTENT_FIELDS,
                "event_key": EVENT_IDENTITY_FIELDS,
                "building_price_key": "sha256(run_id, building_key)",
                "building_price_content_hash": BUILDING_PRICE_CONTENT_FIELDS,
                "ledger_write_mode": "atomic_jsonl_upsert",
                "snapshot_write_mode": "atomic_replace",
            },
        },
        "selected_airbnb_listing_count": len(records),
        "building_count": len(targets),
        "run_complete": run_complete,
        "stop_reason": stop_reason,
        "canonical_outputs_preserved": protect_complete_snapshot,
        "canonical_json_path": str(canonical_json_path),
        "last_good_guard": last_good_guard,
        "warehouse_exports": warehouse_exports,
        "buildings": targets,
        "search_run_count": len(search_runs),
        "observation_count": len(observations),
        "event_count": len(events),
        "building_price_snapshot_count": len(building_price_snapshots),
        "failure_count": len(failures),
        "observations": observations,
        "events": events,
        "building_price_snapshots": building_price_snapshots,
        "search_runs": search_runs,
        "failures": failures[:200],
    },
        source_family="external_public_market",
        surface_class="external_public_market",
        auth_context="persistent_headful_chrome_public_web",
        collection_status=collection_status,
        last_good_guard_record=last_good_guard,
        warehouse_exports=warehouse_exports,
    )
    _integrity.validate_collection_output(output)
    atomic_write_json(json_path, output)
    write_csv(observations_csv, observations)
    write_csv(events_csv, events)
    write_csv(building_prices_csv, building_price_snapshots)
    write_csv(search_runs_csv, search_runs)
    write_csv(failures_csv, failures)
    if not protect_complete_snapshot:
        upsert_jsonl_by_key(raw_path, raw_rows, "raw_record_id")
        upsert_jsonl_by_key(OBSERVATION_LEDGER, observations, "observation_id")
        upsert_jsonl_by_key(EVENT_LEDGER, events, "event_id")
        upsert_jsonl_by_key(BUILDING_PRICE_LEDGER, building_price_snapshots, "building_price_snapshot_id")

    receipt = _integrity.stamp_collection_contract({
        "run_id": run_id,
        "observed_at": observed_at,
        "airbnb_listing_file": str(listing_file),
        "listing_scope": listing_scope["label"],
        "selected_airbnb_listing_count": len(records),
        "building_count": len(targets),
        "run_complete": run_complete,
        "collection_status": output["collection_status"],
        "source_family": output["source_family"],
        "surface_class": output["surface_class"],
        "auth_context": output["auth_context"],
        "last_good_guard": last_good_guard,
        "warehouse_exports": warehouse_exports,
        "stop_reason": stop_reason,
        "canonical_outputs_preserved": protect_complete_snapshot,
        "canonical_json_path": str(canonical_json_path),
        "search_run_count": len(search_runs),
        "observation_count": len(observations),
        "event_count": len(events),
        "building_price_snapshot_count": len(building_price_snapshots),
        "failure_count": len(failures),
        "json_path": str(json_path),
        "observations_csv": str(observations_csv),
        "events_csv": str(events_csv),
        "building_prices_csv": str(building_prices_csv),
        "search_runs_csv": str(search_runs_csv),
        "failures_csv": str(failures_csv) if failures else None,
        "observation_ledger": str(OBSERVATION_LEDGER),
        "event_ledger": str(EVENT_LEDGER),
        "building_price_ledger": str(BUILDING_PRICE_LEDGER),
        "raw_listing_path": str(raw_path),
        "checkpoint_path": str(checkpoint_path),
        "idempotency": output["source"]["idempotency"],
        "failure_sample": failures[:10],
    },
        source_family="external_public_market",
        surface_class="external_public_market",
        auth_context="persistent_headful_chrome_public_web",
        collection_status=output["collection_status"],
        last_good_guard_record=last_good_guard,
        warehouse_exports=warehouse_exports,
    )
    _integrity.validate_receipt(receipt)
    atomic_write_json(receipt_path, receipt)
    print(json.dumps(receipt, indent=2, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
