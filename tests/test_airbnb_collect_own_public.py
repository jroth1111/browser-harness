import importlib.util
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest


def load_module(path, name):
    path = Path(path)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_own_public_module():
    return load_module("domain-skills/airbnb/scripts/collect_own_public.py", "airbnb_collect_own_public")


def load_competitors_module():
    return load_module("domain-skills/airbnb/scripts/collect_competitors.py", "airbnb_collect_competitors")


def test_public_page_failure_tolerates_malformed_block_metadata():
    own = load_own_public_module()
    competitors = load_competitors_module()

    status = {"title": "Search results", "text": "Normal page", "block": "not-an-object"}

    assert own.page_failure(status) is None
    assert competitors.page_failure(status) is None


def test_parse_listing_text_extracts_review_distribution_and_categories():
    module = load_own_public_module()
    parsed = module.parse_listing_text(
        """
        Stylish apartment in Melbourne
        5 guests \u00b7 2 bedrooms \u00b7 3 beds \u00b7 2 baths
        Rated 4.83 out of 5 stars from 127 reviews
        Cleanliness
        4.8
        Accuracy
        4.9
        Check-in
        4.7
        Communication
        4.9
        Location
        4.8
        Value
        4.6
        5 stars, 87% of reviews
        4 stars, 10% of reviews
        1 star, 1% of reviews
        Wifi
        Free parking
        Pool
        """
    )

    assert parsed["max_guests"] == 5
    assert parsed["bedrooms"] == 2
    assert parsed["beds"] == 3
    assert parsed["bathrooms"] == 2
    assert parsed["overall_rating"] == 4.83
    assert parsed["review_count"] == 127
    assert parsed["cleanliness_rating"] == 4.8
    assert parsed["accuracy_rating"] == 4.9
    assert parsed["checkin_rating"] == 4.7
    assert parsed["rating_category_source"] == "category_widget"
    assert parsed["5_star_pct"] == 87
    assert parsed["5_star_count_estimate"] == 110
    assert parsed["1_star_pct"] == 1
    assert parsed["star_distribution_source"] == "percentage_widget"
    assert parsed["star_distribution_confidence"] == "percentage_estimate"
    assert parsed["visible_individual_review_star_count"] == 0
    assert parsed["parking_flag"] is True
    assert parsed["pool_spa_flag"] is True
    assert "wifi" in parsed["visible_amenities_core"]


def test_parse_listing_text_does_not_confuse_host_reviews_for_listing_reviews():
    module = load_own_public_module()
    parsed = module.parse_listing_text(
        """
        New listing in Southbank
        New listing
        Entire rental unit in Southbank, Australia
        5 guests \u00b7 2 bedrooms \u00b7 2 beds \u00b7 2 baths
        No reviews (yet)
        This host has 1,039 reviews for other places to stay.
        Hosted by Jacob
        Meet your host
        Jacob
        Host
        1 review
        5.0 out of 5 average rating
        5 years of hosting
        """
    )

    assert parsed["review_count"] == 0
    assert parsed["overall_rating"] is None
    assert parsed["rating_display_state"] == "no_reviews_yet"
    assert parsed["star_distribution_source"] == "not_visible"
    assert parsed["star_distribution_confidence"] == "not_available"
    assert parsed["visible_individual_review_star_count"] == 0
    assert parsed["rating_category_source"] == "not_visible"
    assert parsed.get("5_star_pct") is None


def test_parse_listing_text_uses_visible_individual_review_distribution_for_low_review_count():
    module = load_own_public_module()
    parsed = module.parse_listing_text(
        """
        Melbourne CBD Stay
        1 review
        Entire rental unit in Melbourne, Australia
        7 guests \u00b7 3 bedrooms \u00b7 4 beds \u00b7 2 baths
        Average rating will appear after 3 reviews
        Julia
        Rating, 5 stars
        March 2026
        We had a great stay.
        Meet your host
        Msa
        Host
        1,039 reviews
        4.44 out of 5 average rating
        """
    )

    assert parsed["review_count"] == 1
    assert parsed["overall_rating"] is None
    assert parsed["rating_display_state"] == "hidden_until_minimum_reviews"
    assert parsed["rating_category_source"] == "not_visible"
    assert parsed["5_star_pct"] == 100
    assert parsed["5_star_count_estimate"] == 1
    assert parsed["star_distribution_source"] == "visible_individual_review_stars"
    assert parsed["star_distribution_confidence"] == "complete_visible_review_rows"
    assert parsed["visible_individual_review_star_count"] == 1
    assert len(parsed["visible_review_rows"]) == 1
    assert parsed["visible_review_rows"][0]["reviewer_name_visible"] == "Julia"
    assert parsed["visible_review_rows"][0]["review_rating"] == 5
    assert parsed["visible_review_rows"][0]["review_date_label"] == "March 2026"
    assert parsed["visible_review_rows"][0]["review_text"] == "We had a great stay."
    assert parsed["visible_review_rows"][0]["review_row_confidence"] == "visible_review_row_with_text"


