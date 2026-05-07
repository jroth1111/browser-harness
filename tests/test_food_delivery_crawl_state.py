import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "domain-skills" / "food-delivery" / "scripts" / "lib" / "crawl_state.py"


def load_module():
    spec = importlib.util.spec_from_file_location("food_delivery_crawl_state", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_standalone_crawl_state_load_rejects_malformed_checkpoint_shapes(tmp_path):
    module = load_module()
    path = tmp_path / "checkpoint.json"
    path.write_text(json.dumps({"key_field": "store_id", "occurrences": []}), encoding="utf-8")

    with pytest.raises(ValueError, match="occurrences.*dict"):
        module.CrawlState.load(path)


def test_standalone_crawl_state_load_rejects_boolean_integer_fields(tmp_path):
    module = load_module()
    path = tmp_path / "checkpoint.json"
    path.write_text(json.dumps({"key_field": "store_id", "marginal_window": True}), encoding="utf-8")

    with pytest.raises(ValueError, match="marginal_window.*int"):
        module.CrawlState.load(path)


def test_standalone_crawl_state_reports_missing_keys_in_receipts_and_checkpoints(tmp_path):
    module = load_module()
    state = module.CrawlState("store_id")

    assert state.add({"name": "missing id"}) is False
    receipt = state.receipt(source_context={"domain": "food"}, safety=None)
    assert receipt["summary"]["missing_key"] == 1
    assert receipt["source_context"] == {"domain": "food"}

    path = tmp_path / "checkpoint.json"
    state.save(path)
    restored = module.CrawlState.load(path)
    assert restored.summary()["missing_key"] == 1
