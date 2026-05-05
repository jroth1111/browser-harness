"""Network capture via SeleniumBase's CDP driver.

Wraps mycdp.network events for discovering JSON APIs within a UC Mode session."""
import asyncio, json, time
from pathlib import Path


class SBCapture:
    """Capture network traffic via SB's CDP connection."""

    def __init__(self):
        self._requests = {}   # request_id -> {url, method, headers}
        self._responses = {}  # request_id -> {url, status, content_type, body}
        self._json_endpoints = []

    async def start_capture(self, driver):
        """Enable Network domain and register event handlers via SB's CDP."""
        cdp = driver.cdp
        await cdp.page.enable()
        await cdp.network.enable()

        cdp.network.request_will_be_sent = self._on_request
        cdp.network.response_received = self._on_response

    def _on_request(self, event):
        self._requests[event.request_id] = {
            "url": event.request.url,
            "method": event.request.method,
            "headers": dict(event.request.headers) if event.request.headers else {},
        }

    def _on_response(self, event):
        self._responses[event.request_id] = {
            "url": event.response.url,
            "status": event.response.status,
            "content_type": event.response.mime_type if hasattr(event.response, 'mime_type') else "",
            "request_id": event.request_id,
        }

    async def get_json_responses(self, driver):
        """Fetch response bodies for all captured JSON responses."""
        cdp = driver.cdp
        results = []
        for req_id, resp in list(self._responses.items()):
            ct = resp.get("content_type", "")
            url = resp.get("url", "")
            if "json" in ct or "/api/" in url or "graphql" in url:
                try:
                    body_result = await cdp.network.get_response_body(
                        request_id=req_id
                    )
                    body = body_result.body if hasattr(body_result, 'body') else str(body_result)
                    req_info = self._requests.get(req_id, {})
                    results.append({
                        "url": url,
                        "method": req_info.get("method", "GET"),
                        "status": resp["status"],
                        "content_type": ct,
                        "request_headers": req_info.get("headers", {}),
                        "body_preview": body[:2000] if body else "",
                    })
                except Exception as e:
                    results.append({
                        "url": url,
                        "status": resp["status"],
                        "content_type": ct,
                        "error": str(e),
                    })
        self._json_endpoints = results
        return results

    def endpoints(self):
        """Return deduplicated URL list from captured requests."""
        seen = set()
        urls = []
        for req_id, req in self._requests.items():
            url = req["url"]
            if url not in seen:
                seen.add(url)
                urls.append(url)
        return urls

    def save(self, path):
        """Save captured endpoints and JSON responses to file."""
        Path(path).write_text(json.dumps({
            "json_endpoints": self._json_endpoints,
            "all_urls": self.endpoints(),
        }, indent=2, default=str))
