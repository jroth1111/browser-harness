import pytest

from browser_harness.extraction_contracts import (
    UNOBSERVABLE,
    classify_field,
    summarize_extraction_coverage,
    validate_extraction_record,
)


def test_classify_field_uses_four_state_contract():
    record = {
        "title": "Widget",
        "seller": None,
        "price": UNOBSERVABLE,
    }

    assert classify_field(record, "title") == "value"
    assert classify_field(record, "seller") == "absent"
    assert classify_field(record, "price") == "unobservable"
    assert classify_field(record, "not_applicable") == "not_checked"


def test_classify_field_rejects_ambiguous_empty_string():
    with pytest.raises(ValueError, match="empty string is ambiguous"):
        classify_field({"title": ""}, "title")


def test_validate_extraction_record_requires_primary_key_value():
    with pytest.raises(ValueError, match="primary key"):
        validate_extraction_record(
            {"title": None, "price": "$10"},
            expected_fields=["title", "price"],
            key_field="title",
        )


def test_validate_extraction_record_allows_unobservable_primary_key_when_blocked():
    states = validate_extraction_record(
        {"title": UNOBSERVABLE, "price": UNOBSERVABLE, "_block_reason": "auth_gate"},
        expected_fields=["title", "price"],
        key_field="title",
        allow_unobservable_key=True,
    )

    assert states == {"title": "unobservable", "price": "unobservable"}


def test_summarize_extraction_coverage_counts_states_and_key_failures():
    summary = summarize_extraction_coverage(
        [
            {"title": "A", "price": "$10", "seller": None},
            {"title": "B", "price": UNOBSERVABLE},
            {"title": None, "price": "$12", "seller": "Shop"},
        ],
        expected_fields=["title", "price", "seller"],
        key_field="title",
    )

    assert summary["records"] == 3
    assert summary["primary_key_failures"] == 1
    assert summary["fields"]["title"]["value"] == 2
    assert summary["fields"]["title"]["absent"] == 1
    assert summary["fields"]["price"]["unobservable"] == 1
    assert summary["fields"]["seller"]["not_checked"] == 1


def test_summarize_extraction_coverage_counts_failed_key_outside_expected_fields():
    summary = summarize_extraction_coverage(
        [
            {"id": None, "title": "A"},
        ],
        expected_fields=["title"],
        key_field="id",
    )

    assert summary["primary_key_failures"] == 1
    assert summary["fields"]["title"]["value"] == 1
    assert summary["fields"]["id"]["absent"] == 1


def test_validate_extraction_record_rejects_scalar_expected_fields():
    with pytest.raises(TypeError, match="expected_fields must be a list"):
        validate_extraction_record({"title": "A"}, expected_fields="title")


def test_summarize_extraction_coverage_rejects_non_string_expected_field():
    with pytest.raises(TypeError, match="non-empty field-name strings"):
        summarize_extraction_coverage([{"title": "A"}], expected_fields=["title", None])
