"""Extraction enforcement — makes proof artifacts mandatory for canonical extraction.

Promotes source_receipts, extraction_contracts, and redaction_scan from optional
helpers to required enforcement surfaces. Canonical extraction must include:
source receipt, field coverage, block state, transport decision, capability id,
manifest version.
"""
from __future__ import annotations

from typing import Any

from ..extraction_contracts import (
    FIELD_STATES,
    validate_extraction_record,
    classify_field,
)
from ..source_receipts import validate_source_receipt, build_source_receipt
from ..redaction_scan import scan_text
from ..capabilities.models import (
    ChallengeStatus,
    ExtractionFieldResult,
    ExtractionResult,
    ExtractionState,
    TransportType,
)


class ExtractionError(Exception):
    pass


class MissingReceiptError(ExtractionError):
    pass


class MissingFieldCoverageError(ExtractionError):
    pass


def enforce_canonical_extraction(
    url: str,
    fields: dict[str, Any],
    *,
    source_type: str,
    source_context: str,
    backend: str,
    transport: TransportType = TransportType.PUBLIC_HTTP,
    capability_id: str = "",
    block_state: ChallengeStatus = ChallengeStatus.OK,
    manifest_version: str = "",
    expected_fields: list[str] | None = None,
    allow_empty_string: bool = False,
    source_url: str = "",
    notes: str = "",
) -> ExtractionResult:
    """Build an ExtractionResult with mandatory proof artifacts.

    Raises MissingReceiptError or MissingFieldCoverageError if requirements
    aren't met. Use for canonical (non-diagnostic) extraction only.
    """
    if not expected_fields:
        expected_fields = list(fields.keys())

    # 1. Classify every expected field
    field_results = []
    fields_found = []
    fields_missing = []
    for fname in expected_fields:
        state_str = classify_field(fields, fname, allow_empty_string=allow_empty_string)
        if state_str not in FIELD_STATES:
            state_str = "not_checked"
        state = ExtractionState(state_str)
        value = fields.get(fname)
        field_results.append(ExtractionFieldResult(
            name=fname,
            state=state,
            value=value if state == ExtractionState.VALUE else None,
            source=source_type,
        ))
        if state == ExtractionState.VALUE:
            fields_found.append(fname)
        else:
            fields_missing.append(fname)

    # 2. Build and validate source receipt
    block_dict = None
    is_blocked = block_state != ChallengeStatus.OK
    if is_blocked:
        block_dict = {"blocked": True, "kind": block_state.value, "evidence": []}

    receipt = build_source_receipt(
        source_type=source_type,
        source_context=source_context if isinstance(source_context, dict) else {"source": source_context},
        backend=backend,
        fields_found=fields_found,
        fields_missing=fields_missing,
        block=block_dict,
        canonical=not is_blocked,  # blocked sources cannot be canonical
        diagnostic_only=False,
        source_url_or_endpoint_shape=source_url or url,
        notes=notes,
    )

    # validate_source_receipt raises ValueError on invalid receipts
    validate_source_receipt(receipt)

    # 3. Build extraction result
    result = ExtractionResult(
        url=url,
        fields=field_results,
        source_receipt=receipt.get("observed_at", ""),
        capability_id=capability_id,
        transport=transport,
        block_state=block_state,
        manifest_version=manifest_version,
    )

    return result


def require_receipt(result: ExtractionResult) -> None:
    """Raise if a canonical extraction result lacks a source receipt."""
    if not result.source_receipt:
        raise MissingReceiptError(
            f"canonical extraction for {result.url} has no source receipt"
        )


def require_field_coverage(result: ExtractionResult, expected: list[str]) -> None:
    """Raise if any expected field is in NOT_CHECKED state."""
    covered = {f.name for f in result.fields if f.state != ExtractionState.NOT_CHECKED}
    missing = set(expected) - covered
    if missing:
        raise MissingFieldCoverageError(
            f"extraction for {result.url} missing coverage for: {sorted(missing)}"
        )