@pytest.mark.parametrize("loader", [load_own_public_module, load_competitors_module])
def test_parse_listing_text_tracks_partial_visible_individual_review_stars(loader):
    module = loader()
    parsed = module.parse_listing_text(
        """
        Melbourne CBD Stay
        12 reviews
        Entire rental unit in Melbourne, Australia
        7 guests \u00b7 3 bedrooms \u00b7 4 beds \u00b7 2 baths
        Julia
        Rating, 5 stars
        March 2026
        Great stay.
        Tom
        Rating, 4 stars
        February 2026
        Good location.
        Meet your host
        Msa
        Host
        1,039 reviews
        4.44 out of 5 average rating
        """
    )

    assert parsed["review_count"] == 12
    assert parsed["star_distribution_source"] == "partial_visible_individual_review_stars"
    assert parsed["star_distribution_confidence"] == "insufficient_visible_review_rows"
    assert parsed["visible_individual_review_star_count"] == 2
    assert parsed.get("5_star_pct") is None


@pytest.mark.parametrize("loader", [load_own_public_module, load_competitors_module])
def test_listing_review_count_prefers_numeric_count_over_stray_no_review_copy(loader):
    module = loader()
    parsed = module.parse_listing_text(
        """
        Melbourne CBD Stay
        4 reviews
        Rated 5.0 out of 5 from 4 reviews.
        No reviews yet
        Julia
        Rating, 5 stars
        March 2026
        Great stay.
        Tom
        Rating, 5 stars
        February 2026
        Good location.
        Sue
        Rating, 5 stars
        January 2026
        Spotless.
        Lee
        Rating, 5 stars
        December 2025
        Easy check-in.
        Meet your host
        Msa
        Host
        1,039 reviews
        """
    )

    assert parsed["review_count"] == 4
    assert parsed["rating_display_state"] == "average_visible"
    assert parsed["visible_individual_review_star_count"] == 4


def test_own_public_parse_listing_text_extracts_visible_review_rows():
    module = load_own_public_module()
    parsed = module.parse_listing_text(
        """
        Melbourne CBD Stay
        12 reviews
        Entire rental unit in Melbourne, Australia
        7 guests \u00b7 3 bedrooms \u00b7 4 beds \u00b7 2 baths
        Julia
        Rating, 5 stars
        March 2026
        Great stay.
        Tom
        Rating, 4 stars
        February 2026
        Good location.
        Meet your host
        Msa
        Host
        1,039 reviews
        4.44 out of 5 average rating
        """
    )

    assert len(parsed["visible_review_rows"]) == 2
    assert [row["reviewer_name_visible"] for row in parsed["visible_review_rows"]] == ["Julia", "Tom"]
    assert [row["review_rating"] for row in parsed["visible_review_rows"]] == [5, 4]
    assert [row["review_date_label"] for row in parsed["visible_review_rows"]] == ["March 2026", "February 2026"]
    assert parsed["visible_review_rows"][0]["review_text"] == "Great stay."
    assert parsed["visible_review_rows"][1]["review_text"] == "Good location."
    assert "location" in parsed["visible_review_rows"][1]["review_theme_tags"]


def test_visible_review_id_is_stable_and_listing_scoped():
    module = load_own_public_module()
    row = {
        "reviewer_name_visible": "Julia",
        "review_rating": 5,
        "review_date_label": "March 2026",
        "review_text": "We had a great stay.",
    }

    assert module.visible_review_id("100", row) == module.visible_review_id("100", row)
    assert module.visible_review_id("100", row) != module.visible_review_id("200", row)


