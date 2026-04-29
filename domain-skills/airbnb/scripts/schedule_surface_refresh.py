"""Build a staleness-prioritized Airbnb surface refresh plan.

This is a local scheduler: it reads compact capability receipts and probe
outputs, then writes a JSON task plan. It does not contact Airbnb.
"""

from __future__ import annotations

import importlib.util
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path


SESSION_PATH = Path("domain-skills/airbnb/.session-store/capability")
CAPABILITY_PROBE_PATH = Path("domain-skills/airbnb/.private-data/capability-probes")
OUTPUT_PATH = Path("domain-skills/airbnb/.private-data/schedules")


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


def capability_records_from_payload(payload):
    records = []
    if not isinstance(payload, dict):
        return records
    for key in ("records", "surface_capabilities"):
        value = payload.get(key)
        if isinstance(value, list):
            records.extend(row for row in value if isinstance(row, dict) and row.get("surface_id"))
    source = payload.get("source")
    if isinstance(source, dict) and isinstance(source.get("surface_capabilities"), list):
        records.extend(
            row for row in source["surface_capabilities"]
            if isinstance(row, dict) and row.get("surface_id")
        )
    return records


def read_capability_records(paths):
    records = []
    for path in paths:
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        records.extend(capability_records_from_payload(payload))
    return records


def latest_observed_by_surface(records, observed_statuses=("capability_observed",)):
    latest = {}
    for record in records or []:
        surface_id = record.get("surface_id")
        observed_at = record.get("observed_at")
        if not surface_id or not observed_at:
            continue
        if observed_statuses and record.get("status") not in observed_statuses:
            continue
        if surface_id not in latest or str(observed_at) > str(latest[surface_id]):
            latest[surface_id] = observed_at
    return latest


def default_input_paths():
    paths = []
    paths.extend(sorted(SESSION_PATH.glob("*receipt.json")))
    paths.extend(sorted(CAPABILITY_PROBE_PATH.glob("*.json")))
    return paths


def build_schedule(paths=None, today=None, surface_ids=None, include_fresh=False):
    paths = paths if paths is not None else default_input_paths()
    records = read_capability_records(paths)
    latest = latest_observed_by_surface(records)
    ids = surface_ids or _surfaces.surface_ids()
    plan = _surfaces.build_staleness_plan(latest, today=today, surface_ids_to_check=ids)
    tasks = _surfaces.build_refresh_tasks(latest, today=today, surface_ids_to_check=ids, include_fresh=include_fresh)
    return {
        "observed_record_count": len(records),
        "last_observed_by_surface": latest,
        "staleness_plan": plan,
        "refresh_tasks": tasks,
        "stale_task_count": len([task for task in tasks if task.get("stale")]),
    }


def main():
    observed_at = utc_now()
    run_id = os.environ.get("AIRBNB_SURFACE_SCHEDULE_RUN_ID") or "airbnb-surface-schedule-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    requested = os.environ.get("AIRBNB_SURFACE_IDS")
    surface_ids = [part.strip() for part in requested.split(",") if part.strip()] if requested else None
    include_fresh = os.environ.get("AIRBNB_SURFACE_SCHEDULE_INCLUDE_FRESH") == "1"
    today = date.fromisoformat(os.environ["AIRBNB_SURFACE_SCHEDULE_TODAY"]) if os.environ.get("AIRBNB_SURFACE_SCHEDULE_TODAY") else None

    schedule = build_schedule(today=today, surface_ids=surface_ids, include_fresh=include_fresh)
    output = _integrity.stamp_collection_contract({
        "run_id": run_id,
        "observed_at": observed_at,
        "source_family": "scheduler",
        "surface_class": "scheduler",
        "auth_context": "local_receipt_reader",
        "collection_status": "complete",
        **schedule,
    },
        source_family="scheduler",
        surface_class="scheduler",
        auth_context="local_receipt_reader",
        collection_status="complete",
    )
    OUTPUT_PATH.mkdir(parents=True, exist_ok=True)
    SESSION_PATH.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_PATH / f"{run_id}.json"
    receipt_path = SESSION_PATH / f"{run_id}-receipt.json"
    _integrity.write_collection_json(json_path, output)
    receipt = _integrity.stamp_collection_contract({
        "run_id": run_id,
        "observed_at": observed_at,
        "source_family": "scheduler",
        "surface_class": "scheduler",
        "auth_context": "local_receipt_reader",
        "collection_status": "complete",
        "stale_task_count": output["stale_task_count"],
        "refresh_task_count": len(output["refresh_tasks"]),
        "json_path": str(json_path),
    },
        source_family="scheduler",
        surface_class="scheduler",
        auth_context="local_receipt_reader",
        collection_status="complete",
    )
    _integrity.write_receipt_json(receipt_path, receipt)
    print(json.dumps(receipt, indent=2, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
