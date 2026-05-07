import pytest

from browser_harness.source_receipts import build_source_receipt, validate_source_receipt


def test_build_source_receipt_accepts_canonical_api_source():
    receipt = build_source_receipt(
        source_type="api",
        source_context={"domain": "example.com", "auth_state": "logged_out"},
        backend={"kind": "chromium", "path_type": "api"},
        fields_found=["price", "title", "title"],
        fields_missing=["seller_rating"],
        canonical=True,
        diagnostic_only=False,
        observed_at="2026-05-04T00:00:00Z",
        source_url_or_endpoint_shape="https://example.com/api/search?q={query}",
    )

    assert receipt["fields_found"] == ["price", "title"]
    assert receipt["canonical"] is True
    assert receipt["diagnostic_only"] is False
    assert validate_source_receipt(receipt) is True


def test_diagnostic_source_receipt_requires_fallback_reason():
    with pytest.raises(ValueError, match="fallback_reason"):
        build_source_receipt(
            source_type="http",
            source_context={"domain": "example.com"},
            backend="plain_http",
            fields_found=[],
            fields_missing=["title"],
            diagnostic_only=True,
        )


def test_blocked_source_receipt_cannot_be_canonical():
    with pytest.raises(ValueError, match="blocked source cannot be canonical"):
        build_source_receipt(
            source_type="browser_ui",
            source_context={"domain": "example.com"},
            backend={"kind": "chromium"},
            fields_found=["title"],
            block={"blocked": True, "kind": "auth_gate", "evidence": ["/login"]},
            canonical=True,
            diagnostic_only=False,
        )


def test_source_receipt_rejects_scalar_block_evidence():
    receipt = build_source_receipt(
        source_type="api",
        source_context={"domain": "example.com"},
        backend={"kind": "chromium"},
        fields_found=["title"],
        canonical=True,
        diagnostic_only=False,
    )
    receipt["block"]["evidence"] = "/login"

    with pytest.raises(ValueError, match="block.evidence must be a list"):
        validate_source_receipt(receipt)


def test_blocked_source_receipt_requires_block_kind():
    with pytest.raises(ValueError, match="blocked sources require block.kind"):
        build_source_receipt(
            source_type="browser_ui",
            source_context={"domain": "example.com"},
            backend={"kind": "chromium"},
            fields_found=["title"],
            block={"blocked": True, "kind": "", "evidence": ["/login"]},
            canonical=False,
            diagnostic_only=False,
        )


def test_source_receipt_rejects_overlapping_found_and_missing_fields():
    with pytest.raises(ValueError, match="both found and missing"):
        build_source_receipt(
            source_type="embedded_json",
            source_context={"domain": "example.com"},
            backend="chromium",
            fields_found=["price"],
            fields_missing=["price"],
            canonical=True,
            diagnostic_only=False,
        )


def test_source_receipt_rejects_unknown_source_type():
    with pytest.raises(ValueError, match="unsupported source_type"):
        build_source_receipt(
            source_type="private_magic",
            source_context={"domain": "example.com"},
            backend="chromium",
            fields_found=["title"],
            fallback_reason="diagnostic only",
        )


def test_source_receipt_rejects_scalar_field_lists():
    receipt = build_source_receipt(
        source_type="api",
        source_context={"domain": "example.com"},
        backend={"kind": "chromium"},
        fields_found=["title"],
        canonical=True,
        diagnostic_only=False,
    )

    receipt["fields_found"] = "title"

    with pytest.raises(ValueError, match="fields_found must be a list"):
        validate_source_receipt(receipt)


def test_source_receipt_rejects_non_string_field_names():
    with pytest.raises(ValueError, match="non-empty field-name strings"):
        build_source_receipt(
            source_type="api",
            source_context={"domain": "example.com"},
            backend={"kind": "chromium"},
            fields_found=["title", None],
            canonical=True,
            diagnostic_only=False,
        )
