"""Capture network requests observed during browser navigation."""
import time

from . import helpers

_MAX_BODY_CHARS = 2 * 1024 * 1024  # 2MB


def _dict(value):
    return value if isinstance(value, dict) else {}


def _status_code(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else 0


def redact_capture_entry(entry):
    """Return a receipt-safe copy of a captured network entry."""
    return helpers.NetworkCapture._redact_entry(entry)


def redacted_capture_entries(entries):
    return [redact_capture_entry(entry) for entry in entries]


def capture_network_requests(url, timeout=15.0, capture_bodies=False):
    """Navigate to *url* and return captured network requests.

    Returns a list of dicts: {url, method, status, resource_type, mime_type,
    response_headers}. When capture_bodies is True, also includes {body} for
    responses up to 2MB.

    Uses a simple timed wait instead of smart_wait to avoid draining the
    daemon event buffer and disabling the Network domain prematurely.
    """
    capture = helpers.NetworkCapture(capture_bodies=capture_bodies, max_body_chars=_MAX_BODY_CHARS)
    capture.start()

    try:
        helpers.goto_url(url)
        time.sleep(timeout)
        capture.poll()
    finally:
        capture.stop()

    return [_legacy_entry(entry, capture_bodies) for entry in list(capture._entries)] + [
        _legacy_entry(entry, capture_bodies) for entry in capture._requests.values()
    ]


def _legacy_entry(entry, include_body):
    status = _status_code(entry.get("status"))
    out = {
        "url": entry.get("url", ""),
        "method": "" if entry.get("url", "") == "" and entry.get("method") == "GET" else entry.get("method", ""),
        "status": status,
        "resource_type": entry.get("resource_type", ""),
        "mime_type": entry.get("content_type", ""),
        "response_headers": _dict(entry.get("response_headers")),
    }
    if include_body and 200 <= status < 400 and "body" in entry:
        out["body"] = entry["body"]
    return out
