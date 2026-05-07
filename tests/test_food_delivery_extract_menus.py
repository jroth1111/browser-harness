import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "domain-skills" / "food-delivery" / "scripts" / "extract_menus.py"


def load_module():
    spec = importlib.util.spec_from_file_location("food_delivery_extract_menus", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    scripts_dir = str(MODULE_PATH.parent)
    old_path = list(sys.path)
    old_lib = sys.modules.pop("lib", None)
    old_lib_children = {
        name: sys.modules.pop(name)
        for name in list(sys.modules)
        if name.startswith("lib.")
    }
    try:
        sys.path.insert(0, scripts_dir)
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = old_path
        for name in list(sys.modules):
            if name.startswith("lib."):
                sys.modules.pop(name)
        if old_lib is not None:
            sys.modules["lib"] = old_lib
        sys.modules.update(old_lib_children)
    return module


def test_load_restaurant_input_accepts_top_level_list(tmp_path):
    module = load_module()
    source = tmp_path / "restaurants.json"
    rows = [{"store_id": "1", "url": "https://example.test/store/1"}]
    source.write_text(json.dumps(rows), encoding="utf-8")

    restaurants, platform = module.load_restaurant_input(source)

    assert restaurants == rows
    assert platform == "doordash"


def test_load_restaurant_input_accepts_wrapped_restaurants(tmp_path):
    module = load_module()
    source = tmp_path / "restaurants.json"
    rows = [{"store_id": "1", "url": "https://example.test/store/1"}]
    source.write_text(json.dumps({"platform": "ubereats", "restaurants": rows}), encoding="utf-8")

    restaurants, platform = module.load_restaurant_input(source)

    assert restaurants == rows
    assert platform == "ubereats"


def test_load_restaurant_input_rejects_non_array_restaurants(tmp_path):
    module = load_module()
    source = tmp_path / "restaurants.json"
    source.write_text(json.dumps({"restaurants": {"store_id": "1"}}), encoding="utf-8")

    with pytest.raises(ValueError, match="restaurants.*array"):
        module.load_restaurant_input(source)
