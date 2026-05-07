import importlib.util
from pathlib import Path


def load_module():
    path = Path("domain-skills/airbnb/scripts/collect_listings.py")
    spec = importlib.util.spec_from_file_location("airbnb_collect_listings", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_normalize_overview_record_prefers_listing_specific_ids():
    module = load_module()
    row = {
        "id": "123456789012345678",
        "status": "ACTIVE",
        "name": "Harbour view apartment",
        "listing": {"id": "999999999999999999"},
        "photos": [{"id": "555555555555555555"}],
        "personCapacity": 4,
        "bedrooms": 2,
        "bathrooms": 1.5,
        "beds": 2,
    }

    record = module.normalize_overview_record(row)

    assert record["listing_id"] == "123456789012345678"
    assert record["status"] == "ACTIVE"
    assert record["listing_name"] == "Harbour view apartment"
    assert record["max_guests"] == 4
    assert record["public_listing_url"].endswith("/rooms/123456789012345678")


def test_dedupe_records_merges_non_empty_fields():
    module = load_module()
    records = [
        {"listing_id": "1", "listing_name": "A", "address": None},
        {"listing_id": "1", "address": "Private address", "beds": 2},
    ]

    assert module.dedupe_records(records) == [
        {"listing_id": "1", "listing_name": "A", "address": "Private address", "beds": 2}
    ]


def test_first_total_count_skips_boolean_totals():
    module = load_module()

    assert module.first_total_count({
        "totalCount": True,
        "data": {"total_count": 42},
    }) == 42


def test_detail_fields_from_text_extracts_required_private_fields():
    module = load_module()
    fields = module.detail_fields_from_text(
        "\n".join([
            "Property type",
            "Entire place",
            "Apartment",
            "Location",
            "1 Example Street, Melbourne VIC",
            "Number of guests",
            "5 guests",
            "29 photos",
        ])
    )

    assert fields["address"] == "1 Example Street, Melbourne VIC"
    assert fields["max_guests"] == 5
    assert fields["guest_label"] == "5 guests"
    assert fields["photo_count"] == 29


def test_discover_query_hash_honors_env_override(monkeypatch):
    module = load_module()
    monkeypatch.setenv("AIRBNB_LISTINGS_QUERY_HASH", "f" * 64)

    assert module.discover_query_hash() == {
        "hash": "f" * 64,
        "source": "AIRBNB_LISTINGS_QUERY_HASH",
        "discovery": None,
    }


def test_discover_query_hash_falls_back_on_malformed_browser_context(monkeypatch):
    module = load_module()
    monkeypatch.delenv("AIRBNB_LISTINGS_QUERY_HASH", raising=False)
    monkeypatch.setattr(module, "js", lambda script: "not-a-context", raising=False)

    result = module.discover_query_hash()

    assert result["hash"] == module.OBSERVED_QUERY_HASH
    assert result["source"] == "observed_2026_04_27_fallback"


def test_discover_query_hash_falls_back_on_malformed_discovery(monkeypatch):
    module = load_module()
    monkeypatch.delenv("AIRBNB_LISTINGS_QUERY_HASH", raising=False)
    monkeypatch.setattr(
        module,
        "js",
        lambda script: {
            "html": "",
            "scripts": [],
            "resources": [],
        },
        raising=False,
    )
    monkeypatch.setattr(
        module._operation_hashes,
        "discover_operation_hashes",
        lambda *args, **kwargs: {"hashes": "not-a-map", "sources": "not-a-map"},
    )

    result = module.discover_query_hash()

    assert result["hash"] == module.OBSERVED_QUERY_HASH
    assert result["source"] == "observed_2026_04_27_fallback"
