"""Standard year-view sync for Airbnb Insights.

Role: runner (canonical Insights workflow). Use this script instead of calling
`collect_insights.py` directly for the standard year-view dashboard refresh.

Reads:
    - Latest complete `airbnb-live-listings-*.json` (consumed by
      `collect_insights.py`).
    - `domain-skills/airbnb/insights-granularity-map.md` (refreshed via
      `probe_chart_granularity.py` when stale).
    - Cross-run ledger at `.private-data/insights-collections/.ledger.jsonl`.

Produces:
    - `airbnb-insights-year-view-<ts>.json` snapshot under
      `.private-data/insights-collections/`.
    - Per-family extracts: `<run_id>-conversion-only` /
      `<run_id>-occupancy-only` / `<run_id>-quality-only`
      JSON + summary CSV + daily CSV + rendered HTML.
    - `<run_id>-year-view-receipt.json` under `.session-store/capability/`.

Pipeline: preflight cookies → optional granularity probe → `collect_insights.py`
in patient mode → validate snapshot → per-family extraction → render via
`data_display.render_dataset` → optional browser-open verification → write
receipt.

Requires (CLI flags):
    --run-id           Override the auto-generated run id.
    --open             Open rendered HTML in browser-harness; verify payload sizes.
    --skip-preflight   Skip the cookie preflight (use only for pure-test runs).
    --skip-probe       Skip the granularity probe even if the map is stale.
    --allow-partial    Render partial collector output (failures or limited scope).

Refuses to run if:
    - Authenticated Airbnb host cookies are missing (preflight failure) unless
      `--skip-preflight` is set.
    - The collector reported failures or scoped fewer listings than expected,
      unless `--allow-partial` is set.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shlex
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
_pkg = ROOT / "src" / "browser_harness"
if str(_pkg) not in sys.path:
    sys.path.insert(0, str(_pkg))

from data_display import render_dataset

AIRBNB_DIR = ROOT / "domain-skills" / "airbnb"
SCRIPTS_DIR = AIRBNB_DIR / "scripts"
OUTPUT_PATH = AIRBNB_DIR / ".private-data" / "insights-collections"
SESSION_PATH = AIRBNB_DIR / ".session-store" / "capability"
GRANULARITY_MAP = AIRBNB_DIR / "insights-granularity-map.md"
HOST_AUTH_COOKIE_NAMES = {
    "_aaj",
    "_aat",
    "_airbed_session_id",
    "_iidt",
    "_pt",
    "_vid_t",
    "hli",
    "li",
    "rclu",
}


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


extract_module = load_module(SCRIPTS_DIR / "extract_route_family.py", "airbnb_extract_route_family")
integrity_module = load_module(SCRIPTS_DIR / "run_integrity.py", "airbnb_run_integrity")


def run_shell(command, env=None):
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=merged_env,
        capture_output=True,
        text=True,
        shell=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"Command failed: {command}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    return completed.stdout


def preflight_cookies():
    snippet = """python3 run.py <<'PY'
