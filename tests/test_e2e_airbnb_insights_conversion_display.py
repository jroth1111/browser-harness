import json
import os
import re
import subprocess
from pathlib import Path

from browser_harness.data_display import render_dataset


BASE = Path("agent-workspace/domain-skills/airbnb/.private-data/insights-collections")
RUN_ID = "e2e-airbnb-insights-conversion-browser"


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_payload_rows(html_path: Path):
    html = html_path.read_text(encoding="utf-8")
    match = re.search(
        r'<script type="application/json" id="payload-json">(.*?)</script>',
        html,
        flags=re.S,
    )
    assert match is not None, "Expected payload-json script tag in rendered HTML"
    payload = json.loads(match.group(1).replace("<\\/", "</"))
    datasets = payload.get("datasets") or []
    assert datasets, "Expected at least one dataset in payload"
    return datasets[0]


def _browser_smoke(html_path: Path):
    script = f"""python3 run.py <<'PY'
from pathlib import Path
new_tab(Path({json.dumps(str(html_path))}).as_uri())
wait_for_load()
wait(1)
count = js(\"(() => {{ const el = document.querySelector('#payload-json'); if (!el) return -1; const p = JSON.parse(el.textContent); const ds = (p.datasets || [])[0] || {{}}; return (ds.data || []).length; }})()\")
print(count)
PY"""
    output = subprocess.check_output(script, shell=True, text=True)
    rows = int([line.strip() for line in output.splitlines() if line.strip().isdigit()][-1])
    return rows


def test_insights_families_e2e_collector_and_display_parity():
    source_json = BASE / f"{RUN_ID}.json"
    receipt_json = Path(f"agent-workspace/domain-skills/airbnb/.session-store/capability/{RUN_ID}-receipt.json")
    for path in [source_json, receipt_json]:
        assert path.exists(), f"Missing artifact: {path}"

    source = _load_json(source_json)
    receipt = _load_json(receipt_json)

    assert source["run_id"] == RUN_ID
    assert source["failures_count"] == 0
    assert receipt["all_api_requests_ok"] is True
    assert receipt["all_parsers_found_rows"] is True

    extract_module_path = Path("agent-workspace/domain-skills/airbnb/scripts/extract_route_family.py")
    namespace = {}
    exec(extract_module_path.read_text(encoding="utf-8"), namespace)
    extract_family = namespace["extract_family"]

    for family in ("conversion", "occupancy", "quality"):
        extracted = extract_family(source_json, family)
        family_json = _load_json(Path(extracted["json_path"]))
        assert family_json["route_family"] == family
        assert family_json["summary_rows_count"] > 0
        assert family_json["daily_rows_count"] > 0

        summary_html = Path(render_dataset(extracted["summary_csv_path"]))
        daily_html = Path(render_dataset(extracted["daily_csv_path"]))
        summary_payload = _extract_payload_rows(summary_html)
        daily_payload = _extract_payload_rows(daily_html)

        summary_rows = summary_payload.get("data", [])
        daily_rows = daily_payload.get("data", [])
        assert len(summary_rows) == family_json["summary_rows_count"]
        assert len(daily_rows) == family_json["daily_rows_count"]
        assert {row.get("route_family") for row in summary_rows} == {family}
        assert {row.get("route_family") for row in daily_rows} == {family}
        assert "series_granularity" in {field.get("name") for field in daily_payload.get("schema", {}).get("fields", [])}
        assert set(row.get("series_granularity") for row in daily_rows if row.get("series_granularity"))

        if os.environ.get("AIRBNB_E2E_BROWSER_SMOKE") == "1":
            assert _browser_smoke(daily_html) == len(daily_rows)

    conversion_rows = [row for row in source.get("summary_rows", []) if row.get("route_family") == "conversion"]
    assert any(
        row.get("route_subroute") == "p3_impressions" and (row.get("value") or 0) > 0
        for row in conversion_rows
    )
    assert any(
        row.get("route_subroute") in {"booking_window", "return_guest"} and row.get("value_string") == "-"
        for row in conversion_rows
    )
