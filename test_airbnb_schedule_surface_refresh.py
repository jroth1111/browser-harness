import importlib.util
import json
from datetime import date
from pathlib import Path


def load_module():
    path = Path("agent-workspace/domain-skills/airbnb/scripts/schedule_surface_refresh.py")
    spec = importlib.util.spec_from_file_location("airbnb_schedule_surface_refresh", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_capability_records_from_payload_reads_probe_and_receipt_shapes():
    module = load_module()

    records = module.capability_records_from_payload({
        "records": [{"surface_id": "public_comp_search", "observed_at": "2026-04-20T00:00:00Z"}],
        "source": {
            "surface_capabilities": [
                {"surface_id": "host_reviews", "observed_at": "2026-04-21T00:00:00Z"}
            ]
        },
    })

    assert [record["surface_id"] for record in records] == ["public_comp_search", "host_reviews"]


def test_build_schedule_reads_receipts_and_emits_stale_tasks(tmp_path):
    module = load_module()
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps({
        "source": {
            "surface_capabilities": [
                {
                    "surface_id": "public_comp_search",
                    "observed_at": "2026-04-20T00:00:00Z",
                    "status": "capability_observed",
                }
            ]
        }
    }), encoding="utf-8")

    schedule = module.build_schedule(
        paths=[receipt],
        today=date(2026, 4, 28),
        surface_ids=["public_comp_search", "own_public_audit"],
    )

    assert schedule["last_observed_by_surface"] == {"public_comp_search": "2026-04-20T00:00:00Z"}
    assert [task["surface_id"] for task in schedule["refresh_tasks"]] == [
        "public_comp_search",
        "own_public_audit",
    ]
    assert schedule["stale_task_count"] == 2
