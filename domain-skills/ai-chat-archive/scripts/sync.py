#!/usr/bin/env python3
"""Run a sync pass against archived cookie jars.

Usage:
    python -m scripts.sync                       # all providers, all jars
    python -m scripts.sync --provider chatgpt
    python -m scripts.sync --provider chatgpt --account me@example.com
    python -m scripts.sync --fresh               # re-capture every thread
    python -m scripts.sync --limit 10            # cap per-account capture count

Reads ``cookie_jars`` (auth_status='ok'), drives each through the provider's
sync runner, and writes results into the archive. Updates jar status as a
side effect so a later harvest pass knows which jars went stale.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))

from lib import archive_db, schema, sync_runner
from lib.cookie_jar_io import cookies_from_jar_row
from lib.providers_registry import list_provider_ids, load_provider


def sync_one_jar(
    db,
    jar: dict,
    *,
    fresh: bool,
    limit: int | None,
    options: dict | None,
) -> sync_runner.SyncResult:
    cls = load_provider(jar["provider_id"])
    cookies = cookies_from_jar_row(jar)
    result = sync_runner.run_sync(
        cls(),
        db=db,
        cookies_by_domain=cookies,
        since=None,
        limit=limit,
        options=options or {},
        fresh=fresh,
    )
    archive_db.mark_jar_status(
        db, jar["jar_id"],
        status=result.auth_status,
        used=True,
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync threads from cookie jars into the archive.")
    parser.add_argument("--db", default="archive.sqlite3", help="Archive SQLite path")
    parser.add_argument("--provider", action="append", default=[],
                        help="Restrict to one or more provider ids")
    parser.add_argument("--account", help="Match jars by account_label (substring)")
    parser.add_argument("--fresh", action="store_true",
                        help="Re-capture every thread, ignoring cached content_hash")
    parser.add_argument("--limit", type=int, help="Cap captures per jar")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    schema.init_db(args.db).close()
    db = archive_db.connect(args.db)

    provider_ids = args.provider or list_provider_ids()
    summaries = []
    for pid in provider_ids:
        jars = archive_db.list_cookie_jars(db, provider_id=pid, only_active=True)
        if args.account:
            jars = [j for j in jars if args.account.lower() in (j.get("account_label") or "").lower()]
        if not jars:
            if not args.json:
                print(f"[{pid}] no active jars; harvest first?")
            continue
        for jar in jars:
            label = jar.get("account_label") or "?"
            if not args.json:
                print(f"[{pid}] sync {label} via {jar['source_browser']}/{jar['source_profile']}")
            try:
                result = sync_one_jar(
                    db, jar,
                    fresh=args.fresh,
                    limit=args.limit,
                    options={},
                )
            except Exception as e:
                if not args.json:
                    print(f"  failed: {e}", file=sys.stderr)
                summaries.append({
                    "provider_id": pid,
                    "jar_id": jar["jar_id"],
                    "account_label": label,
                    "error": str(e)[:200],
                })
                continue
            summaries.append(result.as_dict())
            if not args.json:
                print(f"  listed={result.listed} captured={result.captured} "
                      f"skipped={result.skipped_unchanged} failed={result.failed}")

    if args.json:
        print(json.dumps(summaries, indent=2, default=str))
    else:
        captured = sum(s.get("captured", 0) for s in summaries)
        print(f"\nsync complete: {captured} captures across {len(summaries)} jar(s)")

    return 0 if summaries else 1


if __name__ == "__main__":
    sys.exit(main())
