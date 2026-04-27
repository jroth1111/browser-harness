"""Collect authenticated Airbnb host live-listing inventory.

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

import login_session


BASE = "https://www.airbnb.com.au"
HOST_LISTINGS_URL = BASE + "/hosting/listings"
OUTPUT_PATH = Path("domain-skills/airbnb/.private-data/listing-collections")
SESSION_PATH = Path("domain-skills/airbnb/.session-store/capability")

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


def discover_query_hash():
    env_hash = os.environ.get("AIRBNB_LISTINGS_QUERY_HASH")
    if env_hash:
        return {"hash": env_hash, "source": "AIRBNB_LISTINGS_QUERY_HASH"}
    found = js(r"""(() => {
  const haystacks = [];
  for (const script of Array.from(document.scripts || [])) {
    if (script.src) haystacks.push(script.src);
    const text = script.textContent || "";
    if (text.includes("BeehiveGetListingsQuery")) haystacks.push(text);
  }
  for (const entry of performance.getEntriesByType("resource") || []) {
    if (entry.name) haystacks.push(entry.name);
  }
  const joined = haystacks.join("\n");
  const nearby = joined.match(/BeehiveGetListingsQuery[\s\S]{0,500}?([a-f0-9]{64})/i);
  return nearby ? nearby[1] : null;
})()""")
    if found:
        return {"hash": found, "source": "page_discovery"}
    return {"hash": OBSERVED_QUERY_HASH, "source": "observed_2026_04_27_fallback"}


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
    hash_info = discover_query_hash()

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
    active_records = [record for record in overview_records if (record.get("status") or "").upper() == "ACTIVE"]
    if detail_limit:
        active_records = active_records[: int(detail_limit)]

    records = []
    failures = []
    for index, record in enumerate(active_records, start=1):
        if skip_details:
            enriched = {**record, "detail_field_ok": all(record.get(field) not in (None, "", []) for field in REQUIRED_FIELDS)}
        else:
            print(json.dumps({"phase": "detail", "progress": index, "total": len(active_records), "listing_id": record["listing_id"]}), flush=True)
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
    output = {
        "run_id": run_id,
        "observed_at": observed_at,
        "partial_run": bool(detail_limit or skip_details),
        "auth_context": (
            "restored_private_host_session_in_fresh_agent_chrome_profile"
            if auth_restore else "caller_provided_authenticated_browser_context"
        ),
        "source": {
            "overview": f"{OPERATION_NAME} /api/v3 persisted query",
            "overview_hash": hash_info["hash"],
            "overview_hash_source": hash_info["source"],
            "detail": "authenticated listing editor page text",
        },
        "overview_pages": pages,
        "total_listings_seen": len(overview_records),
        "status_counts": dict(status_counts),
        "active_count": len(records),
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
    }
    json_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    write_csv(csv_path, records)

    receipt = {
        "run_id": run_id,
        "observed_at": observed_at,
        "auth_context": output["auth_context"],
        "partial_run": output["partial_run"],
        "source": output["source"],
        "overview_pages": pages,
        "total_listings_seen": len(overview_records),
        "status_counts": dict(status_counts),
        "active_count": len(records),
        "records_count": len(records),
        "detail_limit": output["detail_limit"],
        "skip_details": output["skip_details"],
        "field_validation": output["field_validation"],
        "json_path": str(json_path),
        "csv_path": str(csv_path),
    }
    if auth_restore:
        receipt["auth_restore"] = auth_restore
    receipt_path.write_text(json.dumps(receipt, indent=2, ensure_ascii=False))
    print(json.dumps(receipt, indent=2, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
