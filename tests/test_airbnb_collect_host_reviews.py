import importlib.util
from pathlib import Path


def load_host_reviews_module():
    path = Path("domain-skills/airbnb/scripts/collect_host_reviews.py")
    spec = importlib.util.spec_from_file_location("airbnb_collect_host_reviews", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parse_host_review_json_normalizes_private_review_rows():
    module = load_host_reviews_module()
    payload = {
        "data": {
            "reviews": {
                "totalCount": 2,
                "items": [
                    {
                        "reviewId": "r-1",
                        "listingId": "100",
                        "reservationId": "HM123",
                        "reviewDate": "2026-04-01T10:00:00Z",
                        "stayMonth": "March 2026",
                        "overallRating": 5,
                        "categoryRatings": {"cleanliness": 5, "checkIn": 4, "value": 5},
                        "reviewText": "Spotless apartment and easy check-in.",
                        "hostResponse": {
                            "text": "Thanks for staying with us.",
                            "createdAt": "2026-04-02T09:00:00Z",
                        },
                    },
                    {
                        "reviewId": "r-2",
                        "listingId": "100",
                        "reservationId": "HM124",
                        "reviewDate": "2026-04-03",
                        "overallRating": "4",
                        "reviewText": "Good value and quiet.",
                    },
                ],
            }
        }
    }

    rows, total = module.parse_host_review_json(
        payload,
        listing_id="100",
        observed_at="2026-04-28T00:00:00Z",
        source_url="https://www.airbnb.com.au/hosting/reviews?listingId=100",
    )

    assert total == 2
    assert [row["review_id"] for row in rows] == ["r-1", "r-2"]
    assert rows[0]["listing_id"] == "100"
    assert rows[0]["reservation_id"] == "HM123"
    assert rows[0]["review_date"] == "2026-04-01"
    assert rows[0]["category_ratings"] == {"cleanliness": 5, "checkin": 4, "value": 5}
    assert rows[0]["host_response_present"] is True
    assert rows[0]["host_response_date"] == "2026-04-02"
    assert rows[0]["source_family"] == "host_private"
    assert rows[0]["surface_class"] == "host_private"
    assert rows[0]["auth_context"] == "host_private_browser_session"
    assert {"cleanliness", "checkin"} <= set(rows[0]["review_theme_tags"])


def test_review_export_confidence_never_overclaims_without_total():
    module = load_host_reviews_module()

    assert module.review_export_confidence(3, None) == "rows_collected_without_known_total"
    assert module.review_export_confidence(0, None) == "no_rows_without_known_total"
    assert module.review_export_confidence(3, 5) == "partial_against_host_total"
    assert module.review_export_confidence(5, 5) == "complete_against_host_total"
    assert module.review_export_confidence(0, 0) == "complete_no_reviews"


def test_rendered_text_parser_is_sample_only_without_known_total():
    module = load_host_reviews_module()

    rows = module.parse_host_review_text(
        """
        Julia
        Rating, 5 stars
        March 2026
        Great location and spotless rooms.
        Tom
        Rating, 4 stars
        February 2026
        Good value.
        """,
        listing_id="100",
        observed_at="2026-04-28T00:00:00Z",
        source_url="https://www.airbnb.com.au/hosting/reviews?listingId=100",
    )

    assert len(rows) == 2
    assert [row["overall_rating"] for row in rows] == [5, 4]
    assert rows[0]["review_row_source"] == "host_reviews_rendered_text"
    assert module.review_export_confidence(len(rows), None) == "rows_collected_without_known_total"
