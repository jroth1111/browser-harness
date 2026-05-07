#!/usr/bin/env python3
"""Camoufox-driven endpoint reconnaissance for an authenticated provider URL.

Loads the harvested cookie jar for ``--provider``, launches Camoufox
(Firefox-derivative with engine-level fingerprint spoofing), injects the
cookies, navigates to ``--url``, and prints a network capture report covering
every API-shaped request the page made.

Output is grouped by host and clustered by URL path skeleton so you can spot
list/detail/search endpoint families at a glance.

Usage:
    python -m scripts.recon --provider perplexity --url https://www.perplexity.ai/library
    python -m scripts.recon --provider perplexity --url https://www.perplexity.ai/library --idle 8
    python -m scripts.recon --provider perplexity --account me@example.com --url ...

This script must run under the browser-harness uv tool's Python so camoufox
is on sys.path. The ``./recon`` shim handles that automatically.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))

_API_HINT_RE = re.compile(r"/(rest|api|pplx-api|graphql|batchexecute|_next/data|trpc)/")


def _path_skeleton(path: str) -> str:
    """Replace UUIDs / long ids in path with placeholders for clustering."""
    out = []
    for seg in path.split("/"):
        if not seg:
            out.append(seg)
            continue
        if re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", seg, re.I):
            out.append("{uuid}")
        elif re.fullmatch(r"\d{6,}", seg):
            out.append("{n}")
        elif re.fullmatch(r"[A-Za-z0-9_-]{20,}", seg):
            out.append("{id}")
        else:
            out.append(seg)
    return "/".join(out)


def _cookies_to_playwright(rich: dict[str, dict[str, dict]]) -> list[dict]:
    """Convert the rich cookie shape stored in the vault to Playwright's
    ``Cookie`` dicts. Drops cookies missing required fields."""
    out: list[dict] = []
    if not isinstance(rich, dict):
        return out
    for host, jar in rich.items():
        if not isinstance(jar, dict):
            continue
        domain = host  # cookie_extract uses ".perplexity.ai"-style host_keys
        for name, entry in jar.items():
            if not isinstance(entry, dict):
                continue
            value = entry.get("value")
            if value is None:
                continue
            ck: dict[str, Any] = {
                "name": name,
                "value": value,
                "domain": domain,
                "path": entry.get("path") or "/",
                "secure": bool(entry.get("secure")),
                "httpOnly": bool(entry.get("http_only")),
            }
            ss = (entry.get("same_site") or "").capitalize()
            if ss in ("Strict", "Lax", "None"):
                ck["sameSite"] = ss
            exp = entry.get("expires")
            if isinstance(exp, (int, float)) and exp > 0:
                ck["expires"] = int(exp)
            out.append(ck)
    return out


def _load_jar(db_path: str, provider_id: str, account: str | None) -> dict:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    if account:
        row = conn.execute(
            "SELECT * FROM cookie_jars WHERE provider_id=? AND account_label=? "
            "AND last_auth_status='ok' ORDER BY harvested_at DESC LIMIT 1",
            (provider_id, account),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM cookie_jars WHERE provider_id=? AND last_auth_status='ok' "
            "ORDER BY harvested_at DESC LIMIT 1",
            (provider_id,),
        ).fetchone()
    conn.close()
    if row is None:
        sys.exit(f"no authenticated cookie jar for {provider_id}"
                 + (f" / {account}" if account else ""))
    return dict(row)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--provider", required=True)
    p.add_argument("--url", required=True, help="URL to navigate to")
    p.add_argument("--account", default=None, help="filter to a specific account_label")
    p.add_argument("--db", default=str(_SKILL_ROOT / ".private-data" / "archive" / "archive.sqlite3"))
    p.add_argument("--idle", type=float, default=6.0, help="seconds to wait after load for XHR/fetch traffic")
    p.add_argument("--filter", default=None, help="regex to filter URLs in report (case-insensitive)")
    p.add_argument("--show-bodies", action="store_true",
                   help="include first 400 bytes of JSON response bodies")
    p.add_argument("--out", default=None, help="optional path to write full capture JSON")
    p.add_argument("--no-headless", action="store_true", help="show the browser window")
    args = p.parse_args(argv)

    from camoufox.sync_api import Camoufox  # type: ignore

    jar_row = _load_jar(args.db, args.provider, args.account)
    rich_cookies = json.loads(jar_row["cookies_json"])
    cookies = _cookies_to_playwright(rich_cookies)

    print(f"[recon] provider={args.provider} jar={jar_row['source_browser']}/"
          f"{jar_row['source_profile']} account={jar_row.get('account_label') or '(none)'} "
          f"cookies={len(cookies)}")
    print(f"[recon] navigating to {args.url}")

    captured: list[dict] = []
    custom_filter = re.compile(args.filter, re.I) if args.filter else None

    with Camoufox(headless=not args.no_headless, humanize=False) as browser:
        ctx = browser.new_context()
        ctx.add_cookies(cookies)
        page = ctx.new_page()

        def on_response(resp):
            try:
                req = resp.request
                url = resp.url
                ct = (resp.headers.get("content-type") or "").split(";")[0].strip()
                entry: dict[str, Any] = {
                    "method": req.method,
                    "url": url,
                    "status": resp.status,
                    "content_type": ct,
                    "resource_type": req.resource_type,
                }
                if args.show_bodies and ct.startswith("application/json"):
                    try:
                        body = resp.body()
                        entry["body_preview"] = body[:400].decode("utf-8", errors="replace")
                        entry["body_length"] = len(body)
                    except Exception as e:
                        entry["body_error"] = str(e)[:80]
                captured.append(entry)
            except Exception:
                pass

        page.on("response", on_response)
        try:
            page.goto(args.url, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print(f"[recon] goto warning: {e}")
        time.sleep(args.idle)
        title = page.title() if page else ""
        print(f"[recon] page title: {title!r}")

        ctx.close()

    if args.out:
        Path(args.out).write_text(json.dumps(captured, indent=2))
        print(f"[recon] wrote {len(captured)} entries to {args.out}")

    api_only = [e for e in captured
                if (urlparse(e["url"]).path and _API_HINT_RE.search(urlparse(e["url"]).path))
                   or e["content_type"].startswith("application/json")]
    if custom_filter:
        api_only = [e for e in api_only if custom_filter.search(e["url"])]

    print("\n=== API-shaped requests ===")
    by_host_path: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for e in api_only:
        u = urlparse(e["url"])
        skel = _path_skeleton(u.path)
        by_host_path[(u.netloc, e["method"], skel)].append(e)

    for (host, method, skel), entries in sorted(by_host_path.items()):
        statuses = sorted({str(x["status"]) for x in entries})
        cts = sorted({x["content_type"] for x in entries if x["content_type"]})
        print(f"  {method:6s} {host}{skel}  hits={len(entries)} status={','.join(statuses)} ct={','.join(cts)}")
        sample = entries[0]["url"]
        print(f"      sample: {sample}")
        if args.show_bodies:
            for e in entries[:1]:
                if "body_preview" in e:
                    preview = e["body_preview"].replace("\n", "\\n")[:200]
                    print(f"      body[{e.get('body_length','?')}]: {preview}")

    print(f"\n[recon] total responses captured: {len(captured)}; API-shaped: {len(api_only)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