def test_parse_card_text_extracts_target_search_card_fields():
    module = load_own_public_module()
    parsed = module.parse_card_text(
        """
        26 to 30 May
        26\u201330 May
        29 May\u2009 to \u20091 June
        Apartment in Southbank
        Skyline 2BR with parking
        2 bedrooms
        3 beds
        2 baths
        $738 AUD total
        4.91 out of 5 average rating, 44 reviews
        Guest favourite
        """,
        photo_items=[
            "Photo of secure parking bay",
            "Photo of city view bedroom",
            "Photo of kitchen",
        ],
    )

    assert parsed["visible_location_label"] == "Apartment in Southbank"
    assert parsed["visible_title_short"] == "Skyline 2BR with parking"
    assert parsed["visible_price_total"] == 738
    assert parsed["visible_rating"] == 4.91
    assert parsed["visible_review_count"] == 44
    assert parsed["visible_badge"] == "Guest favourite"
    assert parsed["hero_photo_subject_tag"] == "parking"
    assert parsed["first_five_photo_subjects"] == ["parking", "view", "kitchen"]
    assert parsed["obvious_differentiator_tags"] == ["parking", "view"]


def test_competitor_card_parser_skips_airbnb_date_lines():
    module = load_competitors_module()
    parsed = module.parse_card_text(
        """
        29 May\u2009 to \u20091 June
        Apartment in Carlton
        Central 3BR with two car parks
        3 bedrooms
        4 beds
        2 baths
        $1,147 AUD total
        4.93 out of 5 average rating, 337 reviews
        """
    )

    assert parsed["visible_location_label"] == "Apartment in Carlton"
    assert parsed["visible_title_short"] == "Central 3BR with two car parks"
    assert parsed["visible_price_total"] == 1147
    assert parsed["visible_rating"] == 4.93
    assert parsed["visible_review_count"] == 337


def test_competitor_listing_parser_does_not_confuse_host_reviews():
    module = load_competitors_module()
    parsed = module.parse_listing_text(
        """
        Riverside Retreat
        1 review
        Entire rental unit in Richmond, Australia
        4 guests \u00b7 2 bedrooms \u00b7 2 beds \u00b7 2 baths
        Average rating will appear after 3 reviews
        Ron
        Rating, 5 stars
        January 2024
        Amazing place.
        Meet your host
        Msa
        Host
        1,039 reviews
        4.44 out of 5 average rating
        """
    )

    assert parsed["review_count"] == 1
    assert parsed["rating"] is None
    assert parsed["rating_display_state"] == "hidden_until_minimum_reviews"
    assert parsed["5_star_pct"] == 100


@pytest.mark.parametrize("loader", [load_own_public_module, load_competitors_module])
def test_listing_parser_adds_photo_product_evidence(loader):
    module = loader()
    parsed = module.parse_listing_text(
        """
        Family apartment with parking and pool
        Entire rental unit in Melbourne, Australia
        6 guests \u00b7 3 bedrooms \u00b7 4 beds \u00b7 2 baths
        24 photos
        Free parking, pool, kitchen, dedicated workspace.
        """,
        photo_items=[
            {"alt": "Secure garage parking"},
            {"alt": "Primary bedroom with queen bed"},
            {"alt": "Bathroom with walk-in shower"},
            {"alt": "Kitchen with full oven"},
            {"alt": "Dedicated workspace by the window"},
        ],
    )

    assert parsed["hero_photo_subject"] == "parking"
    assert parsed["first_five_photo_subjects"] == ["parking", "bedroom", "bathroom", "kitchen", "workspace"]
    assert parsed["bedroom_proof_flag"] is True
    assert parsed["bathroom_proof_flag"] is True
    assert parsed["parking_proof_flag"] is True
    assert "pool_or_spa" in parsed["missing_photo_proof"]


@pytest.mark.parametrize("loader", [load_own_public_module, load_competitors_module])
def test_merge_search_cards_preserves_first_seen_rank_window(loader):
    module = loader()
    seen = {}

    assert module.merge_search_cards(
        seen,
        [
            {"href": "https://www.airbnb.com.au/rooms/100", "room_id": "100", "text": "first"},
            {"href": "https://www.airbnb.com.au/rooms/200", "room_id": "200", "text": "second"},
        ],
        scroll_depth=0,
    ) == 2
    assert module.merge_search_cards(
        seen,
        [
            {"href": "https://www.airbnb.com.au/rooms/100", "room_id": "100", "text": "duplicate"},
            {"href": "https://www.airbnb.com.au/rooms/300", "room_id": "300", "text": "third"},
        ],
        scroll_depth=2,
    ) == 1

    assert list(seen) == ["100", "200", "300"]
    assert seen["100"]["text"] == "first"
    assert seen["300"]["page_number_or_scroll_depth"] == 2


