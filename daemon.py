"""CDP WS holder + Unix socket relay. One daemon per BH_NAME."""
import asyncio
import ipaddress
import json
import os
import socket
import sys
import time
import urllib.request
from collections import deque
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from cdp_use.client import CDPClient


def _load_env():
    p = Path(__file__).parent / ".env"
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()

NAME = os.environ.get("BH_NAME", "default")
SOCK = f"/tmp/bh-{NAME}.sock"
LOG = f"/tmp/bh-{NAME}.log"
PID = f"/tmp/bh-{NAME}.pid"
BUF = 500
PROFILES = [
    Path.home() / "Library/Application Support/Google/Chrome",
    Path.home() / "Library/Application Support/Microsoft Edge",
    Path.home() / "Library/Application Support/Microsoft Edge Beta",
    Path.home() / "Library/Application Support/Microsoft Edge Dev",
    Path.home() / "Library/Application Support/Microsoft Edge Canary",
    Path.home() / ".config/google-chrome",
    Path.home() / ".config/chromium",
    Path.home() / ".config/chromium-browser",
    Path.home() / ".config/microsoft-edge",
    Path.home() / ".config/microsoft-edge-beta",
    Path.home() / ".config/microsoft-edge-dev",
    Path.home() / ".var/app/org.chromium.Chromium/config/chromium",
    Path.home() / ".var/app/com.google.Chrome/config/google-chrome",
    Path.home() / ".var/app/com.brave.Browser/config/BraveSoftware/Brave-Browser",
    Path.home() / ".var/app/com.microsoft.Edge/config/microsoft-edge",
    Path.home() / "AppData/Local/Google/Chrome/User Data",
    Path.home() / "AppData/Local/Chromium/User Data",
    Path.home() / "AppData/Local/Microsoft/Edge/User Data",
    Path.home() / "AppData/Local/Microsoft/Edge Beta/User Data",
    Path.home() / "AppData/Local/Microsoft/Edge Dev/User Data",
    Path.home() / "AppData/Local/Microsoft/Edge SxS/User Data",
]
INTERNAL = ("chrome://", "chrome-untrusted://", "devtools://", "chrome-extension://", "about:")


def log(msg):
    open(LOG, "a").write(f"{msg}\n")


def _is_loopback_host(host):
    if not host:
        return False
    host = host.strip("[]").lower()
    if host in {"localhost", "localhost."}:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _redact_url(url):
    parsed = urlparse(url)
    if not parsed.username and not parsed.password:
        return url
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return urlunparse((parsed.scheme, host, parsed.path, "", parsed.query, parsed.fragment))


def _remote_allowed():
    return os.environ.get("BH_CDP_ALLOW_REMOTE") == "1"


def _validate_endpoint_url(url, *, source, http_base=None):
    parsed = urlparse(url)
    if parsed.scheme not in {"ws", "http"}:
        raise RuntimeError(f"unsupported CDP endpoint scheme: {parsed.scheme or '(missing)'}")
    if parsed.username or parsed.password:
        raise RuntimeError("CDP endpoint URLs must not contain credentials")
    host = parsed.hostname
    port = parsed.port
    if (host or "").strip("[]") == "0.0.0.0":
        raise RuntimeError("CDP endpoint host 0.0.0.0 is unsafe; use 127.0.0.1 or localhost")
    is_loopback = _is_loopback_host(host)
    allowed_remote = _remote_allowed()
    warnings = []
    if not is_loopback:
        if not allowed_remote:
            raise RuntimeError(
                "refusing non-loopback CDP endpoint; set BH_CDP_ALLOW_REMOTE=1 only for a user-owned self-hosted browser"
            )
        warnings.append("remote CDP endpoint allowed by BH_CDP_ALLOW_REMOTE=1")
    return {
        "source": source,
        "input": "BH_CDP_WS" if source == "env" else "DevToolsActivePort",
        "resolved_url": _redact_url(url),
        "http_base": _redact_url(http_base) if http_base else None,
        "host": host,
        "port": port,
        "is_loopback": is_loopback,
        "remote_allowed": allowed_remote and not is_loopback,
        "warnings": warnings,
        "browser": None,
        "protocol_version": None,
    }


