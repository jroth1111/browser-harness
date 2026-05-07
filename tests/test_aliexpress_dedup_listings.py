import csv
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "domain-skills" / "aliexpress" / "scripts" / "dedup_listings.py"


def run_dedup(existing_csv, input_rows, *args):
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), str(existing_csv), "--format", "csv", *args],
        input=json.dumps(input_rows),
        text=True,
        capture_output=True,
        check=True,
    )
    return proc.stdout


def write_existing(path, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["product_id", "title", "price"])
        writer.writeheader()
        writer.writerows(rows)


def test_csv_output_preserves_header_when_all_rows_are_duplicates(tmp_path):
    existing = tmp_path / "existing.csv"
    write_existing(existing, [{"product_id": "123", "title": "Old", "price": "AU$1"}])
    input_rows = [{"product_id": "123", "title": "New title", "price": "AU$2"}]

    output = run_dedup(existing, input_rows)

    assert output.splitlines() == ["product_id,title,price"]


def test_csv_output_preserves_input_field_order_for_rows(tmp_path):
    existing = tmp_path / "existing.csv"
    write_existing(existing, [])
    input_rows = [{"title": "Mini PC", "product_id": "456", "price": "AU$400"}]

    output = run_dedup(existing, input_rows)

    reader = csv.DictReader(output.splitlines())
    assert reader.fieldnames == ["title", "product_id", "price"]
    assert list(reader) == [{"title": "Mini PC", "product_id": "456", "price": "AU$400"}]


def test_json_input_rejects_non_object_array_items(tmp_path):
    existing = tmp_path / "existing.csv"
    write_existing(existing, [])

    proc = subprocess.run(
        [sys.executable, str(SCRIPT), str(existing)],
        input=json.dumps(["not a listing"]),
        text=True,
        capture_output=True,
    )

    assert proc.returncode != 0
    assert "array of objects" in proc.stderr
