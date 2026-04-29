"""Airbnb surface capability receipts and source-family metadata."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


API_V3_RE = re.compile(r"/api/v3/([^/?]+)/([0-9a-f]{64})", re.I)
OPERATION_NAME_RE = re.compile(r"[?&]operationName=([^&]+)")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")


SURFACE_SPECS = {
    "public_comp_search": {
        "plan_item": 1,
        "auth": "logged_out",
        "collector": "collect_competitors.py",
        "operations": ("StaysSearch",),
        "resource_keywords": ("StaysSearch", "search_results", "/s/", "/rooms/"),
        "cadence_days": 7,
        "priority": 20,
        "source_family": "public_market",
    },
    "own_public_audit": {
        "plan_item": 2,
        "auth": "logged_out",
        "collector": "collect_own_public.py",
        "operations": ("StaysPdpSections", "PdpAvailabilityCalendar", "StaysPdpReviewsQuery"),
        "resource_keywords": ("Pdp", "pdp", "reviews", "availability", "/rooms/"),
        "cadence_days": 30,
        "priority": 40,
        "source_family": "own_public",
    },
    "host_listing_inventory": {
        "plan_item": 3,
        "auth": "logged_in",
        "collector": "collect_listings.py",
        "operations": ("BeehiveGetListingsQuery",),
        "resource_keywords": ("BeehiveGetListingsQuery", "/hosting/listings", "/api/v3/"),
        "cadence_days": 30,
        "priority": 10,
        "source_family": "host_private",
    },
    "host_reviews": {
        "plan_item": 4,
        "auth": "logged_in",
        "collector": "collect_host_reviews.py",
        "operations": ("ReviewsSectionQuery", "ListOfMetricsQuery", "ChartQuery"),
        "resource_keywords": ("ReviewsSectionQuery", "review", "Review", "/performance/quality/overall", "/api/v3/"),
        "cadence_days": 7,
        "priority": 30,
        "source_family": "host_private",
    },
    "calendar_availability": {
        "plan_item": 5,
        "auth": "logged_in_or_logged_out_by_surface",
        "collector": "probe_surfaces.py",
        "operations": (
            "multicalBootstrap",
            "multicalListingsAndCalendars",
            "multicalAdditionalReservationData",
            "getCalendarTimelines",
        ),
        "resource_keywords": ("multical", "calendar", "Calendar", "availability", "Availability"),
        "cadence_days": 7,
        "priority": 35,
        "source_family": "calendar",
    },
    "calendar_export": {
        "plan_item": 6,
        "auth": "export_url",
        "collector": "collect_calendar_export.py",
        "operations": (),
        "resource_keywords": ("text/calendar", "VEVENT", "VCALENDAR", ".ics"),
        "cadence_days": 1,
        "priority": 12,
        "source_family": "calendar_export",
    },
    "pricing_rules": {
        "plan_item": 7,
        "auth": "logged_in",
        "collector": "probe_surfaces.py",
        "operations": ("multicalBootstrap", "multicalListingsAndCalendars", "getOpportunities"),
        "resource_keywords": ("HOST_PRICE", "SMART_PRICING", "pricing", "Pricing", "smart", "promotion"),
        "cadence_days": 7,
        "priority": 45,
        "source_family": "host_private",
    },
    "earnings_reservations_payouts": {
        "plan_item": 8,
        "auth": "logged_in",
        "collector": "probe_surfaces.py",
        "operations": (
            "FetchHostTransactionStats",
            "FetchPayoutNotificationsQuery",
            "HostBookingStats",
            "FetchEarningsComparisonGraphQuery",
            "FetchAvailableReportMetadata",
        ),
        "resource_keywords": ("transaction_history", "earnings", "Earnings", "reservation", "Reservation", "payout", "Payout"),
        "cadence_days": 30,
        "priority": 60,
        "source_family": "host_private_sensitive",
    },
    "market_research_scan": {
        "plan_item": 9,
        "auth": "logged_out",
        "collector": "collect_competitors.py",
        "operations": ("StaysSearch",),
        "resource_keywords": ("StaysSearch", "search_results", "price", "availability"),
        "cadence_days": 7,
        "priority": 25,
        "source_family": "public_market",
    },
    "regression_probes": {
        "plan_item": 10,
        "auth": "mixed",
        "collector": "probe_surfaces.py",
        "operations": ("StaysSearch", "BeehiveGetListingsQuery", "ChartQuery", "ListOfMetricsQuery"),
        "resource_keywords": ("/api/v3/", "operationName", "persistedQuery"),
        "cadence_days": 7,
        "priority": 15,
        "source_family": "capability",
    },
}


SENSITIVE_QUERY_KEYS = {
    "variables",
    "extensions",
    "api_key",
    "key",
    "token",
    "authorization",
    "x-airbnb-api-key",
}


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_observed_date(value):
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def surface_ids():
    return tuple(SURFACE_SPECS)


def get_surface_spec(surface_id):
    try:
        return SURFACE_SPECS[surface_id]
    except KeyError as error:
        raise ValueError(f"Unknown Airbnb surface: {surface_id}") from error


def redact_url(url):
    if not url:
        return None
    parts = urlsplit(str(url))
    safe_query = []
    redacted = False
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key.lower() in SENSITIVE_QUERY_KEYS:
            redacted = True
            continue
        if key in {"operationName", "locale", "currency"}:
            safe_query.append((key, value))
        else:
            redacted = True
    if redacted:
        safe_query.append(("redacted_query", "1"))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(safe_query), ""))


def matching_resource_urls(urls, surface_id, limit=25):
    spec = get_surface_spec(surface_id)
    keywords = tuple(spec.get("resource_keywords") or ())
    matches = []
    seen = set()
    for url in urls or []:
        if not isinstance(url, str):
            continue
        if keywords and not any(keyword in url for keyword in keywords):
            continue
        safe = redact_url(url)
        if safe and safe not in seen:
            seen.add(safe)
            matches.append(safe)
        if len(matches) >= limit:
            break
    return matches


def operation_hash_record(surface_id, hashes=None, sources=None):
    spec = get_surface_spec(surface_id)
    hashes = hashes or {}
    sources = sources or {}
    rows = {}
    for operation in spec.get("operations") or ():
        if operation in hashes:
            rows[operation] = {
                "hash_present": True,
                "hash_prefix": str(hashes[operation])[:8],
                "hash_source": sources.get(operation),
            }
        else:
            rows[operation] = {
                "hash_present": False,
                "hash_prefix": None,
                "hash_source": None,
            }
    return rows


def network_discovery_record(resource_urls, limit=50):
    """Summarize observed network/API families without storing payloads."""
    operations = {}
    redacted_urls = []
    seen_urls = set()
    family_counts = {}
    for raw_url in resource_urls or []:
        if not isinstance(raw_url, str):
            continue
        safe_url = redact_url(raw_url)
        if safe_url and safe_url not in seen_urls and len(redacted_urls) < limit:
            seen_urls.add(safe_url)
            redacted_urls.append(safe_url)
        parts = urlsplit(raw_url)
        family = parts.path.split("/")[1] if len(parts.path.split("/")) > 1 else "root"
        family_counts[family] = family_counts.get(family, 0) + 1
        api_match = API_V3_RE.search(raw_url)
        op_match = OPERATION_NAME_RE.search(raw_url)
        operation = op_match.group(1) if op_match else (api_match.group(1) if api_match else None)
        if not operation:
            continue
        row = operations.setdefault(operation, {"count": 0, "hash_prefixes": []})
        row["count"] += 1
        if api_match:
            prefix = api_match.group(2)[:8]
            if prefix not in row["hash_prefixes"]:
                row["hash_prefixes"].append(prefix)
    return {
        "resource_count": len([url for url in resource_urls or [] if isinstance(url, str)]),
        "redacted_resource_urls": redacted_urls,
        "resource_family_counts": family_counts,
        "api_operations": operations,
    }


def capability_record(
    surface_id,
    *,
    observed_at=None,
    auth_context=None,
    source_url=None,
    resource_urls=None,
    operation_hashes=None,
    operation_hash_sources=None,
    status=None,
    evidence=None,
):
    spec = get_surface_spec(surface_id)
    matched_resources = matching_resource_urls(resource_urls or [], surface_id)
    hash_rows = operation_hash_record(surface_id, operation_hashes, operation_hash_sources)
    return {
        "surface_id": surface_id,
        "plan_item": spec["plan_item"],
        "source_family": spec["source_family"],
        "surface_class": spec["source_family"],
        "collector": spec["collector"],
        "observed_at": observed_at or utc_now(),
        "expected_auth": spec["auth"],
        "auth_context": auth_context,
        "source_url": redact_url(source_url),
        "status": status or ("capability_observed" if matched_resources or any(row["hash_present"] for row in hash_rows.values()) else "capability_not_observed"),
        "matched_resource_count": len(matched_resources),
        "matched_resource_urls": matched_resources,
        "operation_hashes": hash_rows,
        "evidence": evidence or {},
    }


def upsert_best_capability(records, record):
    """Keep the strongest receipt for a surface without duplicating it."""
    surface_id = record.get("surface_id")
    for index, existing in enumerate(records):
        if existing.get("surface_id") != surface_id:
            continue
        existing_observed = existing.get("status") == "capability_observed"
        record_observed = record.get("status") == "capability_observed"
        existing_count = int(existing.get("matched_resource_count") or 0)
        record_count = int(record.get("matched_resource_count") or 0)
        if (record_observed and not existing_observed) or record_count > existing_count:
            records[index] = record
        return records
    records.append(record)
    return records


def resource_urls_from_performance_entries(entries):
    urls = []
    for entry in entries or []:
        if isinstance(entry, str):
            urls.append(entry)
        elif isinstance(entry, dict) and entry.get("name"):
            urls.append(entry["name"])
    return urls


def stale_after(observed_at, cadence_days, today=None):
    if not observed_at:
        return True
    today = today or date.today()
    if isinstance(observed_at, datetime):
        observed_date = observed_at.date()
    else:
        observed_date = date.fromisoformat(str(observed_at)[:10])
    return observed_date + timedelta(days=int(cadence_days)) < today


def due_date(observed_at, cadence_days):
    if not observed_at:
        return None
    if isinstance(observed_at, datetime):
        observed_date = observed_at.date()
    else:
        observed_date = date.fromisoformat(str(observed_at)[:10])
    return observed_date + timedelta(days=int(cadence_days))


def build_staleness_plan(last_observed_by_surface=None, today=None, surface_ids_to_check=None):
    last_observed_by_surface = last_observed_by_surface or {}
    ids = surface_ids_to_check or surface_ids()
    rows = []
    for surface_id in ids:
        spec = get_surface_spec(surface_id)
        last_observed = last_observed_by_surface.get(surface_id)
        due = due_date(last_observed, spec["cadence_days"])
        stale = stale_after(last_observed, spec["cadence_days"], today=today)
        rows.append({
            "surface_id": surface_id,
            "plan_item": spec["plan_item"],
            "cadence_days": spec["cadence_days"],
            "priority": spec["priority"],
            "last_observed_at": last_observed,
            "due_at": due.isoformat() if due else None,
            "days_overdue": ((today or date.today()) - due).days if due and stale else None,
            "stale": stale,
            "collector": spec["collector"],
            "expected_auth": spec["auth"],
            "source_family": spec["source_family"],
            "surface_class": spec["source_family"],
        })
    return rows


def build_refresh_tasks(last_observed_by_surface=None, today=None, surface_ids_to_check=None, include_fresh=False):
    today = today or date.today()
    rows = build_staleness_plan(
        last_observed_by_surface=last_observed_by_surface,
        today=today,
        surface_ids_to_check=surface_ids_to_check,
    )
    tasks = []
    for row in rows:
        if not include_fresh and not row["stale"]:
            continue
        reason = "never_observed" if not row.get("last_observed_at") else (
            "cadence_expired" if row["stale"] else "fresh"
        )
        tasks.append({
            "task_id": f"airbnb-refresh-{row['surface_id']}",
            "surface_id": row["surface_id"],
            "collector": row["collector"],
            "expected_auth": row["expected_auth"],
            "source_family": row["source_family"],
            "surface_class": row["surface_class"],
            "priority": row["priority"],
            "reason": reason,
            "last_observed_at": row["last_observed_at"],
            "due_at": row["due_at"],
            "days_overdue": row["days_overdue"],
            "stale": row["stale"],
        })
    return sorted(
        tasks,
        key=lambda item: (
            0 if item["stale"] else 1,
            int(item["priority"]),
            -(item["days_overdue"] or 0),
            item["surface_id"],
        ),
    )


def page_api_resource_urls(js):
    return js(
        r"""
