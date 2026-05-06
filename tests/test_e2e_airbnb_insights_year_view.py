import json
import os
import subprocess
from pathlib import Path

import pytest


RUN_ID = os.environ.get("AIRBNB_E2E_YEAR_RUN_ID", "e2e-airbnb-year-view-bounded")
SCRIPT = "domain-skills/airbnb/scripts/sync_insights_year_view.py"
INSIGHTS_DIR = Path("domain-skills/airbnb/.private-data/insights-collections")
SESSION_DIR = Path("domain-skills/airbnb/.session-store/capability")


def _run_year_view(run_id):
    env = os.environ.copy()
    env.setdefault("AIRBNB_INSIGHTS_LIMIT_LISTINGS", "1")
    env.setdefault("AIRBNB_INSIGHTS_LIMIT_ROUTES", "3")
    env.setdefault("AIRBNB_INSIGHTS_LIMIT_PERIODS", "2")
    command = [
        "python3",
        SCRIPT,
        "--run-id",
        run_id,
        "--skip-probe",
        "--skip-preflight",
    ]
    return subprocess.run(command, capture_output=True, text=True, env=env, check=True)


def test_e2e_year_view_bounded_idempotent():
    if os.environ.get("AIRBNB_E2E_YEAR_VIEW") != "1":
        pytest.skip("AIRBNB_E2E_YEAR_VIEW=1 not set (requires live Airbnb host session)")
    first = _run_year_view(RUN_ID)
    second = _run_year_view(RUN_ID)
    assert first.returncode == 0
    assert second.returncode == 0

    snapshot = INSIGHTS_DIR / f"{RUN_ID}.json"
    receipt = SESSION_DIR / f"{RUN_ID}-year-view-receipt.json"
    assert snapshot.exists()
    assert receipt.exists()

    data = json.loads(snapshot.read_text(encoding="utf-8"))
    assert data["summary_rows_count"] > 0
    assert data["daily_rows_count"] > 0

    conversion_html = INSIGHTS_DIR / f"{RUN_ID}-conversion-only-daily.html"
    assert conversion_html.exists()
    html = conversion_html.read_text(encoding="utf-8")
    assert 'id="payload-json"' in html

    ledger = INSIGHTS_DIR / ".ledger.jsonl"
    assert ledger.exists()
    assert ledger.stat().st_size > 0
