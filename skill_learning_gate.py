"""Validate empirical skill-learning candidates before skill promotion."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


REQUIRED_TOP_LEVEL = {
    "schema_version",
    "candidate_id",
    "domain",
    "affected_skill_paths",
    "observed_surface",
    "evidence_refs",
    "observed_behavior",
    "proposed_rule",
    "forbidden_overgeneralization",
    "source_contextuality",
    "positive_probe",
    "negative_probe",
    "redaction_status",
    "confidence",
    "promotion_decision",
}

REQUIRED_SURFACE = {
    "origin",
    "url_pattern",
    "auth_context",
    "browser_backend",
    "source_family",
    "required_fields",
}

SECRET_PATTERNS = [
    ("bearer_token", re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{16,}", re.I)),
    ("api_key", re.compile(r"\b(?:api[_-]?key|x-[a-z0-9-]*api-key)\b\s*[:=]\s*[A-Za-z0-9._~+/=-]{12,}", re.I)),
    ("session_cookie", re.compile(r"\b(?:session|_session|sid|csrf|xsrf|token|cookie)\b\s*[:=]\s*[^;\s]{12,}", re.I)),
    ("cookie_header", re.compile(r"\bCookie\s*:\s*[^\n]{12,}", re.I)),
    ("email_address", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)),
]

CANONICAL_ARTIFACT_FORBIDDEN = [
    "revision history",
    "update notes",
    "replacement instructions",
    "preservation marker",
    "preservation markers",
    "previous version",
    "old version",
    "this update",
    "in this patch",
    "as requested",
    "task narration",
]

AUTH_OVERGENERALIZATION_PATTERNS = [
    re.compile(r"\b(?:always|all|every)\s+[a-z0-9 -]{0,40}\blogged[- ]out\b", re.I),
    re.compile(r"\blogged[- ]out\s+[a-z0-9 -]{0,40}\b(?:always|for all|for every)\b", re.I),
    re.compile(r"\b(?:always|all|every)\s+[a-z0-9 -]{0,40}\blogged[- ]in\b", re.I),
    re.compile(r"\blogged[- ]in\s+[a-z0-9 -]{0,40}\b(?:always|for all|for every)\b", re.I),
]

ALLOWED_DECISIONS = {"accept", "revise", "reject"}
ALLOWED_CONFIDENCE = {"low", "medium", "high"}
ALLOWED_REDACTION = {"pass", "fail", "not_run"}


def _blank(value):
    return value is None or value == "" or value == [] or value == {}


def scan_text_for_redaction_findings(text, *, source_path=None, max_findings=50):
    findings = []
    for kind, pattern in SECRET_PATTERNS:
        for match in pattern.finditer(str(text or "")):
            findings.append({
                "kind": kind,
                "source_path": str(source_path) if source_path else None,
                "start": match.start(),
                "snippet_prefix": match.group(0)[:24],
            })
            if len(findings) >= max_findings:
                return findings
    return findings


def canonical_artifact_findings(text):
    lowered = str(text or "").lower()
    return [
        {"kind": "process_history_language", "phrase": phrase}
        for phrase in CANONICAL_ARTIFACT_FORBIDDEN
        if phrase in lowered
    ]


def auth_overgeneralization_findings(*texts):
    joined = "\n".join(str(text or "") for text in texts)
    findings = []
    for pattern in AUTH_OVERGENERALIZATION_PATTERNS:
        match = pattern.search(joined)
        if match:
            findings.append({
                "kind": "auth_state_overgeneralization",
                "snippet": match.group(0)[:120],
            })
    return findings


def validate_candidate(candidate, *, source_path=None):
    errors = []
    warnings = []

    if not isinstance(candidate, dict):
        return {
            "decision": "reject",
            "errors": [{"field": "$", "reason": "candidate must be a JSON object"}],
            "warnings": [],
        }

    missing = sorted(key for key in REQUIRED_TOP_LEVEL if _blank(candidate.get(key)))
    errors.extend({"field": key, "reason": "required"} for key in missing)

    if candidate.get("schema_version") != 1:
        errors.append({"field": "schema_version", "reason": "expected 1"})

    decision = candidate.get("promotion_decision")
    if decision and decision not in ALLOWED_DECISIONS:
        errors.append({"field": "promotion_decision", "reason": f"expected one of {sorted(ALLOWED_DECISIONS)}"})

    confidence = candidate.get("confidence")
    if confidence and confidence not in ALLOWED_CONFIDENCE:
        errors.append({"field": "confidence", "reason": f"expected one of {sorted(ALLOWED_CONFIDENCE)}"})

    surface = candidate.get("observed_surface") or {}
    if not isinstance(surface, dict):
        errors.append({"field": "observed_surface", "reason": "expected object"})
        surface = {}
    surface_missing = sorted(key for key in REQUIRED_SURFACE if _blank(surface.get(key)))
    errors.extend({"field": f"observed_surface.{key}", "reason": "required"} for key in surface_missing)

    if _blank(candidate.get("affected_skill_paths")):
        errors.append({"field": "affected_skill_paths", "reason": "at least one skill path is required"})
    else:
        for path in candidate.get("affected_skill_paths") or []:
            if not str(path).startswith(("domain-skills/", "interaction-skills/", "SKILL.md")):
                errors.append({"field": "affected_skill_paths", "reason": f"path is outside shared skill artifacts: {path}"})

    source_contextuality = candidate.get("source_contextuality") or {}
    if not isinstance(source_contextuality, dict):
        errors.append({"field": "source_contextuality", "reason": "expected object"})
        source_contextuality = {}
    if _blank(source_contextuality.get("scope")):
        errors.append({"field": "source_contextuality.scope", "reason": "required"})
    if _blank(source_contextuality.get("does_not_apply_when")):
        errors.append({"field": "source_contextuality.does_not_apply_when", "reason": "at least one counterexample is required"})

    positive_probe = candidate.get("positive_probe") or {}
    if not isinstance(positive_probe, dict):
        errors.append({"field": "positive_probe", "reason": "expected object"})
        positive_probe = {}
    if _blank(positive_probe.get("description")):
        errors.append({"field": "positive_probe.description", "reason": "required"})
    if _blank(positive_probe.get("evidence_required")):
        errors.append({"field": "positive_probe.evidence_required", "reason": "required"})

    negative_probe = candidate.get("negative_probe") or {}
    if not isinstance(negative_probe, dict):
        errors.append({"field": "negative_probe", "reason": "expected object"})
        negative_probe = {}
    if _blank(negative_probe.get("description")):
        errors.append({"field": "negative_probe.description", "reason": "required"})
    if _blank(negative_probe.get("forbidden_path")):
        errors.append({"field": "negative_probe.forbidden_path", "reason": "required"})

    redaction_status = candidate.get("redaction_status") or {}
    if not isinstance(redaction_status, dict):
        errors.append({"field": "redaction_status", "reason": "expected object"})
        redaction_status = {}
    status = redaction_status.get("status")
    if status not in ALLOWED_REDACTION:
        errors.append({"field": "redaction_status.status", "reason": f"expected one of {sorted(ALLOWED_REDACTION)}"})
    elif status != "pass":
        errors.append({"field": "redaction_status.status", "reason": "must pass before promotion"})

    serialized = json.dumps(candidate, ensure_ascii=False, default=str)
    redaction_findings = scan_text_for_redaction_findings(serialized, source_path=source_path)
    if redaction_findings:
        errors.append({
            "field": "$",
            "reason": "redaction findings present",
            "findings": redaction_findings[:10],
        })

    artifact_text = candidate.get("proposed_artifact_text")
    if artifact_text:
        artifact_findings = canonical_artifact_findings(artifact_text)
        if artifact_findings:
            errors.append({
                "field": "proposed_artifact_text",
                "reason": "canonical skill artifact contains process-history language",
                "findings": artifact_findings,
            })

    auth_findings = auth_overgeneralization_findings(
        candidate.get("observed_behavior"),
        candidate.get("proposed_rule"),
        candidate.get("forbidden_overgeneralization"),
        artifact_text,
    )
    if auth_findings:
        errors.append({
            "field": "proposed_rule",
            "reason": "auth state must be workflow- and site-dependent, not universal",
            "findings": auth_findings,
        })

    if candidate.get("promotion_decision") == "accept" and errors:
        decision = "reject" if redaction_findings or auth_findings else "revise"
    elif candidate.get("promotion_decision") == "accept":
        decision = "accept"
    elif candidate.get("promotion_decision") in {"reject", "revise"}:
        decision = candidate.get("promotion_decision")
    else:
        decision = "revise"

    return {
        "decision": decision,
        "candidate_id": candidate.get("candidate_id"),
        "source_path": str(source_path) if source_path else None,
        "errors": errors,
        "warnings": warnings,
    }


def load_candidate(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def evaluate_paths(paths):
    results = []
    for path in paths:
        results.append(validate_candidate(load_candidate(path), source_path=path))
    return {
        "decision": "accept" if all(result["decision"] == "accept" for result in results) else "reject",
        "results": results,
    }


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(
            "usage: browser-harness --skill-learning-gate CANDIDATE.json [...]\n"
            "   or: browser-harness-skill-learning-gate CANDIDATE.json [...]",
            file=sys.stderr,
        )
        raise SystemExit(2)
    result = evaluate_paths(argv)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if result["decision"] != "accept":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
