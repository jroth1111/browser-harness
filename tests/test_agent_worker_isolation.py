"""Agent worker isolation tests — prove the sandbox is real enforcement.

These tests spawn actual worker subprocesses and verify that forbidden
operations are blocked at the runtime level (audit hook + restricted builtins),
not at a self-reported registry.
"""
import json
import struct
import subprocess
import sys
from pathlib import Path
import pytest


WORKER_SCRIPT = (
    "from browser_harness.runtime.agent_worker import worker_main; "
    "import sys; sys.exit(worker_main())"
)


def _spawn_worker():
    # -S skips usercustomize; we add the src dir to sys.path so the
    # worker can import browser_harness without full site-packages.
    src_dir = str(Path(__file__).resolve().parent.parent / "src")
    return subprocess.Popen(
        [sys.executable, "-S", "-c", f"import sys; sys.path.insert(0, {src_dir!r}); {WORKER_SCRIPT}"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _send_frame(proc, msg: dict):
    data = json.dumps(msg).encode()
    proc.stdin.write(struct.pack(">I", len(data)))
    proc.stdin.write(data)
    proc.stdin.flush()


def _recv_frame(proc):
    raw_len = proc.stdout.read(4)
    if not raw_len or len(raw_len) < 4:
        return None
    length = struct.unpack(">I", raw_len)[0]
    data = proc.stdout.read(length)
    return json.loads(data)


class TestWorkerIsolation:
    """Prove the worker subprocess blocks forbidden operations."""

    def test_worker_denies_unknown_tool(self):
        """Worker rejects tools not in the registry."""
        proc = _spawn_worker()
        try:
            _send_frame(proc, {"type": "call", "id": 1, "tool": "_eval", "params": {"code": "1+1"}})
            result = _recv_frame(proc)
            assert result is not None
            assert result.get("status") == "denied" or result.get("type") == "error"
        finally:
            proc.kill()
            proc.wait()

    def test_worker_denies_forbidden_tool(self):
        """Worker rejects cdp and other forbidden tool names."""
        proc = _spawn_worker()
        try:
            _send_frame(proc, {"type": "call", "id": 1, "tool": "cdp", "params": {"method": "Network.getCookies"}})
            result = _recv_frame(proc)
            assert result is not None
            assert result.get("status") == "denied"
            assert "forbidden" in result.get("reason", "").lower()
        finally:
            proc.kill()
            proc.wait()

    def test_worker_denies_exec_tool(self):
        """Worker rejects exec as a tool name."""
        proc = _spawn_worker()
        try:
            _send_frame(proc, {"type": "call", "id": 1, "tool": "exec", "params": {"code": "import urllib"}})
            result = _recv_frame(proc)
            assert result is not None
            assert result.get("status") == "denied"
        finally:
            proc.kill()
            proc.wait()

    def test_worker_validates_fetch_params(self):
        """Worker validates and forwards fetch tool calls."""
        proc = _spawn_worker()
        try:
            _send_frame(proc, {"type": "call", "id": 1, "tool": "fetch", "params": {"url": "https://example.com"}})
            result = _recv_frame(proc)
            assert result is not None
            # Worker forwards as callback for host to execute
            assert result.get("type") in ("callback", "result")
        finally:
            proc.kill()
            proc.wait()

    def test_worker_audit_hook_blocks_http_client(self):
        """Audit hook actively rejects `import http.client` after install.

        Spawns a subprocess that installs the audit hook, attempts the
        forbidden import, and exits with a sentinel code on success
        (i.e. the import was correctly denied).
        """
        src_dir = str(Path(__file__).resolve().parent.parent / "src")
        bootstrap = (
            f"import sys; sys.path.insert(0, {src_dir!r}); "
            "from browser_harness.runtime.sandbox import install_audit_hook; "
            "install_audit_hook(); "
            "import_blocked = False\n"
            "try:\n"
            "    import http.client  # noqa: F401\n"
            "except ImportError as e:\n"
            "    if 'denied by sandbox' in str(e):\n"
            "        import_blocked = True\n"
            "sys.exit(42 if import_blocked else 1)"
        )
        result = subprocess.run(
            [sys.executable, "-S", "-c", bootstrap],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 42, (
            f"audit hook failed to block http.client; "
            f"returncode={result.returncode} stderr={result.stderr}"
        )

    def test_worker_audit_hook_blocks_urllib_request(self):
        """Audit hook actively rejects `import urllib.request` after install."""
        src_dir = str(Path(__file__).resolve().parent.parent / "src")
        bootstrap = (
            f"import sys; sys.path.insert(0, {src_dir!r}); "
            "from browser_harness.runtime.sandbox import install_audit_hook; "
            "install_audit_hook(); "
            "import_blocked = False\n"
            "try:\n"
            "    import urllib.request  # noqa: F401\n"
            "except ImportError as e:\n"
            "    if 'denied by sandbox' in str(e):\n"
            "        import_blocked = True\n"
            "sys.exit(42 if import_blocked else 1)"
        )
        result = subprocess.run(
            [sys.executable, "-S", "-c", bootstrap],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 42, (
            f"audit hook failed to block urllib.request; "
            f"returncode={result.returncode} stderr={result.stderr}"
        )

    def test_worker_audit_hook_allows_json(self):
        """Audit hook permits stdlib modules in STDLIB_ALLOWLIST (sanity check)."""
        src_dir = str(Path(__file__).resolve().parent.parent / "src")
        bootstrap = (
            f"import sys; sys.path.insert(0, {src_dir!r}); "
            "from browser_harness.runtime.sandbox import install_audit_hook; "
            "install_audit_hook(); "
            "import json; import hashlib; import struct; "
            "sys.exit(0 if (json and hashlib and struct) else 1)"
        )
        result = subprocess.run(
            [sys.executable, "-S", "-c", bootstrap],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, (
            f"audit hook incorrectly blocked allowlisted stdlib; "
            f"stderr={result.stderr}"
        )

    def test_worker_audit_hook_blocks_private_socket(self):
        """Audit hook rejects `import _socket` — raw network access not allowed."""
        src_dir = str(Path(__file__).resolve().parent.parent / "src")
        bootstrap = (
            f"import sys; sys.path.insert(0, {src_dir!r}); "
            "from browser_harness.runtime.sandbox import install_audit_hook; "
            "install_audit_hook(); "
            "import_blocked = False\n"
            "try:\n"
            "    import _socket  # noqa: F401\n"
            "except ImportError as e:\n"
            "    if 'denied by sandbox' in str(e):\n"
            "        import_blocked = True\n"
            "sys.exit(42 if import_blocked else 1)"
        )
        result = subprocess.run(
            [sys.executable, "-S", "-c", bootstrap],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 42, (
            f"audit hook failed to block _socket; "
            f"returncode={result.returncode} stderr={result.stderr}"
        )

    def test_worker_audit_hook_blocks_private_ctypes(self):
        """Audit hook rejects `import _ctypes` — arbitrary FFI not allowed."""
        src_dir = str(Path(__file__).resolve().parent.parent / "src")
        bootstrap = (
            f"import sys; sys.path.insert(0, {src_dir!r}); "
            "from browser_harness.runtime.sandbox import install_audit_hook; "
            "install_audit_hook(); "
            "import_blocked = False\n"
            "try:\n"
            "    import _ctypes  # noqa: F401\n"
            "except ImportError as e:\n"
            "    if 'denied by sandbox' in str(e):\n"
            "        import_blocked = True\n"
            "sys.exit(42 if import_blocked else 1)"
        )
        result = subprocess.run(
            [sys.executable, "-S", "-c", bootstrap],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 42, (
            f"audit hook failed to block _ctypes; "
            f"returncode={result.returncode} stderr={result.stderr}"
        )

    def test_worker_clean_shutdown(self):
        """Worker shuts down cleanly on shutdown frame."""
        proc = _spawn_worker()
        try:
            _send_frame(proc, {"type": "shutdown"})
            proc.wait(timeout=5)
            assert proc.returncode == 0
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()


    def test_worker_cdp_gate(self):
        """Worker denies cdp tool at tool level (FORBIDDEN_TOOLS)."""
        proc = _spawn_worker()
        try:
            _send_frame(proc, {"type": "call", "id": 1, "tool": "cdp", "params": {"method": "Runtime.evaluate"}})
            result = _recv_frame(proc)
            assert result is not None
            assert result.get("status") == "denied"
            assert "forbidden" in result.get("reason", "").lower()
        finally:
            proc.kill()
            proc.wait()


class TestAgentHostSubprocess:
    """Prove AgentHost spawns worker and routes tool calls."""

    def test_host_fetch_routes_through_worker(self):
        from browser_harness.runtime.agent_host import AgentHost
        from browser_harness.authority.policy import PolicyEngine
        from browser_harness.capabilities.resolver import AccessPlane

        plane = AccessPlane(
            policy=PolicyEngine(),
            http_fn=lambda url, **kw: "host-executed content",
        )
        host = AgentHost(access_plane=plane)
        try:
            result = host.call("fetch", {"url": "https://example.com", "risk": "public_read"})
            assert result.get("status") == "ok"
            assert result.get("source") == "http"
        finally:
            host.shutdown()

    def test_host_denied_tool_through_worker(self):
        from browser_harness.runtime.agent_host import AgentHost
        host = AgentHost()
        try:
            result = host.call("cdp", {"method": "Network.getCookies"})
            assert result.get("status") == "denied"
        finally:
            host.shutdown()

    def test_host_click_through_worker(self):
        from browser_harness.runtime.agent_host import AgentHost
        host = AgentHost()
        try:
            result = host.call("click", {"target": "expand-details", "risk": "low_risk_write"})
            assert result.get("status") == "ok"
        finally:
            host.shutdown()
