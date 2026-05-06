"""Collect authenticated Airbnb host live-listing inventory.

Role: collector (private). Run this first; every other private and public
collector reads the newest complete `airbnb-live-listings-*.json` it produces.

Reads:
    - `BeehiveGetListingsQuery` overview API at `/api/v3/...`, paginated.
    - Authenticated listing editor pages for private detail fields per active
      listing.
    - Optional restorable auth bundle at `AIRBNB_AUTH_STATE_PATH` (loaded into a
      fresh agent profile to verify cross-process auth restore).

Produces:
    - `domain-skills/airbnb/.private-data/listing-collections/<run_id>.json`
    - `domain-skills/airbnb/.private-data/listing-collections/<run_id>.csv`
    - `domain-skills/airbnb/.session-store/capability/<run_id>-receipt.json`

Requires (env, optional unless noted):
    - `AIRBNB_AUTH_STATE_PATH` — path to a private auth bundle. Required only
      when proving auth restore in a fresh profile; otherwise the caller-
      provided authenticated browser context is used.
    - `AIRBNB_LISTINGS_RUN_ID`, `AIRBNB_LISTINGS_PAGE_LIMIT`,
      `AIRBNB_LISTINGS_STATUS_SCOPE`, `AIRBNB_LISTINGS_LIMIT_ACTIVE`,
      `AIRBNB_LISTINGS_SKIP_DETAILS`, `AIRBNB_LISTINGS_DETAIL_PAUSE_SEC`,
      `AIRBNB_LISTINGS_QUERY_HASH` — see host-sources.md.

Refuses to run if:
    - The Airbnb bootstrap API key cannot be read from the loaded
      `/hosting/listings` page.
    - `AIRBNB_AUTH_STATE_PATH` is set but the restored session does not load
      authenticated host content.

Partial runs (`AIRBNB_LISTINGS_LIMIT_ACTIVE` or `AIRBNB_LISTINGS_SKIP_DETAILS`)
are flagged with `partial_run: true` and downstream collectors refuse them by
default. Use `AIRBNB_LISTINGS_FILE` only to intentionally point a downstream
collector at a partial scope.

Run from the browser-harness repo against an authenticated Airbnb host browser
context:

    BH_NAME=airbnb-listings BH_CDP_WS=http://127.0.0.1:52862 \
      python3 run.py < domain-skills/airbnb/scripts/collect_listings.py

For a fresh agent-owned profile, launch Chrome first, then optionally restore a
private auth bundle without printing cookie values:

    python3 run.py --launch-profile domain-skills/airbnb/.session-store/profiles/listings \
      --port 52862 --url about:blank --json

    AIRBNB_AUTH_STATE_PATH=domain-skills/airbnb/.private-data/auth-state/host-main-cdp-state.json \
    BH_NAME=airbnb-listings BH_CDP_WS=http://127.0.0.1:52862 \
      python3 run.py < domain-skills/airbnb/scripts/collect_listings.py

Private outputs are written under ignored domain-skills/airbnb/.private-data/.
Receipts are compact and avoid private addresses and cookie values.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import os
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from browser_harness import login_session


BASE = "https://www.airbnb.com.au"
HOST_LISTINGS_URL = BASE + "/hosting/listings"
OUTPUT_PATH = Path("domain-skills/airbnb/.private-data/listing-collections")
SESSION_PATH = Path("domain-skills/airbnb/.session-store/capability")
CAPABILITY_REGISTRY_PATH = SESSION_PATH / "capability-registry.json"

OPERATION_NAME = "BeehiveGetListingsQuery"
OBSERVED_QUERY_HASH = "6a50773b7e0bf1c1c7c54d7b12d12c2db5be0eb4ce1ebfb8df1c3b42a9e2aaca"
REQUIRED_FIELDS = [
    "listing_id",
    "listing_name",
    "status",
    "address",
    "bedrooms",
    "bathrooms",
    "beds",
    "max_guests",
]

_NAVIGATED = False


def _load_local_module(module_filename, module_name):
    path = Path("domain-skills/airbnb/scripts") / module_filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_listing_scope = _load_local_module("listing_scope.py", "airbnb_listing_scope")
_operation_hashes = _load_local_module("operation_hashes.py", "airbnb_operation_hashes")
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


def wrapper_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.lower()
        if lowered in {"true", "yes", "instant book"}:
            return True
        if lowered in {"false", "no"}:
            return False
    return None


def as_number(value):
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        match = re.search(r"\d+(?:\.\d+)?", value)
        if match:
            parsed = float(match.group(0))
            return int(parsed) if parsed.is_integer() else parsed
    return None


def stringify(value):
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, (int, float, bool)):
        return str(value)
    return None


def direct_value(obj, names):
    if not isinstance(obj, dict):
        return None
    lowered = {str(key).lower(): key for key in obj}
    for name in names:
        key = lowered.get(name.lower())
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


def likely_listing_id(value):
    text = stringify(value)
    if not text:
        return None
    match = re.search(r"\d{6,}", text)
    return match.group(0) if match else None


def normalize_overview_record(row):
    listing_id = (
        likely_listing_id(direct_value(row, ["listingId", "listing_id", "roomId", "id"]))
        or likely_listing_id(recursive_value(row, ["listingId", "listing_id", "roomId"]))
    )
    if not listing_id:
        return None
    status = stringify(recursive_value(row, ["status", "listingStatus", "publishStatus"]))
    name = stringify(recursive_value(row, ["listingName", "name", "title", "internalName"]))
    if not status and not name:
        return None
    location = recursive_value(row, ["locationLabel", "localizedLocation", "location", "address"])
    if isinstance(location, dict):
        location = stringify(recursive_value(location, ["subtitle", "title", "name", "city"]))
    else:
        location = stringify(location)
    public_url = stringify(recursive_value(row, ["publicUrl", "listingUrl", "url"]))
    if public_url and public_url.startswith("/"):
        public_url = BASE + public_url
    return {
        "listing_id": listing_id,
        "listing_name": name,
        "nickname": stringify(recursive_value(row, ["nickname", "internalName"])),
        "status": status,
        "api_state": stringify(recursive_value(row, ["state", "apiState", "publishState"])),
        "location_label": location,
        "address": stringify(recursive_value(row, ["fullAddress", "address"])),
        "bedrooms": as_number(recursive_value(row, ["bedrooms", "bedroomCount"])),
        "bathrooms": as_number(recursive_value(row, ["bathrooms", "bathroomCount"])),
        "beds": as_number(recursive_value(row, ["beds", "bedCount"])),
        "max_guests": as_number(recursive_value(row, ["personCapacity", "guestCapacity", "maxGuests", "guestCount"])),
        "instant_book_enabled": wrapper_bool(recursive_value(row, ["instantBookEnabled", "isInstantBookable"])),
        "modified_at": stringify(recursive_value(row, ["modifiedAt", "updatedAt", "lastModifiedAt"])),
        "photo_count": as_number(recursive_value(row, ["photoCount", "photosCount"])),
        "public_listing_url": public_url or f"{BASE}/rooms/{listing_id}",
        "host_editor_path": stringify(recursive_value(row, ["hostEditorPath", "editorPath"])) or f"/hosting/listings/{listing_id}",
        "source_overview": OPERATION_NAME,
    }


def walk_listing_candidates(obj):
    records = []
    if isinstance(obj, dict):
        normalized = normalize_overview_record(obj)
        if normalized:
            records.append(normalized)
        for value in obj.values():
            records.extend(walk_listing_candidates(value))
    elif isinstance(obj, list):
        for value in obj:
            records.extend(walk_listing_candidates(value))
    return records


def dedupe_records(records):
    out = {}
    for record in records:
        key = record.get("listing_id")
        if not key:
            continue
        current = out.get(key, {})
        merged = {**current, **{k: v for k, v in record.items() if v not in (None, "", [])}}
        out[key] = merged
    return list(out.values())


def first_total_count(obj):
    if isinstance(obj, dict):
        for key, value in obj.items():
            if str(key).lower() in {"totalcount", "total_count"} and isinstance(value, int):
                return value
        for value in obj.values():
            found = first_total_count(value)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = first_total_count(value)
            if found is not None:
                return found
    return None


def discover_query_hash(base_headers=None):
    env_hash = os.environ.get("AIRBNB_LISTINGS_QUERY_HASH")
    if env_hash:
        return {"hash": env_hash, "source": "AIRBNB_LISTINGS_QUERY_HASH", "discovery": None}
    registry_hashes, registry_sources = _operation_hashes.operation_hashes_from_registry(
        _surfaces.load_capability_registry(CAPABILITY_REGISTRY_PATH),
        [OPERATION_NAME],
        surface_id="host_listing_inventory",
    )
    if registry_hashes.get(OPERATION_NAME):
        return {
            "hash": registry_hashes[OPERATION_NAME],
            "source": registry_sources.get(OPERATION_NAME) or "capability_registry",
            "discovery": {"source": "capability_registry", "path": str(CAPABILITY_REGISTRY_PATH)},
        }

    context = js(r"""(() => ({
  html: document.documentElement.outerHTML,
  scripts: Array.from(document.scripts || []).map(script => script.src).filter(Boolean),
  resources: Array.from(performance.getEntriesByType("resource") || []).map(entry => entry.name || "").filter(Boolean)
}))()""") or {}
    seed_texts = [context.get("html") or ""]
    seed_urls = [
        url for url in [*(context.get("scripts") or []), *(context.get("resources") or [])]
        if isinstance(url, str) and "/airbnb/static/packages/web/" in url and url.endswith(".js")
    ]

    def fetcher(url):
        headers = {
            **(base_headers or {}),
            "Accept": "application/javascript,text/javascript,text/plain,*/*",
            "Accept-Encoding": "identity",
        }
        try:
            with urlopen(Request(url, headers=headers), timeout=float(os.environ.get("AIRBNB_LISTINGS_HASH_FETCH_TIMEOUT_SEC", "15"))) as response:
                return read_response_text(response)
        except (HTTPError, URLError, TimeoutError):
            return ""

    discovery = _operation_hashes.discover_operation_hashes(
        fetcher,
        [OPERATION_NAME],
        seed_texts=seed_texts,
        seed_urls=seed_urls,
        max_fetches=int(os.environ.get("AIRBNB_LISTINGS_HASH_DISCOVERY_MAX_FETCHES", "80")),
    )
    hash_value = discovery.get("hashes", {}).get(OPERATION_NAME)
    if hash_value:
        return {
            "hash": hash_value,
            "source": discovery.get("sources", {}).get(OPERATION_NAME) or "bundle_discovery",
            "discovery": discovery,
        }
    return {
        "hash": OBSERVED_QUERY_HASH,
        "source": "observed_2026_04_27_fallback",
        "discovery": discovery,
    }


def api_url(query_hash, variables):
    extensions = {"persistedQuery": {"version": 1, "sha256Hash": query_hash}}
    return (
        f"{BASE}/api/v3/{OPERATION_NAME}/{query_hash}"
        f"?operationName={OPERATION_NAME}"
        "&locale=en-AU&currency=AUD"
        f"&variables={quote(json.dumps(variables, separators=(',', ':')))}"
        f"&extensions={quote(json.dumps(extensions, separators=(',', ':')))}"
    )


def fetch_json(url, api_key, base_headers):
    headers = {
        **base_headers,
        "Accept": "application/json",
        "Accept-Encoding": "identity",
        "X-Airbnb-API-Key": api_key,
        "X-Airbnb-GraphQL-Platform": "web",
        "X-CSRF-Without-Token": "1",
    }
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=float(os.environ.get("AIRBNB_LISTINGS_FETCH_TIMEOUT_SEC", "25"))) as response:
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


def variable_candidates(offset, limit):
    return [
        {"request": {"limit": limit, "offset": offset}},
        {"input": {"limit": limit, "offset": offset}},
        {"limit": limit, "offset": offset},
    ]


def fetch_overview_page(query_hash, api_key, base_headers, offset, limit, preferred_shape=None):
    candidates = [preferred_shape(offset, limit)] if preferred_shape else variable_candidates(offset, limit)
    attempts = []
    for index, variables in enumerate(candidates):
        result = fetch_json(api_url(query_hash, variables), api_key, base_headers)
        records = dedupe_records(walk_listing_candidates(result.get("data")))
        total = first_total_count(result.get("data"))
        attempts.append({"variables": variables, "result": result, "records": records, "total": total, "shape_index": index})
        if result.get("ok") and records:
            return attempts[-1]
    return attempts[-1] if attempts else {"result": {"ok": False, "error": "no_variable_candidates"}, "records": [], "total": None}


def preferred_shape_from_variables(variables):
    if "request" in variables:
        return lambda offset, limit: {"request": {"limit": limit, "offset": offset}}
    if "input" in variables:
        return lambda offset, limit: {"input": {"limit": limit, "offset": offset}}
    return lambda offset, limit: {"limit": limit, "offset": offset}


def line_after(lines, labels):
    labels = {label.lower() for label in labels}
    for index, line in enumerate(lines):
        if line.strip().lower().rstrip(":") in labels:
            for candidate in lines[index + 1 : index + 5]:
                if candidate and candidate.strip().lower().rstrip(":") not in labels:
                    return candidate.strip()
    return None


def detail_fields_from_text(text):
    text = re.sub(r"\n{2,}", "\n", text or "")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    property_type = line_after(lines, ["Property type"])
    if property_type:
        property_type = " ".join(lines[max(0, lines.index(property_type) - 2) : lines.index(property_type) + 3])
    room_photo_lines = [line for line in lines if re.search(r"\b\d+\s+photos?\b", line, re.I)]
    return {
        "address": line_after(lines, ["Location", "Address"]),
        "max_guests": (
            as_number(first_regex(text, r"Number of guests\s+(\d+)\s+guests?"))
            or as_number(first_regex(text, r"\b(\d+)\s+guests?\s+maximum\b"))
        ),
        "guest_label": (
            first_regex(text, r"Number of guests\s+(\d+\s+guests?)")
            or first_regex(text, r"\b(\d+\s+guests?\s+maximum)\b")
        ),
        "property_type_summary": property_type,
        "photo_count": as_number(first_regex(text, r"\b(\d+)\s+photos?\b")),
        "room_photo_lines": room_photo_lines[:20],
    }


def first_regex(text, pattern):
    match = re.search(pattern, text or "", re.I)
    return match.group(1).strip() if match else None


def collect_detail(record, pause):
    listing_id = record["listing_id"]
    url = f"{BASE}/hosting/listings/editor/{listing_id}/details/photo-tour"
    navigate(url)
    wait_for_load()
    if pause:
        wait(pause)
    deadline = time.time() + float(os.environ.get("AIRBNB_LISTINGS_DETAIL_TIMEOUT_SEC", "20"))
    text = ""
    while time.time() < deadline:
        text = js("document.body ? document.body.innerText : ''") or ""
        fields = detail_fields_from_text(text)
        if fields.get("address") and fields.get("max_guests"):
            break
        wait(0.5)
    final_url = js("location.href")
    fields = detail_fields_from_text(text)
    merged = {**record}
    for key, value in fields.items():
        if value not in (None, "", []):
            merged[key] = value
    merged["source_detail_url"] = final_url or url
    merged["detail_field_ok"] = all(merged.get(field) not in (None, "", []) for field in REQUIRED_FIELDS)
    return merged


def write_csv(path, rows):
    if not rows:
        return
    fields = [
        "listing_id",
        "listing_name",
        "nickname",
        "status",
        "api_state",
        "location_label",
        "address",
        "bedrooms",
        "bathrooms",
        "beds",
        "max_guests",
        "guest_label",
        "property_type_summary",
        "instant_book_enabled",
        "modified_at",
        "photo_count",
        "public_listing_url",
        "host_editor_path",
        "detail_field_ok",
        "observed_at",
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def maybe_restore_auth():
    state_path = os.environ.get("AIRBNB_AUTH_STATE_PATH")
    if not state_path:
        return None
    state = json.loads(Path(state_path).read_text())
    verification = login_session.restore_session_state_and_verify(
        cdp,
        state,
        [HOST_LISTINGS_URL],
        include_session_storage=True,
        min_text=int(os.environ.get("AIRBNB_LISTINGS_AUTH_MIN_TEXT", "500")),
        timeout=float(os.environ.get("AIRBNB_LISTINGS_AUTH_TIMEOUT_SEC", "45")),
    )
    if not verification.get("ok"):
        raise SystemExit(f"Airbnb auth restore failed: {json.dumps(verification, ensure_ascii=False)}")
    return {
        "state_path": state_path,
        "cookie_restore": verification.get("restore", {}).get("cookies", {}),
        "resources_checked": verification.get("resources_checked", []),
    }


def read_bootstrap_api_key(timeout=20.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        api_key = os.environ.get("AIRBNB_API_KEY") or js("JSON.parse(document.querySelector('#data-initializer-bootstrap')?.textContent || '{}')['layout-init']?.api_config?.key")
        if api_key:
            return api_key
        wait(0.5)
    return None


def main():
    observed_at = utc_now()
    run_id = os.environ.get("AIRBNB_LISTINGS_RUN_ID") or "airbnb-live-listings-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    limit = int(os.environ.get("AIRBNB_LISTINGS_PAGE_LIMIT", "30"))
    pause = float(os.environ.get("AIRBNB_LISTINGS_DETAIL_PAUSE_SEC", "1.5"))
    max_pages = int(os.environ.get("AIRBNB_LISTINGS_MAX_PAGES", "20"))
    detail_limit = os.environ.get("AIRBNB_LISTINGS_LIMIT_ACTIVE")
    skip_details = os.environ.get("AIRBNB_LISTINGS_SKIP_DETAILS") == "1"

    OUTPUT_PATH.mkdir(parents=True, exist_ok=True)
    SESSION_PATH.mkdir(parents=True, exist_ok=True)

    auth_restore = maybe_restore_auth()
    navigate(HOST_LISTINGS_URL)
    wait_for_load()
    wait(2)
    api_key = read_bootstrap_api_key(float(os.environ.get("AIRBNB_LISTINGS_BOOTSTRAP_TIMEOUT_SEC", "20")))
    if not api_key:
        raise SystemExit("Could not read Airbnb API key from listings page bootstrap")
    base_headers = login_session.browser_session_headers(
        cdp,
        BASE + "/api/v3/",
        cookie_urls=[BASE + "/"],
    )
    hash_info = discover_query_hash(base_headers)
    surface_capability = _surfaces.capability_record(
        "host_listing_inventory",
        observed_at=observed_at,
        auth_context=(
            "restored_private_host_session_in_fresh_agent_chrome_profile"
            if auth_restore else "caller_provided_authenticated_browser_context"
        ),
        source_url=HOST_LISTINGS_URL,
        resource_urls=_surfaces.page_api_resource_urls(js),
        operation_hashes={OPERATION_NAME: hash_info["hash"]},
        operation_hash_sources={OPERATION_NAME: hash_info["source"]},
        evidence={"hash_discovery": hash_info.get("discovery")},
    )
    capability_registry_entry = _surfaces.capability_registry_entry(
        "host_listing_inventory",
        observed_at=observed_at,
        endpoint_url=HOST_LISTINGS_URL,
        operation_name=OPERATION_NAME,
        operation_hash=hash_info["hash"],
        provenance={"source": hash_info["source"]},
    )
    capability_registry = _surfaces.upsert_capability_registry(
        _surfaces.load_capability_registry(CAPABILITY_REGISTRY_PATH),
        capability_registry_entry,
    )
    _surfaces.save_capability_registry(CAPABILITY_REGISTRY_PATH, capability_registry)
    capability_registry_ref = _surfaces.registry_ref(capability_registry_entry)

    pages = []
    overview_records = []
    preferred_shape = None
    total_count = None
    offset = 0
    for _ in range(max_pages):
        page = fetch_overview_page(hash_info["hash"], api_key, base_headers, offset, limit, preferred_shape=preferred_shape)
        result = page.get("result", {})
        records = page.get("records", [])
        total_count = page.get("total") if page.get("total") is not None else total_count
        if records and preferred_shape is None:
            preferred_shape = preferred_shape_from_variables(page["variables"])
        pages.append({
            "ok": bool(result.get("ok")),
            "status": result.get("status"),
            "offset": offset,
            "limit": limit,
            "resultCount": len(records),
            "totalCount": total_count,
            "variableShapeIndex": page.get("shape_index"),
            "errors": (result.get("data") or {}).get("errors") if isinstance(result.get("data"), dict) else result.get("error"),
        })
        overview_records.extend(records)
        if not records:
            break
        offset += limit
        if total_count is not None and offset >= int(total_count):
            break

    overview_records = dedupe_records(overview_records)
    status_counts = Counter(record.get("status") or "UNKNOWN" for record in overview_records)
    scoped_records, listing_scope = _listing_scope.select_listings(
        overview_records,
        os.environ.get("AIRBNB_LISTINGS_STATUS_SCOPE"),
    )
    total_scope_listings = len(scoped_records)
    if detail_limit:
        scoped_records = scoped_records[: int(detail_limit)]

    records = []
    failures = []
    for index, record in enumerate(scoped_records, start=1):
        if skip_details:
            enriched = {**record, "detail_field_ok": all(record.get(field) not in (None, "", []) for field in REQUIRED_FIELDS)}
        else:
            print(json.dumps({"phase": "detail", "progress": index, "total": len(scoped_records), "listing_id": record["listing_id"]}), flush=True)
            try:
                enriched = collect_detail(record, pause)
            except Exception as error:
                enriched = {**record, "detail_field_ok": False, "source_detail_url": f"{BASE}/hosting/listings/{record['listing_id']}"}
                failures.append({"listing_id": record.get("listing_id"), "error": repr(error)})
        enriched["observed_at"] = observed_at
        missing = [field for field in REQUIRED_FIELDS if enriched.get(field) in (None, "", [])]
        if missing:
            failures.append({"listing_id": enriched.get("listing_id"), "error": "missing_required_fields", "missing_fields": missing})
        records.append(enriched)

    json_path = OUTPUT_PATH / f"{run_id}.json"
    csv_path = OUTPUT_PATH / f"{run_id}.csv"
    receipt_path = SESSION_PATH / f"{run_id}-receipt.json"
    prior_counts = _integrity.latest_prior_count(
        OUTPUT_PATH,
        count_keys=("records_count",),
        current_run_id=run_id,
    )
    last_good_guard = _integrity.last_good_guard(
        subject="host_listing_inventory_records",
        current_count=len(records),
        prior_positive_count=prior_counts["prior_positive_count"],
        allow_empty=os.environ.get("AIRBNB_LISTINGS_ALLOW_EMPTY") == "1",
    )
    warehouse_exports = _integrity.warehouse_manifest([
        {
            "table": "airbnb_listing_master",
            "path": str(csv_path),
            "row_count": len(records),
            "grain": "listing_id",
            "source_family": "host_private",
            "surface_class": "host_private",
            "auth_context": (
                "restored_private_host_session_in_fresh_agent_chrome_profile"
                if auth_restore else "caller_provided_authenticated_browser_context"
            ),
        },
    ])
    collection_status = _integrity.collection_status(
        last_good_guard_record=last_good_guard,
        failures_count=len(failures),
        complete=not bool(detail_limit or skip_details) and len(records) == total_scope_listings,
    )
    output = _integrity.stamp_collection_contract({
        "run_id": run_id,
        "observed_at": observed_at,
        "partial_run": bool(detail_limit or skip_details),
        "source": {
            "overview": f"{OPERATION_NAME} /api/v3 persisted query",
            "overview_hash": hash_info["hash"],
            "overview_hash_source": hash_info["source"],
            "overview_hash_discovery": hash_info.get("discovery"),
            "detail": "authenticated listing editor page text",
            "surface_capabilities": [surface_capability],
            "capability_registry_ref": capability_registry_ref,
        },
        "overview_pages": pages,
        "total_listings_seen": len(overview_records),
        "status_counts": dict(status_counts),
        "active_count": int(status_counts.get("ACTIVE") or 0),
        "listing_status_scope": listing_scope["label"],
        "scoped_listing_count": len(records),
        "total_scope_listings": total_scope_listings,
        "listing_scope_complete": len(records) == total_scope_listings,
        "records_count": len(records),
        "detail_limit": int(detail_limit) if detail_limit else None,
        "skip_details": skip_details,
        "field_validation": {
            "required_fields": REQUIRED_FIELDS,
            "all_active_detail_pages_ok": all(record.get("detail_field_ok") for record in records),
            "failures_count": len(failures),
        },
        "records": records,
        "failures": failures[:100],
    },
        source_family="host_private",
        surface_class="host_private",
        auth_context=(
            "restored_private_host_session_in_fresh_agent_chrome_profile"
            if auth_restore else "caller_provided_authenticated_browser_context"
        ),
        collection_status=collection_status,
        last_good_guard_record=last_good_guard,
        warehouse_exports=warehouse_exports,
        capability_registry_ref=capability_registry_ref,
    )
    _integrity.write_collection_json(json_path, output)
    write_csv(csv_path, records)

    receipt = _integrity.stamp_collection_contract({
        "run_id": run_id,
        "observed_at": observed_at,
        "auth_context": output["auth_context"],
        "source_family": output["source_family"],
        "surface_class": output["surface_class"],
        "collection_status": output["collection_status"],
        "last_good_guard": last_good_guard,
        "warehouse_exports": warehouse_exports,
        "capability_registry_ref": capability_registry_ref,
        "partial_run": output["partial_run"],
        "source": output["source"],
        "surface_capabilities": [surface_capability],
        "overview_pages": pages,
        "total_listings_seen": len(overview_records),
        "status_counts": dict(status_counts),
        "active_count": output["active_count"],
        "listing_status_scope": output["listing_status_scope"],
        "scoped_listing_count": output["scoped_listing_count"],
        "total_scope_listings": output["total_scope_listings"],
        "listing_scope_complete": output["listing_scope_complete"],
        "records_count": len(records),
        "detail_limit": output["detail_limit"],
        "skip_details": output["skip_details"],
        "field_validation": output["field_validation"],
        "json_path": str(json_path),
        "csv_path": str(csv_path),
    },
        source_family="host_private",
        surface_class="host_private",
        auth_context=output["auth_context"],
        collection_status=output["collection_status"],
        last_good_guard_record=last_good_guard,
        warehouse_exports=warehouse_exports,
        capability_registry_ref=capability_registry_ref,
    )
    if auth_restore:
        receipt["auth_restore"] = auth_restore
    _integrity.write_receipt_json(receipt_path, receipt)
    print(json.dumps(receipt, indent=2, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
