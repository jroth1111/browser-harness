import importlib.util
from datetime import date
from pathlib import Path

import pytest


def load_module():
    path = Path("agent-workspace/domain-skills/airbnb/scripts/operation_hashes.py")
    spec = importlib.util.spec_from_file_location("airbnb_operation_hashes", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_operation_hashes_from_direct_api_path():
    module = load_module()
    hash_value = "1" * 64

    found = module.operation_hashes_from_text(
        f'fetch("/api/v3/ChartQuery/{hash_value}?operationName=ChartQuery")',
        ["ChartQuery"],
    )

    assert found == {"ChartQuery": hash_value}


def test_discover_operation_hashes_walks_airbnb_static_bundle_references():
    module = load_module()
    chart_hash = "2" * 64
    metrics_hash = "3" * 64
    seed = (
        'src="https://a0.muscache.com/airbnb/static/packages/web/frontend/airmetro/browser/asyncRequire.abc.js"'
    )
    files = {
        "https://a0.muscache.com/airbnb/static/packages/web/frontend/airmetro/browser/asyncRequire.abc.js":
            '"/airbnb/static/packages/web/common/frontend/performance/route.prepare.def.js"',
        "https://a0.muscache.com/airbnb/static/packages/web/common/frontend/performance/route.prepare.def.js":
            f'operationName:"ChartQuery",operationId:"{chart_hash}";'
            f'operationName:"ListOfMetricsQuery",persistedQuery:{{sha256Hash:"{metrics_hash}"}};',
    }

    result = module.discover_operation_hashes(
        lambda url: files[url],
        ["ChartQuery", "ListOfMetricsQuery"],
        seed_texts=[seed],
    )

    assert result["hashes"] == {"ChartQuery": chart_hash, "ListOfMetricsQuery": metrics_hash}
    assert result["visited_count"] == 2


def test_resolve_operation_hashes_prefers_explicit_env_over_discovery():
    module = load_module()
    defaults = {"ChartQuery": "1" * 64}
    discovered = {"ChartQuery": "2" * 64}
    env = {"AIRBNB_INSIGHTS_CHARTQUERY_HASH": "3" * 64}

    hashes, sources = module.resolve_operation_hashes(defaults, discovered=discovered, env=env)

    assert hashes == {"ChartQuery": "3" * 64}
    assert sources == {"ChartQuery": "env"}


def test_resolve_operation_hashes_rejects_invalid_env_override():
    module = load_module()

    with pytest.raises(ValueError, match="Invalid AIRBNB_INSIGHTS_CHARTQUERY_HASH"):
        module.resolve_operation_hashes(
            {"ChartQuery": "1" * 64},
            env={"AIRBNB_INSIGHTS_CHARTQUERY_HASH": "not-a-hash"},
        )


def test_operation_hashes_from_registry_uses_active_non_expired_rows():
    module = load_module()

    hashes, sources = module.operation_hashes_from_registry(
        [
            {
                "surface_id": "host_reviews",
                "operation_name": "ChartQuery",
                "operation_hash": "2" * 64,
                "last_seen_at": "2026-04-28T00:00:00Z",
                "expires_at": "2026-05-05T00:00:00Z",
                "status": "active",
            },
            {
                "surface_id": "host_reviews",
                "operation_name": "ListOfMetricsQuery",
                "operation_hash": "3" * 64,
                "last_seen_at": "2026-04-28T00:00:00Z",
                "expires_at": "2026-04-01T00:00:00Z",
                "status": "active",
            },
        ],
        ["ChartQuery", "ListOfMetricsQuery"],
        surface_id="host_reviews",
        today=date(2026, 4, 29),
    )

    assert hashes == {"ChartQuery": "2" * 64}
    assert sources == {"ChartQuery": "capability_registry"}
