"""Validation helpers for four-state extraction records."""

UNOBSERVABLE = "__UNOBSERVABLE__"
FIELD_STATES = {"value", "absent", "unobservable", "not_checked"}


def classify_field(record, field, *, allow_empty_string=False):
    """Classify one extracted field using the four-state contract."""
    if field not in record:
        return "not_checked"
    value = record[field]
    if value == UNOBSERVABLE:
        return "unobservable"
    if value is None:
        return "absent"
    if value == "" and not allow_empty_string:
        raise ValueError(f"{field}: empty string is ambiguous; use null, omit the key, or {UNOBSERVABLE!r}")
    return "value"


def validate_extraction_record(
    record,
    *,
    expected_fields,
    key_field=None,
    allow_empty_string=False,
    allow_unobservable_key=False,
):
    """Validate one extraction record and return `{field: state}`."""
    if not isinstance(record, dict):
        raise TypeError("extraction record must be a dict")
    states = {
        field: classify_field(record, field, allow_empty_string=allow_empty_string)
        for field in expected_fields
    }
    if key_field:
        key_state = states.get(key_field)
        if key_state is None:
            key_state = classify_field(record, key_field, allow_empty_string=allow_empty_string)
            states[key_field] = key_state
        if key_state != "value" and not (allow_unobservable_key and key_state == "unobservable"):
            raise ValueError(f"{key_field}: primary key must be a value, got {key_state}")
    return states


def summarize_extraction_coverage(
    records,
    *,
    expected_fields,
    key_field=None,
    allow_empty_string=False,
    allow_unobservable_key=False,
):
    """Return field-state counts and primary-key failure count for records."""
    summary = {
        field: {state: 0 for state in FIELD_STATES}
        for field in expected_fields
    }
    primary_key_failures = 0
    total = 0
    for record in records:
        total += 1
        try:
            states = validate_extraction_record(
                record,
                expected_fields=expected_fields,
                key_field=key_field,
                allow_empty_string=allow_empty_string,
                allow_unobservable_key=allow_unobservable_key,
            )
        except ValueError as error:
            if key_field and str(error).startswith(f"{key_field}:"):
                primary_key_failures += 1
                states = {
                    field: classify_field(record, field, allow_empty_string=allow_empty_string)
                    for field in expected_fields
                }
                if key_field not in states:
                    states[key_field] = classify_field(
                        record,
                        key_field,
                        allow_empty_string=allow_empty_string,
                    )
            else:
                raise
        for field, state in states.items():
            summary.setdefault(field, {s: 0 for s in FIELD_STATES})
            summary[field][state] += 1
    return {
        "records": total,
        "fields": summary,
        "primary_key_failures": primary_key_failures,
    }