cookies = browser_cookies(["https://www.airbnb.com.au/"]) or []
names = sorted({cookie.get("name") for cookie in cookies if cookie.get("name")})
print(json.dumps({"cookie_names": names}))
PY"""
    out = run_shell(snippet)
    line = [row for row in out.splitlines() if row.strip().startswith("{")][-1]
    payload = json.loads(line)
    names = set(payload.get("cookie_names") or [])
    auth_names = sorted(names & HOST_AUTH_COOKIE_NAMES)
    if not auth_names:
        raise RuntimeError(
            "Airbnb host session not detected (authenticated Airbnb cookie missing). "
            "Open Airbnb in Chrome and ensure host login is active."
        )
    payload["auth_cookie_names_present"] = auth_names
    return payload


def run_probe():
    command = "python3 run.py < domain-skills/airbnb/scripts/probe_chart_granularity.py"
    return run_shell(command)


def maybe_run_probe(skip_probe):
    if skip_probe:
        return {"skipped": True, "reason": "skip_probe"}
    if not map_is_stale(GRANULARITY_MAP):
        return {"skipped": True, "reason": "granularity_map_fresh", "path": str(GRANULARITY_MAP)}
    try:
        stdout = run_probe()
    except RuntimeError as error:
        return {
            "skipped": False,
            "ok": False,
            "error": str(error)[:2000],
        }
    return {
        "skipped": False,
        "ok": True,
        "stdout_tail": stdout.splitlines()[-10:],
        "path": str(GRANULARITY_MAP),
    }


def map_is_stale(path, max_age_days=30):
    if not path.exists():
        return True
    modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    return (datetime.now(timezone.utc) - modified) > timedelta(days=max_age_days)


def run_collect(run_id):
    env = {
        "AIRBNB_INSIGHTS_RUN_ID": run_id,
        "AIRBNB_INSIGHTS_PATIENT_MODE": "1",
    }
    command = "python3 run.py < domain-skills/airbnb/scripts/collect_insights.py"
    return run_shell(command, env=env)


def validate_collect_output(run_id, allow_partial=False, allow_quarantined=False):
    snapshot_json = OUTPUT_PATH / f"{run_id}.json"
    receipt_json = SESSION_PATH / f"{run_id}-receipt.json"
    if not snapshot_json.exists():
        raise RuntimeError(f"Collector did not write expected snapshot: {snapshot_json}")
    snapshot = json.loads(snapshot_json.read_text(encoding="utf-8"))
    receipt = {}
    if receipt_json.exists():
        receipt = json.loads(receipt_json.read_text(encoding="utf-8"))
    try:
        integrity_module.assert_usable_collection(
            snapshot,
            expected_source_family="host_private" if snapshot.get("source_family") else None,
            allow_partial=allow_partial,
            allow_quarantined=allow_quarantined,
        )
    except ValueError as error:
        raise RuntimeError(str(error)) from error

    failures_count = int(snapshot.get("failures_count") or 0)
    summary_rows_count = int(snapshot.get("summary_rows_count") or 0)
    daily_rows_count = int(snapshot.get("daily_rows_count") or 0)
    chart_request_count = int(snapshot.get("chart_request_count") or 0)
    sentinel_rows_count = int(snapshot.get("sentinel_rows_count") or 0)
    listing_count = int(snapshot.get("listing_count") or 0)
    total_active_listings = int(snapshot.get("total_active_listings") or 0)
    total_scope_listings = int(snapshot.get("total_scope_listings") or total_active_listings or 0)
    listing_status_scope = snapshot.get("listing_status_scope") or "active"
    # listing_scope_complete is a newer field. On legacy snapshots without
    # total_active_listings (pre-sentinel collector), skip the scope check
    # rather than fail. The collector run that wrote the snapshot is
    # authoritative for whether listings were dropped.
    if "listing_scope_complete" in snapshot:
        listing_scope_complete = bool(snapshot.get("listing_scope_complete"))
    else:
        listing_scope_complete = True  # legacy snapshots assumed complete
    if total_scope_listings and not listing_scope_complete and not allow_partial:
        raise RuntimeError(
            f"Collector scoped only {listing_count} of {total_scope_listings} listings "
            f"for scope {listing_status_scope} in run {run_id}. Unset AIRBNB_INSIGHTS_LIMIT_LISTINGS "
            "or pass --allow-partial to render a subset explicitly."
        )
    if failures_count and not allow_partial:
        raise RuntimeError(
            f"Collector reported {failures_count} failures for run {run_id}; "
            "rerun after cooldown or pass --allow-partial to render partial data explicitly."
        )
    # Summary rows must always be present (summary requests are always made).
    # Daily rows can legitimately be zero on a steady-state run where the ledger
    # is fully covered and the planner emits zero chart requests.
    if summary_rows_count <= 0:
        raise RuntimeError(
            f"Collector output is missing summary rows for run {run_id}: "
            f"summary_rows_count={summary_rows_count}"
        )
    if daily_rows_count <= 0 and chart_request_count > 0 and sentinel_rows_count <= 0:
        raise RuntimeError(
            f"Collector ran {chart_request_count} chart requests but produced 0 daily or sentinel rows for run {run_id}"
        )
    return {
        "snapshot_path": str(snapshot_json),
        "receipt_path": str(receipt_json) if receipt_json.exists() else None,
        "failures_count": failures_count,
        "listing_count": listing_count,
        "total_active_listings": total_active_listings,
        "total_scope_listings": total_scope_listings,
        "listing_status_scope": listing_status_scope,
        "listing_scope_complete": listing_scope_complete,
        "summary_rows_count": summary_rows_count,
        "daily_rows_count": daily_rows_count,
        "sentinel_rows_count": sentinel_rows_count,
        "summary_request_count": snapshot.get("summary_request_count"),
        "chart_request_count": snapshot.get("chart_request_count"),
        "receipt_all_api_requests_ok": receipt.get("all_api_requests_ok"),
        "receipt_all_parsers_found_rows": receipt.get("all_parsers_found_rows"),
        "collection_status": snapshot.get("collection_status") or "complete",
        "allow_partial": allow_partial,
        "allow_quarantined": allow_quarantined,
    }


def render_family_outputs(run_id, families, *, allow_partial=False, allow_quarantined=False):
    snapshot_json = OUTPUT_PATH / f"{run_id}.json"
    rendered = []
    for family in families:
        extracted = extract_module.extract_family(
            snapshot_json,
            family,
            allow_partial=allow_partial,
            allow_quarantined=allow_quarantined,
        )
        summary_html = render_dataset(extracted["summary_csv_path"])
        daily_html = render_dataset(extracted["daily_csv_path"])
        rendered.append(
            {
                "family": family,
                **extracted,
                "summary_html_path": summary_html,
                "daily_html_path": daily_html,
            }
        )
    return rendered


def browser_open_verify(rendered_outputs):
    quoted = shlex.quote(json.dumps(rendered_outputs))
    snippet = f"""python3 run.py <<'PY'
