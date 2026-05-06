#!/usr/bin/env python3
"""Generate a stable summary report from the YouTube surface map and receipts."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def latest_live_receipt(receipts_dir: Path) -> Path | None:
    receipts = sorted(receipts_dir.glob("live-smoke-*.json"))
    return receipts[-1] if receipts else None


def build_summary(root: Path = ROOT) -> dict:
    surface_map = load_json(root / "surface-map.json")
    receipt_path = latest_live_receipt(root / "receipts")
    receipt = load_json(receipt_path) if receipt_path else {}
    primitive_checks = receipt.get("primitive_checks", [])
    status_counts = Counter(check.get("status", "unknown") for check in primitive_checks)
    blocked_surfaces = [
        {
            "primitive_id": check.get("primitive_id"),
            "status": check.get("status"),
            "terminal_reason": check.get("terminal_reason"),
        }
        for check in primitive_checks
        if check.get("status") in {"fail", "not_run"}
    ]
    conditional_surfaces = [
        {
            "primitive_id": check.get("primitive_id"),
            "status": check.get("status"),
            "terminal_reason": check.get("terminal_reason"),
        }
        for check in primitive_checks
        if check.get("status") == "conditional"
    ]
    availability = surface_map.get("availability", {})
    availability_notes = {
        **availability.get("primitives", {}),
        **availability.get("fallback_nodes", {}),
    }
    drift_notes = [
        {
            "id": item_id,
            "status": note.get("status"),
            "reason": note.get("conditional_reason"),
            "last_live_observation": note.get("last_live_observation"),
        }
        for item_id, note in sorted(availability_notes.items())
        if note.get("status") in {"conditional", "degraded", "terminal_probe"}
    ]
    return {
        "report_version": 1,
        "generated_at": receipt.get("created_at") or surface_map.get("field_tested", {}).get("date"),
        "domain": surface_map["domain"],
        "surface_map": {
            "schema_version": surface_map["schema_version"],
            "primitive_count": len(surface_map["primitives"]),
            "availability_default": availability.get("default", "happy_path"),
        },
        "latest_live_receipt": str(receipt_path.relative_to(root)) if receipt_path else None,
        "live_status_counts": dict(sorted(status_counts.items())),
        "live_primitive_count": len(primitive_checks),
        "blocked_surfaces": blocked_surfaces,
        "conditional_surfaces": conditional_surfaces,
        "drift_notes": drift_notes,
    }


def main() -> int:
    report = build_summary()
    out_dir = ROOT / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "latest-summary.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
