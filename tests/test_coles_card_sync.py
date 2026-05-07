import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).parent.parent / "domain-skills" / "coles_card" / "scripts" / "sync.py"
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
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyMTIzNCJ9.s4mPL3SiGn4tur3xx"
    payload = {
        "url": (
            f"https://id.colesgroupprofile.com.au/?token={jwt}"
            f"&state=secret&session_state=sess1234&code_verifier=vCode99&clientName=NAB"
        ),
        "page": {
            "body_excerpt": (
                f"signed in as user@example.com with {jwt} via auth.colesgroupprofile.com.au"
            )
        },
    }
    sanitized = coles_card_sync.sanitize_payload(payload)
    sanitized_str = str(sanitized)

    assert jwt not in sanitized_str
    assert "secret" not in sanitized_str
    assert "sess1234" not in sanitized_str
    assert "vCode99" not in sanitized_str
    assert "user@example.com" not in sanitized_str
    assert "clientName=NAB" in sanitized["url"]
    # Domain names must NOT be matched by the JWT redactor.
    assert "auth.colesgroupprofile.com.au" in sanitized["page"]["body_excerpt"]


def test_normalize_date_rejects_invalid_month():
    assert coles_card_sync.normalize_date("12/31/2025") == "12/31/2025"
    assert coles_card_sync.normalize_date("05/05/2026") == "2026-05-05"
    assert coles_card_sync.normalize_date("5 May 2026") == "2026-05-05"


def test_upsert_payload_skips_dom_rows_when_csv_present(tmp_path):
    db_path = tmp_path / "coles.sqlite3"
    conn = coles_card_sync.init_db(db_path)
    coles_card_sync.insert_run(conn, "run-mixed")
    payload = {
        "url": "https://secure.coles.com.au/transactions",
        "account_label": "Coles Mastercard ending 1234",
        "balances": [],
        "transactions": [
            {
                "posted_date_text": "5 May 2026",
                "description": "DiDi Card ending 8954",
                "amount_text": "-$9.27",
                "currency": "AUD",
                "raw_text": "5 May 2026 DiDi Card ending 8954 -$9.27",
            }
        ],
        "transactions_csv": [
            {
                "Date": "05 May 26",
                "Amount": "-$9.27",
                "Account Number": "Card ending 8954",
                "Transaction Type": "Pending",
                "Transaction Details": "Pending: DiDi Card ending 8954",
                "Category": "Taxis & ride shares",
                "Merchant Name": "DiDi",
                "Processed On": "",
            }
        ],
    }
    counts = coles_card_sync.upsert_payload(conn, "run-mixed", payload)

    assert counts["transactions_csv"] == 1
    assert counts["transactions_dom"] == 0
    assert conn.execute("select count(*) from transactions").fetchone()[0] == 1
    row = conn.execute(
        "select source_method, merchant_name from transactions"
    ).fetchone()
    assert row["source_method"] == "csv_export"
    assert row["merchant_name"] == "DiDi"
    conn.close()


def test_upsert_payload_uses_account_label_override(tmp_path):
    db_path = tmp_path / "coles.sqlite3"
    conn = coles_card_sync.init_db(db_path)
    coles_card_sync.insert_run(conn, "run-label")
    payload = {
        "url": "https://secure.coles.com.au/transactions",
        "account_label": "Drifted page label 5678",
        "balances": [],
        "transactions": [
            {
                "posted_date_text": "5 May 2026",
                "description": "Coffee",
                "amount_text": "-$5.00",
            }
        ],
    }
    stable = "Coles Mastercard ending 1234"
    counts = coles_card_sync.upsert_payload(
        conn, "run-label", payload, account_label_override=stable
    )

    assert counts["account_key"] == coles_card_sync.account_key(stable)
    label_in_db = conn.execute("select account_label from accounts").fetchone()[0]
    assert label_in_db == stable
    conn.close()