@pytest.mark.parametrize("loader", [load_own_public_module, load_competitors_module])
def test_collect_search_cards_marks_scrolled_scope_only_after_scroll(loader):
    module = loader()
    batches = iter([
        [{"href": "https://www.airbnb.com.au/rooms/100", "room_id": "100", "text": "first"}],
        [{"href": "https://www.airbnb.com.au/rooms/200", "room_id": "200", "text": "second"}],
    ])
    module.extract_search_cards_from_page = lambda: next(batches)
    module.wait = lambda seconds: None

    def fake_js(expression):
        if "window.scrollBy" in expression:
            return None
        if "Math.max(document.body.scrollHeight" in expression:
            return {"y": 0, "h": 100, "page": 1000}
        return {"y": 100}

    module.js = fake_js
    cards, meta = module.collect_search_cards_from_page(max_cards=2, max_scrolls=1, pause=0)

    assert [card["room_id"] for card in cards] == ["100", "200"]
    assert [card["page_number_or_scroll_depth"] for card in cards] == [0, 1]
    assert meta["search_scrolls_attempted"] == 1
    assert meta["rank_collection_scope"] == "scrolled_result_window"


@pytest.mark.parametrize("loader", [load_own_public_module, load_competitors_module])
def test_collect_search_cards_marks_initial_scope_when_limit_met(loader):
    module = loader()
    module.extract_search_cards_from_page = lambda: [
        {"href": "https://www.airbnb.com.au/rooms/100", "room_id": "100", "text": "first"}
    ]

    cards, meta = module.collect_search_cards_from_page(max_cards=1, max_scrolls=3, pause=0)

    assert [card["room_id"] for card in cards] == ["100"]
    assert meta["search_scrolls_attempted"] == 0
    assert meta["rank_collection_scope"] == "initial_viewport"


def test_own_public_rank_observation_confidence_uses_bounded_window_terms():
    module = load_own_public_module()

    assert module.rank_observation_confidence({"listing_url": "https://www.airbnb.com.au/rooms/100"}) == "matched_in_bounded_result_window"
    assert module.rank_observation_confidence(None) == "not_seen_in_bounded_result_window"


@pytest.mark.parametrize("loader", [load_own_public_module, load_competitors_module])
def test_public_ranking_collectors_refuse_logged_in_airbnb_cookie_names(loader):
    module = loader()
    module.browser_cookies = lambda urls: [{"name": "bev"}, {"name": "_aat"}, {"name": "li"}]

    with pytest.raises(SystemExit) as exc:
        module.assert_logged_out_public_session()

    assert "Refusing" in str(exc.value)
    assert "logged-in Airbnb session" in str(exc.value)


@pytest.mark.parametrize("loader", [load_own_public_module, load_competitors_module])
def test_public_ranking_collectors_skip_malformed_cookie_rows(loader):
    module = loader()
    module.browser_cookies = lambda urls: ["not-a-cookie", {"name": "bev"}]

    result = module.assert_logged_out_public_session()

    assert result["checked"] is True
    assert result["auth_cookie_names_present"] == []


@pytest.mark.parametrize("loader", [load_own_public_module, load_competitors_module])
def test_public_search_url_defaults_to_entire_home(loader):
    module = loader()
    listing = {
        "address": "500 Elizabeth St, Melbourne VIC 3000, Australia",
        "location_label": "Melbourne, Victoria, Australia",
        "max_guests": 8,
        "bedrooms": 3,
    }

    query = parse_qs(urlsplit(module.search_url(listing, "2026-05-29", 3)).query)

    assert query["room_types[]"] == ["Entire home/apt"]
    assert query["min_bedrooms"] == ["3"]
    assert query["adults"] == ["8"]


def test_competitor_search_url_applies_optional_price_band():
    module = load_competitors_module()
    listing = {
        "address": "500 Elizabeth St, Melbourne VIC 3000, Australia",
        "location_label": "Melbourne, Victoria, Australia",
        "max_guests": 4,
        "bedrooms": 2,
    }

    query = parse_qs(urlsplit(module.search_url(
        listing,
        "2026-05-29",
        3,
        price_band={"price_min": 251, "price_max": 500, "label": "251-500"},
    )).query)

    assert query["price_min"] == ["251"]
    assert query["price_max"] == ["500"]
    assert module.search_run_id("100", "2026-05-29", 3, "251-500").endswith("-price-251-500")
