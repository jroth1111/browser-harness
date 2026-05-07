"""Cookie shape conversions between cookie_extract and provider consumers.

cookie_extract emits the rich shape:
    {host_key: {cookie_name: {value, path, expires, secure, http_only, same_site}}}

Providers want the flat shape:
    {host_key: {cookie_name: value}}

The vault stores the rich shape so we can later filter by expiry, drop
non-secure cookies, or compute jar-expiry timestamps. Flattening happens at
read-time.
"""
from __future__ import annotations

import json
import time
from typing import Any


def flatten_cookies(rich: dict[str, dict[str, Any]]) -> dict[str, dict[str, str]]:
    """Convert rich → flat for provider consumption.

    Tolerates jars stored in either shape: existing string values pass through.
    """
    flat: dict[str, dict[str, str]] = {}
    if not isinstance(rich, dict):
        return flat
    for host, jar in rich.items():
        if not isinstance(jar, dict):
            continue
        flat[host] = {}
        for name, entry in jar.items():
            if isinstance(entry, dict):
                v = entry.get("value")
                if isinstance(v, str):
                    flat[host][name] = v
            elif isinstance(entry, str):
                flat[host][name] = entry
    return flat


def jar_min_expiry(rich: dict[str, dict[str, Any]]) -> str | None:
    """Earliest non-zero cookie expiry across the jar, as ISO8601 UTC.

    Used to populate cookie_jars.expires_at so we can surface
    soon-to-expire jars before sync calls fail. Cookies with expires=0
    (session cookies) are ignored — they expire when the browser closes."""
    earliest: float | None = None
    if not isinstance(rich, dict):
        return None
    for jar in rich.values():
        if not isinstance(jar, dict):
            continue
        for entry in jar.values():
            if not isinstance(entry, dict):
                continue
            exp = entry.get("expires")
            if isinstance(exp, bool):
                continue
            if not exp or not isinstance(exp, (int, float)):
                continue
            if exp <= 0:
                continue
            if earliest is None or exp < earliest:
                earliest = exp
    if earliest is None:
        return None
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(earliest))


def cookies_from_jar_row(row: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Read cookie_jars.cookies_json (rich) and return the flat provider shape."""
    raw = row.get("cookies_json")
    if not raw:
        return {}
    try:
        rich = json.loads(raw)
    except Exception:
        return {}
    return flatten_cookies(rich)
