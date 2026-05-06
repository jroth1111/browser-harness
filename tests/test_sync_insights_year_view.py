import importlib.util
import json
from pathlib import Path

import pytest


def load_sync_module():
    path = Path("domain-skills/airbnb/scripts/sync_insights_year_view.py")
    spec = importlib.util.spec_from_file_location("airbnb_sync_insights_year_view", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_preflight_rejects_bev_only_cookie(monkeypatch):
    module = load_sync_module()
    monkeypatch.setattr(module, "run_shell", lambda command: json.dumps({"cookie_names": ["bev"]}))

    with pytest.raises(RuntimeError, match="host session not detected"):
        module.preflight_cookies()


def test_preflight_accepts_authenticated_cookie(monkeypatch):
    module = load_sync_module()
    monkeypatch.setattr(module, "run_shell", lambda command: json.dumps({"cookie_names": ["bev", "_aat"]}))

    payload = module.preflight_cookies()

    assert payload["auth_cookie_names_present"] == ["_aat"]


def test_validate_collect_output_rejects_failed_collection_without_partial_flag(tmp_path, monkeypatch):
    module = load_sync_module()
    output_path = tmp_path / "insights"
    session_path = tmp_path / "session"
    output_path.mkdir()
    session_path.mkdir()
    monkeypatch.setattr(module, "OUTPUT_PATH", output_path)
    monkeypatch.setattr(module, "SESSION_PATH", session_path)
    (output_path / "run-1.json").write_text(
        json.dumps({
            "failures_count": 2,
            "summary_rows_count": 1,
            "daily_rows_count": 1,
            "listing_count": 27,
            "total_active_listings": 27,
            "listing_scope_complete": True,
        }),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="reported 2 failures"):
        module.validate_collect_output("run-1")

    assert module.validate_collect_output("run-1", allow_partial=True)["failures_count"] == 2


def test_validate_collect_output_rejects_empty_summary(tmp_path, monkeypatch):
    """Summary rows are always expected (summary requests are always made).
    A zero summary rows count indicates a broken collector, even with
    allow_partial.
    """
    module = load_sync_module()
    output_path = tmp_path / "insights"
    session_path = tmp_path / "session"
    output_path.mkdir()
    session_path.mkdir()
    monkeypatch.setattr(module, "OUTPUT_PATH", output_path)
    monkeypatch.setattr(module, "SESSION_PATH", session_path)
    (output_path / "run-empty.json").write_text(
        json.dumps({
            "failures_count": 0,
            "summary_rows_count": 0,
            "daily_rows_count": 0,
            "listing_count": 27,
            "total_active_listings": 27,
            "listing_scope_complete": True,
        }),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="missing summary rows"):
        module.validate_collect_output("run-empty", allow_partial=True)


def test_validate_collect_output_accepts_steady_state_with_zero_chart_rows(tmp_path, monkeypatch):
    """Regression: a fully-covered ledger legitimately produces 0 chart requests
    and 0 daily rows. This is the steady-state convergence outcome and must NOT
    be rejected as failure.
    """
    module = load_sync_module()
    output_path = tmp_path / "insights"
    session_path = tmp_path / "session"
    output_path.mkdir()
    session_path.mkdir()
    monkeypatch.setattr(module, "OUTPUT_PATH", output_path)
    monkeypatch.setattr(module, "SESSION_PATH", session_path)
    (output_path / "run-steady.json").write_text(
        json.dumps({
            "failures_count": 0,
            "summary_rows_count": 1296,
            "daily_rows_count": 0,
            "chart_request_count": 0,
            "sentinel_rows_count": 1500,
            "listing_count": 27,
            "total_active_listings": 27,
            "listing_scope_complete": True,
        }),
        encoding="utf-8",
    )
    result = module.validate_collect_output("run-steady")
    assert result["daily_rows_count"] == 0
    assert result["sentinel_rows_count"] == 1500


def test_validate_collect_output_accepts_sentinel_only_chart_success(tmp_path, monkeypatch):
    module = load_sync_module()
    output_path = tmp_path / "insights"
    session_path = tmp_path / "session"
    output_path.mkdir()
    session_path.mkdir()
    monkeypatch.setattr(module, "OUTPUT_PATH", output_path)
    monkeypatch.setattr(module, "SESSION_PATH", session_path)
    (output_path / "run-sentinel-only.json").write_text(
        json.dumps({
            "failures_count": 0,
            "summary_rows_count": 10,
            "daily_rows_count": 0,
            "chart_request_count": 3,
            "sentinel_rows_count": 3,
            "listing_count": 1,
            "total_active_listings": 1,
            "listing_scope_complete": True,
        }),
        encoding="utf-8",
    )

    result = module.validate_collect_output("run-sentinel-only")

    assert result["daily_rows_count"] == 0
    assert result["sentinel_rows_count"] == 3


def test_validate_collect_output_rejects_partial_listing_scope(tmp_path, monkeypatch):
    """Regression: silently dropping listings via AIRBNB_INSIGHTS_LIMIT_LISTINGS
    must be flagged unless allow_partial is explicitly set.
    """
    module = load_sync_module()
    output_path = tmp_path / "insights"
    session_path = tmp_path / "session"
    output_path.mkdir()
    session_path.mkdir()
    monkeypatch.setattr(module, "OUTPUT_PATH", output_path)
    monkeypatch.setattr(module, "SESSION_PATH", session_path)
    (output_path / "run-partial.json").write_text(
        json.dumps({
            "failures_count": 0,
            "summary_rows_count": 100,
            "daily_rows_count": 100,
            "chart_request_count": 50,
            "listing_count": 5,
            "total_active_listings": 27,
            "listing_scope_complete": False,
        }),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="scoped only 5 of 27 listings for scope active"):
        module.validate_collect_output("run-partial")

    # allow_partial bypasses the check.
    result = module.validate_collect_output("run-partial", allow_partial=True)
    assert result["listing_scope_complete"] is False
    assert result["listing_count"] == 5


def test_validate_collect_output_rejects_quarantined_without_override(tmp_path, monkeypatch):
    module = load_sync_module()
    output_path = tmp_path / "insights"
    session_path = tmp_path / "session"
    output_path.mkdir()
    session_path.mkdir()
    monkeypatch.setattr(module, "OUTPUT_PATH", output_path)
    monkeypatch.setattr(module, "SESSION_PATH", session_path)
    (output_path / "run-quarantined.json").write_text(
        json.dumps({
            "run_id": "run-quarantined",
            "observed_at": "2026-04-29T00:00:00Z",
            "collection_status": "quarantined_empty_after_prior_nonempty",
            "source_family": "host_private",
            "surface_class": "host_private",
            "auth_context": "fixture",
            "last_good_guard": {"checked": True, "status": "quarantined_empty_after_prior_nonempty"},
            "warehouse_exports": [],
            "failures_count": 0,
            "summary_rows_count": 1,
            "daily_rows_count": 1,
            "chart_request_count": 1,
            "listing_count": 1,
            "total_active_listings": 1,
            "listing_scope_complete": True,
        }),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="allow_quarantined|collection_status"):
        module.validate_collect_output("run-quarantined")

    assert module.validate_collect_output("run-quarantined", allow_quarantined=True)["allow_quarantined"] is True


def test_stale_probe_failure_is_recorded_without_blocking_collection(monkeypatch, tmp_path):
    module = load_sync_module()
    monkeypatch.setattr(module, "GRANULARITY_MAP", tmp_path / "missing-map.md")

    def fail_probe():
        raise RuntimeError("probe failed")

    monkeypatch.setattr(module, "run_probe", fail_probe)

    result = module.maybe_run_probe(skip_probe=False)

    assert result["ok"] is False
    assert "probe failed" in result["error"]


def test_browser_open_verify_counts_render_dataset_payload_shape(monkeypatch):
    module = load_sync_module()
    captured = {}

    def fake_run_shell(command):
        captured["command"] = command
        return "[]"

    monkeypatch.setattr(module, "run_shell", fake_run_shell)

    module.browser_open_verify(
        [
            {
                "family": "conversion",
                "summary_html_path": "/tmp/summary.html",
                "daily_html_path": "/tmp/daily.html",
            }
        ]
    )

    command = captured["command"]
    assert "(p.datasets || [])[0]" in command
    assert "(ds.data || []).length" in command
    assert "(p.data || []).length" not in command
