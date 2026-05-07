import importlib.util
import json
from pathlib import Path


def load_module():
    path = Path("domain-skills/airbnb/scripts/collect_calendar_export.py")
    spec = importlib.util.spec_from_file_location("airbnb_collect_calendar_export", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SAMPLE_ICS = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:reservation-abc@example
DTSTART;VALUE=DATE:20260501
DTEND;VALUE=DATE:20260504
SUMMARY:Reserved - HMABC12345
DESCRIPTION:Booking ID: HMABC12345\\nGuests: 2\\nFolded
 line
END:VEVENT
BEGIN:VEVENT
UID:block-1@example
DTSTART;VALUE=DATE:20260510
DTEND;VALUE=DATE:20260511
SUMMARY:Blocked
DESCRIPTION:Owner block
END:VEVENT
END:VCALENDAR
"""


def test_build_collection_expands_ical_events_to_daily_snapshots():
    module = load_module()

    events, snapshots = module.build_collection(
        SAMPLE_ICS,
        listing_id="100",
        observed_at="2026-04-28T00:00:00Z",
        source="https://calendar.example/export.ics?secret=token",
    )

    assert len(events) == 2
    assert events[0]["status"] == "booked"
    assert events[0]["reservation_id"] == "HMABC12345"
    assert events[0]["source_url"] == "https://calendar.example/export.ics?redacted_query=1"
    assert "raw_description" not in events[0]
    assert [row["calendar_date"] for row in snapshots[:3]] == ["2026-05-01", "2026-05-02", "2026-05-03"]
    assert snapshots[0]["surface_class"] == "calendar_export"
    assert snapshots[-1]["status"] == "blocked"


def test_include_raw_text_is_explicit_opt_in():
    module = load_module()

    events, _ = module.build_collection(
        SAMPLE_ICS,
        listing_id="100",
        observed_at="2026-04-28T00:00:00Z",
        source="/tmp/sample.ics",
        include_raw_text=True,
    )

    assert events[0]["raw_summary"] == "Reserved - HMABC12345"
    assert "Foldedline" in events[0]["raw_description"]


def test_latest_prior_event_count_filters_by_listing(tmp_path, monkeypatch):
    module = load_module()
    monkeypatch.setattr(module, "OUTPUT_PATH", tmp_path)
    (tmp_path / "custom-run-id.json").write_text(json.dumps({
        "observed_at": "2026-04-27T00:00:00Z",
        "listing_id": "100",
        "event_count": 3,
    }))
    (tmp_path / "airbnb-calendar-export-other.json").write_text(json.dumps({
        "observed_at": "2026-04-28T00:00:00Z",
        "listing_id": "200",
        "event_count": 9,
    }))

    assert module.latest_prior_event_count("100") == 3
    assert module.latest_prior_event_count("missing") == 0


def test_latest_prior_event_count_tolerates_malformed_count(tmp_path, monkeypatch):
    module = load_module()
    monkeypatch.setattr(module, "OUTPUT_PATH", tmp_path)
    (tmp_path / "airbnb-calendar-export-bad.json").write_text(json.dumps({
        "observed_at": "2026-04-29T00:00:00Z",
        "listing_id": "100",
        "event_count": "not-a-count",
    }))
    (tmp_path / "airbnb-calendar-export-good.json").write_text(json.dumps({
        "observed_at": "2026-04-28T00:00:00Z",
        "listing_id": "100",
        "event_count": 3,
    }))

    assert module.latest_prior_event_count("100") == 0
