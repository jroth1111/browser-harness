#!/usr/bin/env python3
"""Harvest cookies from local browsers into the archive's cookie vault.

Sweeps every detected browser profile (Chrome/Edge/Comet/Brave/Vivaldi/Cursor/
Safari) for cookies matching each registered provider's cookie domains, then
calls the provider's ``probe_login`` to verify the jar authenticates and
attach it to an account.

Usage:
    python -m scripts.harvest                 # all providers, all browsers
    python -m scripts.harvest --provider chatgpt
    python -m scripts.harvest --skip-browser safari
    python -m scripts.harvest --db /path/to/archive.sqlite3

Idempotent: re-running refreshes existing jars in place (keyed by
provider + account + browser + profile).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make the skill root importable when run via `python scripts/harvest.py`.
_SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))

from lib import archive_db, cookie_extract, schema
from lib.cookie_jar_io import flatten_cookies, jar_min_expiry
from lib.provider_base import ProviderContext
from lib.providers_registry import list_provider_ids, load_provider


def _filter_for_provider_domains(
    rich_jar: dict[str, dict[str, dict]],
    provider_domains: list[str],
) -> dict[str, dict[str, dict]]:
    """Keep only host_keys that match one of the provider's cookie_domains."""
    out: dict[str, dict[str, dict]] = {}
    if not isinstance(rich_jar, dict):
        return out
    for host, jar in rich_jar.items():
        if not isinstance(jar, dict):
            continue
        for d in provider_domains:
            if host == d or host.endswith(d) or d.endswith(host.lstrip(".")):
                out[host] = jar
                break
    return out


def harvest_provider(
    db,
    provider_id: str,
    *,
    skip_browsers: tuple[str, ...] = (),
    verbose: bool = True,
) -> list[dict]:
    """Run one provider's harvest pass. Returns a list of jar summaries."""
    cls = load_provider(provider_id)
    archive_db.ensure_provider(db, cls.provider_id, cls.display_name)

    if verbose:
        print(f"[{provider_id}] sweeping browsers for {cls.cookie_domains}")

    summaries: list[dict] = []
    seen_profiles = set()

    for profile in cookie_extract.list_browser_profiles():
        if profile.browser in skip_browsers:
            continue
        key = (profile.browser, profile.profile)
        if key in seen_profiles:
            continue
        seen_profiles.add(key)

        try:
            rich = cookie_extract.extract_cookies_from_profile(profile)
        except Exception as e:
            if verbose:
                print(f"  [{profile.browser}/{profile.profile}] read failed: {e}", file=sys.stderr)
            continue

        rich = _filter_for_provider_domains(rich, cls.cookie_domains)
        if not rich:
            continue

        flat = flatten_cookies(rich)
        ctx = ProviderContext(
            provider_id=cls.provider_id,
            cookies_by_domain=flat,
            db=db,
        )

        provider = cls()
        try:
            account = provider.probe_login(ctx)
        except Exception as e:
            account = None
            probe_err = str(e)[:200]
        else:
            probe_err = None

        if account is None:
            jar_id = archive_db.upsert_cookie_jar(
                db,
                provider_id=cls.provider_id,
                account_key=None,
                account_label=None,
                source_browser=profile.browser,
                source_profile=profile.profile,
                cookies=rich,
                auth_status="failed",
                expires_at=jar_min_expiry(rich),
            )
            summaries.append({
                "provider": provider_id,
                "browser": profile.browser,
                "profile": profile.profile,
                "jar_id": jar_id,
                "auth_status": "failed",
                "error": probe_err,
            })
            if verbose:
                print(f"  [{profile.browser}/{profile.profile}] auth failed")
            continue

        archive_db.ensure_account(
            db, cls.provider_id, account.account_key, account.account_label,
        )
        jar_id = archive_db.upsert_cookie_jar(
            db,
            provider_id=cls.provider_id,
            account_key=account.account_key,
            account_label=account.account_label,
            source_browser=profile.browser,
            source_profile=profile.profile,
            cookies=rich,
            auth_status="ok",
            expires_at=jar_min_expiry(rich),
        )
        summaries.append({
            "provider": provider_id,
            "browser": profile.browser,
            "profile": profile.profile,
            "account_label": account.account_label,
            "account_key": account.account_key,
            "jar_id": jar_id,
            "auth_status": "ok",
        })
        if verbose:
            print(f"  [{profile.browser}/{profile.profile}] -> {account.account_label}")

    return summaries


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Harvest cookies into the archive vault.")
    parser.add_argument("--db", default="archive.sqlite3", help="Archive SQLite path")
    parser.add_argument("--provider", action="append", default=[],
                        help="Restrict to one or more provider ids (default: all registered)")
    parser.add_argument("--skip-browser", action="append", default=[],
                        help="Skip a browser by short name (e.g. safari)")
    parser.add_argument("--json", action="store_true", help="Emit JSON summary on stdout")
    args = parser.parse_args(argv)

    schema.init_db(args.db).close()
    db = archive_db.connect(args.db)

    provider_ids = args.provider or list_provider_ids()
    skip = tuple(args.skip_browser)

    all_summaries: list[dict] = []
    for pid in provider_ids:
        all_summaries.extend(harvest_provider(db, pid, skip_browsers=skip,
                                              verbose=not args.json))

    if args.json:
        print(json.dumps(all_summaries, indent=2, default=str))
    else:
        ok = sum(1 for s in all_summaries if s["auth_status"] == "ok")
        failed = len(all_summaries) - ok
        print(f"\nharvest complete: {ok} authenticated, {failed} failed, "
              f"across {len(provider_ids)} provider(s)")

    return 0 if all_summaries else 1


if __name__ == "__main__":
    sys.exit(main())