import json
from pathlib import Path
payload = json.loads({quoted})
results = []
for row in payload:
    for key in ("summary_html_path", "daily_html_path"):
        url = Path(row[key]).as_uri()
        new_tab(url)
        wait_for_load()
        wait(1)
        count = js("(() => {{ const el = document.querySelector('#payload-json'); if (!el) return -1; const p = JSON.parse(el.textContent); const ds = (p.datasets || [])[0] || {{}}; return (ds.data || []).length; }})()")
        shot = capture_screenshot()
        results.append({{"family": row["family"], "kind": key, "url": url, "payload_rows": count, "screenshot": shot}})
print(json.dumps(results))
PY"""
    return run_shell(snippet)


def write_receipt(run_id, preflight_info, probe_info, collect_stdout, collect_validation, rendered_outputs, browser_stdout):
    SESSION_PATH.mkdir(parents=True, exist_ok=True)
    path = SESSION_PATH / f"{run_id}-year-view-receipt.json"
    receipt = integrity_module.stamp_collection_contract({
        "run_id": run_id,
        "observed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "preflight": preflight_info,
        "probe": probe_info,
        "collector": collect_validation,
        "rendered_outputs": rendered_outputs,
        "collect_stdout_tail": collect_stdout.splitlines()[-30:],
        "browser_stdout_tail": browser_stdout.splitlines()[-20:] if browser_stdout else [],
    },
        source_family="host_private",
        surface_class="host_private",
        auth_context="year_view_runner",
        collection_status=collect_validation.get("collection_status") or "complete",
        last_good_guard_record={"checked": True, "status": "delegated_to_collector"},
        warehouse_exports=[],
    )
    integrity_module.write_receipt_json(path, receipt)
    return path


def parse_args():
    parser = argparse.ArgumentParser(description="Sync Airbnb Insights year view")
    parser.add_argument("--run-id", default="airbnb-insights-year-view-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    parser.add_argument("--open", action="store_true", help="Open rendered outputs in browser-harness and verify payload sizes")
    parser.add_argument("--skip-preflight", action="store_true")
    parser.add_argument("--skip-probe", action="store_true")
    parser.add_argument("--allow-partial", action="store_true", help="Render partial collector output even when collector recorded failures")
    parser.add_argument("--allow-quarantined", action="store_true", help="Render quarantined collector output explicitly")
    return parser.parse_args()


def main():
    args = parse_args()
    preflight_info = {"skipped": True}
    if not args.skip_preflight:
        preflight_info = preflight_cookies()
    probe_info = maybe_run_probe(args.skip_probe)
    collect_stdout = run_collect(args.run_id)
    collect_validation = validate_collect_output(
        args.run_id,
        allow_partial=args.allow_partial,
        allow_quarantined=args.allow_quarantined,
    )
    rendered_outputs = render_family_outputs(
        args.run_id,
        families=["conversion", "occupancy", "quality"],
        allow_partial=args.allow_partial,
        allow_quarantined=args.allow_quarantined,
    )
    browser_stdout = ""
    if args.open:
        browser_stdout = browser_open_verify(rendered_outputs)
    receipt_path = write_receipt(
        args.run_id,
        preflight_info,
        probe_info,
        collect_stdout,
        collect_validation,
        rendered_outputs,
        browser_stdout,
    )
    print(
        json.dumps(
            {
                "run_id": args.run_id,
                "receipt_path": str(receipt_path),
                "rendered_outputs": rendered_outputs,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
