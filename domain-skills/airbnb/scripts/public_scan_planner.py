"""Logged-out public Airbnb search matrix and partition helpers."""

from __future__ import annotations

import re
from datetime import date, timedelta
from urllib.parse import parse_qs, urlsplit


ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PRICE_BAND_RE = re.compile(r"^(\d*)-(\d*)$")
ROOM_URL_RE = re.compile(r"^/rooms/\d+$")
ENTIRE_HOME_FILTER = "Entire home/apt"
VALID_ROOM_TYPES = {"Entire home/apt", "Private room", "Shared room", "Hotel room"}
RESEARCH_MODES = {"opportunity_discovery", "property_validation", "repositioning"}
PROPERTY_VALIDATION_PROOF_KEYS = {
    "same_building_or_same_block_comps",
    "equal_or_worse_profitable_comps",
}
OPPORTUNITY_DISCOVERY_REQUIRED_KEYS = {
    "winning_product_patterns",
    "repeated_winner_examples",
    "reproducibility_assessment",
}


def parse_bool(value, default=False):
    if value in (None, ""):
        return default
    lowered = str(value).strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Invalid boolean value: {value!r}")


def safe_int(value, default=0):
    if isinstance(value, bool):
        return int(default)
    try:
        return int(value if value not in (None, "") else default)
    except (TypeError, ValueError):
        return int(default)


def optional_int(value):
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_csv_ints(value, default):
    raw = value if value not in (None, "") else default
    return [int(part.strip()) for part in str(raw).split(",") if part.strip()]


def require_iso_date(value, name="date"):
    text = str(value or "").strip()
    if not ISO_DATE_RE.fullmatch(text):
        raise ValueError(f"Invalid {name}: expected YYYY-MM-DD")
    try:
        return date.fromisoformat(text)
    except ValueError as error:
        raise ValueError(f"Invalid {name}: expected a real calendar date") from error


def normalize_date_value(value, name="date"):
    if isinstance(value, date):
        return value
    return require_iso_date(value, name)


def parse_range(value, name, cast=int):
    text = str(value or "").strip()
    if ".." not in text:
        raise ValueError(f"Invalid {name}: expected START..END")
    left, right = text.split("..", 1)
    if not left.strip() or not right.strip():
        raise ValueError(f"Invalid {name}: expected START..END")
    return cast(left.strip()), cast(right.strip())


def date_range(start, end, step_days=1):
    current = require_iso_date(start, "range start")
    stop = require_iso_date(end, "range end")
    step_days = int(step_days)
    if step_days <= 0:
        raise ValueError("step_days must be positive")
    if current > stop:
        raise ValueError("range start must be on or before range end")
    rows = []
    while current <= stop:
        rows.append(current.isoformat())
        current += timedelta(days=step_days)
    return rows


def resolve_checkin_dates(
    explicit=None,
    offsets=None,
    default_offsets="14,30,60,90",
    today=None,
    checkin_range=None,
    step_days=1,
):
    if explicit:
        return [part.strip() for part in str(explicit).split(",") if part.strip()]
    if checkin_range:
        start, end = parse_range(checkin_range, "check-in date range", cast=str)
        return date_range(start, end, step_days=step_days)
    today = today or date.today()
    return [(today + timedelta(days=offset)).isoformat() for offset in parse_csv_ints(offsets, default_offsets)]


def resolve_nights_values(explicit=None, night_range=None, default="3"):
    if explicit:
        return parse_csv_ints(explicit, default)
    if night_range:
        start, end = parse_range(night_range, "night range", cast=int)
        if start <= 0 or end <= 0:
            raise ValueError("night range values must be positive")
        if start > end:
            raise ValueError("night range start must be <= end")
        return list(range(start, end + 1))
    return parse_csv_ints(None, default)


