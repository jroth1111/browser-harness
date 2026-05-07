import json
import importlib.util
import time
from pathlib import Path

import pytest


def load_batch_functions():
    source = Path("domain-skills/airbnb/scripts/collect_insights.py").read_text(encoding="utf-8")
    start = source.index("def result_key")
    end = source.index("\n\ndef components")
    namespace = {"json": json, "os": __import__("os"), "time": time}
    exec(source[start:end], namespace)
    return namespace


def load_collect_module():
    path = Path("domain-skills/airbnb/scripts/collect_insights.py")
    spec = importlib.util.spec_from_file_location("airbnb_collect_insights", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def request(request_id):
    return {
        "meta": {
            "request_kind": "daily_chart",
            "listing_id": request_id,
            "route_family": "quality",
            "route_subroute": "overall",
            "relative_ds_start": -7,
            "relative_ds_end": 0,
        }
    }


def result(request_id, ok, status=None, error=None):
    payload = {**request(request_id)["meta"], "ok": ok, "status": status}
    if error:
        payload["error"] = error
    return payload


def chart_result(components=None, errors=None):
    payload = {
        "ok": True,
        "status": 200,
        "data": {
            "data": {
                "porygon": {
                    "getPerformanceComponents": {
                        "components": components or [],
                    }
                }
            }
        },
    }
    if errors is not None:
        payload["data"]["errors"] = errors
    return payload


def test_run_request_batches_preserves_successes_from_mixed_retry_attempts(tmp_path, monkeypatch):
    module = load_batch_functions()
    calls = []
    responses = [
        [result("a", True, 200), result("b", False, 429), result("c", False, None, "timeout")],
        [result("b", True, 200), result("c", False, 429)],
        [result("c", True, 200)],
    ]

    def fake_fetch(pending, api_key, base_headers):
        calls.append([item["meta"]["listing_id"] for item in pending])
        return responses.pop(0)

    monkeypatch.setenv("AIRBNB_INSIGHTS_BATCH_SIZE", "3")
    monkeypatch.setenv("AIRBNB_INSIGHTS_BATCH_DELAY_SEC", "0")
    monkeypatch.setenv("AIRBNB_INSIGHTS_RETRY_LIMIT", "2")
    monkeypatch.setenv("AIRBNB_INSIGHTS_429_BACKOFF_SEC", "0")
    monkeypatch.setattr(time, "sleep", lambda _: None)
    module["fetch_performance_batch"] = fake_fetch

    checkpoint = tmp_path / "checkpoint.jsonl"
    results, failures = module["run_request_batches"](
        "daily_chart",
        [request("a"), request("b"), request("c")],
        "api-key",
        {},
        checkpoint,
    )

    assert calls == [["a", "b", "c"], ["b", "c"], ["c"]]
    assert [row["listing_id"] for row in results] == ["a", "b", "c"]
    assert failures == []
    checkpointed = [json.loads(line) for line in checkpoint.read_text(encoding="utf-8").splitlines()]
    assert [row["listing_id"] for row in checkpointed] == ["a", "b", "c"]


def test_live_listing_file_rejects_malformed_counts(tmp_path):
    module = load_collect_module()
    path = tmp_path / "airbnb-live-listings-bad-counts.json"
    path.write_text(
        json.dumps(
            {
                "records": [{"status": "ACTIVE"}],
                "active_count": "not-a-count",
                "status_counts": {"ACTIVE": "not-a-count"},
                "field_validation": {"all_active_detail_pages_ok": True},
            }
        ),
        encoding="utf-8",
    )

    assert module.is_complete_live_listing_file(path) is False


def test_run_request_batches_does_not_checkpoint_graphql_error_payload(tmp_path, monkeypatch):
    module = load_batch_functions()

    def fake_fetch(pending, api_key, base_headers):
        return [
            {
                **pending[0]["meta"],
                "ok": False,
                "status": 200,
                "error": "ServiceBadRequestError",
                "data": {"errors": [{"message": "ServiceBadRequestError"}]},
            }
        ]

    monkeypatch.setenv("AIRBNB_INSIGHTS_BATCH_DELAY_SEC", "0")
    monkeypatch.setenv("AIRBNB_INSIGHTS_RETRY_LIMIT", "0")
    monkeypatch.setattr(time, "sleep", lambda _: None)
    module["fetch_performance_batch"] = fake_fetch

    checkpoint = tmp_path / "checkpoint.jsonl"
    results, failures = module["run_request_batches"](
        "daily_chart",
        [request("graphql-error")],
        "api-key",
        {},
        checkpoint,
    )

    assert results == failures
    assert failures[0]["error"] == "ServiceBadRequestError"
    assert not checkpoint.exists()


def test_fetch_performance_one_treats_graphql_errors_as_failed(monkeypatch):
    module = load_collect_module()

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(
                {
                    "errors": [
                        {
                            "message": "malformed input",
                            "extensions": {"errorClass": "ServiceBadRequestError"},
                        }
                    ],
                    "data": {},
                }
            ).encode()

    monkeypatch.setattr(module, "urlopen", lambda request, timeout: FakeResponse())
    item = module.performance_request(
        "ChartQuery",
        {"family": "conversion", "metric_type": "CONVERSION", "subroute": "p3_impressions"},
        "123",
        -1,
        -1,
    )
    item["meta"] = request("123")["meta"]

    result = module.fetch_performance_one(item, "api-key", {})

    assert result["ok"] is False
    assert result["status"] == 200
    assert "ServiceBadRequestError" in result["error"]


def test_build_requests_accepts_discovered_operation_hash():
    module = load_collect_module()
    discovered_hash = "a" * 64

    requests = module.build_requests_from_plan(
        [
            {
                "request_kind": "daily_chart",
                "listing_id": "123",
                "route_subroute": "p3_impressions",
                "relative_ds_start": -7,
                "relative_ds_end": -1,
                "chart_mode": "rolling_daily",
            }
        ],
        listings_by_id={"123": {"listing_name": "Demo"}},
        routes_by_subroute={
            "p3_impressions": {
                "family": "conversion",
                "metric_type": "CONVERSION",
                "subroute": "p3_impressions",
                "label": "Views",
            }
        },
        operation_name="ChartQuery",
        operation_hashes={"ChartQuery": discovered_hash, "ListOfMetricsQuery": "b" * 64},
    )

    assert requests[0]["hash"] == discovered_hash


def test_legacy_history_days_bounds_tiered_horizons():
    module = load_collect_module()

    horizons = module.resolve_horizons({"AIRBNB_INSIGHTS_HISTORY_DAYS": "14"})

    assert horizons["history_days"] == 14
    assert horizons["daily_horizon_days"] == 14
    assert horizons["older_horizon_days"] == 0
    assert horizons["weekly_window_days"] == 56


def test_explicit_tiered_horizons_are_reported_as_actual_history():
    module = load_collect_module()

    horizons = module.resolve_horizons(
        {
            "AIRBNB_INSIGHTS_HISTORY_DAYS": "14",
            "AIRBNB_INSIGHTS_DAILY_HORIZON_DAYS": "7",
            "AIRBNB_INSIGHTS_OLDER_HORIZON_DAYS": "21",
            "AIRBNB_INSIGHTS_WEEKLY_WINDOW_DAYS": "28",
        }
    )

    assert horizons["history_days"] == 28
    assert horizons["daily_horizon_days"] == 7
    assert horizons["older_horizon_days"] == 21
    assert horizons["legacy_history_days"] == 14
    assert horizons["weekly_window_days"] == 28


def test_validate_collection_scope_rejects_empty_listings_or_routes():
    module = load_collect_module()

    with pytest.raises(SystemExit, match="No listings in scope"):
        module.validate_collection_scope([], [{"family": "quality", "subroute": "overall"}])

    with pytest.raises(SystemExit, match="No routes in scope"):
        module.validate_collection_scope([{"listing_id": "123"}], [])


def test_weekly_window_days_must_span_at_least_two_days():
    module = load_collect_module()

    with pytest.raises(SystemExit, match="weekly window days must be at least 2"):
        module.resolve_horizons({"AIRBNB_INSIGHTS_WEEKLY_WINDOW_DAYS": "1"})


def test_confirmed_empty_chart_requires_recognized_empty_series():
    module = load_collect_module()
    result = chart_result(
        components=[
            {
                "componentName": "PIVOT_CHART_SECTION",
                "metricLineCharts": [{"label": "Views", "dataPoints": []}],
            }
        ]
    )

    assert module.parse_chart(result) == []
    assert module.is_confirmed_empty_chart(result) is True

    empty_chart_list = chart_result(
        components=[
            {
                "componentName": "PIVOT_CHART_SECTION",
                "metricLineCharts": [],
            }
        ]
    )
    assert module.parse_chart(empty_chart_list) == []
    assert module.is_confirmed_empty_chart(empty_chart_list) is True


def test_ok_chart_parser_miss_is_not_confirmed_empty():
    module = load_collect_module()
    error_result = chart_result(
        components=[
            {
                "componentName": "PIVOT_CHART_SECTION",
                "metricLineCharts": [{"label": "Views", "dataPoints": []}],
            }
        ],
        errors=[{"message": "ServiceBadRequestError"}],
    )
    missing_chart_result = chart_result(
        components=[
            {
                "componentName": "LIST_OF_METRICS_SECTION",
                "metrics": [],
            }
        ]
    )

    assert module.parse_chart(error_result) == []
    assert module.is_confirmed_empty_chart(error_result) is False
    assert module.parse_chart(missing_chart_result) == []
    assert module.is_confirmed_empty_chart(missing_chart_result) is False


def test_sentinel_dedup_prefers_widest_span_for_same_start():
    """If overlapping empty windows share the same ds start, keep the widest
    sentinel so coverage is not accidentally reduced.
    """
    wider = {
        "listing_id": "123",
        "route_family": "quality",
        "route_subroute": "overall",
        "ds": "2026-01-01",
        "_attempt_span_days": 56,
        "observed_at": "2026-04-28T00:00:00Z",
    }
    narrower = {
        "listing_id": "123",
        "route_family": "quality",
        "route_subroute": "overall",
        "ds": "2026-01-01",
        "_attempt_span_days": 7,
        "observed_at": "2026-04-29T00:00:00Z",
    }

    seen_sentinels = {}
    for row in [wider, narrower]:
        key = (
            row.get("listing_id"),
            row.get("route_family"),
            row.get("route_subroute"),
            row.get("ds"),
        )
        existing = seen_sentinels.get(key)
        row_span = int(row.get("_attempt_span_days") or 1)
        existing_span = int((existing or {}).get("_attempt_span_days") or 1)
        if (
            existing is None
            or row_span > existing_span
            or (
                row_span == existing_span
                and str(row.get("observed_at") or "") >= str(existing.get("observed_at") or "")
            )
        ):
            seen_sentinels[key] = row

    kept = seen_sentinels[("123", "quality", "overall", "2026-01-01")]
    assert kept["_attempt_span_days"] == 56


def test_sentinel_dedup_keeps_distinct_route_families():
    quality = {
        "listing_id": "123",
        "route_family": "quality",
        "route_subroute": "overall",
        "ds": "2026-01-01",
        "_attempt_span_days": 56,
        "observed_at": "2026-04-28T00:00:00Z",
    }
    occupancy = {
        "listing_id": "123",
        "route_family": "occupancy",
        "route_subroute": "overall",
        "ds": "2026-01-01",
        "_attempt_span_days": 56,
        "observed_at": "2026-04-28T00:00:00Z",
    }

    seen_sentinels = {}
    for row in [quality, occupancy]:
        key = (
            row.get("listing_id"),
            row.get("route_family"),
            row.get("route_subroute"),
            row.get("ds"),
        )
        seen_sentinels[key] = row

    assert len(seen_sentinels) == 2
