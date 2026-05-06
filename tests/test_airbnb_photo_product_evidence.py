import importlib.util
from pathlib import Path


def load_module():
    path = Path("agent-workspace/domain-skills/airbnb/scripts/photo_product_evidence.py")
    spec = importlib.util.spec_from_file_location("airbnb_photo_product_evidence", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_normalizer_extracts_hero_first_five_room_and_amenity_proof():
    module = load_module()

    result = module.normalize_photo_product_evidence(
        raw_listing_text="""
        Entire rental unit in Melbourne
        8 guests - 3 bedrooms - 4 beds - 2 baths
        Free parking, pool, dedicated workspace, kitchen, washer, air conditioning.
        """,
        raw_photo_data=[
            {"alt": "Private secure parking bay at the building"},
            {"alt": "Queen bedroom with city view"},
            {"alt": "Bright bathroom with shower"},
            {"alt": "Full kitchen with oven"},
            {"alt": "Dedicated workspace and monitor"},
            {"alt": "Dining table near the lounge"},
        ],
    )

    assert result["hero_photo_subject"] == "parking"
    assert result["first_five_photo_subjects"] == ["parking", "view", "bathroom", "kitchen", "workspace"]
    assert result["bedroom_proof_flag"] is True
    assert result["bathroom_proof_flag"] is True
    assert result["kitchen_proof_flag"] is True
    assert result["workspace_proof_flag"] is True
    assert result["parking_proof_flag"] is True
    assert result["pool_or_spa_proof_flag"] is False
    assert "pool_or_spa" in result["missing_photo_proof"]
    assert "parking" in result["amenity_claims_proven_in_photos"]
    assert result["photo_product_score"] > 0


def test_normalizer_flags_design_gaps_without_treating_claims_as_photo_proof():
    module = load_module()

    result = module.normalize_photo_product_evidence(
        raw_listing_text="Free parking, pool, and family amenities. Photos look dark and dated.",
        raw_photo_data=[{"alt": "Building exterior"}],
    )

    assert result["hero_photo_subject"] == "exterior"
    assert result["parking_proof_flag"] is False
    assert result["pool_or_spa_proof_flag"] is False
    assert result["family_proof_flag"] is False
    assert result["missing_photo_proof"] == ["parking", "pool_or_spa", "family"]
    assert set(result["design_gap_flags"]) == {"dated_finish", "dark_photo"}
