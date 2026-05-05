import json
import importlib.util
from pathlib import Path


def load_module():
    path = Path("agent-workspace/domain-skills/airbnb/scripts/collect_rea_building_rentals.py")
    spec = importlib.util.spec_from_file_location("collect_rea_building_rentals", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_building_targets_normalize_unit_prefixes_to_same_building():
    module = load_module()

    targets = module.building_targets_from_airbnb_records(
        [
            {
                "listing_id": "100",
                "nickname": "Bank 1303",
                "status": "ACTIVE",
                "address": "1303/38 Bank St, South Melbourne VIC 3205, Australia",
                "bedrooms": 1,
            },
            {
                "listing_id": "200",
                "nickname": "Bank 2401",
                "status": "ACTIVE",
                "address": "38 Bank Street, South Melbourne VIC 3205, Australia",
                "bedrooms": 2,
            },
        ]
    )

    assert len(targets) == 1
    assert targets[0]["building_address"] == "38 Bank St, South Melbourne VIC 3205"
    assert targets[0]["source_airbnb_listing_ids"] == ["100", "200"]
    assert targets[0]["source_airbnb_bedrooms"] == [1, 2]


def test_building_targets_normalize_named_building_prefixes():
    module = load_module()

    targets = module.building_targets_from_airbnb_records(
        [
            {
                "listing_id": "300",
                "nickname": "Nexus 11",
                "status": "ACTIVE",
                "address": "Nexus, 11/69 Palmer St, Richmond VIC 3121, Australia",
                "bedrooms": 1,
            }
        ]
    )

    assert targets[0]["building_address"] == "69 Palmer St, Richmond VIC 3121"
    assert targets[0]["building_key"] == "69 palmer st|richmond|VIC|3121"


def test_building_watchlist_targets_add_new_buildings_and_merge_existing():
    module = load_module()
    airbnb_targets = module.building_targets_from_airbnb_records(
        [
            {
                "listing_id": "100",
                "nickname": "Bank 1303",
                "status": "ACTIVE",
                "address": "1303/38 Bank St, South Melbourne VIC 3205, Australia",
                "bedrooms": 1,
            }
        ]
    )

    targets = module.merge_building_watchlist_targets(
        airbnb_targets,
        [
            {
                "id": "short-001",
                "label": "Prima shortlist",
                "address": "9 Power Street, Southbank VIC 3006",
                "reason": "high Airbnb amenity potential",
                "priority": 25,
                "tags": ["pool", "gym", "cbd"],
                "target_bedrooms": [1, 2],
            },
            {
                "id": "benchmark-001",
                "label": "Existing Bank benchmark",
                "address": "38 Bank Street, South Melbourne VIC 3205",
                "reason": "known operating benchmark",
            },
        ],
    )

    by_key = {target["building_key"]: target for target in targets}
    watch_only = by_key["9 power st|southbank|VIC|3006"]
    merged = by_key["38 bank st|south melbourne|VIC|3205"]

    assert watch_only["source_airbnb_listing_count"] == 0
    assert watch_only["target_sources"] == ["building_watchlist"]
    assert watch_only["source_watchlist_ids"] == ["short-001"]
    assert watch_only["source_watchlist_target_bedrooms"] == [1, 2]
    assert watch_only["target_priority"] == 25
    assert merged["target_sources"] == ["airbnb_inventory", "building_watchlist"]
    assert merged["source_airbnb_listing_ids"] == ["100"]
    assert merged["source_watchlist_labels"] == ["Existing Bank benchmark"]


def test_building_watchlist_records_from_json_object_file(tmp_path):
    module = load_module()
    path = tmp_path / "watchlist.json"
    path.write_text(json.dumps({"buildings": [{"id": "b1", "address": "9 Power Street, Southbank VIC 3006"}]}))

    records = module.building_watchlist_records_from_file(path)

    assert records == [{"id": "b1", "address": "9 Power Street, Southbank VIC 3006"}]


def test_parse_rea_rental_listing_text_extracts_active_price_and_unit():
    module = load_module()

    parsed = module.parse_rea_rental_listing_text(
        """
        Rent / VIC / Southbank / Apartment
        1705/250 City Road, Southbank, Vic 3006
        $725 per week
        Bond $3,150
        Available from Friday, 10 May 2026
        Open for inspection Saturday 11 May 10:00 am - 10:15 am
        Fully furnished
        Pets considered on application
        Apply via Ignite
        2 bedrooms
        1 bathroom
        1 car space
        Balcony
        Dishwasher
        Built-in wardrobes
        Listed by Jane Agent - Example Real Estate
        Property ID: 439776600
        """,
        url="https://www.realestate.com.au/property-apartment-vic-southbank-439776600",
    )

    assert parsed["listing_state"] == "active"
    assert parsed["available_flag"] is True
    assert parsed["listing_lifecycle_evidence"] == "active_price_visible"
    assert parsed["listing_lifecycle_confidence"] == "high"
    assert parsed["unavailable_reason"] is None
    assert parsed["rent_per_week_aud"] == 725
    assert parsed["annual_rent_aud"] == 37700
    assert parsed["bond_aud"] == 3150
    assert parsed["bond_weeks_equivalent"] == 4.34
    assert parsed["unit_identifier"] == "1705"
    assert parsed["listing_building_key"] == "250 city rd|southbank|VIC|3006"
    assert parsed["rea_listing_id"] == "439776600"
    assert parsed["property_type"] == "apartment"
    assert parsed["bedrooms"] == 2
    assert parsed["bathrooms"] == 1
    assert parsed["car_spaces"] == 1
    assert parsed["furnishing_status"] == "furnished"
    assert parsed["furnished_flag"] is True
    assert parsed["pets_policy_text"] == "Pets considered on application"
    assert parsed["inspection_times"] == ["Open for inspection Saturday 11 May 10:00 am - 10:15 am"]
    assert parsed["application_text"] == ["Pets considered on application", "Apply via Ignite"]
    assert {"balcony", "dishwasher", "built_in_wardrobes", "secure_parking"}.issubset(set(parsed["property_features"]))
    assert parsed["agency_or_contact_lines"] == ["Listed by Jane Agent - Example Real Estate"]


def test_parse_rea_rental_listing_text_marks_leased_as_unavailable():
    module = load_module()

    parsed = module.parse_rea_rental_listing_text(
        """
        9/70 Canterbury Road, Toorak VIC 3142
        Leased
        $530 per week
        Bond $2,120
        Property ID 438111222
        """,
        url="https://www.realestate.com.au/property-apartment-vic-toorak-438111222",
    )

    assert parsed["listing_state"] == "leased_or_unavailable"
    assert parsed["available_flag"] is False
    assert parsed["unavailable_reason"] == "leased"
    assert parsed["listing_lifecycle_evidence"] == "explicit_leased"
    assert parsed["listing_lifecycle_confidence"] == "high"
    assert parsed["rent_per_week_aud"] == 530
    assert parsed["listing_building_key"] == "70 canterbury rd|toorak|VIC|3142"


def test_parse_rea_rental_listing_text_ignores_related_leased_page_chrome():
    module = load_module()

    parsed = module.parse_rea_rental_listing_text(
        """
        1101/118 Kavanagh Street, Southbank VIC 3006
        $760 per week
        2 bedrooms
        2 bathrooms
        Apartment
        Similar properties
        Recently leased nearby apartments
        $690 per week
        1 bedroom
        1 bathroom
        Apartment
        Leased
        1203/118 Kavanagh Street, Southbank VIC 3006
        """,
        url="https://www.realestate.com.au/property-apartment-vic-southbank-444003228",
    )

    assert parsed["listing_state"] == "active"
    assert parsed["available_flag"] is True
    assert parsed["unavailable_reason"] is None
    assert parsed["listing_lifecycle_evidence"] == "active_price_visible"


def test_parse_rea_rental_listing_text_keeps_direct_leased_signal():
    module = load_module()

    parsed = module.parse_rea_rental_listing_text(
        """
        1101/118 Kavanagh Street, Southbank VIC 3006
        Leased
        $760 per week
        2 bedrooms
        2 bathrooms
        Apartment
        """,
        url="https://www.realestate.com.au/property-apartment-vic-southbank-444003228",
    )

    assert parsed["listing_state"] == "leased_or_unavailable"
    assert parsed["available_flag"] is False
    assert parsed["unavailable_reason"] == "leased"


def test_parse_rea_rental_listing_text_keeps_recently_leased_listing_status():
    module = load_module()

    parsed = module.parse_rea_rental_listing_text(
        """
        1101/118 Kavanagh Street, Southbank VIC 3006
        This property was recently leased
        $760 per week
        2 bedrooms
        2 bathrooms
        Apartment
        """,
        url="https://www.realestate.com.au/property-apartment-vic-southbank-444003228",
    )

    assert parsed["listing_state"] == "leased_or_unavailable"
    assert parsed["available_flag"] is False
    assert parsed["unavailable_reason"] == "leased"


def test_parse_rea_rental_listing_text_handles_repeated_unit_address_fragments():
    module = load_module()

    parsed = module.parse_rea_rental_listing_text(
        """
        G07/2 Princes St
        G07/2 Princes Street, St Kilda VIC 3182
        $520 per week
        Apartment
        """,
        url="https://www.realestate.com.au/property-apartment-vic-st+kilda-443625764",
    )

    assert parsed["unit_identifier"] == "G07"
    assert parsed["listing_address"] == "G07/2 Princes St, St Kilda VIC 3182"
    assert parsed["listing_building_key"] == "2 princes st|st kilda|VIC|3182"


def test_parse_rea_rental_listing_text_does_not_treat_unit_404_as_removed():
    module = load_module()

    parsed = module.parse_rea_rental_listing_text(
        """
        404/118 Kavanagh Street, Southbank VIC 3006
        $760 per week
        2 bedrooms
        Apartment
        """,
        url="https://www.realestate.com.au/property-apartment-vic-southbank-444003228",
    )

    assert parsed["unit_identifier"] == "404"
    assert parsed["listing_state"] == "active"
    assert parsed["listing_lifecycle_evidence"] == "active_price_visible"
    assert module.page_failure({"title": "404/118 Kavanagh Street", "text": "404/118 Kavanagh Street\n$760 per week"}) is None


def test_clean_rea_candidate_url_canonicalizes_listing_urls_and_rejects_profiles():
    module = load_module()

    cleaned = module.clean_rea_candidate_url(
        "https://www.realestate.com.au/property-apartment-vic-melbourne-439123456?source=foo"
    )

    assert cleaned == "https://www.realestate.com.au/property-apartment-vic-melbourne-439123456"
    assert module.clean_rea_candidate_url("https://www.realestate.com.au/property/500-elizabeth-st-melbourne-vic-3000") is None


def test_rea_search_url_uses_suburb_only_and_page_number():
    module = load_module()
    target = {
        "street_address": "118 Kavanagh St",
        "suburb": "Southbank",
        "state": "VIC",
        "postcode": "3006",
    }

    assert module.rea_rent_search_url(target, 3) == (
        "https://www.realestate.com.au/rent/in-southbank+vic+3006/list-3"
    )
    assert module.rea_search_location_query(target) == "Southbank VIC 3006"
    assert module.rea_building_match_query(target) == "118 Kavanagh Street, Southbank VIC 3006"


def test_parse_search_result_count_calculates_total_pages():
    module = load_module()

    parsed = module.parse_search_result_count("Showing 26 – 50 of 367 properties")

    assert parsed == {"start": 26, "end": 50, "total": 367, "page_size": 25, "total_pages": 15}


def test_observation_from_search_card_matches_building_without_opening_listing():
    module = load_module()
    target = {
        "building_key": "118 kavanagh st|southbank|VIC|3006",
        "building_address": "118 Kavanagh St, Southbank VIC 3006",
        "street_address": "118 Kavanagh St",
        "suburb": "Southbank",
        "state": "VIC",
        "postcode": "3006",
        "source_airbnb_listing_ids": ["abc"],
        "source_airbnb_nicknames": ["118 kav"],
        "source_airbnb_listing_count": 1,
    }

    observation, failure = module.observation_from_search_card(
        target,
        {
            "href": "https://www.realestate.com.au/property-apartment-vic-southbank-444003228",
            "text": """
            Image: 2210/118 Kavanagh Street, Southbank, Vic 3006
            $760 per week
            ## 2210/118 Kavanagh Street, Southbank
            2 bedrooms
            2 bathrooms
            1 car space
            Apartment
            """,
        },
        "2026-04-29T00:00:00Z",
        "run-1",
        "https://www.realestate.com.au/rent/in-southbank+vic+3006/list-1",
        1,
    )

    assert failure is None
    assert observation["discovery_source"] == "rea_search_page"
    assert observation["listing_key"] == "rea:444003228"
    assert observation["observation_id"]
    assert observation["content_hash"]
    assert observation["unit_identifier"] == "2210"
    assert observation["rent_per_week_aud"] == 760
    assert observation["listing_state"] == "active"
    assert observation["match_confidence"] == "parsed_address_key"
    assert observation["discovery_query"] == "Southbank VIC 3006"
    assert observation["building_match_query"] == "118 Kavanagh Street, Southbank VIC 3006"


def test_event_rows_detect_first_seen_price_change_rented_and_relisted():
    module = load_module()
    base = {
        "listing_key": "rea:439776600",
        "rea_listing_id": "439776600",
        "rea_listing_url": "https://www.realestate.com.au/property-apartment-vic-southbank-439776600",
        "building_key": "250 city rd|southbank|VIC|3006",
        "building_address": "250 City Rd, Southbank VIC 3006",
        "unit_identifier": "1705",
    }

    first = module.event_rows_for_observations(
        [{**base, "listing_state": "active", "rent_per_week_aud": 725}],
        {},
        "2026-04-29T00:00:00Z",
        "run-1",
    )
    price = module.event_rows_for_observations(
        [{**base, "listing_state": "active", "rent_per_week_aud": 760}],
        {"rea:439776600": {**base, "listing_state": "active", "rent_per_week_aud": 725, "observed_at": "2026-04-29T00:00:00Z"}},
        "2026-04-30T00:00:00Z",
        "run-2",
    )
    leased = module.event_rows_for_observations(
        [{**base, "listing_state": "leased_or_unavailable", "rent_per_week_aud": 760, "unavailable_reason": "leased", "listing_lifecycle_evidence": "explicit_leased", "listing_lifecycle_confidence": "high"}],
        {"rea:439776600": {**base, "listing_state": "active", "rent_per_week_aud": 760, "observed_at": "2026-04-30T00:00:00Z"}},
        "2026-05-01T00:00:00Z",
        "run-3",
    )
    removed = module.event_rows_for_observations(
        [{**base, "listing_state": "removed_or_unknown", "rent_per_week_aud": None, "unavailable_reason": "page_not_found_or_removed", "listing_lifecycle_evidence": "known_url_page_not_found_from_previous_observation", "listing_lifecycle_confidence": "medium"}],
        {"rea:439776600": {**base, "listing_state": "active", "rent_per_week_aud": 760, "observed_at": "2026-04-30T00:00:00Z"}},
        "2026-05-02T00:00:00Z",
        "run-3b",
    )
    relisted = module.event_rows_for_observations(
        [{**base, "listing_state": "active", "rent_per_week_aud": 790}],
        {"rea:439776600": {**base, "listing_state": "leased_or_unavailable", "rent_per_week_aud": 760, "observed_at": "2026-05-01T00:00:00Z"}},
        "2026-05-10T00:00:00Z",
        "run-4",
    )
    evidence_upgrade = module.event_rows_for_observations(
        [{**base, "listing_state": "leased_or_unavailable", "rent_per_week_aud": 760, "unavailable_reason": "leased", "listing_lifecycle_evidence": "explicit_leased", "listing_lifecycle_confidence": "high"}],
        {"rea:439776600": {**base, "listing_state": "leased_or_unavailable", "rent_per_week_aud": 760, "unavailable_reason": "no_longer_available", "listing_lifecycle_evidence": "explicit_no_longer_available", "listing_lifecycle_confidence": "medium", "observed_at": "2026-05-01T00:00:00Z"}},
        "2026-05-03T00:00:00Z",
        "run-3c",
    )
    relisted_after_404 = module.event_rows_for_observations(
        [{**base, "listing_state": "active", "rent_per_week_aud": 790}],
        {"rea:439776600": {**base, "listing_state": "removed_or_unknown", "rent_per_week_aud": None, "last_known_rent_per_week_aud": 760, "unavailable_reason": "page_not_found_or_removed", "listing_lifecycle_evidence": "known_url_page_not_found_from_previous_observation", "listing_lifecycle_confidence": "medium", "observed_at": "2026-05-02T00:00:00Z"}},
        "2026-05-11T00:00:00Z",
        "run-5",
    )
    first_unknown = module.event_rows_for_observations(
        [{**base, "listing_state": "unknown", "rent_per_week_aud": None, "listing_lifecycle_evidence": "no_price_or_unavailable_signal", "listing_lifecycle_confidence": "low"}],
        {},
        "2026-05-12T00:00:00Z",
        "run-6",
    )
    confidence_upgrade = module.event_rows_for_observations(
        [{**base, "listing_state": "leased_or_unavailable", "rent_per_week_aud": 760, "unavailable_reason": "no_longer_available", "listing_lifecycle_evidence": "explicit_no_longer_available", "listing_lifecycle_confidence": "high"}],
        {"rea:439776600": {**base, "listing_state": "leased_or_unavailable", "rent_per_week_aud": 760, "unavailable_reason": "no_longer_available", "listing_lifecycle_evidence": "explicit_no_longer_available", "listing_lifecycle_confidence": "medium", "observed_at": "2026-05-01T00:00:00Z"}},
        "2026-05-13T00:00:00Z",
        "run-7",
    )
    unknown_to_active = module.event_rows_for_observations(
        [{**base, "listing_state": "active", "rent_per_week_aud": 760, "listing_lifecycle_evidence": "active_price_visible", "listing_lifecycle_confidence": "high"}],
        {"rea:439776600": {**base, "listing_state": "unknown", "rent_per_week_aud": None, "listing_lifecycle_evidence": "no_price_or_unavailable_signal", "listing_lifecycle_confidence": "low", "observed_at": "2026-05-12T00:00:00Z"}},
        "2026-05-14T00:00:00Z",
        "run-8",
    )
    active_to_unknown = module.event_rows_for_observations(
        [{**base, "listing_state": "unknown", "rent_per_week_aud": None, "listing_lifecycle_evidence": "no_price_or_unavailable_signal", "listing_lifecycle_confidence": "low"}],
        {"rea:439776600": {**base, "listing_state": "active", "rent_per_week_aud": 760, "listing_lifecycle_evidence": "active_price_visible", "listing_lifecycle_confidence": "high", "observed_at": "2026-05-14T00:00:00Z"}},
        "2026-05-15T00:00:00Z",
        "run-9",
    )

    assert [row["event_type"] for row in first] == ["first_seen_active"]
    assert [row["event_type"] for row in price] == ["price_changed"]
    assert [row["event_type"] for row in leased] == ["leased_confirmed"]
    assert leased[0]["new_unavailable_reason"] == "leased"
    assert leased[0]["new_listing_lifecycle_evidence"] == "explicit_leased"
    assert [row["event_type"] for row in removed] == ["listing_removed_or_unreachable"]
    assert removed[0]["new_unavailable_reason"] == "page_not_found_or_removed"
    assert removed[0]["new_listing_lifecycle_confidence"] == "medium"
    assert [row["event_type"] for row in relisted] == ["relisted", "price_changed"]
    assert [row["event_type"] for row in evidence_upgrade] == ["leased_confirmed"]
    assert evidence_upgrade[0]["old_unavailable_reason"] == "no_longer_available"
    assert evidence_upgrade[0]["new_unavailable_reason"] == "leased"
    assert [row["event_type"] for row in relisted_after_404] == ["relisted", "price_changed"]
    assert relisted_after_404[1]["old_rent_per_week_aud"] == 760
    assert relisted_after_404[1]["old_rent_basis"] == "previous_last_known_rent_per_week_aud"
    assert [row["event_type"] for row in first_unknown] == ["first_seen_unknown"]
    assert [row["event_type"] for row in confidence_upgrade] == ["unavailable_confirmed"]
    assert confidence_upgrade[0]["old_listing_lifecycle_confidence"] == "medium"
    assert confidence_upgrade[0]["new_listing_lifecycle_confidence"] == "high"
    assert [row["event_type"] for row in unknown_to_active] == ["active_confirmed"]
    assert [row["event_type"] for row in active_to_unknown] == ["active_signal_lost"]
    assert all(row["event_id"] for row in first + price + leased + removed + relisted + evidence_upgrade + relisted_after_404 + first_unknown + confidence_upgrade + unknown_to_active + active_to_unknown)


def test_observation_identity_is_stable_and_content_hash_tracks_material_changes():
    module = load_module()
    base = {
        "run_id": "run-1",
        "building_key": "250 city rd|southbank|VIC|3006",
        "rea_listing_id": "439776600",
        "rea_listing_url": "https://www.realestate.com.au/property-apartment-vic-southbank-439776600",
        "listing_state": "active",
        "rent_per_week_aud": 725,
        "listing_address": "1705/250 City Rd, Southbank VIC 3006",
    }

    first = module.with_observation_identity(dict(base))
    same = module.with_observation_identity({**base, "observed_at": "2026-04-29T00:00:00Z"})
    changed = module.with_observation_identity({**base, "rent_per_week_aud": 760})

    assert first["observation_id"] == same["observation_id"]
    assert first["content_hash"] == same["content_hash"]
    assert first["observation_id"] == changed["observation_id"]
    assert first["content_hash"] != changed["content_hash"]


def test_jsonl_upsert_by_key_retries_without_duplicates(tmp_path):
    module = load_module()
    path = tmp_path / "ledger.jsonl"

    module.upsert_jsonl_by_key(path, [{"id": "a", "value": 1}, {"id": "b", "value": 2}], "id")
    module.upsert_jsonl_by_key(path, [{"id": "a", "value": 3}], "id")
    module.upsert_jsonl_by_key(path, [{"id": "a", "value": 3}], "id")

    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert rows == [{"id": "a", "value": 3}, {"id": "b", "value": 2}]


def test_latest_observations_can_exclude_current_run_for_idempotent_retry(tmp_path):
    module = load_module()
    path = tmp_path / "observations.jsonl"
    previous = {
        "run_id": "run-1",
        "observed_at": "2026-04-28T00:00:00Z",
        "listing_key": "rea:439776600",
        "listing_state": "active",
        "rent_per_week_aud": 725,
    }
    current = {
        "run_id": "run-2",
        "observed_at": "2026-04-29T00:00:00Z",
        "listing_key": "rea:439776600",
        "listing_state": "active",
        "rent_per_week_aud": 760,
    }
    path.write_text(json.dumps(previous) + "\n" + json.dumps(current) + "\n")

    latest = module.latest_observations_by_listing(path, exclude_run_id="run-2")

    assert latest["rea:439776600"]["run_id"] == "run-1"
    assert latest["rea:439776600"]["rent_per_week_aud"] == 725


def test_building_price_snapshot_rows_aggregate_observed_prices_by_building():
    module = load_module()
    targets = [
        {
            "building_key": "118 kavanagh st|southbank|VIC|3006",
            "building_address": "118 Kavanagh St, Southbank VIC 3006",
            "street_address": "118 Kavanagh St",
            "suburb": "Southbank",
            "state": "VIC",
            "postcode": "3006",
            "source_airbnb_listing_ids": ["abc"],
            "source_airbnb_nicknames": ["118 kav"],
            "source_airbnb_listing_count": 1,
        },
        {
            "building_key": "250 city rd|southbank|VIC|3006",
            "building_address": "250 City Rd, Southbank VIC 3006",
            "street_address": "250 City Rd",
            "suburb": "Southbank",
            "state": "VIC",
            "postcode": "3006",
            "source_airbnb_listing_ids": ["def"],
            "source_airbnb_nicknames": ["250 city"],
            "source_airbnb_listing_count": 1,
        },
    ]
    observations = [
        {
            "observation_id": "obs-1",
            "listing_key": "rea:1",
            "building_key": "118 kavanagh st|southbank|VIC|3006",
            "listing_state": "active",
            "rent_per_week_aud": 700,
            "bedrooms": 1,
        },
        {
            "observation_id": "obs-2",
            "listing_key": "rea:2",
            "building_key": "118 kavanagh st|southbank|VIC|3006",
            "listing_state": "active",
            "rent_per_week_aud": 800,
            "bedrooms": 2,
        },
        {
            "observation_id": "obs-3",
            "listing_key": "rea:3",
            "building_key": "118 kavanagh st|southbank|VIC|3006",
            "listing_state": "leased_or_unavailable",
            "rent_per_week_aud": 750,
            "bedrooms": 2,
        },
    ]

    snapshots = module.building_price_snapshot_rows(targets, observations, "2026-04-29T00:00:00Z", "run-1")

    first = snapshots[0]
    assert first["building_price_snapshot_id"]
    assert first["building_price_content_hash"]
    assert first["observed_listing_count"] == 3
    assert first["active_listing_count"] == 2
    assert first["unavailable_listing_count"] == 1
    assert first["rent_min_per_week_aud"] == 700
    assert first["rent_median_per_week_aud"] == 750
    assert first["rent_mean_per_week_aud"] == 750
    assert first["rent_max_per_week_aud"] == 800
    assert first["active_rents_per_week_aud"] == [700, 800]
    assert first["bedroom_rent_summary"]["1"]["rent_median_per_week_aud"] == 700
    assert first["bedroom_rent_summary"]["2"]["rent_median_per_week_aud"] == 800
    assert snapshots[1]["snapshot_status"] == "no_active_rent_observed"


def test_retry_backoff_seconds_exponential_and_capped(monkeypatch):
    module = load_module()

    monkeypatch.setenv("REA_BUILDING_RENTALS_RETRY_BASE_DELAY_SEC", "5")
    monkeypatch.setenv("REA_BUILDING_RENTALS_RETRY_MAX_DELAY_SEC", "12")

    assert module.retry_backoff_seconds(1) == 5
    assert module.retry_backoff_seconds(2) == 10
    assert module.retry_backoff_seconds(3) == 12
    assert module.retryable_failure_kind("http_429_or_too_many_requests") is True
    assert module.retryable_failure_kind("page_not_found_or_removed") is False


def test_removed_observation_from_previous_known_listing_keeps_old_record_context():
    module = load_module()
    target = {
        "building_key": "118 kavanagh st|southbank|VIC|3006",
        "building_address": "118 Kavanagh St, Southbank VIC 3006",
        "street_address": "118 Kavanagh St",
        "suburb": "Southbank",
        "state": "VIC",
        "postcode": "3006",
        "source_airbnb_listing_ids": ["abc"],
        "source_airbnb_nicknames": ["118 kav"],
        "source_airbnb_listing_count": 1,
    }
    previous = module.with_observation_identity(
        {
            "run_id": "run-1",
            "observed_at": "2026-04-28T00:00:00Z",
            "building_key": target["building_key"],
            "building_address": target["building_address"],
            "rea_listing_id": "444003228",
            "listing_key": "rea:444003228",
            "rea_listing_url": "https://www.realestate.com.au/property-apartment-vic-southbank-444003228",
            "listing_state": "active",
            "rent_per_week_aud": 760,
            "listing_address": "2210/118 Kavanagh St, Southbank VIC 3006",
            "unit_identifier": "2210",
        }
    )
    failure = {
        "failure_kind": "page_not_found_or_removed",
        "title": "Page not found",
        "text_sample": "Sorry, this property could not be found",
    }

    observation = module.removed_observation_from_previous(
        target,
        previous,
        "2026-04-29T00:00:00Z",
        "run-2",
        {
            "url": "https://www.realestate.com.au/property-apartment-vic-southbank-444003228",
            "source": "known_previous_listing",
            "query": None,
        },
        failure,
    )

    assert observation["run_id"] == "run-2"
    assert observation["listing_key"] == "rea:444003228"
    assert observation["listing_state"] == "removed_or_unknown"
    assert observation["available_flag"] is False
    assert observation["unavailable_reason"] == "page_not_found_or_removed"
    assert observation["listing_lifecycle_evidence"] == "known_url_page_not_found_from_previous_observation"
    assert observation["listing_lifecycle_confidence"] == "medium"
    assert observation["rent_per_week_aud"] is None
    assert observation["last_known_rent_per_week_aud"] == 760
    assert observation["last_known_listing_state"] == "active"
    assert observation["removed_detection_failure_kind"] == "page_not_found_or_removed"
    assert observation["match_confidence"] == "previous_observation_same_building"
    assert observation["observation_id"] != previous["observation_id"]


def test_checkpoint_does_not_downgrade_successful_page_on_failed_retry(tmp_path):
    module = load_module()
    path = tmp_path / "checkpoint.json"
    key = "page-1"

    module.mark_checkpoint(path, "search_pages", {"checkpoint_key": key, "status": "ok", "failure_kind": None})
    module.mark_checkpoint(path, "search_pages", {"checkpoint_key": key, "status": "failed", "failure_kind": "http_429_or_too_many_requests"})

    data = json.loads(path.read_text())
    assert data["search_pages"][0]["status"] == "ok"
    assert data["search_pages"][0]["failure_kind"] is None
    assert data["search_pages"][0]["last_retry_failure_kind"] == "http_429_or_too_many_requests"


def test_complete_run_snapshot_detection(tmp_path):
    module = load_module()
    path = tmp_path / "run.json"

    assert module.complete_run_snapshot_exists(path) is False
    path.write_text(json.dumps({"run_complete": False}))
    assert module.complete_run_snapshot_exists(path) is False
    path.write_text(json.dumps({"run_complete": True}))
    assert module.complete_run_snapshot_exists(path) is True


def test_detail_address_contradiction_suppresses_search_card_observation():
    module = load_module()
    observations = [
        {
            "listing_key": "rea:443931304",
            "rea_listing_url": "https://www.realestate.com.au/property-apartment-vic-southbank-443931304",
            "building_key": "118 kavanagh st|southbank|VIC|3006",
        }
    ]
    failures = [
        {
            "failure_kind": "listing_address_not_in_target_building",
            "rea_listing_url": "https://www.realestate.com.au/property-apartment-vic-southbank-443931304",
            "parsed_listing_building_key": "60 kavanagh st|southbank|VIC|3006",
        }
    ]

    assert module.filter_detail_rejected_observations(observations, failures) == []


def test_page_failure_detects_chrome_http_429_error_text():
    module = load_module()

    assert module.page_failure({"title": "www.realestate.com.au", "text": "This page isn't working\nHTTP ERROR 429"}) == "http_429_or_too_many_requests"
    assert module.page_failure({"title": "Page not found", "text": "Sorry, this property could not be found"}) == "page_not_found_or_removed"