(() => Array.from(performance.getEntriesByType('resource') || [])
  .map(entry => entry.name || '')
  .filter(url => /airbnb|\/api\//i.test(url))
  .slice(-200))()
"""
    ) or []


def text_matches_any(text, patterns):
    haystack = text or ""
    return any(re.search(pattern, haystack, re.I) for pattern in patterns or ())


def capability_registry_entry(
    surface_id,
    *,
    observed_at=None,
    endpoint_url=None,
    operation_name=None,
    operation_hash=None,
    ttl_days=None,
    status=None,
    provenance=None,
):
    """Build a validated capability registry row with redacted provenance."""
    spec = get_surface_spec(surface_id)
    observed_at = observed_at or utc_now()
    ttl_days = int(ttl_days if ttl_days is not None else spec["cadence_days"])
    if operation_hash and not HASH_RE.fullmatch(str(operation_hash)):
        raise ValueError("operation_hash must be 64 lowercase hex characters")
    observed_dt = parse_observed_date(observed_at)
    expires_at = (observed_dt + timedelta(days=ttl_days)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    identifier = operation_name or (urlsplit(endpoint_url or "").path or surface_id).rsplit("/", 1)[-1] or surface_id
    registry_id = "|".join([surface_id, str(identifier), str(operation_hash or endpoint_url or "capability")[:80]])
    return {
        "registry_id": registry_id,
        "surface_id": surface_id,
        "source_family": spec["source_family"],
        "surface_class": spec["source_family"],
        "collector": spec["collector"],
        "operation_name": operation_name,
        "operation_hash": str(operation_hash) if operation_hash else None,
        "operation_hash_prefix": str(operation_hash)[:8] if operation_hash else None,
        "endpoint_url": redact_url(endpoint_url),
        "first_seen_at": observed_at,
        "last_seen_at": observed_at,
        "ttl_days": ttl_days,
        "expires_at": expires_at,
        "status": status or "active",
        "provenance": provenance or {},
    }


def capability_registry_status(entry, today=None):
    today = today or date.today()
    if entry.get("status") in {"disabled", "invalid"}:
        return entry["status"]
    expires_at = entry.get("expires_at")
    if not expires_at:
        return "stale"
    expires = date.fromisoformat(str(expires_at)[:10])
    return "active" if expires >= today else "stale"


def upsert_capability_registry(entries, entry):
    entries = list(entries or [])
    for index, existing in enumerate(entries):
        if existing.get("registry_id") == entry.get("registry_id"):
            entries[index] = {
                **existing,
                **entry,
                "first_seen_at": existing.get("first_seen_at") or entry.get("first_seen_at"),
            }
            return entries
    entries.append(entry)
    return entries


def registry_ref(entry):
    return {
        "registry_id": entry.get("registry_id"),
        "surface_id": entry.get("surface_id"),
        "status": capability_registry_status(entry),
        "last_seen_at": entry.get("last_seen_at"),
        "expires_at": entry.get("expires_at"),
    }


def load_capability_registry(path):
    path = Path(path)
    if not path.exists():
        return []
    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return [row for row in payload.get("entries", []) if isinstance(row, dict)]
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    return []


def save_capability_registry(path, entries):
    import json

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema_version": 1, "updated_at": utc_now(), "entries": list(entries or [])}
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload
