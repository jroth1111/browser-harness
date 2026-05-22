from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SKILL_ROOT = ROOT / "domain-skills" / "booking-com"


def test_booking_com_host_subskill_documents_all_property_download_scope():
    text = (SKILL_ROOT / "host_bookingcom.md").read_text(encoding="utf-8")

    assert "https://admin.booking.com/" in text
    assert "account.booking.com/sign-in" in text
    assert "all properties" in text.lower()
    assert "bookings_status" in text
    assert "invoices_status" in text
    assert "loginname" in text
    assert "hidden-password" in text
    assert "has_op_token: true" in text
    assert "Group homepage" in text
    assert "properties-free-text-search" in text
    assert "groups/reservations/index.html" in text
    assert "dateType=ARRIVAL" in text
    assert "search_reservations.html" in text
    assert "Reservations \u00b7 Booking.com" in text
    assert "peg-reservations-ranged" in text
    assert "Commission and charges" in text
    assert "booking.html" in text
    assert "Payout info" in text
    assert "Documents and invoices" in text
    assert "finance_invoices.html" in text
    assert "Download all 2026 PDFs" in text
    assert "get_document" in text
    assert "finance_reservations.html" in text
    assert "createDownloadableReservations" in text
    assert "checkReservationsDownloadableFilesStatus" in text
    assert "partner/exports/download" in text
    assert "typeOfDate: BOOKING" in text
    assert "propertyIds: []" in text
    assert "requests.reservation[]" in text
    assert "REQUEST_IS_DONE" in text
    assert "monthly `BOOKING` chunks" in text
    assert "download_blocked_by_browser_surface" in text
    assert "Verify your identity" in text
    assert "auth-assurance" in text
    assert "ses=<redacted>" in text
    assert ".private-data/host-bookingcom" in text
    assert "Do not type credentials" in text


def test_booking_com_overview_routes_admin_to_host_subskill():
    text = (SKILL_ROOT / "overview.md").read_text(encoding="utf-8")

    assert "host_bookingcom.md" in text
    assert "scraping.md" in text
    assert "admin.booking.com" in text


def test_booking_com_host_subskill_does_not_persist_session_secrets():
    text = (SKILL_ROOT / "host_bookingcom.md").read_text(encoding="utf-8")

    forbidden = [
        "bkng_sso_auth=",
        "aws-waf-token=",
        "esadm=",
        "op_token=Eg",
        "04a5d944c39269d5edd20f7c15a022c8",
    ]
    for secret in forbidden:
        assert secret not in text
