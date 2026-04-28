import json
import os
import subprocess
from pathlib import Path

import pytest


LISTINGS_FILE = Path("domain-skills/airbnb/.private-data/listing-collections/airbnb-live-listings-20260427T080658Z.json")
SESSION_DIR = Path("domain-skills/airbnb/.session-store/capability")
LEDGER_PATH = Path("domain-skills/airbnb/.private-data/insights-collections/.ledger.jsonl")


def test_429_storm_simulation_stops_with_partial_receipt():
    if os.environ.get("AIRBNB_E2E_NEGATIVE_429") != "1":
        pytest.skip("AIRBNB_E2E_NEGATIVE_429=1 not set (requires live Airbnb host session)")
    before_size = LEDGER_PATH.stat().st_size if LEDGER_PATH.exists() else 0
    run_id = "e2e-airbnb-insights-forced-429"
    env = os.environ.copy()
    env.update(
        {
            "AIRBNB_INSIGHTS_RUN_ID": run_id,
            "AIRBNB_INSIGHTS_FORCE_429_SIM": "1",
            "AIRBNB_INSIGHTS_SKIP_BOOTSTRAP": "1",
            "AIRBNB_API_KEY": "forced-429",
            "AIRBNB_LISTINGS_FILE": str(LISTINGS_FILE),
            "AIRBNB_INSIGHTS_LIMIT_LISTINGS": "1",
            "AIRBNB_INSIGHTS_LIMIT_ROUTES": "1",
            "AIRBNB_INSIGHTS_LIMIT_PERIODS": "1",
            "AIRBNB_INSIGHTS_HISTORY_DAYS": "14",
            "AIRBNB_INSIGHTS_429_BACKOFF_SEC": "0",
            "AIRBNB_INSIGHTS_BATCH_DELAY_SEC": "0",
            "AIRBNB_INSIGHTS_RETRY_LIMIT": "0",
            "AIRBNB_INSIGHTS_STOP_AFTER_429_BATCHES": "1",
        }
    )
    subprocess.run(
        ["python3", "domain-skills/airbnb/scripts/collect_insights.py"],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    receipt_path = SESSION_DIR / f"{run_id}-receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["all_api_requests_ok"] is False
    assert receipt["failures_count"] > 0
    assert any(item.get("status") == 429 for item in receipt.get("failure_sample", []))
    after_size = LEDGER_PATH.stat().st_size if LEDGER_PATH.exists() else 0
    assert after_size == before_size
