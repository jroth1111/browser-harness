import importlib.util
from pathlib import Path


def load_scope_module():
    path = Path("domain-skills/airbnb/scripts/listing_scope.py")
    spec = importlib.util.spec_from_file_location("airbnb_listing_scope", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sample_records():
    return [
        {"listing_id": "100", "status": "ACTIVE"},
        {"listing_id": "200", "status": "UNLISTED"},
        {"listing_id": "300", "status": "SNOOZED"},
    ]


def test_listing_scope_defaults_to_active():
    module = load_scope_module()

    selected, scope = module.select_listings(sample_records())

    assert scope["label"] == "active"
    assert [row["listing_id"] for row in selected] == ["100"]


def test_listing_scope_can_include_all_non_active_records():
    module = load_scope_module()

    selected, scope = module.select_listings(sample_records(), "all")

    assert scope["label"] == "all"
    assert [row["listing_id"] for row in selected] == ["100", "200", "300"]


def test_listing_scope_can_select_non_active_statuses_or_ids():
    module = load_scope_module()

    selected, scope = module.select_listings(sample_records(), "statuses:UNLISTED,SNOOZED")
    assert scope["label"] == "statuses:SNOOZED,UNLISTED"
    assert [row["listing_id"] for row in selected] == ["200", "300"]

    selected, scope = module.select_listings(sample_records(), "ids:300,100")
    assert scope["label"] == "ids:100,300"
    assert [row["listing_id"] for row in selected] == ["100", "300"]
