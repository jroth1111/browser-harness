"""Persisted GraphQL operation-hash discovery for Airbnb web bundles."""

from __future__ import annotations

import json
import os
import re
from collections import deque
from datetime import date
from urllib.parse import urljoin


HASH_RE = re.compile(r"\b[0-9a-f]{64}\b")
STATIC_JS_RE = re.compile(
    r"(?:https://a0\.muscache\.com)?/airbnb/static/packages/web/[^\"'\\\s]+?\.js"
)


def validate_hash(value, name="operation hash"):
    value = str(value or "").strip()
    if not HASH_RE.fullmatch(value):
        raise ValueError(f"Invalid {name}: expected 64 lowercase hex characters")
    return value


def operation_hashes_from_text(text, operation_names):
    """Extract persisted-query hashes near operation names in JS/HTML text.

    Airbnb bundles have changed shape over time. Public tools commonly look for
    `operationId`; current bundles may also expose API paths or `sha256Hash`.
    Keep the parser intentionally structural: require the operation name and a
    64-hex hash in the same local window, or a direct `/api/v3/<operation>/<hash>`
    path. This avoids adopting unrelated package hashes.
    """
    text = text or ""
    found = {}
    for operation in operation_names:
        endpoint_re = re.compile(rf"/api/v3/{re.escape(operation)}/([0-9a-f]{{64}})")
        endpoint_match = endpoint_re.search(text)
        if endpoint_match:
            found[operation] = endpoint_match.group(1)
            continue

        forward_re = re.compile(
            rf"{re.escape(operation)}(?:(?!operationName).){{0,900}}?"
            rf"(?:operationId|sha256Hash)['\"]?\s*:\s*['\"]([0-9a-f]{{64}})",
            re.DOTALL,
        )
        forward_match = forward_re.search(text)
        if forward_match:
            found[operation] = forward_match.group(1)
            continue

        best = None
        for match in re.finditer(re.escape(operation), text):
            window = text[max(0, match.start() - 900) : match.end() + 900]
            for hash_match in HASH_RE.finditer(window):
                hash_value = hash_match.group(0)
                keyword_bonus = 0
                prefix = window[max(0, hash_match.start() - 80) : hash_match.start()]
                if any(keyword in prefix for keyword in ("operationId", "sha256Hash", "persistedQuery")):
                    keyword_bonus = 200
                distance = abs((hash_match.start() + hash_match.end()) // 2 - (match.start() - max(0, match.start() - 900)))
                score = keyword_bonus - distance
                if best is None or score > best[0]:
                    best = (score, hash_value)
        if best is not None:
            found[operation] = best[1]
    return found


def static_js_urls_from_text(text, base_url="https://a0.muscache.com"):
    urls = []
    seen = set()
    for match in STATIC_JS_RE.finditer(text or ""):
        url = match.group(0)
        if url.startswith("/"):
            url = urljoin(base_url, url)
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def discover_operation_hashes(fetch_text, operation_names, seed_texts=(), seed_urls=(), max_fetches=80):
    """Discover operation hashes by walking Airbnb static JS references.

    `fetch_text(url)` is injected so collectors can use browser-session headers
    while unit tests can use deterministic fixtures.
    """
    found = {}
    sources = {}
    queue = deque(seed_urls or [])
    queued = set(queue)
    visited = set()

    for index, text in enumerate(seed_texts or []):
        for operation, hash_value in operation_hashes_from_text(text, operation_names).items():
            found.setdefault(operation, hash_value)
            sources.setdefault(operation, f"seed_text:{index}")
        for url in static_js_urls_from_text(text):
            if url not in queued:
                queued.add(url)
                queue.append(url)

    fetches = 0
    while queue and fetches < max_fetches and set(found) != set(operation_names):
        url = queue.popleft()
        if url in visited:
            continue
        visited.add(url)
        fetches += 1
        text = fetch_text(url)
        for operation, hash_value in operation_hashes_from_text(text, operation_names).items():
            found.setdefault(operation, hash_value)
            sources.setdefault(operation, url)
        for next_url in static_js_urls_from_text(text):
            if next_url not in queued and next_url not in visited:
                queued.add(next_url)
                queue.append(next_url)

    return {
        "hashes": found,
        "sources": sources,
        "visited_count": len(visited),
        "remaining_queue_count": len(queue),
    }


def resolve_operation_hashes(defaults, discovered=None, env=None, prefix="AIRBNB_INSIGHTS"):
    """Merge defaults, discovered hashes, and explicit env overrides."""
    env = os.environ if env is None else env
    hashes = dict(defaults)
    sources = {operation: "default" for operation in hashes}

    discovered = discovered or {}
    for operation, hash_value in discovered.items():
        if operation in hashes and HASH_RE.fullmatch(str(hash_value or "")):
            hashes[operation] = str(hash_value)
            sources[operation] = "discovered"

    raw_json = env.get(f"{prefix}_OPERATION_HASHES_JSON")
    if raw_json:
        try:
            overrides = json.loads(raw_json)
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid {prefix}_OPERATION_HASHES_JSON") from error
        if not isinstance(overrides, dict):
            raise ValueError(f"Invalid {prefix}_OPERATION_HASHES_JSON: expected object")
        for operation, hash_value in overrides.items():
            if operation in hashes:
                hashes[operation] = validate_hash(hash_value, f"{operation} override")
                sources[operation] = "env_json"

    for operation in list(hashes):
        env_name = f"{prefix}_{operation.upper()}_HASH"
        if env.get(env_name):
            hashes[operation] = validate_hash(env[env_name], env_name)
            sources[operation] = "env"

    return hashes, sources


def operation_hashes_from_registry(entries, operation_names, *, surface_id=None, today=None):
    """Return active operation hashes from a persisted capability registry."""
    today = today or date.today()
    wanted = set(operation_names or [])
    selected = {}
    sources = {}
    for entry in entries or []:
        if surface_id and entry.get("surface_id") != surface_id:
            continue
        operation = entry.get("operation_name")
        hash_value = entry.get("operation_hash")
        if operation not in wanted or not HASH_RE.fullmatch(str(hash_value or "")):
            continue
        status = entry.get("status") or "active"
        expires_at = entry.get("expires_at")
        if status in {"disabled", "invalid"}:
            continue
        if expires_at and date.fromisoformat(str(expires_at)[:10]) < today:
            continue
        observed = str(entry.get("last_seen_at") or entry.get("first_seen_at") or "")
        if operation not in selected or observed >= selected[operation][0]:
            selected[operation] = (observed, str(hash_value))
            sources[operation] = "capability_registry"
    return {operation: value for operation, (_, value) in selected.items()}, sources
