import importlib.util
import json
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit


def load_probe_module():
    path = Path("domain-skills/airbnb/scripts/probe_chart_granularity.py")
    spec = importlib.util.spec_from_file_location("airbnb_probe_chart_granularity", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_single_day_probe_import_does_not_execute_main():
    path = Path("domain-skills/airbnb/scripts/probe_single_day_windows.py")
    spec = importlib.util.spec_from_file_location("airbnb_probe_single_day_windows", path)
    module = importlib.util.module_from_spec(spec)

    spec.loader.exec_module(module)

    assert hasattr(module, "main")


def load_single_day_probe_module():
    path = Path("domain-skills/airbnb/scripts/probe_single_day_windows.py")
    spec = importlib.util.spec_from_file_location("airbnb_probe_single_day_windows", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_probe_live_listing_file_rejects_malformed_counts(tmp_path):
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

    assert load_probe_module().is_complete_live_listing_file(path) is False
    assert load_single_day_probe_module().is_complete_live_listing_file(path) is False


def test_probe_live_listing_file_rejects_boolean_counts(tmp_path):
    path = tmp_path / "airbnb-live-listings-boolean-counts.json"
    path.write_text(
        json.dumps(
            {
                "records": [{"status": "ACTIVE"}],
                "active_count": True,
                "status_counts": {"ACTIVE": True},
                "field_validation": {"all_active_detail_pages_ok": True},
            }
        ),
        encoding="utf-8",
    )

    assert load_probe_module().is_complete_live_listing_file(path) is False
    assert load_single_day_probe_module().is_complete_live_listing_file(path) is False


def test_chart_bounds_end_yesterday():
    module = load_probe_module()

    assert module.chart_bounds_for_horizon(14) == (-14, -1)


def test_fetch_chart_uses_yesterday_bound_and_reports_granularity(monkeypatch):
    module = load_probe_module()
    requested_urls = []

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(
                {
                    "data": {
                        "porygon": {
                            "getPerformanceComponents": {
                                "components": [
                                    {
                                        "componentName": "PIVOT_CHART_SECTION",
                                        "metricLineCharts": [{"granularity": "DAY"}],
                                    }
                                ]
                            }
                        }
                    }
                }
            ).encode()

    def fake_urlopen(request, timeout):
        requested_urls.append(request.full_url)
        return FakeResponse()

    monkeypatch.setattr(module, "urlopen", fake_urlopen)

    result = module.fetch_chart(
        "api-key",
        {},
        {"family": "conversion", "metric_type": "CONVERSION", "subroute": "conversion_rate"},
        "123",
        14,
    )

    query = parse_qs(urlsplit(requested_urls[0]).query)
    variables = json.loads(unquote(query["variables"][0]))
    args = variables["request"]["arguments"]
    assert args["relativeDsStart"] == -14
    assert args["relativeDsEnd"] == -1
    assert result["ok"] is True
    assert result["granularity"] == ["DAY"]


def test_fetch_chart_marks_graphql_errors_failed(monkeypatch):
    module = load_probe_module()

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

    result = module.fetch_chart(
        "api-key",
        {},
        {"family": "conversion", "metric_type": "CONVERSION", "subroute": "conversion_rate"},
        "123",
        14,
    )

    assert result["ok"] is False
    assert result["status"] == 200
    assert result["granularity"] == []
    assert "ServiceBadRequestError" in result["error"]


def test_fetch_chart_accepts_operation_hash_override(monkeypatch):
    module = load_probe_module()
    requested_urls = []
    override_hash = "c" * 64

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({"data": {"porygon": {"getPerformanceComponents": {"components": []}}}}).encode()

    monkeypatch.setattr(module, "urlopen", lambda request, timeout: requested_urls.append(request.full_url) or FakeResponse())

    module.fetch_chart(
        "api-key",
        {},
        {"family": "conversion", "metric_type": "CONVERSION", "subroute": "conversion_rate"},
        "123",
        14,
        hash_value=override_hash,
    )

    assert f"/api/v3/ChartQuery/{override_hash}" in requested_urls[0]