def parse_price_bands(value):
    """Parse `0-250,251-500,501-` into inclusive min/max dicts.

    A blank value returns one unbounded band. The max side is intentionally
    optional because Airbnb accepts open-ended price filters in the UI.
    """
    if not value:
        return [{"price_min": None, "price_max": None, "label": "all_prices"}]
    bands = []
    for raw in str(value).split(","):
        part = raw.strip()
        if not part:
            continue
        if "-" not in part:
            amount = int(part)
            if amount < 0:
                raise ValueError("price bands must be non-negative")
            bands.append({"price_min": amount, "price_max": amount, "label": f"{amount}-{amount}"})
            continue
        match = PRICE_BAND_RE.fullmatch(part)
        if not match:
            raise ValueError(f"Invalid price band: {part}")
        left, right = match.groups()
        price_min = int(left) if left.strip() else None
        price_max = int(right) if right.strip() else None
        if price_min is not None and price_min < 0:
            raise ValueError("price_min must be non-negative")
        if price_max is not None and price_max < 0:
            raise ValueError("price_max must be non-negative")
        if price_min is not None and price_max is not None and price_min > price_max:
            raise ValueError("price_min must be <= price_max")
        bands.append({
            "price_min": price_min,
            "price_max": price_max,
            "label": f"{price_min if price_min is not None else ''}-{price_max if price_max is not None else ''}",
        })
    return bands or [{"price_min": None, "price_max": None, "label": "all_prices"}]


def initial_price_bands(value=None, auto_min=None, auto_max=None):
    if value:
        return parse_price_bands(value)
    if auto_min not in (None, "") or auto_max not in (None, ""):
        if auto_min in (None, "") or auto_max in (None, ""):
            raise ValueError("AIRBNB_COMP_AUTO_PRICE_MIN and AIRBNB_COMP_AUTO_PRICE_MAX must be set together")
        return parse_price_bands(f"{int(auto_min)}-{int(auto_max)}")
    return parse_price_bands(None)


def fixed_width_price_bands(price_min, price_max, width):
    price_min = int(price_min)
    price_max = int(price_max)
    width = int(width)
    if width <= 0:
        raise ValueError("width must be positive")
    bands = []
    current = price_min
    while current <= price_max:
        end = min(price_max, current + width - 1)
        bands.append({"price_min": current, "price_max": end, "label": f"{current}-{end}"})
        current = end + 1
    return bands


def split_price_band(band):
    def parse_int(value):
        if value in (None, "") or isinstance(value, bool):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    band = band if isinstance(band, dict) else {}
    price_min = parse_int(band.get("price_min"))
    price_max = parse_int(band.get("price_max"))
    if price_min is None or price_max is None or price_min >= price_max:
        return []
    midpoint = (price_min + price_max) // 2
    if midpoint < price_min or midpoint >= price_max:
        return []
    parent_label = band.get("label") or f"{price_min}-{price_max}"
    parsed_depth = parse_int(band.get("partition_depth") or 0)
    if parsed_depth is None:
        return []
    depth = parsed_depth + 1
    return [
        {
            "price_min": price_min,
            "price_max": midpoint,
            "label": f"{price_min}-{midpoint}",
            "partition_depth": depth,
            "parent_price_band_label": parent_label,
        },
        {
            "price_min": midpoint + 1,
            "price_max": price_max,
            "label": f"{midpoint + 1}-{price_max}",
            "partition_depth": depth,
            "parent_price_band_label": parent_label,
        },
    ]


def should_partition_price_band(visible_result_count, threshold, band, max_depth):
    if isinstance(visible_result_count, bool) or isinstance(threshold, bool) or isinstance(max_depth, bool):
        return False
    threshold = int(threshold)
    max_depth = int(max_depth)
    band = band if isinstance(band, dict) else {}
    depth = safe_int(band.get("partition_depth"), 0)
    if threshold <= 0 or max_depth <= 0:
        return False
    if int(visible_result_count or 0) < threshold:
        return False
    if depth >= max_depth:
        return False
    return bool(split_price_band(band or {}))


def checkout_date(checkin, nights):
    return (date.fromisoformat(checkin) + timedelta(days=int(nights))).isoformat()


def normalize_filter_tokens(filters):
    tokens = []
    for item in filters or []:
        token = str(item or "").strip()
        if token:
            tokens.append(token)
    return tokens


def has_entire_home_filter(filters):
    return any(
        token == ENTIRE_HOME_FILTER
        or token == "room_types[]=Entire home/apt"
        or token == "room_types%5B%5D=Entire%20home%2Fapt"
        for token in normalize_filter_tokens(filters)
    )


def validate_similarity_filter_pack(filters, *, explicit_room_study=False):
    tokens = normalize_filter_tokens(filters)
    if not explicit_room_study and not has_entire_home_filter(tokens):
        raise ValueError("property validation public searches must include the Entire home room type")
    return {"checked": True, "filters": tokens, "entire_home_default_applied": has_entire_home_filter(tokens)}


