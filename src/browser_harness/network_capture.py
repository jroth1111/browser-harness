"""Capture network requests observed during browser navigation."""
import base64
import time

import helpers

_MAX_BODY_CHARS = 2 * 1024 * 1024  # 2MB


def capture_network_requests(url, timeout=15.0, capture_bodies=False):
    """Navigate to *url* and return captured network requests.

    Returns a list of dicts: {url, method, status, resource_type, mime_type,
    response_headers}. When capture_bodies is True, also includes {body} for
    responses up to 2MB.

    Uses a simple timed wait instead of smart_wait to avoid draining the
    daemon event buffer and disabling the Network domain prematurely.
    """
    helpers.cdp("Network.enable")
    helpers.drain_events()

    helpers.goto_url(url)
    time.sleep(timeout)

    events = helpers.drain_events()

    try:
        helpers.cdp("Network.disable")
    except Exception:
        pass

    # Index request → {requestId, url, method, resourceType}
    requests = {}
    # Index response → {requestId, status, mimeType, headers}
    responses = {}

    for ev in events:
        method = ev.get("method", "")
        params = ev.get("params") or {}
        rid = params.get("requestId")

        if method == "Network.requestWillBeSent" and rid:
            req = params.get("request", {})
            requests[rid] = {
                "requestId": rid,
                "url": req.get("url", ""),
                "method": req.get("method", ""),
                "resource_type": params.get("type", ""),
            }
        elif method == "Network.responseReceived" and rid:
            resp = params.get("response", {})
            responses[rid] = {
                "requestId": rid,
                "status": resp.get("status", 0),
                "mime_type": resp.get("mimeType", ""),
                "response_headers": resp.get("headers", {}),
            }

    out = []
    for rid, req in requests.items():
        entry = {
            "url": req["url"],
            "method": req["method"],
            "status": 0,
            "resource_type": req["resource_type"],
            "mime_type": "",
            "response_headers": {},
        }
        if rid in responses:
            resp = responses[rid]
            entry["status"] = resp["status"]
            entry["mime_type"] = resp["mime_type"]
            entry["response_headers"] = resp["response_headers"]

            if capture_bodies and resp["status"] >= 200 and resp["status"] < 400:
                try:
                    body_result = helpers.cdp(
                        "Network.getResponseBody", requestId=rid
                    )
                    body = body_result.get("body", "")
                    if body_result.get("base64Encoded"):
                        body = base64.b64decode(body).decode("utf-8", errors="replace")
                    entry["body"] = body[:_MAX_BODY_CHARS]
                except Exception:
                    pass

        out.append(entry)

    return out
