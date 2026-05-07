import csv
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "domain-skills" / "g2g" / "scripts" / "search.py"


def test_seller_command_writes_header_only_output_for_empty_input(tmp_path):
    input_csv = tmp_path / "results.csv"
    output_csv = tmp_path / "seller-results.csv"
    fieldnames = ["seller_user_id", "seller_name", "product_title"]
    with input_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "seller", str(input_csv), "--output", str(output_csv)],
        text=True,
        capture_output=True,
        check=True,
    )

    assert "Wrote empty seller output" in proc.stderr
    with output_csv.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        assert list(reader) == [fieldnames]


def test_coverage_command_writes_zero_count_report_for_empty_input(tmp_path):
    input_csv = tmp_path / "results.csv"
    fieldnames = ["search_query", "target_keywords", "discovery_path", "coverage_notes"]
    with input_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

    subprocess.run(
        [sys.executable, str(SCRIPT), "coverage", str(input_csv)],
        text=True,
        capture_output=True,
        check=True,
    )

    report = json.loads((tmp_path / "results-coverage.json").read_text(encoding="utf-8"))
    assert report["summary"] == {
        "categories_discovered": 0,
        "categories_inspected": 0,
        "offers_collected": 0,
        "offers_deduplicated": 0,
        "target_keyword_matches": 0,
    }
    assert report["by_category"] == {}


def test_api_get_preserves_empty_payload_values(monkeypatch):
    module = load_g2g_module()
    responses = iter([
        json.dumps({"code": 2000, "payload": []}),
        json.dumps({"code": 2000, "payload": {}}),
        json.dumps({"code": 2000, "data": []}),
        json.dumps({"code": 2000, "message": "ok"}),
    ])
    monkeypatch.setattr(module, "http_get", lambda url, timeout=20.0: next(responses))
    client = module.G2GClient()

    assert client._api_get("/empty-list") == []
    assert client._api_get("/empty-dict") == {}
    assert client._api_get("/empty-data") == []
    assert client._api_get("/envelope") == {"code": 2000, "message": "ok"}


def test_search_categories_returns_empty_for_malformed_index_shape(monkeypatch):
    module = load_g2g_module()
    monkeypatch.setattr(module, "http_get", lambda url, timeout=30.0: json.dumps(["not", "an", "object"]))

    assert module.G2GClient().search_categories("gold") == []


def test_search_offers_falls_back_when_total_metadata_is_malformed(monkeypatch):
    module = load_g2g_module()
    monkeypatch.setattr(module.G2GClient, "_api_get", lambda self, path, params=None: {
        "offers": [{"id": "offer-1"}, {"id": "offer-2"}],
        "meta": {"total": "not-a-count"},
    })

    offers, total = module.G2GClient().search_offers("gold")

    assert [offer["id"] for offer in offers] == ["offer-1", "offer-2"]
    assert total == 2


def load_g2g_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("g2g_search_api", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module
