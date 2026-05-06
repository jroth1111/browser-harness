import importlib.util
from pathlib import Path


def load_module():
    path = Path("domain-skills/airbnb/scripts/collect_exports.py")
    spec = importlib.util.spec_from_file_location("airbnb_collect_exports", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_earnings_csv_parser_normalizes_money_and_source_metadata():
    module = load_module()
    text = Path("domain-skills/airbnb/fixtures/parser-contracts/exports/earnings.csv").read_text()

    rows = module.parse_earnings_csv(
        text,
        observed_at="2026-04-29T00:00:00Z",
        source_path="earnings.csv",
    )

    assert len(rows) == 1
    assert rows[0]["source_family"] == "host_export"
    assert rows[0]["surface_class"] == "earnings_export"
    assert rows[0]["listing_id"] == "100"
    assert rows[0]["reservation_id"] == "HMABC12345"
    assert rows[0]["gross_earnings"] == 900.0
    assert rows[0]["host_service_fee"] == 27.0
    assert rows[0]["payout_amount"] == 873.0


def test_reservation_detail_parser_extracts_print_export_fields_without_raw_guest_name():
    module = load_module()
    text = Path("domain-skills/airbnb/fixtures/parser-contracts/exports/reservation-detail.txt").read_text()

    rows = module.parse_reservation_detail_text(
        text,
        observed_at="2026-04-29T00:00:00Z",
        source_path="reservation-detail.txt",
    )

    assert rows == [
        {
            "reservation_export_row_id": "reservation:reservation-detail.txt:HMABC12345",
            "observed_at": "2026-04-29T00:00:00Z",
            "source_family": "host_export",
            "surface_class": "reservation_detail_export",
            "auth_context": "downloaded_export_file",
            "source_path": "reservation-detail.txt",
            "reservation_id": "HMABC12345",
            "listing_id": "100",
            "listing_name": "City apartment",
            "guest_name_present": True,
            "check_in_date": "2026-05-01",
            "check_out_date": "2026-05-04",
            "nights": 3,
            "guest_count": 2,
            "currency": "AUD",
            "total_payout": 873.0,
            "raw_field_keys": [
                "check_in",
                "check_out",
                "currency",
                "guest",
                "guests",
                "listing",
                "listing_id",
                "nights",
                "payout",
                "reservation_id",
            ],
        }
    ]


def test_personal_data_export_catalog_classifies_directory_entries(tmp_path):
    module = load_module()
    (tmp_path / "reservations.csv").write_text("id\n1\n")
    (tmp_path / "messages.json").write_text("[]")
    (tmp_path / "profile.txt").write_text("profile")

    rows = module.parse_personal_data_export_catalog(tmp_path, observed_at="2026-04-29T00:00:00Z")

    by_path = {row["entry_path"]: row for row in rows}
    assert by_path["reservations.csv"]["entry_category"] == "reservations"
    assert by_path["messages.json"]["entry_category"] == "messages"
    assert by_path["profile.txt"]["entry_category"] == "profile"
    assert all(row["source_family"] == "host_export" for row in rows)
