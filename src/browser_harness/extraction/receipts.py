"""Reusable source-selection receipt helpers.

Receipts are compact, redacted evidence records for why a workflow used a
particular source/backend for a field set. They are intentionally plain dicts so
domain scripts can write them as JSON without depending on a framework.
"""

from datetime import datetime, timezone


ALLOWED_SOURCE_TYPES = {
    "export",
    "api",
    "embedded_json",
    "browser_session_http",
    "browser_ui",
    "http",
    "hybrid",
    "local",
}

REQUIRED_BLOCK_FIELDS = {"blocked", "kind", "evidence"}
REQUIRED_RECEIPT_FIELDS = {
    "schema_version",
    "observed_at",
    "source_type",
    "source_context",
    "backend",
    "fields_found",
    "fields_missing",
    "block",
    "fallback_reason",
    "canonical",
    "diagnostic_only",
}


def _utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_field_names(value, name):
    if value is None:
        return []
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple, set)):
        raise ValueError(f"{name} must be a list of field-name strings")
    fields = []
    for field in value:
        if not isinstance(field, str) or not field:
            raise ValueError(f"{name} must contain non-empty field-name strings")
        fields.append(field)
    return sorted(set(fields))


def build_source_receipt(
    *,
    source_type,
    source_context,
    backend,
    fields_found,
    fields_missing=(),
    block=None,
    fallback_reason="",
    canonical=False,
    diagnostic_only=True,
    observed_at=None,
    source_url_or_endpoint_shape="",
    notes="",
):
    """Build and validate a source-selection receipt dict."""
    if not isinstance(source_context, dict) or not source_context:
        raise ValueError("source_context must be a non-empty object")
    receipt = {
        "schema_version": 1,
        "observed_at": observed_at or _utc_now(),
        "source_type": source_type,
        "source_context": dict(source_context),
        "backend": backend,
        "fields_found": _normalize_field_names(fields_found, "fields_found"),
        "fields_missing": _normalize_field_names(fields_missing, "fields_missing"),
        "block": block or {"blocked": False, "kind": None, "evidence": []},
        "fallback_reason": fallback_reason,
        "canonical": bool(canonical),
        "diagnostic_only": bool(diagnostic_only),
    }
    if source_url_or_endpoint_shape:
        receipt["source_url_or_endpoint_shape"] = source_url_or_endpoint_shape
    if notes:
        receipt["notes"] = notes
    validate_source_receipt(receipt)
    return receipt


def validate_source_receipt(receipt):
    """Return True for valid receipts, otherwise raise ValueError."""
    if not isinstance(receipt, dict):
        raise ValueError("source receipt must be an object")
    missing = REQUIRED_RECEIPT_FIELDS - set(receipt)
    if missing:
        raise ValueError(f"source receipt missing required fields: {sorted(missing)}")
    if receipt.get("schema_version") != 1:
        raise ValueError("source receipt schema_version must be 1")
    if receipt.get("source_type") not in ALLOWED_SOURCE_TYPES:
        raise ValueError(f"unsupported source_type: {receipt.get('source_type')!r}")
    if not isinstance(receipt.get("source_context"), dict) or not receipt["source_context"]:
        raise ValueError("source_context must be a non-empty object")
    if not receipt.get("backend"):
        raise ValueError("backend is required")
    found = set(_normalize_field_names(receipt.get("fields_found"), "fields_found"))
    missing_fields = set(_normalize_field_names(receipt.get("fields_missing"), "fields_missing"))
    overlap = found & missing_fields
    if overlap:
        raise ValueError(f"fields cannot be both found and missing: {sorted(overlap)}")
    if not found and not missing_fields:
        raise ValueError("at least one found or missing field is required")
    block = receipt.get("block")
    if not isinstance(block, dict) or not REQUIRED_BLOCK_FIELDS <= set(block):
        raise ValueError("block must include blocked, kind, and evidence")
    if not isinstance(block.get("blocked"), bool):
        raise ValueError("block.blocked must be a boolean")
    if not isinstance(block.get("evidence"), list):
        raise ValueError("block.evidence must be a list")
    if block.get("blocked") and not block.get("kind"):
        raise ValueError("blocked sources require block.kind")
    if not isinstance(receipt.get("canonical"), bool):
        raise ValueError("canonical must be a boolean")
    if not isinstance(receipt.get("diagnostic_only"), bool):
        raise ValueError("diagnostic_only must be a boolean")
    if block.get("blocked") and receipt.get("canonical"):
        raise ValueError("blocked source cannot be canonical")
    if receipt.get("diagnostic_only") and receipt.get("canonical"):
        raise ValueError("source cannot be both diagnostic_only and canonical")
    if receipt.get("diagnostic_only") and not receipt.get("fallback_reason"):
        raise ValueError("diagnostic_only receipts require fallback_reason")
    return True
