import csv
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_script(name, relative_path):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_listing_csv_writer_creates_header_for_zero_rows(tmp_path):
    module = load_script("airbnb_collect_listings_csv", "domain-skills/airbnb/scripts/collect_listings.py")
    output = tmp_path / "nested" / "listings.csv"

    module.write_csv(output, [])

    with output.open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows
    assert rows[0][:4] == ["listing_id", "listing_name", "nickname", "status"]


def test_dynamic_airbnb_csv_writers_create_empty_zero_row_artifact(tmp_path):
    modules = [
        ("airbnb_collect_insights_csv", "domain-skills/airbnb/scripts/collect_insights.py"),
        ("airbnb_collect_host_reviews_csv", "domain-skills/airbnb/scripts/collect_host_reviews.py"),
        ("airbnb_collect_competitors_csv", "domain-skills/airbnb/scripts/collect_competitors.py"),
        ("airbnb_collect_own_public_csv", "domain-skills/airbnb/scripts/collect_own_public.py"),
    ]

    for name, relative_path in modules:
        module = load_script(name, relative_path)
        output = tmp_path / name / "rows.csv"

        module.write_csv(output, [])

        assert output.exists()
        assert output.read_text(encoding="utf-8") == ""