def _devtools_version_url(url):
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    path = f"{path}/json/version" if path else "/json/version"
    return urlunparse((parsed.scheme, parsed.netloc, path, "", parsed.query, ""))


def _resolve_devtools_http_base(url):
    parsed = urlparse(url)
    if parsed.scheme != "http":
        raise RuntimeError(f"unsupported DevTools HTTP endpoint scheme: {parsed.scheme or '(missing)'}")
    info = _validate_endpoint_url(url, source="env", http_base=url)
    with urllib.request.urlopen(_devtools_version_url(url), timeout=5) as resp:
        data = json.loads(resp.read().decode())
    ws_url = data.get("webSocketDebuggerUrl")
    if not ws_url:
        raise RuntimeError(f"{_redact_url(url)}/json/version did not include webSocketDebuggerUrl")
    ws_info = _validate_endpoint_url(ws_url, source="env", http_base=url)
    ws_info["browser"] = data.get("Browser")
    ws_info["protocol_version"] = data.get("Protocol-Version")
    ws_info["warnings"] = [*info["warnings"], *ws_info["warnings"]]
    return ws_url, ws_info


def _resolve_cdp_endpoint_from_env():
    url = os.environ.get("BH_CDP_WS")
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme == "http":
        return _resolve_devtools_http_base(url)
    info = _validate_endpoint_url(url, source="env")
    return url, info


def _resolve_cdp_endpoint_from_devtools_active_port(wait_for_port=True):
    for base in PROFILES:
        try:
            port, path = (base / "DevToolsActivePort").read_text().strip().split("\n", 1)
        except (FileNotFoundError, NotADirectoryError):
            continue
        port = port.strip()
        path = path.strip()
        if wait_for_port:
            deadline = time.time() + 30
            while True:
                probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                probe.settimeout(1)
                try:
                    probe.connect(("127.0.0.1", int(port)))
                    break
                except OSError:
                    if time.time() >= deadline:
                        raise RuntimeError(
                            "Chrome's remote-debugging page is open, but DevTools is not live yet "
                            f"on 127.0.0.1:{port} - if Chrome opened a profile picker, choose your "
                            "normal profile first, then tick the checkbox and click Allow if shown"
                        )
                    time.sleep(1)
                finally:
                    probe.close()
        url = f"ws://127.0.0.1:{port}{path}"
        return url, _validate_endpoint_url(url, source="devtools_active_port")
    raise RuntimeError(f"DevToolsActivePort not found in {[str(p) for p in PROFILES]} - enable chrome://inspect/#remote-debugging")


def resolve_cdp_endpoint(wait_for_port=True):
    env_endpoint = _resolve_cdp_endpoint_from_env()
    if env_endpoint:
        return env_endpoint
    return _resolve_cdp_endpoint_from_devtools_active_port(wait_for_port=wait_for_port)


def get_ws_url():
    return resolve_cdp_endpoint()[0]


def is_real_page(t):
    return t["type"] == "page" and not t.get("url", "").startswith(INTERNAL)