def validate_research_mode_gate(research_mode, evidence):
    mode = str(research_mode or "").strip()
    if mode not in RESEARCH_MODES:
        raise ValueError(f"research_mode must be one of: {', '.join(sorted(RESEARCH_MODES))}")
    evidence = evidence or {}
    missing = []
    decision_constraint = None
    if mode == "opportunity_discovery":
        missing = [key for key in sorted(OPPORTUNITY_DISCOVERY_REQUIRED_KEYS) if not evidence.get(key)]
        if missing:
            decision_constraint = "cannot recommend a product profile until repeated winners and reproducibility are recorded"
    elif mode == "property_validation":
        if not evidence.get("target_address_or_building"):
            missing.append("target_address_or_building")
        if not evidence.get("map_boundary_receipt"):
            missing.append("map_boundary_receipt")
        if not any(evidence.get(key) for key in PROPERTY_VALIDATION_PROOF_KEYS):
            missing.append("same_building_or_same_block_comps_or_equal_or_worse_profitable_comps")
        if missing:
            decision_constraint = "cannot issue pursue without address-level boundary proof and equal-or-worse comp evidence"
    else:
        if not evidence.get("existing_listing_ref"):
            missing.append("existing_listing_ref")
        if missing:
            decision_constraint = "cannot reposition without the current listing reference"
    return {
        "research_mode": mode,
        "required_evidence_present_flag": not missing,
        "mode_specific_missing_evidence": missing,
        "mode_gate_result": "pass" if not missing else "needs_more_data",
        "decision_constraint": decision_constraint,
    }


def listing_maturity_filter(
    *,
    review_count=0,
    latest_review_date=None,
    observed_at=None,
    future_availability_signal=None,
    first_seen_at=None,
):
    observed = normalize_date_value(observed_at or date.today(), "observed_at")
    reviews = int(review_count or 0)
    latest = normalize_date_value(latest_review_date, "latest_review_date") if latest_review_date else None
    first_seen = normalize_date_value(first_seen_at, "first_seen_at") if first_seen_at else None
    days_since_latest = (observed - latest).days if latest else None
    days_since_first_seen = (observed - first_seen).days if first_seen else None
    recent_review_90d = days_since_latest is not None and 0 <= days_since_latest <= 90
    recent_review_180d = days_since_latest is not None and 0 <= days_since_latest <= 180
    new_listing_flag = reviews < 3 or (days_since_first_seen is not None and days_since_first_seen <= 45)
    possible_boost = new_listing_flag and bool(future_availability_signal in {None, "", "high_rank", "scarce_availability"})
    if reviews >= 10 and recent_review_90d:
        grade = "mature"
        use = "base_case"
    elif reviews >= 3 and recent_review_180d:
        grade = "promising"
        use = "sensitivity"
    elif reviews > 0 and days_since_latest is not None and days_since_latest > 365:
        grade = "stale"
        use = "exclude"
    elif new_listing_flag:
        grade = "boosted_or_unproven"
        use = "inspiration"
    else:
        grade = "unknown"
        use = "exclude"
    return {
        "review_count": reviews,
        "latest_review_date": latest.isoformat() if latest else None,
        "recent_review_count_window": "90d" if recent_review_90d else "180d" if recent_review_180d else None,
        "new_listing_flag": new_listing_flag,
        "possible_airbnb_boost_flag": possible_boost,
        "maturity_grade": grade,
        "can_use_for_underwriting_flag": use == "base_case",
        "underwriting_use": use,
    }


def search_matrix(listings, checkin_dates, nights_values, price_bands=None):
    price_bands = price_bands or [{"price_min": None, "price_max": None, "label": "all_prices"}]
    rows = []
    for listing in listings or []:
        listing_id = str(listing.get("listing_id"))
        for checkin in checkin_dates:
            for nights in nights_values:
                for band in price_bands:
                    rows.append({
                        "listing_id": listing_id,
                        "check_in_date": checkin,
                        "check_out_date": checkout_date(checkin, nights),
                        "nights": int(nights),
                        "price_min": band.get("price_min"),
                        "price_max": band.get("price_max"),
                        "price_band_label": band.get("label") or "all_prices",
                    })
    return rows


