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
