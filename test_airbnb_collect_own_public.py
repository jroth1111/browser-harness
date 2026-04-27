import importlib.util
from pathlib import Path

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
    assert parsed["5_star_pct"] == 87
    assert parsed["5_star_count_estimate"] == 110
    assert parsed["1_star_pct"] == 1
    assert parsed["parking_flag"] is True
    assert parsed["pool_spa_flag"] is True
    assert "wifi" in parsed["visible_amenities_core"]


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
        """
    )

    assert parsed["visible_location_label"] == "Apartment in Southbank"
    assert parsed["visible_title_short"] == "Skyline 2BR with parking"
    assert parsed["visible_price_total"] == 738
    assert parsed["visible_rating"] == 4.91
    assert parsed["visible_review_count"] == 44
    assert parsed["visible_badge"] == "Guest favourite"


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


@pytest.mark.parametrize("loader", [load_own_public_module, load_competitors_module])
def test_public_ranking_collectors_refuse_logged_in_airbnb_cookie_names(loader):
    module = loader()
    module.browser_cookies = lambda urls: [{"name": "bev"}, {"name": "_aat"}, {"name": "li"}]

    with pytest.raises(SystemExit) as exc:
        module.assert_logged_out_public_session()

    assert "Refusing" in str(exc.value)
    assert "logged-in Airbnb session" in str(exc.value)