def validate_currency(value):
    text = str(value or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", text):
        raise ValueError("currency must be a three-letter ISO code")
    return text


def validate_guest_counts(*, adults=1, children=0, infants=0, pets=0):
    counts = {
        "adults": int(adults or 0),
        "children": int(children or 0),
        "infants": int(infants or 0),
        "pets": int(pets or 0),
    }
    if counts["adults"] < 1 or counts["adults"] > 16:
        raise ValueError("adults must be between 1 and 16")
    if counts["children"] < 0 or counts["children"] > 15:
        raise ValueError("children must be between 0 and 15")
    if counts["infants"] < 0 or counts["infants"] > 5:
        raise ValueError("infants must be between 0 and 5")
    if counts["pets"] < 0 or counts["pets"] > 5:
        raise ValueError("pets must be between 0 and 5")
    if counts["adults"] + counts["children"] > 16:
        raise ValueError("adult + child guest count must be <= 16")
    return counts


def validate_room_type_filters(filters, *, explicit_room_study=False):
    tokens = normalize_filter_tokens(filters)
    room_types = []
    for token in tokens:
        raw = token
        if token.startswith("room_types[]="):
            raw = token.split("=", 1)[1]
        if raw in VALID_ROOM_TYPES:
            room_types.append(raw)
    if not room_types:
        raise ValueError("at least one Airbnb room type filter is required")
    invalid = [room_type for room_type in room_types if room_type not in VALID_ROOM_TYPES]
    if invalid:
        raise ValueError(f"invalid Airbnb room type filter: {invalid[0]}")
    if not explicit_room_study and ENTIRE_HOME_FILTER not in room_types:
        raise ValueError("public market scans must default to Entire home/apt unless explicitly studying rooms")
    return {"checked": True, "room_types": room_types}


def validate_airbnb_room_url(value):
    parts = urlsplit(str(value or ""))
    path = parts.path if parts.scheme else str(value or "")
    if parts.netloc and not parts.netloc.endswith("airbnb.com.au") and not parts.netloc.endswith("airbnb.com"):
        raise ValueError("room URL must be an Airbnb URL")
    if not ROOM_URL_RE.fullmatch(path):
        raise ValueError("room URL must use /rooms/<numeric_id>")
    return True


def validate_airbnb_search_url(value):
    parts = urlsplit(str(value or ""))
    if parts.scheme not in {"http", "https"}:
        raise ValueError("search URL must be absolute HTTP(S)")
    if not (parts.netloc.endswith("airbnb.com.au") or parts.netloc.endswith("airbnb.com")):
        raise ValueError("search URL must be an Airbnb URL")
    if not parts.path.startswith("/s/") or not parts.path.endswith("/homes"):
        raise ValueError("search URL must use Airbnb /s/<destination>/homes")
    params = parse_qs(parts.query)
    for required in ("checkin", "checkout", "adults"):
        if required not in params:
            raise ValueError(f"search URL missing {required}")
    checkin = require_iso_date(params["checkin"][0], "check-in date")
    checkout = require_iso_date(params["checkout"][0], "check-out date")
    if checkout <= checkin:
        raise ValueError("check-out date must be after check-in date")
    validate_guest_counts(adults=params["adults"][0])
    return True


def validate_public_search_context(
    *,
    destination,
    checkin,
    checkout,
    nights=None,
    adults=1,
    children=0,
    infants=0,
    pets=0,
    currency="AUD",
    filters=None,
    price_band=None,
    url=None,
    explicit_room_study=False,
):
    dest = str(destination or "").strip()
    if not dest or len(dest) > 160:
        raise ValueError("destination must be a non-empty Airbnb-searchable label")
    checkin_date = require_iso_date(checkin, "check-in date")
    checkout_date_value = require_iso_date(checkout, "check-out date")
    if checkout_date_value <= checkin_date:
        raise ValueError("check-out date must be after check-in date")
    if nights is not None and (checkin_date + timedelta(days=int(nights))) != checkout_date_value:
        raise ValueError("nights must match check-in/check-out dates")
    counts = validate_guest_counts(adults=adults, children=children, infants=infants, pets=pets)
    room_types = validate_room_type_filters(filters or [ENTIRE_HOME_FILTER], explicit_room_study=explicit_room_study)
    band = price_band or {"price_min": None, "price_max": None, "label": "all_prices"}
    validate_public_market_options(
        checkin_dates=[checkin_date.isoformat()],
        nights_values=[(checkout_date_value - checkin_date).days],
        price_bands=[band],
        top_results=1,
        max_search_scrolls=0,
        currency=currency,
    )
    if url:
        validate_airbnb_search_url(url)
    return {
        "checked": True,
        "destination": dest,
        "check_in_date": checkin_date.isoformat(),
        "check_out_date": checkout_date_value.isoformat(),
        "nights": (checkout_date_value - checkin_date).days,
        "guest_counts": counts,
        "currency": validate_currency(currency),
        "room_types": room_types["room_types"],
        "price_band_label": band.get("label") or "all_prices",
        "search_url_checked": bool(url),
    }


def partition_key(target_listing_id, checkin, nights, price_band):
    band = price_band if isinstance(price_band, dict) else {}
    label = band.get("label") or "all_prices"
    depth = safe_int(band.get("partition_depth"), 0)
    return f"{target_listing_id}|{checkin}|{int(nights)}|{label}|d{depth}"


def dedupe_listing_ids(rows, key="listing_id_if_extractable"):
    ids = []
    seen = set()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        value = str(row.get(key) or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        ids.append(value)
    return ids


def build_partition_manifest(search_runs, result_rows=None, *, trigger_threshold=None, max_depth=None):
    """Summarize deterministic search partitions and listing-ID dedupe."""
    partitions = []
    for row in search_runs or []:
        if not isinstance(row, dict):
            continue
        child_labels = row.get("partition_child_labels") or []
        partitions.append({
            "partition_key": row.get("partition_key"),
            "search_run_id": row.get("search_run_id"),
            "target_listing_id": row.get("target_listing_id"),
            "check_in_date": row.get("check_in_date"),
            "nights": row.get("nights"),
            "price_band_label": row.get("price_band_label"),
            "price_min": row.get("price_min"),
            "price_max": row.get("price_max"),
            "partition_depth": safe_int(row.get("partition_depth"), 0),
            "parent_price_band_label": row.get("parent_price_band_label"),
            "visible_result_count": safe_int(row.get("results_count_visible"), 0),
            "status": row.get("status"),
            "partition_triggered": bool(row.get("partition_triggered")),
            "partition_child_labels": list(child_labels) if isinstance(child_labels, list) else [],
        })
    deduped_ids = dedupe_listing_ids(result_rows or [])
    return {
        "strategy": "deterministic_price_date_stay_partition",
        "trigger_threshold": optional_int(trigger_threshold),
        "max_depth": optional_int(max_depth),
        "partition_count": len(partitions),
        "triggered_partition_count": len([row for row in partitions if row["partition_triggered"]]),
        "partitions": partitions,
        "dedupe_key": "listing_id_if_extractable",
        "deduped_listing_count": len(deduped_ids),
        "deduped_listing_ids": deduped_ids,
    }


def validate_public_market_options(
    *,
    checkin_dates,
    nights_values,
    price_bands=None,
    top_results=12,
    max_search_scrolls=6,
    currency="AUD",
):
    if not checkin_dates:
        raise ValueError("at least one check-in date is required")
    for value in checkin_dates:
        require_iso_date(value, "check-in date")
    if not nights_values:
        raise ValueError("at least one stay length is required")
    normalized_nights = []
    for value in nights_values:
        nights = int(value)
        if nights <= 0 or nights > 90:
            raise ValueError("stay lengths must be between 1 and 90 nights")
        normalized_nights.append(nights)
    bands = price_bands or [{"price_min": None, "price_max": None, "label": "all_prices"}]
    for band in bands:
        parse_price_bands(band.get("label") if band.get("label") not in (None, "all_prices") else None)
        if band.get("price_min") is not None and int(band["price_min"]) < 0:
            raise ValueError("price_min must be non-negative")
        if band.get("price_max") is not None and int(band["price_max"]) < 0:
            raise ValueError("price_max must be non-negative")
        if (
            band.get("price_min") is not None
            and band.get("price_max") is not None
            and int(band["price_min"]) > int(band["price_max"])
        ):
            raise ValueError("price_min must be <= price_max")
    top_results = int(top_results)
    max_search_scrolls = int(max_search_scrolls)
    if top_results <= 0 or top_results > 100:
        raise ValueError("top_results must be between 1 and 100")
    if max_search_scrolls < 0 or max_search_scrolls > 50:
        raise ValueError("max_search_scrolls must be between 0 and 50")
    return {
        "checked": True,
        "checkin_date_count": len(checkin_dates),
        "nights_values": normalized_nights,
        "price_band_count": len(bands),
        "top_results": top_results,
        "max_search_scrolls": max_search_scrolls,
        "currency": validate_currency(currency),
    }
