import csv
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "domain-skills" / "food-delivery" / "scripts" / "export.py"


def load_module():
    spec = importlib.util.spec_from_file_location("food_delivery_export", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_export_csv_creates_header_only_file_for_empty_menus(tmp_path):
    module = load_module()
    output = tmp_path / "food_data"

    rows = module.export_csv([], [], output)

    assert rows == []
    with (tmp_path / "food_data.csv").open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        assert list(reader) == [module.CSV_FIELDNAMES]


def test_export_csv_uses_stable_header_for_joined_rows(tmp_path):
    module = load_module()
    output = tmp_path / "food_data"
    restaurants = [
        {
            "platform": "doordash",
            "store_id": "store-1",
            "name": "Example Cafe",
            "url": "https://example.test/store-1",
            "rating": "4.8",
            "delivery_fee": "$2.99",
            "delivery_time_min": 15,
            "delivery_time_max": 25,
            "promo_badge": "Free item",
        }
    ]
    menus = [
        {
            "platform": "doordash",
            "store_id": "store-1",
            "item_name": "Toast",
            "item_price": "$8.00",
            "category": "Breakfast",
        }
    ]

    rows = module.export_csv(restaurants, menus, output)

    assert rows[0]["store_name"] == "Example Cafe"
    with (tmp_path / "food_data.csv").open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == module.CSV_FIELDNAMES
        exported_rows = list(reader)
    assert exported_rows[0]["store_url"] == "https://example.test/store-1"
    assert exported_rows[0]["item_name"] == "Toast"
