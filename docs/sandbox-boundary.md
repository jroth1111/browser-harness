# Sandbox Boundary Spec

## Decision

Agent runtime runs in a **subprocess**, not in-process.

Rationale: `sys.addaudithook` + `subprocess.run([sys.executable, "-I", "-S", ...])` is the only
configuration where "agent cannot import raw authorities" is provable. In-process restricted builtins
leak via `ctypes`, `importlib`, and `__builtins__` mutation.

## Architecture

```
┌──────────────────────┐       JSON-over-stdio        ┌──────────────────────┐
│   agent_host.py      │◄──────────────────────────►  │   agent_worker.py    │
│   (parent process)   │  length-prefixed frames       │   (child process)    │
│                      │                               │                      │
│  • CLI entry point   │   {"tool":"fetch","params":…} │  • audit hook        │
│  • owns transports   │   {"result":{…}}              │  • tool dispatch     │
│  • owns PolicyEngine │   {"error":"…"}               │  • type validation   │
│  • owns SessionBroker│                               │  • allowlist only    │
│  • owns AccessPlane  │                               │                      │
└──────────────────────┘                               └──────────────────────┘
```

## Protocol

Framing: 4-byte big-endian length prefix + UTF-8 JSON body.

Messages host→worker:
```json
{"type": "call", "id": 1, "tool": "fetch", "params": {"url": "https://example.com", "risk": "public_read"}}
{"type": "call", "id": 2, "tool": "click", "params": {"target": "submit-btn", "risk": "low_risk_write"}}
```

Messages worker→host:
```json
{"type": "result", "id": 1, "status": "ok", "data": {"status": 200, "text": "..."}}
{"type": "result", "id": 2, "status": "denied", "reason": "policy denied click on submit"}
{"type": "error", "id": 1, "error": "tool 'eval' not found"}
```

Transport requests: worker cannot do I/O. When a tool needs transport, worker sends a callback:
```json
{"type": "transport", "id": 1, "transport": "public_http", "request": {"url": "...", "method": "GET"}}
```
Host executes via AccessPlane and returns the result.

## Worker allowlist

The worker process may import only:
- `json`, `dataclasses`, `typing`, `enum`, `time`, `hashlib`, `struct`
- `browser_harness.capabilities.models`
- `browser_harness.authority.policy` (for type references only — no I/O)
- `browser_harness.authority.challenge` (for type references only)
- `browser_harness.authority.action_policy` (for type references only)

All other imports are blocked by the audit hook.

## Audit hook implementation

```python
import sys

ALLOWED_MODULES = frozenset({
    "json", "dataclasses", "typing", "enum", "time", "hashlib", "struct",
    "browser_harness.capabilities.models",
    "browser_harness.authority.policy",
    "browser_harness.authority.challenge",
    "browser_harness.authority.action_policy",
    "browser_harness.capabilities.resolver",  # type refs only
})

def _audit_import(event, args):
    if event == "import":
        module = args[0] if args else ""
        # Allow stdlib internals needed by the allowlist modules
        if module.startswith("_") and not module.startswith("__"):
            return
        # Check top-level module
        top = module.split(".")[0]
        if top in ("browser_harness",) and module not in ALLOWED_MODULES:
            raise ImportError(f"import denied: {module}")
        if top in ("urllib", "socket", "subprocess", "ctypes", "multiprocessing",
                    "threading", "signal", "os", "sys"):
            # os/sys needed for audit hook itself, but block user-level access
            if module not in ("os", "sys") or event != "import":
                return  # let os/sys through for infrastructure
            return
        # Block dangerous builtins
    if event == "exec":
        raise RuntimeError("exec denied in agent worker")
    if event == "compile":
        raise RuntimeError("compile denied in agent worker")

sys.addaudithook(_audit_import)
```

Note: `os` and `sys` remain importable in the worker for infrastructure (audit hook needs `sys`),
but `exec`, `compile`, `__import__` of blocked modules are denied at the audit level.

## Subprocess flags

```python
subprocess.run(
    [sys.executable, "-I", "-S", "-c", worker_script],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)
```

`-I` = isolated mode (no user site-packages, no PYTHONSTARTUP)
`-S` = skip site.py initialization

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | clean shutdown |
| 1 | tool error (reported in JSON) |
| 2 | import denied (audit hook caught forbidden import) |
| 3 | protocol error (malformed JSON, bad frame) |
| 10 | unhandled exception |

## What this replaces

- `runtime/sandbox.py` `AgentSandbox` class — deleted. The subprocess IS the sandbox.
- `FORBIDDEN_MODULES` list — deleted. The audit hook allowlist replaces it.
- `FORBIDDEN_NAMES` set — deleted. `exec`/`compile`/`__import__` blocked by audit hook.
- `os`/`sys` in `FORBIDDEN_MODULES` — this was wrong; fixed by moving enforcement to audit hook level.

## Test plan

`tests/test_agent_worker_isolation.py`:
1. Spawn worker, send `{"tool": "_eval", "params": {"code": "import urllib.request"}}` → exit code 2
2. Spawn worker, send `{"tool": "_eval", "params": {"code": "__import__('socket')"}}` → exit code 2
3. Spawn worker, send `{"tool": "_eval", "params": {"code": "open('/etc/passwd').read()"}}` → exit code 2
4. Spawn worker, send `{"tool": "fetch", "params": {"url": "https://example.com"}}` → result with status 200 (transport executed by host)
5. Spawn worker, send `{"tool": "cdp", "params": {"method": "Network.getCookies"}}` → denied (tool not in registry)
