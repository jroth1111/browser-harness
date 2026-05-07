"""Probe Airbnb source-family capabilities without collecting private payloads.

This runner records which API/resource families and persisted-operation hashes
are reachable for Airbnb surfaces. It is intentionally a capability probe, not
a data collector for money, reservations, payouts, pricing rules, or calendars.
"""

from __future__ import annotations

import importlib.util
import json
import os
from datetime import datetime, timezone
from pathlib import Path


BASE = "https://www.airbnb.com.au"
OUTPUT_PATH = Path("domain-skills/airbnb/.private-data/capability-probes")
SESSION_PATH = Path("domain-skills/airbnb/.session-store/capability")
LISTINGS_PATH = Path("domain-skills/airbnb/.private-data/listing-collections")
CAPABILITY_REGISTRY_PATH = SESSION_PATH / "capability-registry.json"


def _load_local_module(module_filename, module_name):
    path = Path("domain-skills/airbnb/scripts") / module_filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_surfaces = _load_local_module("surface_capabilities.py", "airbnb_surface_capabilities")
_operation_hashes = _load_local_module("operation_hashes.py", "airbnb_operation_hashes")
_integrity = _load_local_module("run_integrity.py", "airbnb_run_integrity")


SURFACE_URLS = {
    "public_comp_search": BASE + "/s/Melbourne--Victoria--Australia/homes",
    "own_public_audit": BASE + "/rooms/{listing_id}",
    "host_listing_inventory": BASE + "/hosting/listings",
    "host_reviews": BASE + "/performance/quality/overall/listing/{listing_id}",
    "calendar_availability": BASE + "/calendar-router",
    "calendar_export": BASE + "/help/article/99",
    "pricing_rules": BASE + "/calendar-router",
    "earnings_reservations_payouts": BASE + "/users/transaction_history",
    "market_research_scan": BASE + "/s/Melbourne--Victoria--Australia/homes",
    "regression_probes": BASE + "/",
}


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def latest_listing_id():
    explicit = os.environ.get("AIRBNB_SURFACE_PROBE_LISTING_ID")
    if explicit:
        return explicit
    files = sorted(LISTINGS_PATH.glob("airbnb-live-listings-*.json"))
    for path in reversed(files):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        records = payload.get("records") or []
        if records:
            return str(records[0].get("listing_id"))
    return os.environ.get("AIRBNB_LISTING_ID", "0")


def surface_url(surface_id, listing_id):
    template = os.environ.get(f"AIRBNB_SURFACE_{surface_id.upper()}_URL") or SURFACE_URLS[surface_id]
    return template.format(listing_id=listing_id)


def discover_hashes_for_page(surface_id):
    spec = _surfaces.get_surface_spec(surface_id)
    operations = tuple(spec.get("operations") or ())
    if not operations:
        return {"hashes": {}, "sources": {}, "visited_count": 0, "remaining_queue_count": 0}
    context = js(
        """(() => ({
          html: document.documentElement.outerHTML,
          scripts: Array.from(document.scripts).map(script => script.src).filter(Boolean),
          resources: performance.getEntriesByType('resource').map(entry => entry.name)
        }))()"""
    ) or {}
    seed_texts = [context.get("html") or ""]
    seed_urls = [
        url for url in [*(context.get("scripts") or []), *(context.get("resources") or [])]
        if isinstance(url, str) and "/airbnb/static/packages/web/" in url and url.endswith(".js")
    ]

    def fetcher(url):
        return http_get(url)

    return _operation_hashes.discover_operation_hashes(
        fetcher,
        operations,
        seed_texts=seed_texts,
        seed_urls=seed_urls,
        max_fetches=int(os.environ.get("AIRBNB_SURFACE_HASH_DISCOVERY_MAX_FETCHES", "60")),
    )