def test_upsert_payload_skips_malformed_payload_rows(tmp_path):
    db_path = tmp_path / "coles.sqlite3"
    conn = coles_card_sync.init_db(db_path)
    coles_card_sync.insert_run(conn, "run-malformed")
    payload = {
        "url": "https://secure.coles.com.au/transactions",
        "account_label": "Coles Mastercard ending 1234",
        "balances": [
            "not-a-row",
            {"balance_type": "current_balance", "label": "Current balance", "amount_text": "$123.45"},
        ],
        "transactions_csv": ["not-a-row"],
        "transactions": [
            "not-a-row",
            {"posted_date_text": "5 May 2026", "description": "Coffee", "amount_text": "-$5.00"},
        ],
    }

    counts = coles_card_sync.upsert_payload(conn, "run-malformed", payload)

    assert counts["balances"] == 1
    assert counts["transactions"] == 1
    assert counts["transactions_csv"] == 0
    assert counts["transactions_dom"] == 1
    assert conn.execute("select count(*) from balance_snapshots").fetchone()[0] == 1
    assert conn.execute("select count(*) from transactions").fetchone()[0] == 1
    conn.close()


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


def test_upsert_payload_dedups_balance_snapshots_per_type(tmp_path):
    db_path = tmp_path / "coles.sqlite3"
    conn = coles_card_sync.init_db(db_path)
    coles_card_sync.insert_run(conn, "run-bal")
    payload = {
        "url": "https://secure.coles.com.au/home/account_dashboard",
        "account_label": "Coles Mastercard ending 1234",
        "balances": [
            {
                "balance_type": "current_balance",
                "label": "Current balance",
                "amount_text": "$123.45",
                "currency": "AUD",
                "raw_text": "Current balance $123.45 (header)",
            },
            {
                "balance_type": "current_balance",
                "label": "Current balance",
                "amount_text": "$123.45",
                "currency": "AUD",
                "raw_text": "Current balance $123.45 (summary card)",
            },
        ],
        "transactions": [],
    }
    counts = coles_card_sync.upsert_payload(conn, "run-bal", payload)

    assert counts["balances"] == 2
    assert conn.execute("select count(*) from balance_snapshots").fetchone()[0] == 1
    conn.close()


def test_upsert_payload_preserves_csv_source_after_dom_run(tmp_path):
    db_path = tmp_path / "coles.sqlite3"
    conn = coles_card_sync.init_db(db_path)
    coles_card_sync.insert_run(conn, "run-csv")
    csv_payload = {
        "url": "https://secure.coles.com.au/transactions",
        "account_label": "Coles Mastercard ending 1234",
        "balances": [],
        "transactions": [],
        "transactions_csv": [
            {
                "Date": "05 May 26",
                "Amount": "-$9.27",
                "Account Number": "Card ending 8954",
                "Transaction Type": "Posted",
                "Transaction Details": "Coffee Shop",
                "Category": "Food",
                "Merchant Name": "Coffee Shop",
                "Processed On": "06 May 26",
            }
        ],
    }
    coles_card_sync.upsert_payload(conn, "run-csv", csv_payload)

    coles_card_sync.insert_run(conn, "run-dom")
    dom_payload = {
        "url": "https://secure.coles.com.au/transactions",
        "account_label": "Coles Mastercard ending 1234",
        "balances": [],
        "transactions": [
            {
                "posted_date_text": "5 May 2026",
                "description": "Coffee Shop",
                "amount_text": "-$9.27",
                "currency": "AUD",
                "raw_text": "5 May 2026 Coffee Shop -$9.27",
                "processed_on": "2026-05-06",
                "account_number": "Card ending 8954",
            }
        ],
    }
    coles_card_sync.upsert_payload(conn, "run-dom", dom_payload)

    rows = conn.execute(
        "select source_method, merchant_name, category, raw_json from transactions"
    ).fetchall()
    assert len(rows) == 1
    row = rows[0]
    assert row["source_method"] == "csv_export"
    assert row["merchant_name"] == "Coffee Shop"
    assert row["category"] == "Food"
    assert "Merchant Name=Coffee Shop" in row["raw_json"]
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
