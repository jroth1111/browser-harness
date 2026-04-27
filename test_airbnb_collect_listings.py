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