def main():
    observed_at = utc_now()
    run_id = os.environ.get("AIRBNB_SURFACE_PROBE_RUN_ID") or "airbnb-surface-probe-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    listing_id = latest_listing_id()
    requested = os.environ.get("AIRBNB_SURFACE_IDS")
    surface_ids = [part.strip() for part in requested.split(",") if part.strip()] if requested else list(_surfaces.surface_ids())
    OUTPUT_PATH.mkdir(parents=True, exist_ok=True)
    SESSION_PATH.mkdir(parents=True, exist_ok=True)

    records = []
    registry_entries = _surfaces.load_capability_registry(CAPABILITY_REGISTRY_PATH)
    for surface_id in surface_ids:
        url = surface_url(surface_id, listing_id)
        new_tab(url)
        wait_for_load()
        wait(float(os.environ.get("AIRBNB_SURFACE_PROBE_WAIT_SEC", "2.0")))
        status = page_content_status(text_limit=4000, html_limit=1000)
        resource_urls = _surfaces.page_api_resource_urls(js)
        discovery = discover_hashes_for_page(surface_id)
        network_discovery = _surfaces.network_discovery_record(resource_urls)
        record = _surfaces.capability_record(
            surface_id,
            observed_at=observed_at,
            auth_context="probe_browser_context",
            source_url=url,
            resource_urls=resource_urls,
            operation_hashes=discovery.get("hashes"),
            operation_hash_sources=discovery.get("sources"),
            evidence={
                "page_title": status.get("title"),
                "text_length": len(status.get("text") or ""),
                "hash_discovery": discovery,
                "network_discovery": network_discovery,
            },
        )
        refs = []
        for operation, hash_value in (discovery.get("hashes") or {}).items():
            entry = _surfaces.capability_registry_entry(
                surface_id,
                observed_at=observed_at,
                endpoint_url=url,
                operation_name=operation,
                operation_hash=hash_value,
                provenance={"source": (discovery.get("sources") or {}).get(operation)},
            )
            registry_entries = _surfaces.upsert_capability_registry(registry_entries, entry)
            refs.append(_surfaces.registry_ref(entry))
        if refs:
            record["capability_registry_refs"] = refs
        records.append(record)

    registry_payload = _surfaces.save_capability_registry(CAPABILITY_REGISTRY_PATH, registry_entries)

    output = _integrity.stamp_collection_contract({
        "run_id": run_id,
        "observed_at": observed_at,
        "source_family": "capability",
        "surface_class": "capability",
        "auth_context": "probe_browser_context",
        "collection_status": "complete",
        "listing_id_probe": listing_id,
        "surface_count": len(records),
        "records": records,
        "capability_registry_path": str(CAPABILITY_REGISTRY_PATH),
        "capability_registry_entry_count": len(registry_payload["entries"]),
        "staleness_plan": _surfaces.build_staleness_plan(surface_ids_to_check=surface_ids),
    },
        source_family="capability",
        surface_class="capability",
        auth_context="probe_browser_context",
        collection_status="complete",
    )
    json_path = OUTPUT_PATH / f"{run_id}.json"
    receipt_path = SESSION_PATH / f"{run_id}-receipt.json"
    _integrity.write_collection_json(json_path, output)
    receipt = _integrity.stamp_collection_contract({
        "run_id": run_id,
        "observed_at": observed_at,
        "source_family": "capability",
        "surface_class": "capability",
        "auth_context": "probe_browser_context",
        "collection_status": "complete",
        "surface_count": len(records),
        "surfaces_observed": [row["surface_id"] for row in records if row["status"] == "capability_observed"],
        "surfaces_not_observed": [row["surface_id"] for row in records if row["status"] != "capability_observed"],
        "capability_registry_path": str(CAPABILITY_REGISTRY_PATH),
        "capability_registry_entry_count": len(registry_payload["entries"]),
        "json_path": str(json_path),
    },
        source_family="capability",
        surface_class="capability",
        auth_context="probe_browser_context",
        collection_status="complete",
    )
    _integrity.write_receipt_json(receipt_path, receipt)
    print(json.dumps(receipt, indent=2, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    import sys
    if any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
        print((__doc__ or "").strip())
        raise SystemExit(0)
    main()
