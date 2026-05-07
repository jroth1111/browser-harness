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


def test_append_ledger_rows_retries_short_os_write(tmp_path, monkeypatch):
    module = load_ledger_module()
    ledger = tmp_path / ".ledger.jsonl"
    rows = [sample_row(ds=f"2026-04-{day:02d}", value=day) for day in range(10, 15)]
    real_write = module.os.write
    write_sizes = []

    def short_write(fd, data):
        size = max(1, len(data) // 3)
        write_sizes.append(size)
        return real_write(fd, data[:size])

    monkeypatch.setattr(module.os, "write", short_write)

    module.append_ledger_rows(ledger, rows)
    index = module.read_ledger_index(ledger)

    assert len(write_sizes) > 1
    assert len(index) == len(rows)
    assert sorted(row["ds"] for row in index.values()) == [row["ds"] for row in rows]


def test_read_ledger_index_skips_trailing_partial_line(tmp_path):
    module = load_ledger_module()
    ledger = tmp_path / ".ledger.jsonl"
    complete = sample_row(ds="2026-04-20", value=4)
    ledger.write_text(
        module.json.dumps(complete, separators=(",", ":")) + "\n" + '{"listing_id":"truncated"',
        encoding="utf-8",
    )

    index = module.read_ledger_index(ledger)

    assert len(index) == 1
    assert next(iter(index.values()))["ds"] == "2026-04-20"


def test_read_ledger_index_skips_non_object_rows(tmp_path):
    module = load_ledger_module()
    ledger = tmp_path / ".ledger.jsonl"
    ledger.write_text(
        '"not-a-row"\n' + module.json.dumps(sample_row(ds="2026-04-20"), separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    index = module.read_ledger_index(ledger)

    assert len(index) == 1
    assert next(iter(index.values()))["ds"] == "2026-04-20"


def test_append_ledger_rows_truncates_trailing_partial_before_appending(tmp_path):
    module = load_ledger_module()
    ledger = tmp_path / ".ledger.jsonl"
    first = sample_row(ds="2026-04-20", value=4)
    second = sample_row(ds="2026-04-21", value=5)
    ledger.write_text(
        module.json.dumps(first, separators=(",", ":")) + "\n" + '{"listing_id":"truncated"',
        encoding="utf-8",
    )

    module.append_ledger_rows(ledger, [second])
    index = module.read_ledger_index(ledger)

    assert sorted(row["ds"] for row in index.values()) == ["2026-04-20", "2026-04-21"]


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


def test_latest_ds_helpers_tolerate_malformed_series_and_span_values():
    from datetime import date as _d

    module = load_ledger_module()
    rows = [
        {**sample_row(ds="2026-04-20"), "series_index": "not-an-index"},
        {**sample_row(ds="2026-04-21"), "series_granularity": module.SENTINEL_GRANULARITY, "_attempt_span_days": "not-a-span"},
    ]
    index = {("bad-series",): rows[0], ("bad-span",): rows[1]}

    assert module.latest_ds_per(index, listing_id="123", route_subroute="p3_impressions", series_index=0).isoformat() == "2026-04-21"
    buckets = module.build_latest_ds_index(index, today=_d(2026, 4, 28))

    assert buckets[("123", "p3_impressions", 0)] == [_d(2026, 4, 21)]


def test_latest_ds_helpers_reject_boolean_series_and_span_values():
    from datetime import date as _d

    module = load_ledger_module()
    rows = [
        {**sample_row(ds="2026-04-20"), "series_index": True},
        {**sample_row(ds="2026-04-21"), "series_granularity": module.SENTINEL_GRANULARITY, "_attempt_span_days": True},
    ]
    index = {("bad-series",): rows[0], ("bad-span",): rows[1]}

    assert module.latest_ds_per(index, listing_id="123", route_subroute="p3_impressions", series_index=0).isoformat() == "2026-04-21"
    buckets = module.build_latest_ds_index(index, today=_d(2026, 4, 28))

    assert buckets[("123", "p3_impressions", 0)] == [_d(2026, 4, 21)]
    assert ("123", "p3_impressions", 1) not in buckets


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


def sentinel_row(ds, observed_at, span_days=56):
    """Build a minimal attempt-sentinel row."""
    module = load_ledger_module()
    return {
        "listing_id": "123",
        "route_family": "conversion",
        "route_subroute": "p3_impressions",
        "series_index": 0,
        "ds": ds,
        "primary_metric_name": module.SENTINEL_PRIMARY_METRIC,
        "_attempt_span_days": span_days,
        "_attempt_window_kind": "single_window",
        "value": None,
        "value_string": None,
        "value_type": "ATTEMPT_SENTINEL",
        "series_granularity": module.SENTINEL_GRANULARITY,
        "observed_at": observed_at,
        "run_id": "run-sentinel",
        "source_url": "https://www.airbnb.com.au/performance/conversion/p3_impressions/listing/123?ds-start=-56&ds-end=0",
    }


def test_attempt_sentinel_expands_to_full_span():
    """A sentinel with _attempt_span_days=56 must add exactly 56 dates to the bucket."""
    from datetime import date as _d, timedelta
    module = load_ledger_module()
    today = _d(2026, 1, 1)
    # ds is 200 days ago — older tier, never expires.
    ds = (today - timedelta(days=200)).isoformat()
    observed_at = (today - timedelta(days=5)).isoformat() + "T00:00:00Z"
    row = sentinel_row(ds=ds, observed_at=observed_at, span_days=56)
    index = {module.ledger_key(row): row}
    buckets = module.build_latest_ds_index(index, today=today)
    key = ("123", "p3_impressions", 0)
    assert key in buckets
    assert len(buckets[key]) == 56


def test_attempt_sentinel_daily_tier_expiry_after_seven_days():
    """Daily-tier sentinel (ds within 90 days of today) observed 8+ days ago is ignored."""
    from datetime import date as _d, timedelta
    module = load_ledger_module()
    today = _d(2026, 4, 28)
    # ds is 30 days ago — within the 90-day daily tier.
    ds = (today - timedelta(days=30)).isoformat()
    # observed_at is 8 days ago — exceeds the 7-day expiry window.
    observed_at = (today - timedelta(days=8)).isoformat() + "T00:00:00Z"
    row = sentinel_row(ds=ds, observed_at=observed_at, span_days=30)
    index = {module.ledger_key(row): row}
    buckets = module.build_latest_ds_index(index, today=today)
    key = ("123", "p3_impressions", 0)
    # Expired sentinel contributes no dates.
    assert key not in buckets or len(buckets[key]) == 0


def test_attempt_sentinel_daily_tier_malformed_observed_at_is_ignored():
    """Daily-tier sentinel without a parseable attempt timestamp cannot suppress planning."""
    from datetime import date as _d, timedelta
    module = load_ledger_module()
    today = _d(2026, 4, 28)
    ds = (today - timedelta(days=30)).isoformat()
    row = sentinel_row(ds=ds, observed_at="not-a-date", span_days=30)
    index = {module.ledger_key(row): row}

    buckets = module.build_latest_ds_index(index, today=today)

    assert ("123", "p3_impressions", 0) not in buckets


def test_attempt_sentinel_older_tier_never_expires():
    """Older-tier sentinel (ds > 90 days ago) is honored regardless of observed_at age."""
    from datetime import date as _d, timedelta
    module = load_ledger_module()
    today = _d(2026, 4, 28)
    # ds is 365 days ago — well outside the 90-day daily tier.
    ds = (today - timedelta(days=365)).isoformat()
    # observed_at is 1 year ago — far beyond the daily-tier expiry window.
    observed_at = (today - timedelta(days=365)).isoformat() + "T00:00:00Z"
    row = sentinel_row(ds=ds, observed_at=observed_at, span_days=56)
    index = {module.ledger_key(row): row}
    buckets = module.build_latest_ds_index(index, today=today)
    key = ("123", "p3_impressions", 0)
    assert key in buckets
    assert len(buckets[key]) == 56


def test_build_latest_ds_index_all_four_granularities():
    """Synthetic 5-row ledger covering DAY, WEEK, MONTH, and ATTEMPT_RANGE.

    This is the comprehensive live-validation test from the plan (section 3).
    Asserts exact bucket contents day-by-day. The ATTEMPT_RANGE sentinel is
    placed in the older tier (> 90 days ago) so tiered expiry does not fire.
    """
    from datetime import date as _d, timedelta
    module = load_ledger_module()
    today = _d(2026, 4, 28)

    day_row = {**sample_row(ds="2026-04-10"), "series_granularity": "DAY"}          # 1 date: 2026-04-10
    week_row = {**sample_row(ds="2026-04-13"), "series_granularity": "WEEK"}         # 7 dates: 2026-04-13..19
    month_row = {**sample_row(ds="2026-03-01"), "series_granularity": "MONTH"}       # 30 dates: 2026-03-01..30
    # Older-tier sentinel: ds = 200 days ago, span = 14 days.
    sentinel_ds = (today - timedelta(days=200)).isoformat()
    sentinel_observed = (today - timedelta(days=5)).isoformat() + "T00:00:00Z"
    sent_row = sentinel_row(ds=sentinel_ds, observed_at=sentinel_observed, span_days=14)

    rows = [day_row, week_row, month_row, sent_row]
    index = {module.ledger_key(r): r for r in rows}

    buckets = module.build_latest_ds_index(index, today=today)
    key = ("123", "p3_impressions", 0)
    dates = buckets[key]

    assert len(dates) == 1 + 7 + 30 + 14, (
        f"Expected 52 total dates (1 DAY + 7 WEEK + 30 MONTH + 14 ATTEMPT_RANGE) but got {len(dates)}"
    )
    # DAY boundary
    assert _d(2026, 4, 10) in set(dates)
    # WEEK boundaries
    assert _d(2026, 4, 13) in set(dates)
    assert _d(2026, 4, 19) in set(dates)
    # MONTH boundaries
    assert _d(2026, 3, 1) in set(dates)
    assert _d(2026, 3, 30) in set(dates)
    # ATTEMPT_RANGE boundaries
    sentinel_start = _d.fromisoformat(sentinel_ds)
    sentinel_end = sentinel_start + timedelta(days=13)
    assert sentinel_start in set(dates)
    assert sentinel_end in set(dates)


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
