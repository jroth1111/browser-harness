import importlib.util
import json
from pathlib import Path


def load_module():
    path = Path("domain-skills/airbnb/scripts/run_integrity.py")
    spec = importlib.util.spec_from_file_location("airbnb_run_integrity", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_latest_prior_count_picks_newest_positive_count(tmp_path):
    module = load_module()
    (tmp_path / "old.json").write_text(json.dumps({
        "run_id": "old",
        "observed_at": "2026-04-27T00:00:00Z",
        "search_result_count": 4,
    }))
    (tmp_path / "new-empty.json").write_text(json.dumps({
        "run_id": "new-empty",
        "observed_at": "2026-04-29T00:00:00Z",
        "search_result_count": 0,
    }))
    (tmp_path / "new-positive.json").write_text(json.dumps({
        "run_id": "new-positive",
        "observed_at": "2026-04-28T00:00:00Z",
        "search_result_count": 7,
    }))

    result = module.latest_prior_count(tmp_path, count_keys=("search_result_count",))

    assert result["prior_positive_count"] == 7
    assert result["prior_positive_path"].endswith("new-positive.json")


def test_latest_prior_count_skips_malformed_count_artifacts(tmp_path):
    module = load_module()
    (tmp_path / "bad-count.json").write_text(json.dumps({
        "run_id": "bad-count",
        "observed_at": "2026-04-29T00:00:00Z",
        "search_result_count": "not-a-count",
    }))
    (tmp_path / "valid-positive.json").write_text(json.dumps({
        "run_id": "valid-positive",
        "observed_at": "2026-04-28T00:00:00Z",
        "search_result_count": 7,
    }))

    result = module.latest_prior_count(tmp_path, count_keys=("search_result_count",))

    assert result["prior_positive_count"] == 7
    assert result["prior_positive_path"].endswith("valid-positive.json")


def test_last_good_guard_quarantines_empty_after_prior_nonempty():
    module = load_module()

    guard = module.last_good_guard(
        subject="public_comp_search_results",
        current_count=0,
        prior_positive_count=3,
    )

    assert guard["quarantined_empty_after_prior_nonempty"] is True
    assert module.collection_status(last_good_guard_record=guard) == "quarantined_empty_after_prior_nonempty"
    assert module.last_good_guard(
        subject="public_comp_search_results",
        current_count=0,
        prior_positive_count=3,
        allow_empty=True,
    )["status"] == "accepted"


def test_warehouse_manifest_records_table_grain_and_auth_context():
    module = load_module()

    manifest = module.warehouse_manifest([
        {
            "table": "airbnb_public_search_result_snapshot",
            "path": "/tmp/results.csv",
            "row_count": 12,
            "grain": "search_run_id + result_position",
            "source_family": "public_market",
            "surface_class": "public_market",
            "auth_context": "logged_out_public_guest_visible",
        }
    ])

    assert manifest == [
        {
            "table": "airbnb_public_search_result_snapshot",
            "path": "/tmp/results.csv",
            "row_count": 12,
            "grain": "search_run_id + result_position",
            "source_family": "public_market",
            "surface_class": "public_market",
            "auth_context": "logged_out_public_guest_visible",
        }
    ]
    assert module.validate_warehouse_manifest(manifest) is True


def test_contract_stamp_and_schema_validation_require_common_receipt_fields():
    module = load_module()

    payload = module.stamp_collection_contract(
        {"run_id": "run-1", "observed_at": "2026-04-29T00:00:00Z"},
        source_family="public_market",
        surface_class="public_market",
        auth_context="logged_out_public_guest_visible",
        collection_status="complete",
    )

    assert module.validate_collection_output(payload) is True
    assert module.validate_receipt(payload) is True
    assert payload["last_good_guard"]["checked"] is False
    assert payload["redaction_scan"]["status"] == "not_run"

    bad = dict(payload)
    del bad["auth_context"]
    try:
        module.validate_receipt(bad)
    except ValueError as error:
        assert "$.auth_context: required" in str(error)
    else:
        raise AssertionError("missing auth_context should fail receipt schema")


def test_assert_usable_collection_rejects_partial_quarantined_and_source_mismatch():
    module = load_module()

    complete = {
        "collection_status": "complete",
        "source_family": "host_private",
    }
    assert module.assert_usable_collection(complete, expected_source_family="host_private")["checked"] is True

    try:
        module.assert_usable_collection({"collection_status": "partial_failed", "source_family": "host_private"})
    except ValueError as error:
        assert "allow_partial" in str(error)
    else:
        raise AssertionError("partial collection should require explicit override")

    try:
        module.assert_usable_collection({
            "collection_status": "quarantined_empty_after_prior_nonempty",
            "source_family": "public_market",
        })
    except ValueError as error:
        assert "allow_quarantined" in str(error)
    else:
        raise AssertionError("quarantined collection should require explicit override")

    try:
        module.assert_usable_collection(complete, expected_source_family="public_market")
    except ValueError as error:
        assert "expected source_family=public_market" in str(error)
    else:
        raise AssertionError("source mismatch should fail")


def test_redaction_scan_flags_tokens_email_and_session_cookie():
    module = load_module()

    findings = module.scan_text_for_redaction_findings(
        "Authorization: Bearer abcdefghijklmnopqrstuvwxyz012345\n"
        "_airbed_session_id=secret-session-value\n"
        "guest@example.com"
    )
    kinds = {item["kind"] for item in findings}

    assert {"bearer_token", "session_cookie", "email_address"}.issubset(kinds)
    assert module.redaction_scan_record(findings)["status"] == "fail"


def test_step_checkpoint_supports_resume_skip(tmp_path):
    module = load_module()
    path = tmp_path / "checkpoint.json"

    assert module.should_skip_completed_step(path, "partition-1") is False
    module.mark_step_checkpoint(path, step_key="partition-1", status="complete")
    module.mark_step_checkpoint(path, step_key="partition-2", status="failed")

    assert module.should_skip_completed_step(path, "partition-1") is True
    assert module.should_skip_completed_step(path, "partition-2") is False
