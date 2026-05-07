import importlib.util
from datetime import date
from pathlib import Path


def load_module():
    path = Path("domain-skills/airbnb/scripts/public_scan_planner.py")
    spec = importlib.util.spec_from_file_location("airbnb_public_scan_planner", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parse_price_bands_supports_unbounded_and_exact_bands():
    module = load_module()

    assert module.parse_price_bands("0-250,251-500,501-,333") == [
        {"price_min": 0, "price_max": 250, "label": "0-250"},
        {"price_min": 251, "price_max": 500, "label": "251-500"},
        {"price_min": 501, "price_max": None, "label": "501-"},
        {"price_min": 333, "price_max": 333, "label": "333-333"},
    ]
    assert module.parse_price_bands("") == [{"price_min": None, "price_max": None, "label": "all_prices"}]


def test_fixed_width_price_bands_are_inclusive_and_non_overlapping():
    module = load_module()

    assert module.fixed_width_price_bands(100, 260, 75) == [
        {"price_min": 100, "price_max": 174, "label": "100-174"},
        {"price_min": 175, "price_max": 249, "label": "175-249"},
        {"price_min": 250, "price_max": 260, "label": "250-260"},
    ]


def test_resolve_checkin_dates_uses_offsets_when_dates_are_not_explicit():
    module = load_module()

    assert module.resolve_checkin_dates(offsets="1,3", today=date(2026, 4, 28)) == [
        "2026-04-29",
        "2026-05-01",
    ]


def test_search_matrix_expands_listing_dates_nights_and_price_bands():
    module = load_module()

    rows = module.search_matrix(
        listings=[{"listing_id": 100}, {"listing_id": 200}],
        checkin_dates=["2026-05-10"],
        nights_values=[2, 3],
        price_bands=module.parse_price_bands("0-200,201-"),
    )

    assert len(rows) == 8
    assert rows[0] == {
        "listing_id": "100",
        "check_in_date": "2026-05-10",
        "check_out_date": "2026-05-12",
        "nights": 2,
        "price_min": 0,
        "price_max": 200,
        "price_band_label": "0-200",
    }
    assert rows[-1]["listing_id"] == "200"
    assert rows[-1]["nights"] == 3
    assert rows[-1]["price_band_label"] == "201-"


def test_date_and_stay_range_expansion_is_deterministic():
    module = load_module()

    assert module.resolve_checkin_dates(checkin_range="2026-05-01..2026-05-07", step_days=3) == [
        "2026-05-01",
        "2026-05-04",
        "2026-05-07",
    ]
    assert module.resolve_nights_values(night_range="2..4") == [2, 3, 4]


def test_recursive_price_partition_splits_bounded_buckets_only():
    module = load_module()
    band = {"price_min": 0, "price_max": 999, "label": "0-999"}

    children = module.split_price_band(band)

    assert children == [
        {"price_min": 0, "price_max": 499, "label": "0-499", "partition_depth": 1, "parent_price_band_label": "0-999"},
        {"price_min": 500, "price_max": 999, "label": "500-999", "partition_depth": 1, "parent_price_band_label": "0-999"},
    ]
    assert module.should_partition_price_band(12, 12, band, max_depth=2) is True
    assert module.should_partition_price_band(11, 12, band, max_depth=2) is False
    assert module.should_partition_price_band(12, 12, {"price_min": 500, "price_max": None, "label": "500-"}, max_depth=2) is False


def test_price_partition_helpers_tolerate_malformed_bands():
    module = load_module()

    assert module.split_price_band("not-a-band") == []
    assert module.split_price_band({"price_min": "cheap", "price_max": "expensive"}) == []
    assert module.split_price_band({"price_min": True, "price_max": 100}) == []
    assert module.split_price_band({"price_min": 0, "price_max": 100, "partition_depth": "deep"}) == []
    assert module.split_price_band({"price_min": 0, "price_max": 100, "partition_depth": True}) == []
    assert module.should_partition_price_band(12, 12, "not-a-band", max_depth=2) is False
    assert module.should_partition_price_band(True, 1, {"price_min": 0, "price_max": 100}, max_depth=2) is False
    assert module.partition_key("100", "2026-05-10", 3, "not-a-band") == "100|2026-05-10|3|all_prices|d0"


def test_public_market_validation_rejects_bad_dates_and_options():
    module = load_module()

    result = module.validate_public_market_options(
        checkin_dates=["2026-05-10"],
        nights_values=[2, 7],
        price_bands=module.parse_price_bands("0-200,201-"),
        top_results=12,
        max_search_scrolls=6,
    )

    assert result["checked"] is True
    assert result["price_band_count"] == 2

    try:
        module.validate_public_market_options(
            checkin_dates=["2026-99-10"],
            nights_values=[2],
            top_results=12,
            max_search_scrolls=6,
        )
    except ValueError as error:
        assert "check-in date" in str(error)
    else:
        raise AssertionError("bad date should fail validation")


def test_public_search_context_matches_airbnb_url_contract():
    module = load_module()
    url = (
        "https://www.airbnb.com.au/s/Melbourne--Victoria--Australia/homes"
        "?query=Melbourne&checkin=2026-05-10&checkout=2026-05-13"
        "&adults=4&room_types%5B%5D=Entire+home%2Fapt"
    )

    result = module.validate_public_search_context(
        destination="Melbourne, Victoria, Australia",
        checkin="2026-05-10",
        checkout="2026-05-13",
        nights=3,
        adults=4,
        filters=["room_types[]=Entire home/apt"],
        price_band={"price_min": 0, "price_max": 300, "label": "0-300"},
        url=url,
    )

    assert result["checked"] is True
    assert result["guest_counts"]["adults"] == 4
    assert result["room_types"] == ["Entire home/apt"]
    assert result["search_url_checked"] is True

    try:
        module.validate_public_search_context(
            destination="Melbourne",
            checkin="2026-05-10",
            checkout="2026-05-12",
            nights=3,
            adults=4,
            filters=["room_types[]=Entire home/apt"],
            url=url,
        )
    except ValueError as error:
        assert "nights" in str(error)
    else:
        raise AssertionError("mismatched nights should fail validation")


def test_public_search_context_requires_entire_home_by_default():
    module = load_module()

    try:
        module.validate_public_search_context(
            destination="Melbourne",
            checkin="2026-05-10",
            checkout="2026-05-13",
            nights=3,
            adults=2,
            filters=["room_types[]=Private room"],
        )
    except ValueError as error:
        assert "Entire home" in str(error)
    else:
        raise AssertionError("private-room scan should require explicit room study")

    assert module.validate_public_search_context(
        destination="Melbourne",
        checkin="2026-05-10",
        checkout="2026-05-13",
        nights=3,
        adults=2,
        filters=["room_types[]=Private room"],
        explicit_room_study=True,
    )["room_types"] == ["Private room"]


def test_partition_key_and_dedupe_listing_ids_are_deterministic():
    module = load_module()

    band = {"price_min": 0, "price_max": 499, "label": "0-499", "partition_depth": 1}

    assert module.partition_key("100", "2026-05-10", 3, band) == "100|2026-05-10|3|0-499|d1"
    assert module.dedupe_listing_ids([
        {"listing_id_if_extractable": "200"},
        {"listing_id_if_extractable": "200"},
        {"listing_id_if_extractable": "300"},
        {"listing_id_if_extractable": ""},
    ]) == ["200", "300"]


def test_partition_manifest_records_tree_and_dedupes_listing_ids():
    module = load_module()

    manifest = module.build_partition_manifest(
        [
            {
                "search_run_id": "search-1",
                "partition_key": "100|2026-05-10|3|0-999|d0",
                "target_listing_id": "100",
                "check_in_date": "2026-05-10",
                "nights": 3,
                "price_band_label": "0-999",
                "results_count_visible": 12,
                "partition_triggered": True,
                "partition_child_labels": ["0-499", "500-999"],
                "status": "ok",
            },
            {
                "search_run_id": "search-2",
                "partition_key": "100|2026-05-10|3|0-499|d1",
                "target_listing_id": "100",
                "check_in_date": "2026-05-10",
                "nights": 3,
                "price_band_label": "0-499",
                "partition_depth": 1,
                "results_count_visible": 8,
                "status": "ok",
            },
        ],
        [
            {"listing_id_if_extractable": "200"},
            {"listing_id_if_extractable": "200"},
            {"listing_id_if_extractable": "300"},
        ],
        trigger_threshold=12,
        max_depth=2,
    )

    assert manifest["partition_count"] == 2
    assert manifest["triggered_partition_count"] == 1
    assert manifest["partitions"][0]["partition_child_labels"] == ["0-499", "500-999"]
    assert manifest["deduped_listing_ids"] == ["200", "300"]


def test_partition_manifest_tolerates_malformed_rows_and_counts():
    module = load_module()

    manifest = module.build_partition_manifest(
        [
            "not-a-row",
            {
                "search_run_id": "search-1",
                "partition_key": "100|2026-05-10|3|0-999|d0",
                "target_listing_id": "100",
                "partition_depth": "not-a-depth",
                "results_count_visible": "not-a-count",
                "partition_triggered": True,
                "partition_child_labels": "not-a-list",
            },
        ],
        ["not-a-row", {"listing_id_if_extractable": "200"}],
        trigger_threshold="not-a-threshold",
        max_depth="not-a-depth",
    )

    assert manifest["partition_count"] == 1
    assert manifest["trigger_threshold"] is None
    assert manifest["max_depth"] is None
    assert manifest["partitions"][0]["partition_depth"] == 0
    assert manifest["partitions"][0]["visible_result_count"] == 0
    assert manifest["partitions"][0]["partition_child_labels"] == []
    assert manifest["deduped_listing_ids"] == ["200"]


def test_validate_airbnb_room_url_rejects_non_airbnb_urls():
    module = load_module()

    assert module.validate_airbnb_room_url("https://www.airbnb.com.au/rooms/123456") is True

    try:
        module.validate_airbnb_room_url("https://example.com/rooms/123456")
    except ValueError as error:
        assert "Airbnb URL" in str(error)
    else:
        raise AssertionError("non-Airbnb URL should fail validation")


def test_property_validation_requires_address_boundary_and_equal_or_worse_proof():
    module = load_module()

    result = module.validate_research_mode_gate(
        "property_validation",
        {
            "target_address_or_building": "500 Elizabeth Street",
            "map_boundary_receipt": {"title": "Homes within map area"},
            "equal_or_worse_profitable_comps": [{"listing_id": "123"}],
        },
    )

    assert result["mode_gate_result"] == "pass"
    assert result["required_evidence_present_flag"] is True

    missing = module.validate_research_mode_gate(
        "property_validation",
        {
            "target_address_or_building": "500 Elizabeth Street",
            "map_boundary_receipt": {"title": "Homes within map area"},
            "beautiful_broad_market_winners": [{"listing_id": "999"}],
        },
    )

    assert missing["mode_gate_result"] == "needs_more_data"
    assert "same_building_or_same_block_comps_or_equal_or_worse_profitable_comps" in missing["mode_specific_missing_evidence"]


def test_opportunity_discovery_allows_broad_winners_only_with_reproducibility():
    module = load_module()

    result = module.validate_research_mode_gate(
        "opportunity_discovery",
        {
            "winning_product_patterns": ["supply-dry 3BR family apartments"],
            "repeated_winner_examples": [{"listing_id": "123"}, {"listing_id": "456"}],
            "reproducibility_assessment": {"parking": "candidate can reproduce"},
        },
    )

    assert result["mode_gate_result"] == "pass"

    missing = module.validate_research_mode_gate(
        "opportunity_discovery",
        {"winning_product_patterns": ["one beautiful winner"]},
    )

    assert missing["mode_gate_result"] == "needs_more_data"
    assert "repeated_winner_examples" in missing["mode_specific_missing_evidence"]


def test_similarity_filter_pack_requires_entire_home_by_default():
    module = load_module()

    assert module.validate_similarity_filter_pack(["Entire home/apt", "min_bedrooms=3"]) == {
        "checked": True,
        "filters": ["Entire home/apt", "min_bedrooms=3"],
        "entire_home_default_applied": True,
    }

    try:
        module.validate_similarity_filter_pack(["min_bedrooms=3"])
    except ValueError as error:
        assert "Entire home" in str(error)
    else:
        raise AssertionError("missing Entire home should fail property-validation filters")

    assert module.validate_similarity_filter_pack(["Room"], explicit_room_study=True)["checked"] is True


def test_listing_maturity_filter_blocks_boosted_or_unproven_base_case_comps():
    module = load_module()

    new_listing = module.listing_maturity_filter(
        review_count=1,
        latest_review_date="2026-04-20",
        observed_at="2026-04-29",
        future_availability_signal="high_rank",
    )

    assert new_listing["maturity_grade"] == "boosted_or_unproven"
    assert new_listing["possible_airbnb_boost_flag"] is True
    assert new_listing["can_use_for_underwriting_flag"] is False
    assert new_listing["underwriting_use"] == "inspiration"


def test_listing_maturity_filter_allows_recent_mature_comps_for_base_case():
    module = load_module()

    mature = module.listing_maturity_filter(
        review_count=42,
        latest_review_date="2026-03-15",
        observed_at="2026-04-29",
    )

    assert mature["maturity_grade"] == "mature"
    assert mature["can_use_for_underwriting_flag"] is True
    assert mature["underwriting_use"] == "base_case"
