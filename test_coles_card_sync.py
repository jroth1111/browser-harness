import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).parent / "domain-skills" / "coles_card" / "scripts" / "sync.py"
spec = importlib.util.spec_from_file_location("coles_card_sync", MODULE_PATH)
coles_card_sync = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(coles_card_sync)


def test_money_parser_handles_aud_formats():
    assert coles_card_sync.parse_money_to_cents("$1,234.56") == 123456
    assert coles_card_sync.parse_money_to_cents("-$12.30") == -1230
    assert coles_card_sync.parse_money_to_cents("−$12.30") == -1230
    assert coles_card_sync.parse_money_to_cents("+$12.30") == 1230
    assert coles_card_sync.parse_money_to_cents("($42.00)") == -4200


def test_sanitize_payload_redacts_auth_redirect_values():
    payload = {
        "url": "https://id.colesgroupprofile.com.au/?token=abc.def.ghi&state=secret&clientName=NAB",
        "page": {"body_excerpt": "signed in as user@example.com with abc.def.ghi"},
    }
    sanitized = coles_card_sync.sanitize_payload(payload)

    assert "abc.def.ghi" not in str(sanitized)
    assert "secret" not in str(sanitized)
    assert "user@example.com" not in str(sanitized)
    assert "clientName=NAB" in sanitized["url"]


def test_defaults_avoid_forced_login_route():
    assert coles_card_sync.DEFAULT_START_URL == "https://secure.coles.com.au/home/account_dashboard"
    assert coles_card_sync.DEFAULT_AUTH_MAX_AGE == 20


def test_upsert_payload_deduplicates_transactions(tmp_path):
    db_path = tmp_path / "coles.sqlite3"
    conn = coles_card_sync.init_db(db_path)
    coles_card_sync.insert_run(conn, "run-1")
    payload = {
        "url": "https://secure.coles.com.au/transactions",
        "account_label": "Coles Mastercard ending 1234",
        "balances": [
            {
                "balance_type": "current_balance",
                "label": "Current balance",
                "amount_text": "$123.45",
                "currency": "AUD",
                "raw_text": "Current balance $123.45",
            }
        ],
        "transactions": [
            {
                "posted_date_text": "5 May 2026",
                "description": "Sample Merchant",
                "amount_text": "-$12.34",
                "currency": "AUD",
                "raw_text": "5 May 2026 Sample Merchant -$12.34",
            },
            {
                "posted_date_text": "5 May 2026",
                "description": "Sample Merchant",
                "amount_text": "-$12.34",
                "currency": "AUD",
                "raw_text": "5 May 2026 Sample Merchant -$12.34",
            },
        ],
    }
    counts = coles_card_sync.upsert_payload(conn, "run-1", payload)

    assert counts["balances"] == 1
    assert counts["transactions"] == 2
    assert conn.execute("select count(*) from transactions").fetchone()[0] == 1
    assert conn.execute("select amount_cents from transactions").fetchone()[0] == -1234
    assert conn.execute("select amount_cents from balance_snapshots").fetchone()[0] == 12345
    conn.close()


def test_upsert_payload_imports_csv_export_fields(tmp_path):
    db_path = tmp_path / "coles.sqlite3"
    conn = coles_card_sync.init_db(db_path)
    coles_card_sync.insert_run(conn, "run-csv")
    payload = {
        "url": "https://secure.coles.com.au/transactions",
        "account_label": "Coles Rewards Mastercard ending 0475",
        "balances": [],
        "transactions": [],
        "transactions_csv": [
            {
                "Date": "05 May 26",
                "Amount": "-$9.27",
                "Account Number": "Card ending 8954",
                "": "",
                "Transaction Type": "Pending",
                "Transaction Details": "Pending: DiDi Card ending 8954",
                "Category": "Taxis & ride shares",
                "Merchant Name": "DiDi",
                "Processed On": "",
            }
        ],
    }
    counts = coles_card_sync.upsert_payload(conn, "run-csv", payload)

    row = conn.execute(
        "select posted_date, amount_cents, merchant_name, category, card_ending, status, source_method from transactions"
    ).fetchone()
    assert counts["transactions"] == 1
    assert counts["transactions_inserted"] == 1
    assert row["posted_date"] == "2026-05-05"
    assert row["amount_cents"] == -927
    assert row["merchant_name"] == "DiDi"
    assert row["category"] == "Taxis & ride shares"
    assert row["card_ending"] == "8954"
    assert row["status"] == "pending"
    assert row["source_method"] == "csv_export"
    conn.close()
