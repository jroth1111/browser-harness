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
    receipt = {
        "schema_version": 1,
        "observed_at": observed_at or _utc_now(),
        "source_type": source_type,
        "source_context": dict(source_context or {}),
        "backend": backend,
        "fields_found": sorted(set(fields_found or ())),
        "fields_missing": sorted(set(fields_missing or ())),
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
    found = set(receipt.get("fields_found") or ())
    missing_fields = set(receipt.get("fields_missing") or ())
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
    if block.get("blocked") and receipt.get("canonical"):
        raise ValueError("blocked source cannot be canonical")
    if receipt.get("diagnostic_only") and receipt.get("canonical"):
        raise ValueError("source cannot be both diagnostic_only and canonical")
    if receipt.get("diagnostic_only") and not receipt.get("fallback_reason"):
        raise ValueError("diagnostic_only receipts require fallback_reason")
    return True
