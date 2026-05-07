"""Small Lightpanda control/translation helpers for browser-harness.

Lightpanda exposes a browser-level CDP websocket. Page operations need an
attached target session, while browser/storage operations should stay on the
browser connection. This module provides that routing in the same `send_raw`
shape used by login_session.py.
"""
import json
import os
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

from websockets.sync.client import connect


_BROWSER_SCOPED_PREFIXES = ("Browser.", "Target.", "Storage.")
_PAGE_EVIDENCE_JS = """(() => {
  const text = document.body ? document.body.innerText : "";
  const links = Array.from(document.querySelectorAll("a[href]"))
    .map(a => a.href)
    .filter(Boolean);
  return {
    url: location.href,
    title: document.title,
    textLength: text.length,
    linkCount: links.length
  };
})()"""


def free_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def wait_json_version(port, timeout=20.0):
    deadline = time.time() + timeout
    url = f"http://127.0.0.1:{port}/json/version"
    last_error = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                return json.loads(response.read().decode())
        except Exception as error:
            last_error = error
            time.sleep(0.2)
    raise RuntimeError(f"Lightpanda did not expose {url}: {last_error}")


def _require_object(value, context):
    if not isinstance(value, dict):
        raise RuntimeError(f"{context} returned invalid response shape: expected object, got {type(value).__name__}")
    return value


def _require_field(value, key, context):
    data = _require_object(value, context)
    if not data.get(key):
        raise RuntimeError(f"{context} response missing required field: {key}")
    return data[key]


def _dict_value(value):
    return value if isinstance(value, dict) else {}


def _int_count(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def runtime_value(client, expression, session_id=None):
    result = client.send_raw(
        "Runtime.evaluate",
        {"expression": expression, "returnByValue": True, "awaitPromise": True},
        session_id=session_id,
    )
    if "exceptionDetails" in result:
        desc = result["exceptionDetails"].get("exception", {}).get("description", "")
        raise RuntimeError(f"JS exception evaluating {expression!r}: {desc}")
    return result.get("result", {}).get("value")


def evaluate_field_contract(client, checks, min_text=0, session_id=None):
    """Return page evidence plus named field-check results.

    `checks` maps stable field names to JavaScript expressions that evaluate in
    the page context. A backend passes only when page text and every required
    field expression are present. This keeps Lightpanda/headful comparison at
    the canonical-field layer instead of accepting a merely loaded page.
    """
    page = _dict_value(runtime_value(client, _PAGE_EVIDENCE_JS, session_id=session_id))
    passed = {}
    for name, expression in (checks or {}).items():
        passed[name] = bool(runtime_value(
            client,
            f"(() => Boolean({expression}))()",
            session_id=session_id,
        ))
    missing = [name for name, ok in passed.items() if not ok]
    if _int_count(page.get("textLength")) < _int_count(min_text):
        missing.insert(0, "min_text")
    return {
        "ok": not missing,
        "page": page,
        "passed": passed,
        "missing": missing,
    }


def wait_for_field_contract(client, checks, min_text=0, timeout=30.0, poll=0.5, session_id=None):
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        last = evaluate_field_contract(client, checks, min_text=min_text, session_id=session_id)
        if last["ok"]:
            return {**last, "reason": "fields_present"}
        time.sleep(poll)
    return {**last, "reason": "field_timeout"}


class LightpandaCDP:
    """CDP adapter that routes page commands through an attached target."""

    def __init__(self, ws_url):
        self.ws_url = ws_url
        self.ws = connect(ws_url, open_timeout=5)
        self.next_id = 0
        self.target_id = None
        self.page_session_id = None

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass

    def _request(self, method, params=None, session_id=None, timeout=30.0):
        self.next_id += 1
        message = {"id": self.next_id, "method": method}
        if params is not None:
            message["params"] = params
        if session_id:
            message["sessionId"] = session_id
        self.ws.send(json.dumps(message))
        deadline = time.time() + timeout
        while time.time() < deadline:
            reply = json.loads(self.ws.recv(timeout=max(0, deadline - time.time())))
            if reply.get("id") != self.next_id:
                continue
            if "error" in reply:
                raise RuntimeError(f"{method} failed: {reply['error']}")
            return reply.get("result", {})
        raise RuntimeError(f"{method} timed out after {timeout}s — no matching response")

    def _default_session_for(self, method):
        if method.startswith(_BROWSER_SCOPED_PREFIXES):
            return None
        return self.page_session_id

    def send_raw(self, method, params=None, session_id=None):
        sid = self._default_session_for(method) if session_id is None else session_id
        return self._request(method, params or {}, session_id=sid)

    def ensure_page(self, url="about:blank"):
        if self.page_session_id:
            return self.page_session_id
        self.target_id = _require_field(
            self._request("Target.createTarget", {"url": url}),
            "targetId",
            "Target.createTarget",
        )
        attached = self._request("Target.attachToTarget", {
            "targetId": self.target_id,
            "flatten": True,
        })
        self.page_session_id = _require_field(attached, "sessionId", "Target.attachToTarget")
        self.send_raw("Page.enable")
        self.send_raw("Runtime.enable")
        self.send_raw("Network.enable")
        return self.page_session_id


class LightpandaServer:
    """Launch a local Lightpanda CDP server and return a routed CDP client."""

    def __init__(self, binary="lightpanda", port=None, host="127.0.0.1", log_path=None):
        self.binary = str(Path(binary).expanduser()) if "/" in str(binary) else str(binary)
        self.host = host
        self.port = port or free_port()
        self.log_path = Path(log_path).expanduser() if log_path else None
        self.proc = None
        self.version = None
        self.client = None
        self._log_file = None

    def start(self, timeout=20.0):
        if self.proc:
            return self
        if self.log_path:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self._log_file = self.log_path.open("a")
            stdout = self._log_file
            stderr = self._log_file
        else:
            stdout = subprocess.DEVNULL
            stderr = subprocess.DEVNULL
        self.proc = subprocess.Popen(
            [self.binary, "serve", "--host", self.host, "--port", str(self.port)],
            stdout=stdout,
            stderr=stderr,
            start_new_session=True,
        )
        try:
            self.version = wait_json_version(self.port, timeout=timeout)
            self.client = LightpandaCDP(
                _require_field(self.version, "webSocketDebuggerUrl", "Lightpanda /json/version")
            )
            self.client.ensure_page()
        except Exception:
            self.close()
            raise
        return self

    def close(self):
        if self.client:
            self.client.close()
            self.client = None
        if self.proc:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=5)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
                try:
                    self.proc.wait(timeout=3)
                except Exception:
                    pass
            self.proc = None
        if self._log_file:
            self._log_file.close()
            self._log_file = None

    def __enter__(self):
        return self.start()

    def __exit__(self, exc_type, exc, tb):
        self.close()
