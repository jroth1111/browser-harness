import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest


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


def test_load_records_accepts_top_level_and_wrapped_arrays(tmp_path):
    module = load_module()
    top_level = tmp_path / "restaurants.json"
    wrapped = tmp_path / "menus.json"
    top_level.write_text(json.dumps([{"store_id": "1"}]), encoding="utf-8")
    wrapped.write_text(json.dumps({"menu_items": [{"item_name": "Toast"}]}), encoding="utf-8")

    assert module.load_records(top_level, "restaurants") == [{"store_id": "1"}]
    assert module.load_records(wrapped, "menu_items") == [{"item_name": "Toast"}]


def test_load_records_rejects_invalid_shapes(tmp_path):
    module = load_module()
    scalar = tmp_path / "scalar.json"
    non_array_field = tmp_path / "non-array.json"
    non_object_row = tmp_path / "non-object-row.json"
    scalar.write_text(json.dumps("not records"), encoding="utf-8")
    non_array_field.write_text(json.dumps({"restaurants": {"store_id": "1"}}), encoding="utf-8")
    non_object_row.write_text(json.dumps({"restaurants": ["not a row"]}), encoding="utf-8")

    with pytest.raises(ValueError, match="input must be an array"):
        module.load_records(scalar, "restaurants")
    with pytest.raises(ValueError, match="must be an array"):
        module.load_records(non_array_field, "restaurants")
    with pytest.raises(ValueError, match="records must be objects"):
        module.load_records(non_object_row, "restaurants")


def test_main_preserves_same_named_menu_items_across_categories_and_prices(tmp_path, monkeypatch):
    module = load_module()
    restaurants = tmp_path / "restaurants.json"
    menus = tmp_path / "menus.json"
    output = tmp_path / "food_data"
    restaurants.write_text(json.dumps({
        "restaurants": [{
            "platform": "doordash",
            "store_id": "store-1",
            "name": "Example Cafe",
        }]
    }), encoding="utf-8")
    menus.write_text(json.dumps({
        "menu_items": [
            {
                "platform": "doordash",
                "store_id": "store-1",
                "item_name": "Coffee",
                "item_price": "$4.00",
                "category": "Drinks",
            },
            {
                "platform": "doordash",
                "store_id": "store-1",
                "item_name": "Coffee",
                "item_price": "$5.50",
                "category": "Breakfast",
            },
        ]
    }), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [
        "export.py",
        "--restaurants", str(restaurants),
        "--menus", str(menus),
        "--output", str(output),
    ])

    module.main()

    with (tmp_path / "food_data.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert [(row["category"], row["item_price"]) for row in rows] == [
        ("Drinks", "$4.00"),
        ("Breakfast", "$5.50"),
    ]
