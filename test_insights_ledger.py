import importlib.util
from pathlib import Path


def load_module(path, name):
    path = Path(path)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_ledger_module():
    return load_module("domain-skills/airbnb/scripts/insights_ledger.py", "airbnb_insights_ledger")


def sample_row(observed_at="2026-04-28T04:15:12Z", ds="2026-04-20", value=1):
    return {
        "listing_id": "123",
        "route_family": "conversion",
        "route_subroute": "p3_impressions",
        "series_index": 0,
        "ds": ds,
        "primary_metric_name": "p3_impressions",
        "value": value,
        "value_string": str(value),
        "value_type": "LONG",
        "series_granularity": "DAY",
        "observed_at": observed_at,
        "run_id": "run-x",
        "source_url": "https://www.airbnb.com.au/performance/conversion/p3_impressions/listing/123?ds-start=-7&ds-end=0",
    }


def test_append_and_read_round_trip(tmp_path):
    module = load_ledger_module()
    ledger = tmp_path / ".ledger.jsonl"
    rows = [sample_row(ds="2026-04-19", value=3), sample_row(ds="2026-04-20", value=4)]

    module.append_ledger_rows(ledger, rows)
    index = module.read_ledger_index(ledger)

    assert len(index) == 2
    assert sorted(row["ds"] for row in index.values()) == ["2026-04-19", "2026-04-20"]


def test_read_ledger_index_newer_observed_at_wins(tmp_path):
    module = load_ledger_module()
    ledger = tmp_path / ".ledger.jsonl"
    older = sample_row(observed_at="2026-04-20T00:00:00Z", ds="2026-04-20", value=1)
    newer = sample_row(observed_at="2026-04-21T00:00:00Z", ds="2026-04-20", value=9)

    module.append_ledger_rows(ledger, [older, newer])
    index = module.read_ledger_index(ledger)

    assert len(index) == 1
    only = next(iter(index.values()))
    assert only["value"] == 9
    assert only["observed_at"] == "2026-04-21T00:00:00Z"


def test_latest_ds_per_ignores_other_series_and_routes(tmp_path):
    module = load_ledger_module()
    ledger = tmp_path / ".ledger.jsonl"
    rows = [
        sample_row(ds="2026-04-10"),
        sample_row(ds="2026-04-21"),
        {**sample_row(ds="2026-04-30"), "series_index": 1},
        {**sample_row(ds="2026-04-29"), "route_subroute": "wishlist"},
    ]
    module.append_ledger_rows(ledger, rows)
    index = module.read_ledger_index(ledger)

    latest = module.latest_ds_per(index, listing_id="123", route_subroute="p3_impressions", series_index=0)
    assert latest.isoformat() == "2026-04-21"


def test_append_ledger_rows_noop_for_empty_rows(tmp_path):
    module = load_ledger_module()
    ledger = tmp_path / ".ledger.jsonl"
    module.append_ledger_rows(ledger, [])
    assert not ledger.exists()


def test_build_latest_ds_index_buckets_and_expands_granularity():
    """A WEEK-granularity row covers 7 calendar days; a MONTH covers 30."""
    module = load_ledger_module()
    rows = [
        {**sample_row(ds="2026-01-05"), "series_granularity": "DAY"},
        {**sample_row(ds="2026-01-12"), "series_granularity": "WEEK"},
        {**sample_row(ds="2026-02-01"), "series_granularity": "MONTH"},
    ]
    index = {module.ledger_key(r): r for r in rows}
    buckets = module.build_latest_ds_index(index)
    key = ("123", "p3_impressions", 0)
    dates = buckets[key]
    # DAY contributes 1 date, WEEK contributes 7, MONTH contributes 30.
    assert len(dates) == 1 + 7 + 30
    from datetime import date as _d
    # First and last bound checks
    assert dates[0] == _d(2026, 1, 5)
    assert dates[-1] == _d(2026, 3, 2)  # 2026-02-01 + 29 days


def test_latest_ds_lookup_respects_max_ds_via_binary_search(tmp_path):
    module = load_ledger_module()
    ledger = tmp_path / ".ledger.jsonl"
    module.append_ledger_rows(
        ledger,
        [
            sample_row(ds="2025-12-01"),
            sample_row(ds="2026-01-15"),
            sample_row(ds="2026-03-20"),
        ],
    )
    index = module.read_ledger_index(ledger)
    buckets = module.build_latest_ds_index(index)

    from datetime import date as _d

    assert module.latest_ds_lookup(buckets, "123", "p3_impressions", 0) == _d(2026, 3, 20)
    assert module.latest_ds_lookup(buckets, "123", "p3_impressions", 0, max_ds="2026-02-01") == _d(2026, 1, 15)
    assert module.latest_ds_lookup(buckets, "123", "p3_impressions", 0, max_ds="2025-11-30") is None
    assert module.latest_ds_lookup(buckets, "999", "p3_impressions", 0) is None


def test_build_latest_ds_index_expands_week_granularity(tmp_path):
    module = load_ledger_module()
    ledger = tmp_path / ".ledger.jsonl"
    module.append_ledger_rows(
        ledger,
        [{**sample_row(ds="2026-04-06"), "series_granularity": "WEEK"}],
    )
    index = module.read_ledger_index(ledger)

    buckets = module.build_latest_ds_index(index)
    covered = buckets[("123", "p3_impressions", 0)]

    assert covered[0].isoformat() == "2026-04-06"
    assert covered[-1].isoformat() == "2026-04-12"
    assert len(covered) == 7
