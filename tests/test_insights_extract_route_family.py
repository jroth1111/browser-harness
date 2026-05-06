import csv
import importlib.util
import json
from pathlib import Path

from browser_harness.data_display import render_dataset


def load_module(path, name):
    path = Path(path)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_extract_route_family_round_trip_and_render(tmp_path):
    module = load_module("domain-skills/airbnb/scripts/extract_route_family.py", "airbnb_extract_route_family")
    source = tmp_path / "run.json"
    payload = {
        "run_id": "run-1",
        "observed_at": "2026-04-28T00:00:00Z",
        "listing_count": 1,
        "summary_rows": [
            {"route_family": "conversion", "route_subroute": "p3_impressions", "value": 5},
            {"route_family": "quality", "route_subroute": "overall", "value": 0.0},
        ],
        "daily_rows": [
            {"route_family": "conversion", "route_subroute": "p3_impressions", "ds": "2026-04-20", "value": 2},
            {"route_family": "quality", "route_subroute": "overall", "ds": "2026-04-20", "value": 0.0},
        ],
    }
    source.write_text(json.dumps(payload), encoding="utf-8")

    out = module.extract_family(source, "conversion")
    out_json = json.loads(Path(out["json_path"]).read_text(encoding="utf-8"))
    assert out_json["route_family"] == "conversion"
    assert out_json["summary_rows_count"] == 1
    assert out_json["daily_rows_count"] == 1
    assert out_json["routes_present"] == ["p3_impressions"]

    with Path(out["summary_csv_path"]).open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1
    assert rows[0]["route_family"] == "conversion"

    html_path = Path(render_dataset(out["summary_csv_path"]))
    html = html_path.read_text(encoding="utf-8")
    assert 'id="payload-json"' in html


def test_extract_route_family_rejects_quarantined_snapshot_without_override(tmp_path):
    module = load_module("domain-skills/airbnb/scripts/extract_route_family.py", "airbnb_extract_route_family")
    source = tmp_path / "run.json"
    payload = {
        "run_id": "run-1",
        "observed_at": "2026-04-28T00:00:00Z",
        "collection_status": "quarantined_empty_after_prior_nonempty",
        "source_family": "host_private",
        "surface_class": "host_private",
        "auth_context": "fixture",
        "last_good_guard": {"checked": True, "status": "quarantined_empty_after_prior_nonempty"},
        "warehouse_exports": [],
        "listing_count": 1,
        "summary_rows": [{"route_family": "conversion", "route_subroute": "p3_impressions", "value": 5}],
        "daily_rows": [{"route_family": "conversion", "route_subroute": "p3_impressions", "ds": "2026-04-20", "value": 2}],
    }
    source.write_text(json.dumps(payload), encoding="utf-8")

    try:
        module.extract_family(source, "conversion")
    except ValueError as error:
        assert "allow_quarantined" in str(error)
    else:
        raise AssertionError("quarantined snapshot should require explicit override")

    out = module.extract_family(source, "conversion", allow_quarantined=True)
    assert Path(out["json_path"]).exists()