class Daemon:
    def __init__(self):
        self.cdp = None
        self.session = None
        self.endpoint_info = None
        self.events = deque(maxlen=BUF)
        self.dialog = None
        self.stop = None  # asyncio.Event, set inside start()

    async def attach_first_page(self):
        """Attach to a real page (or any page). Sets self.session. Returns attached target or None."""
        targets = (await self.cdp.send_raw("Target.getTargets"))["targetInfos"]
        pages = [t for t in targets if is_real_page(t)]
        if not pages:
            tid = (await self.cdp.send_raw("Target.createTarget", {"url": "about:blank"}))["targetId"]
            log(f"no real pages found, created about:blank ({tid})")
            pages = [{"targetId": tid, "url": "about:blank", "type": "page"}]
        self.session = (await self.cdp.send_raw(
            "Target.attachToTarget", {"targetId": pages[0]["targetId"], "flatten": True}
        ))["sessionId"]
        log(f"attached {pages[0]['targetId']} ({pages[0].get('url','')[:80]}) session={self.session}")
        return pages[0]

    async def start(self):
        self.stop = asyncio.Event()
        url, self.endpoint_info = resolve_cdp_endpoint()
        log(f"connecting to {_redact_url(url)}")
        self.cdp = CDPClient(url)
        try:
            await self.cdp.start()
        except Exception as e:
            raise RuntimeError(f"CDP WS handshake failed: {e} -- click Allow in Chrome if prompted, then retry")
        await self.attach_first_page()
        orig = self.cdp._event_registry.handle_event

        async def tap(method, params, session_id=None):
            self.events.append({"method": method, "params": params, "session_id": session_id})
            if method == "Page.javascriptDialogOpening":
                self.dialog = params
            elif method == "Page.javascriptDialogClosed":
                self.dialog = None
            return await orig(method, params, session_id)

        self.cdp._event_registry.handle_event = tap

    async def handle(self, req):
        meta = req.get("meta")
        if meta == "drain_events":
            out = list(self.events); self.events.clear()
            return {"events": out}
        if meta == "session":     return {"session_id": self.session}
        if meta == "endpoint_info": return {"endpoint_info": self.endpoint_info}
        if meta == "set_session":
            self.session = req.get("session_id")
            return {"session_id": self.session}
        if meta == "pending_dialog": return {"dialog": self.dialog}
        if meta == "shutdown":    self.stop.set(); return {"ok": True}

        method = req["method"]
        params = req.get("params") or {}
        # Browser-level Target.* calls must not use a session (stale or otherwise).
        # For everything else, explicit session in req wins; else default.
        sid = None if method.startswith("Target.") else (req.get("session_id") or self.session)
        try:
            return {"result": await self.cdp.send_raw(method, params, session_id=sid)}
        except Exception as e:
            msg = str(e)
            if "Session with given id not found" in msg and sid == self.session and sid:
                log(f"stale session {sid}, re-attaching")
                if await self.attach_first_page():
                    return {"result": await self.cdp.send_raw(method, params, session_id=self.session)}
            return {"error": msg}


async def serve(d):
    if os.path.exists(SOCK):
        os.unlink(SOCK)

    async def handler(reader, writer):
        try:
            line = await reader.readline()
            if not line: return
            resp = await d.handle(json.loads(line))
            writer.write((json.dumps(resp, default=str) + "\n").encode())
            await writer.drain()
        except Exception as e:
            log(f"conn: {e}")
            try:
                writer.write((json.dumps({"error": str(e)}) + "\n").encode())
                await writer.drain()
            except Exception:
                pass
        finally:
            writer.close()

    server = await asyncio.start_unix_server(handler, path=SOCK)
    os.chmod(SOCK, 0o600)
    log(f"listening on {SOCK} (name={NAME})")
    async with server:
        await d.stop.wait()


async def main():
    d = Daemon()
    await d.start()
    await serve(d)


def already_running():
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s.settimeout(1)
        s.connect(SOCK); s.close(); return True
    except (FileNotFoundError, ConnectionRefusedError, socket.timeout):
        return False


if __name__ == "__main__":
    if already_running():
        print(f"daemon already running on {SOCK}", file=sys.stderr)
        sys.exit(0)
    open(LOG, "w").close()
    open(PID, "w").write(str(os.getpid()))
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        log(f"fatal: {e}")
        sys.exit(1)
    finally:
        try: os.unlink(PID)
        except FileNotFoundError: pass
