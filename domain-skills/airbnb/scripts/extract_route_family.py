"""Extract a single Insights route family from a run snapshot."""

from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path


def _load_local_module(module_filename, module_name):
    path = Path("agent-workspace/domain-skills/airbnb/scripts") / module_filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_integrity = _load_local_module("run_integrity.py", "airbnb_run_integrity")


def _write_csv(path, rows):
    path = Path(path)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys = []
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def extract_family(snapshot_json_path, family, *, allow_partial=False, allow_quarantined=False):
    source_path = Path(snapshot_json_path)
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    _integrity.assert_usable_collection(
        payload,
        expected_source_family="host_private" if payload.get("source_family") else None,
        allow_partial=allow_partial,
        allow_quarantined=allow_quarantined,
    )
    summary_rows = [row for row in payload.get("summary_rows", []) if row.get("route_family") == family]
    daily_rows = [row for row in payload.get("daily_rows", []) if row.get("route_family") == family]

    out_json = source_path.with_name(source_path.stem + f"-{family}-only.json")
    out_summary_csv = source_path.with_name(source_path.stem + f"-{family}-only-summary.csv")
    out_daily_csv = source_path.with_name(source_path.stem + f"-{family}-only-daily.csv")
    warehouse_exports = _integrity.warehouse_manifest([
        {
            "table": "airbnb_insights_metric_snapshot",
            "path": str(out_summary_csv),
            "row_count": len(summary_rows),
            "grain": "listing_id + route_subroute + period_label + observed_at",
            "source_family": payload.get("source_family") or "host_private",
            "surface_class": payload.get("surface_class") or "host_private",
            "auth_context": payload.get("auth_context") or "derived_from_host_private_snapshot",
        },
        {
            "table": "airbnb_insights_chart_point",
            "path": str(out_daily_csv),
            "row_count": len(daily_rows),
            "grain": "listing_id + route_subroute + series_index + ds",
            "source_family": payload.get("source_family") or "host_private",
            "surface_class": payload.get("surface_class") or "host_private",
            "auth_context": payload.get("auth_context") or "derived_from_host_private_snapshot",
        },
    ])
    out_payload = _integrity.stamp_collection_contract({
        "run_id": f"{payload.get('run_id')}-{family}-only",
        "source_run_id": payload.get("run_id"),
        "observed_at": payload.get("observed_at"),
        "listing_count": payload.get("listing_count"),
        "route_family": family,
        "summary_rows_count": len(summary_rows),
        "daily_rows_count": len(daily_rows),
        "routes_present": sorted({row.get("route_subroute") for row in summary_rows}),
        "summary_rows": summary_rows,
        "daily_rows": daily_rows,
    },
        source_family=payload.get("source_family") or "host_private",
        surface_class=payload.get("surface_class") or "host_private",
        auth_context=payload.get("auth_context") or "derived_from_host_private_snapshot",
        collection_status=payload.get("collection_status") or "complete",
        last_good_guard_record=payload.get("last_good_guard"),
        warehouse_exports=warehouse_exports,
    )
    _integrity.write_collection_json(out_json, out_payload)
    _write_csv(out_summary_csv, summary_rows)
    _write_csv(out_daily_csv, daily_rows)
    return {
        "json_path": str(out_json),
        "summary_csv_path": str(out_summary_csv),
        "daily_csv_path": str(out_daily_csv),
    }


if __name__ == "__main__":
    import sys

    allow_partial = "--allow-partial" in sys.argv
    allow_quarantined = "--allow-quarantined" in sys.argv
    positional = [arg for arg in sys.argv[1:] if arg not in {"--allow-partial", "--allow-quarantined"}]
    if len(positional) != 2:
        raise SystemExit("Usage: python extract_route_family.py <snapshot_json_path> <family> [--allow-partial] [--allow-quarantined]")
    result = extract_family(positional[0], positional[1], allow_partial=allow_partial, allow_quarantined=allow_quarantined)
    print(json.dumps(result, indent=2))
