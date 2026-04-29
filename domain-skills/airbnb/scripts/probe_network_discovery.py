"""Network-sniffing discovery probe for Airbnb pages.

This probe is for discovery and regression evidence only. It records redacted
resource URLs, API operation names, and persisted-hash prefixes. It never fetches
or stores response payloads and is not a runtime collector path.
"""

from __future__ import annotations

import importlib.util
import json
import os
from datetime import datetime, timezone
from pathlib import Path


BASE = "https://www.airbnb.com.au"
OUTPUT_PATH = Path("domain-skills/airbnb/.private-data/network-discovery")
SESSION_PATH = Path("domain-skills/airbnb/.session-store/capability")


def _load_local_module(module_filename, module_name):
    path = Path("domain-skills/airbnb/scripts") / module_filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_surfaces = _load_local_module("surface_capabilities.py", "airbnb_surface_capabilities")
_integrity = _load_local_module("run_integrity.py", "airbnb_run_integrity")


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


DEFAULT_URLS = [
    BASE + "/s/Melbourne--Victoria--Australia/homes",
    BASE + "/hosting/listings",
    BASE + "/hosting/reviews",
]


def requested_urls():
    raw = os.environ.get("AIRBNB_NETWORK_DISCOVERY_URLS")
    if not raw:
        return DEFAULT_URLS
    return [part.strip() for part in raw.split(",") if part.strip()]


def collect_resource_urls():
    return _surfaces.page_api_resource_urls(js)


def main():
    observed_at = utc_now()
    run_id = os.environ.get("AIRBNB_NETWORK_DISCOVERY_RUN_ID") or "airbnb-network-discovery-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    wait_sec = float(os.environ.get("AIRBNB_NETWORK_DISCOVERY_WAIT_SEC", "2.0"))
    records = []
    for url in requested_urls():
        new_tab(url)
        wait_for_load()
        wait(wait_sec)
        status = page_content_status(text_limit=2000, html_limit=500)
        resource_urls = collect_resource_urls()
        records.append({
            "observed_at": observed_at,
            "source_url": _surfaces.redact_url(url),
            "page_title": status.get("title"),
            "text_length": len(status.get("text") or ""),
            "network_discovery": _surfaces.network_discovery_record(resource_urls),
        })

    output = _integrity.stamp_collection_contract({
        "run_id": run_id,
        "observed_at": observed_at,
        "source_family": "capability",
        "surface_class": "capability",
        "auth_context": "probe_browser_context",
        "collection_status": "complete",
        "record_count": len(records),
        "records": records,
        "usage": "discovery_probe_only_not_runtime_collector",
    },
        source_family="capability",
        surface_class="capability",
        auth_context="probe_browser_context",
        collection_status="complete",
    )
    OUTPUT_PATH.mkdir(parents=True, exist_ok=True)
    SESSION_PATH.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_PATH / f"{run_id}.json"
    receipt_path = SESSION_PATH / f"{run_id}-receipt.json"
    _integrity.write_collection_json(json_path, output)
    operation_names = sorted({
        operation
        for record in records
        for operation in (record.get("network_discovery", {}).get("api_operations") or {})
    })
    receipt = _integrity.stamp_collection_contract({
        "run_id": run_id,
        "observed_at": observed_at,
        "source_family": "capability",
        "surface_class": "capability",
        "auth_context": "probe_browser_context",
        "collection_status": "complete",
        "record_count": len(records),
        "api_operations": operation_names,
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
    main()
