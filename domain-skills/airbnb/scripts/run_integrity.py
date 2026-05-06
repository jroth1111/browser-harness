"""Shared Airbnb run integrity helpers.

These helpers keep collector receipts conservative without changing the
underlying collection path. A suspicious empty run is still written for audit,
but it is marked as quarantined so downstream tools do not treat it as a fresh
zero-state signal.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

AIRBNB_DIR = Path(__file__).resolve().parents[1]
SCHEMA_DIR = AIRBNB_DIR / "schemas"

COLLECTION_STATUSES = {
    "complete",
    "partial_failed",
    "partial_unverified",
    "quarantined_empty_after_prior_nonempty",
    "refused_empty_feed_after_prior_nonempty",
}

SOURCE_CLASSES = {
    "public_market",
    "own_public",
    "host_private",
    "host_private_sensitive",
    "calendar",
    "calendar_export",
    "host_export",
    "external_public_market",
    "capability",
    "scheduler",
}

DEFAULT_LAST_GOOD_GUARD = {
    "checked": False,
    "status": "not_checked",
    "reason": "collector_did_not_apply_last_good_guard",
}

DEFAULT_REDACTION_SCAN = {
    "checked": False,
    "status": "not_run",
    "finding_count": None,
}

SECRET_PATTERNS = [
    ("bearer_token", re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{16,}", re.I)),
    ("airbnb_api_key", re.compile(r"\b(?:x-airbnb-api-key|airbnb_api_key)\b\s*[:=]\s*[A-Za-z0-9._~+/=-]{12,}", re.I)),
    ("session_cookie", re.compile(r"\b(?:_airbed_session_id|_aat|_aaj|hli|rclu)\b\s*[:=]\s*[^;\s]{8,}", re.I)),
    ("cookie_header", re.compile(r"\bCookie\s*:\s*[^\\n]{12,}", re.I)),
    ("email_address", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)),
    ("phone_number", re.compile(r"(?<!\d)(?:\+?61|0)[\s.-]?(?:\d[\s.-]?){8,10}(?!\d)")),
]


def latest_prior_count(output_path, *, count_keys, current_run_id=None, glob_pattern="*.json"):
    """Return the newest prior positive count for one or more count fields."""
    keys = tuple(count_keys if isinstance(count_keys, (list, tuple)) else (count_keys,))
    latest_observed_at = None
    latest_count = 0
    latest_path = None
    for path in sorted(Path(output_path).glob(glob_pattern)):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if current_run_id and str(payload.get("run_id") or "") == str(current_run_id):
            continue
        observed_at = str(payload.get("observed_at") or "")
        count = sum(int(payload.get(key) or 0) for key in keys)
        if count <= 0:
            continue
        if latest_observed_at is None or observed_at > latest_observed_at:
            latest_observed_at = observed_at
            latest_count = count
            latest_path = str(path)
    return {
        "prior_positive_count": latest_count,
        "prior_positive_observed_at": latest_observed_at,
        "prior_positive_path": latest_path,
    }


def last_good_guard(*, subject, current_count, prior_positive_count=0, allow_empty=False):
    """Classify an empty run against the newest prior non-empty run."""
    current = int(current_count or 0)
    prior = int(prior_positive_count or 0)
    quarantined = current == 0 and prior > 0 and not bool(allow_empty)
    return {
        "checked": True,
        "subject": subject,
        "current_count": current,
        "prior_positive_count": prior,
        "allow_empty": bool(allow_empty),
        "quarantined_empty_after_prior_nonempty": quarantined,
        "status": "quarantined_empty_after_prior_nonempty" if quarantined else "accepted",
    }


def collection_status(*, last_good_guard_record=None, failures_count=0, complete=True):
    guard = last_good_guard_record or {}
    if guard.get("quarantined_empty_after_prior_nonempty"):
        return "quarantined_empty_after_prior_nonempty"
    if int(failures_count or 0):
        return "partial_failed"
    return "complete" if complete else "partial_unverified"


def warehouse_manifest(rows):
    """Build a stable BI/export manifest for generated JSON/CSV artifacts."""
    manifest = []
    for row in rows or []:
        table = row.get("table")
        path = row.get("path")
        if not table or not path:
            raise ValueError("warehouse manifest rows require table and path")
        manifest.append({
            "table": table,
            "path": str(path),
            "row_count": int(row.get("row_count") or 0),
            "grain": row.get("grain"),
            "source_family": row.get("source_family"),
            "surface_class": row.get("surface_class"),
            "auth_context": row.get("auth_context"),
        })
    return manifest


def load_schema(schema_name):
    path = SCHEMA_DIR / schema_name
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValueError(f"Missing Airbnb contract schema: {path}") from error


def _type_matches(value, schema_type):
    if schema_type == "object":
        return isinstance(value, dict)
    if schema_type == "array":
        return isinstance(value, list)
    if schema_type == "string":
        return isinstance(value, str)
    if schema_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if schema_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if schema_type == "boolean":
        return isinstance(value, bool)
    if schema_type == "null":
        return value is None
    return True


def _validate_schema(value, schema, path="$"):
    errors = []
    if not isinstance(schema, dict):
        return errors
    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        if not any(_type_matches(value, item) for item in schema_type):
            errors.append(f"{path}: expected one of {schema_type}")
            return errors
    elif schema_type and not _type_matches(value, schema_type):
        errors.append(f"{path}: expected {schema_type}")
        return errors
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: expected one of {schema['enum']}")
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}.{key}: required")
        properties = schema.get("properties") or {}
        for key, child in properties.items():
            if key in value:
                errors.extend(_validate_schema(value[key], child, f"{path}.{key}"))
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, item in enumerate(value):
            errors.extend(_validate_schema(item, schema["items"], f"{path}[{index}]"))
    return errors


def validate_contract(payload, schema_name):
    schema = load_schema(schema_name)
    errors = _validate_schema(payload, schema)
    if errors:
        raise ValueError(f"{schema_name} validation failed: " + "; ".join(errors[:10]))
    return True


def contract_defaults(
    *,
    source_family,
    surface_class=None,
    auth_context,
    collection_status="complete",
    last_good_guard_record=None,
    warehouse_exports=None,
    partition_manifest=None,
    capability_registry_ref=None,
    redaction_scan=None,
):
    source_family = str(source_family)
    surface_class = str(surface_class or source_family)
    if source_family not in SOURCE_CLASSES:
        raise ValueError(f"Unknown source_family: {source_family}")
    if collection_status not in COLLECTION_STATUSES:
        raise ValueError(f"Unknown collection_status: {collection_status}")
    return {
        "source_family": source_family,
        "surface_class": surface_class,
        "auth_context": str(auth_context),
        "collection_status": collection_status,
        "last_good_guard": last_good_guard_record or dict(DEFAULT_LAST_GOOD_GUARD),
        "warehouse_exports": warehouse_exports or [],
        "partition_manifest": partition_manifest,
        "capability_registry_ref": capability_registry_ref,
        "redaction_scan": redaction_scan or dict(DEFAULT_REDACTION_SCAN),
    }


def stamp_collection_contract(payload, **defaults):
    """Add common robustness metadata without overwriting collector specifics."""
    if not isinstance(payload, dict):
        raise ValueError("collection contract payload must be an object")
    stamped = dict(payload)
    contract = contract_defaults(**defaults)
    for key, value in contract.items():
        stamped.setdefault(key, value)
    if stamped.get("source_family") not in SOURCE_CLASSES:
        raise ValueError(f"Unknown source_family: {stamped.get('source_family')}")
    if stamped.get("collection_status") not in COLLECTION_STATUSES:
        raise ValueError(f"Unknown collection_status: {stamped.get('collection_status')}")
    return stamped


def validate_collection_output(payload):
    return validate_contract(payload, "collection-output.schema.json")


def validate_receipt(payload):
    return validate_contract(payload, "collection-receipt.schema.json")


def write_collection_json(path, payload):
    validate_collection_output(payload)
    Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_receipt_json(path, payload):
    validate_receipt(payload)
    Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def assert_usable_collection(payload, *, expected_source_family=None, allow_partial=False, allow_quarantined=False):
    """Reject unsafe downstream inputs unless an explicit override is set."""
    if not isinstance(payload, dict):
        raise ValueError("collection payload must be an object")
    status = payload.get("collection_status") or "complete"
    source_family = payload.get("source_family")
    if expected_source_family and source_family != expected_source_family:
        raise ValueError(f"expected source_family={expected_source_family}, got {source_family}")
    if status in {"partial_failed", "partial_unverified"} and not allow_partial:
        raise ValueError(f"collection_status={status} requires allow_partial")
    if status.startswith("quarantined") and not allow_quarantined:
        raise ValueError(f"collection_status={status} requires allow_quarantined")
    if status.startswith("refused") and not allow_quarantined:
        raise ValueError(f"collection_status={status} is not usable downstream")
    return {
        "checked": True,
        "collection_status": status,
        "source_family": source_family,
        "allow_partial": bool(allow_partial),
        "allow_quarantined": bool(allow_quarantined),
    }


def validate_warehouse_manifest(manifest):
    return validate_contract({"warehouse_exports": manifest or []}, "warehouse-manifest.schema.json")


def scan_text_for_redaction_findings(text, *, source_path=None, max_findings=50):
    findings = []
    for kind, pattern in SECRET_PATTERNS:
        for match in pattern.finditer(str(text or "")):
            snippet = match.group(0)[:80]
            findings.append({
                "kind": kind,
                "source_path": str(source_path) if source_path else None,
                "start": match.start(),
                "snippet_prefix": snippet[:24],
            })
            if len(findings) >= max_findings:
                return findings
    return findings


def scan_jsonable_for_redaction_findings(value, *, source_path=None, max_findings=50):
    return scan_text_for_redaction_findings(
        json.dumps(value, ensure_ascii=False, default=str),
        source_path=source_path,
        max_findings=max_findings,
    )


def redaction_scan_record(findings):
    findings = findings or []
    return {
        "checked": True,
        "status": "fail" if findings else "pass",
        "finding_count": len(findings),
        "findings": findings[:20],
    }


def read_step_checkpoint(path):
    path = Path(path)
    if not path.exists():
        return {"schema_version": 1, "steps": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schema_version": 1, "steps": []}
    payload.setdefault("schema_version", 1)
    payload.setdefault("steps", [])
    return payload


def completed_step_keys(checkpoint):
    return {
        str(row.get("step_key"))
        for row in (checkpoint or {}).get("steps", [])
        if row.get("step_key") and row.get("status") in {"complete", "ok", "observed"}
    }


def should_skip_completed_step(path, step_key):
    return str(step_key) in completed_step_keys(read_step_checkpoint(path))


def mark_step_checkpoint(path, *, step_key, status, observed_at=None, metadata=None):
    path = Path(path)
    checkpoint = read_step_checkpoint(path)
    rows = checkpoint.setdefault("steps", [])
    observed_at = observed_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    replacement = {
        "step_key": str(step_key),
        "status": str(status),
        "observed_at": observed_at,
        "metadata": metadata or {},
    }
    for index, row in enumerate(rows):
        if str(row.get("step_key")) == str(step_key):
            rows[index] = {**row, **replacement}
            break
    else:
        rows.append(replacement)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(checkpoint, indent=2, ensure_ascii=False), encoding="utf-8")
    return replacement
