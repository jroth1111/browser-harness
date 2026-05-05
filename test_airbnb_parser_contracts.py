import importlib.util
import json
from pathlib import Path


def load_module(filename, name):
    path = Path("agent-workspace/domain-skills/airbnb/scripts") / filename
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parser_contract_fixtures_cover_required_families():
    base = Path("agent-workspace/domain-skills/airbnb/fixtures/parser-contracts")

    assert (base / "public-search" / "valid.json").exists()
    assert (base / "listing-inventory" / "valid.json").exists()
    assert (base / "calendar-export" / "valid.ics").exists()
    assert (base / "exports" / "earnings.csv").exists()
    assert (base / "exports" / "reservation-detail.txt").exists()
    assert (base / "insights" / "valid.json").exists()
    assert (base / "warehouse" / "valid-manifest.json").exists()


def test_parser_contract_fixtures_validate_against_contract_helpers():
    integrity = load_module("run_integrity.py", "airbnb_run_integrity")
    planner = load_module("public_scan_planner.py", "airbnb_public_scan_planner")
    calendar = load_module("collect_calendar_export.py", "airbnb_collect_calendar_export")
    exports = load_module("collect_exports.py", "airbnb_collect_exports")
    base = Path("agent-workspace/domain-skills/airbnb/fixtures/parser-contracts")

    listing_payload = json.loads((base / "listing-inventory" / "valid.json").read_text())
    insights_payload = json.loads((base / "insights" / "valid.json").read_text())
    warehouse_payload = json.loads((base / "warehouse" / "valid-manifest.json").read_text())
    public_payload = json.loads((base / "public-search" / "valid.json").read_text())

    assert integrity.validate_collection_output(listing_payload) is True
    assert integrity.validate_collection_output(insights_payload) is True
    assert integrity.validate_warehouse_manifest(warehouse_payload["warehouse_exports"]) is True
    assert planner.build_partition_manifest(
        public_payload["search_runs"],
        public_payload["search_results"],
        trigger_threshold=12,
        max_depth=2,
    )["deduped_listing_ids"] == ["200", "300"]

    events, snapshots = calendar.build_collection(
        (base / "calendar-export" / "valid.ics").read_text(),
        listing_id="100",
        observed_at="2026-04-29T00:00:00Z",
        source="fixture.ics",
    )
    assert len(events) == 1
    assert len(snapshots) == 3
    assert exports.parse_earnings_csv(
        (base / "exports" / "earnings.csv").read_text(),
        observed_at="2026-04-29T00:00:00Z",
    )[0]["payout_amount"] == 873.0
