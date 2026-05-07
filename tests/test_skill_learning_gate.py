import json
from pathlib import Path

from browser_harness import skill_learning_gate


ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "domain-skills" / "skill-learning-candidate.schema.json"
FIXTURE_DIR = ROOT / "domain-skills" / "airbnb" / "fixtures" / "skill-learning"


def load_module():
    return skill_learning_gate


def load_candidate(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_skill_learning_candidate_schema_has_required_process_fields():
    schema = load_candidate(SCHEMA_PATH)
    required = set(schema["required"])
    module = load_module()

    assert {
        "observed_surface",
        "evidence_refs",
        "forbidden_overgeneralization",
        "source_contextuality",
        "positive_probe",
        "negative_probe",
        "redaction_status",
        "promotion_decision",
    } <= required
    surface_required = set(schema["properties"]["observed_surface"]["required"])
    assert {
        "origin",
        "url_pattern",
        "auth_context",
        "browser_backend",
        "source_family",
        "required_fields",
    } <= surface_required
    assert module.REQUIRED_TOP_LEVEL <= required
    assert module.REQUIRED_SURFACE <= surface_required


def test_airbnb_public_comp_candidate_is_promotable():
    module = load_module()
    candidate = load_candidate(FIXTURE_DIR / "accepted" / "public-comp-auth-state.json")

    result = module.validate_candidate(candidate)

    assert result["decision"] == "accept"
    assert result["errors"] == []


def test_candidate_fails_without_source_context():
    module = load_module()
    candidate = load_candidate(FIXTURE_DIR / "accepted" / "public-comp-auth-state.json")
    del candidate["observed_surface"]["auth_context"]

    result = module.validate_candidate(candidate)

    assert result["decision"] == "revise"
    assert {"field": "observed_surface.auth_context", "reason": "required"} in result["errors"]


def test_candidate_fails_without_negative_probe():
    module = load_module()
    candidate = load_candidate(FIXTURE_DIR / "accepted" / "public-comp-auth-state.json")
    candidate["negative_probe"] = {}

    result = module.validate_candidate(candidate)

    assert result["decision"] == "revise"
    fields = {error["field"] for error in result["errors"]}
    assert {"negative_probe.description", "negative_probe.forbidden_path"} <= fields


def test_candidate_rejects_secret_payloads_even_if_marked_pass():
    module = load_module()
    candidate = load_candidate(FIXTURE_DIR / "accepted" / "public-comp-auth-state.json")
    candidate["evidence_refs"].append("Authorization: Bearer abcdefghijklmnopqrstuvwxyz012345")

    result = module.validate_candidate(candidate)

    assert result["decision"] == "reject"
    assert any(error["reason"] == "redaction findings present" for error in result["errors"])
    findings = next(error["findings"] for error in result["errors"] if error["reason"] == "redaction findings present")
    assert findings[0]["snippet_prefix"] == "bearer_token:REDACTED"
    assert "abcdefghijklmnopqrstuvwxyz" not in json.dumps(findings)


def test_candidate_rejects_auth_state_overgeneralization():
    module = load_module()
    candidate = load_candidate(FIXTURE_DIR / "rejected" / "universal-logged-out.json")

    result = module.validate_candidate(candidate)

    assert result["decision"] == "reject"
    assert any(error["reason"] == "auth state must be workflow- and site-dependent, not universal" for error in result["errors"])


def test_candidate_rejects_process_history_in_proposed_artifact_text():
    module = load_module()
    candidate = load_candidate(FIXTURE_DIR / "accepted" / "public-comp-auth-state.json")
    candidate["proposed_artifact_text"] += " This update replaces the previous version."

    result = module.validate_candidate(candidate)

    assert result["decision"] == "revise"
    assert any(error["field"] == "proposed_artifact_text" for error in result["errors"])
