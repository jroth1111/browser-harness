import importlib.util
from datetime import date
from pathlib import Path


def load_module():
    path = Path("domain-skills/airbnb/scripts/surface_capabilities.py")
    spec = importlib.util.spec_from_file_location("airbnb_surface_capabilities", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_capability_record_redacts_sensitive_query_values_and_records_hash_prefix():
    module = load_module()
    url = (
        "https://www.airbnb.com.au/api/v3/BeehiveGetListingsQuery/"
        + "a" * 64
        + "?operationName=BeehiveGetListingsQuery&variables=%7Bprivate%7D&currency=AUD"
    )

    record = module.capability_record(
        "host_listing_inventory",
        observed_at="2026-04-28T00:00:00Z",
        auth_context="test",
        source_url=url,
        resource_urls=[url],
        operation_hashes={"BeehiveGetListingsQuery": "b" * 64},
        operation_hash_sources={"BeehiveGetListingsQuery": "bundle.js"},
    )

    assert record["status"] == "capability_observed"
    assert record["surface_class"] == "host_private"
    assert record["matched_resource_count"] == 1
    assert "variables" not in record["matched_resource_urls"][0]
    assert "redacted_query=1" in record["matched_resource_urls"][0]
    assert record["operation_hashes"]["BeehiveGetListingsQuery"] == {
        "hash_present": True,
        "hash_prefix": "bbbbbbbb",
        "hash_source": "bundle.js",
    }


def test_upsert_best_capability_replaces_not_observed_with_observed():
    module = load_module()
    records = [
        module.capability_record(
            "public_comp_search",
            observed_at="2026-04-28T00:00:00Z",
            resource_urls=[],
        )
    ]
    observed = module.capability_record(
        "public_comp_search",
        observed_at="2026-04-28T00:01:00Z",
        resource_urls=["https://www.airbnb.com.au/api/v3/StaysSearch/{}?operationName=StaysSearch"],
    )

    module.upsert_best_capability(records, observed)

    assert len(records) == 1
    assert records[0]["status"] == "capability_observed"
    assert records[0]["matched_resource_count"] == 1


def test_upsert_best_capability_treats_malformed_counts_as_zero():
    module = load_module()
    records = [
        {
            "surface_id": "public_comp_search",
            "status": "capability_observed",
            "matched_resource_count": "not-a-count",
        }
    ]
    observed = {
        "surface_id": "public_comp_search",
        "status": "capability_observed",
        "matched_resource_count": 1,
    }

    module.upsert_best_capability(records, observed)

    assert records == [observed]


def test_upsert_best_capability_treats_boolean_counts_as_zero():
    module = load_module()
    records = [
        {
            "surface_id": "public_comp_search",
            "status": "capability_observed",
            "matched_resource_count": True,
        }
    ]
    observed = {
        "surface_id": "public_comp_search",
        "status": "capability_observed",
        "matched_resource_count": 1,
    }

    module.upsert_best_capability(records, observed)

    assert records == [observed]


def test_build_staleness_plan_uses_surface_cadence():
    module = load_module()

    plan = module.build_staleness_plan(
        {"public_comp_search": "2026-04-20T00:00:00Z"},
        today=date(2026, 4, 28),
        surface_ids_to_check=["public_comp_search", "host_listing_inventory"],
    )

    assert plan[0]["stale"] is True
    assert plan[0]["cadence_days"] == 7
    assert plan[1]["stale"] is True
    assert plan[1]["last_observed_at"] is None


def test_surface_specs_cover_execute_all_plan_items_once():
    module = load_module()

    items = [module.SURFACE_SPECS[surface_id]["plan_item"] for surface_id in module.surface_ids()]

    assert sorted(items) == list(range(1, 11))


def test_network_discovery_record_extracts_operations_without_payloads():
    module = load_module()
    url = (
        "https://www.airbnb.com.au/api/v3/StaysSearch/"
        + "c" * 64
        + "?operationName=StaysSearch&variables=%7Bsecret%7D&extensions=%7Bhash%7D"
    )

    record = module.network_discovery_record([url, "https://www.airbnb.com.au/rooms/123456"])

    assert record["resource_count"] == 2
    assert record["api_operations"]["StaysSearch"] == {"count": 1, "hash_prefixes": ["cccccccc"]}
    assert "variables" not in record["redacted_resource_urls"][0]
    assert "redacted_query=1" in record["redacted_resource_urls"][0]


def test_refresh_tasks_prioritize_stale_surfaces():
    module = load_module()

    tasks = module.build_refresh_tasks(
        {
            "host_listing_inventory": "2026-03-01T00:00:00Z",
            "own_public_audit": "2026-04-27T00:00:00Z",
        },
        today=date(2026, 4, 28),
        surface_ids_to_check=[
            "host_listing_inventory",
            "own_public_audit",
            "calendar_export",
            "public_comp_search",
        ],
    )

    assert [task["surface_id"] for task in tasks] == ["host_listing_inventory", "calendar_export", "public_comp_search"]
    assert tasks[0]["reason"] == "cadence_expired"
    assert tasks[1]["surface_class"] == "calendar_export"
    assert tasks[1]["reason"] == "never_observed"
    assert tasks[2]["reason"] == "never_observed"


def test_capability_registry_records_ttl_hash_and_redacted_provenance(tmp_path):
    module = load_module()

    entry = module.capability_registry_entry(
        "host_listing_inventory",
        observed_at="2026-04-28T00:00:00Z",
        endpoint_url="https://www.airbnb.com.au/api/v3/BeehiveGetListingsQuery/"
        + "a" * 64
        + "?variables=secret&operationName=BeehiveGetListingsQuery",
        operation_name="BeehiveGetListingsQuery",
        operation_hash="a" * 64,
        ttl_days=7,
        provenance={"source": "bundle.js?token=redacted"},
    )

    assert entry["operation_hash_prefix"] == "aaaaaaaa"
    assert "variables" not in entry["endpoint_url"]
    assert entry["expires_at"] == "2026-05-05T00:00:00Z"
    assert module.capability_registry_status(entry, today=date(2026, 5, 4)) == "active"
    assert module.capability_registry_status(entry, today=date(2026, 5, 6)) == "stale"

    entries = module.upsert_capability_registry([], entry)
    newer = {**entry, "last_seen_at": "2026-04-29T00:00:00Z"}
    entries = module.upsert_capability_registry(entries, newer)
    assert len(entries) == 1
    assert entries[0]["first_seen_at"] == "2026-04-28T00:00:00Z"
    assert module.registry_ref(entries[0])["registry_id"] == entry["registry_id"]

    path = tmp_path / "registry.json"
    module.save_capability_registry(path, entries)
    assert module.load_capability_registry(path) == entries
