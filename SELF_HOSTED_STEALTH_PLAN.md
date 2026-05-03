# Self-Hosted Stealth Improvement Plan

Date: 2026-04-27

Status: reviewed and strengthened after source-code analysis.

Scope: improve `browser-harness` as a local, self-hosted CDP control layer. The core must not add cloud browser providers, hosted browser APIs, captcha-solving services, proxy purchase/rotation services, dashboards, queues, databases, MCP servers, or long-running platform features.

The reference repos were cloned under `/tmp/browser-harness-reference-repos` and inspected at the revisions listed below. They are evidence for design choices, not dependency targets.

## Review Summary

The first version of this plan had the correct direction, but it was still too broad to execute safely. It named the right repos and the right stealth failures, but it did not fully specify:

- which existing browser-harness files and functions must change,
- which old runtime paths must be deleted rather than preserved,
- which CDP methods are allowed on attach versus explicit helper calls,
- how to verify stealth regressions without relying on live Chrome for every test,
- how to keep `run.py` tiny and avoid turning the skill into a provider platform,
- how to remove Browser Use naming and implicit hosted-network calls from normal local operation.

This revision treats the plan as an implementation contract. Later work should implement the phases in order and mark a phase complete only when its acceptance checks pass.

## Second Review Additions

This pass tightens three remaining weak spots:

- Endpoint security must not require DNS lookups. Accept literal loopback addresses and `localhost`; reject other hostnames by default rather than resolving arbitrary names.
- Doctor needs a tiny daemon metadata contract. Without that, endpoint provenance, resolved websocket URL, and remote-allow warnings would have to be inferred from logs.
- Fake-CDP tests need concrete fixtures and expected method traces. Otherwise the most important stealth requirements could degrade into inspection-only checks.

The rest of the document incorporates those changes directly.

## Hard Constraints

These constraints override convenience and compatibility.

- Local/self-hosted only: normal operation must attach to a local or explicitly approved self-hosted CDP endpoint.
- No default external network: `browser-harness`, `--doctor`, and helper imports must not call hosted services by default.
- No cloud browser runtime: no Browser Use Cloud, Browserbase Cloud, Anchor, Steel Cloud, OnKernel Cloud, Hyperbrowser Cloud, Rebrowser Cloud, or equivalent provider API in core.
- No provider SDKs in core: local provider support is endpoint documentation plus diagnostics, not imported SDKs.
- No JavaScript stealth shims: do not patch fingerprints through init scripts, page globals, title markers, or hidden `Runtime.evaluate` calls.
- Explicit JS remains allowed: `js(...)`, DOM-specific helpers, and diagnostic probes may use `Runtime.evaluate`, but those paths must be obvious to the caller and documented as non-stealth/diagnostic.
- CDP-thin by default: attach to the browser and send only the CDP needed for the requested helper.
- Keep the skill shape: `run.py` stays tiny, no argparse, no manager layer, no config system, no daemon supervisor, no logging framework.
- Breaking changes are allowed: delete old `BU_*` names, stale shims, fallback paths, and misleading docs instead of carrying compatibility.

## Source Inventory

| Reference | Revision | Adopt | Reject |
| --- | --- | --- | --- |
| `browser-use/benchmark` | `702bf09` | Treat local headful/headless as tiny local baselines. Keep provider adapters outside the harness. | Do not import benchmark cloud-provider configs or API assumptions. |
| `steel-dev/steel-browser` | `d6b15d5` (`v0.5.3-beta`) | Session metadata, health-style output, debugger URL reporting, structured result shape. | Do not add Steel session server, JS fingerprint injection, provider account model, queues, or APIs. |
| `browserless/browserless` | `b806de6d` (`v2.47.0`) | Docker/CDP endpoint pattern, `/json/version`, websocket proxy awareness, health/pressure checks. | Do not add Browserless-style concurrency queues, hosted service shape, REST platform, or stealth plugin dependency. |
| `kernel/kernel-images` | `c058cb0` | Headful isolated Chromium recipe, supervised browser process, restart-aware CDP proxy, optional local VNC/recording reference. | Do not embed containers, Xorg/Mutter management, recording server, or process orchestration into core. |
| `browserbase/stagehand` | `1fe71b8c` (`v2.2.0`) | Local CDP URL handling, persistent user-data-dir concept, lazy CDP access, action history as optional ergonomics. | Do not include Browserbase API paths, captcha hooks, remote sessions, or init-script stealth. |
| `hyperbrowserai/HyperAgent` | `336a906` (`v1.0.0`) | Local-first controller pattern, optional CDP action mode, accessibility snapshot ideas, network-idle wait stats. | Do not copy Runtime-heavy accessibility/controller paths into default attach. |
| `daijro/camoufox` | `76c30ac` (`v146-hardware`) | Engine-level fingerprinting, Playwright page-agent isolation lessons, native input direction. | Not a Chromium CDP drop-in; do not pretend it is directly supported by current browser-harness. |
| `CloverLabsAI/camoufox` | `61430df` | Same engine-level/no-JS-shim lesson, with AI-agent framing and per-context identity ideas. | No non-CDP adapter unless browser-harness intentionally grows a separate Playwright/Juggler sidecar later. |
| `CloakHQ/CloakBrowser` | `4459f66` (`v0.3.25`) | Best local Chromium-shaped endpoint: source-level patches, `cloakserve`, per-seed profiles, SOCKS5/WebRTC/proxy alignment, loopback CDP guidance. | Do not vendor or manage CloakBrowser binaries in core. |
| `Kaliiiiiiiiii-Vinyzu/patchright` | `748e09d` (`v1.59.x`) | Treat automatic `Runtime.enable`, `Console.enable`, automation flags, and closed-shadow-root assumptions as concrete leaks to prevent. | Do not adopt Playwright as the browser-harness core abstraction. |
| `rebrowser/rebrowser-patches` | `6373894` (`1.0.19`) | `Runtime.Enable` leak research, mitigation thinking, and the "less JS manipulation is better" rule. | Do not add rebrowser patches or JS workarounds as core dependencies. |
| `kameleo-io/kameleo` | `0f76e3a` (`4.4.1`) | Local profile lifecycle model, localhost API, profile-specific Playwright CDP endpoint, blocked switch policy. | Do not add commercial API coupling or profile management to core. |
| `jo-inc/camofox-browser` | `923b7be` (`v1.7.4`) | Optional agent utilities: stable refs, compact accessibility snapshots, per-tab locks, trace capture, structured logs. | Too broad for core; no REST server, VNC login layer, plugin platform, or long-lived session API. |
| `saifyxpro/HeadlessX` | `af2bd4b` (`v2.1.2`) | Operational references: CLI doctor, local bootstrap, persistent shared profile, Docker/self-host recipes. | No dashboard, DB, Redis, queue, MCP, cloud integrations, or platform install surface. |
| `techinz/browsers-benchmark` | `7f14d54` | Local diagnostic inspiration: browser-data checks, IP/WebRTC consistency, screenshots, result reporting. | Do not call public fingerprint/bypass targets by default. |

## Current State Audit

The current browser-harness implementation is small, which is an advantage. The plan should preserve that shape while deleting the high-risk defaults below.

| Area | Current artifact | Problem | Replacement direction |
| --- | --- | --- | --- |
| Endpoint env var | `daemon.get_ws_url`, `admin._is_local_chrome_mode` | Uses `BU_CDP_WS`, preserving old Browser Use naming. | Use `BH_CDP_WS` only. No compatibility fallback. |
| Daemon name/temp paths | `BU_NAME`, `/tmp/bu-*.sock`, `/tmp/bu-*.pid`, `/tmp/bu-*.log`, `/tmp/bu-version-cache.json` | Old `BU` namespace is misleading and leaves stale artifacts. | Rename to `BH_NAME`, `/tmp/bh-*`, and clean old `/tmp/bu-*` opportunistically during reload/setup. |
| Attach behavior | `daemon.Daemon.attach_first_page` | Enables `Page`, `DOM`, `Runtime`, and `Network` on fresh attach. | Attach via `Target.*` only. Enable domains inside explicit helpers when required. |
| Event tap | `daemon.Daemon.start` | Mutates page title after load/dom events through hidden `Runtime.evaluate`. | Keep event capture only if needed; delete title marker. |
| Session switch | `daemon.Daemon.handle(meta=set_session)` | Enables `Page` and injects title marker. | Switch session only; no domain enable or page mutation. |
| Page info | `helpers.page_info` | Uses `Runtime.evaluate` for routine status. | Use `Target.getTargetInfo` plus `Page.getLayoutMetrics`; keep JS fallback as `page_info_js()` only if needed. |
| Tab switching | `helpers._mark_tab`, `helpers.switch_tab`, `helpers.new_tab` | Title marker is page-visible and stealth-hostile. | Delete `_mark_tab`; switch tabs without visible page mutation. |
| Load wait | `helpers.wait_for_load` | Polls `document.readyState` through `js()`. | Use `Page` events or explicit `wait_for_load_js()`; normal helper should not require Runtime. |
| Debug click | `helpers.click_at_xy` with `BH_DEBUG_CLICKS` | Uses `js("window.devicePixelRatio")` for a debug-only overlay. | Prefer `Page.getLayoutMetrics` or make the Runtime use explicit in debug docs. |
| Profile discovery | `admin.list_local_profiles` | Points to `https://browser-use.com/profile.sh` when `profile-use` is missing. | Replace with local browser-harness setup guidance or remove profile-use dependency path. |
| Doctor | `admin.run_doctor` | Calls GitHub release check and only validates Chrome/daemon. | Default offline local doctor with endpoint/CDP hygiene checks; external checks opt-in. |
| Normal CLI | `run.main` | Help advertises heredoc, implementation only accepts `-c`. Also calls update banner in normal execution. | Implement stdin/heredoc and remove default hosted release check from normal runs. |
| Tests | `test_run.py`, `test_admin.py`, `test_js.py` | No tests cover local endpoint contract or CDP stealth invariants. | Add fake-CDP and mock-based tests that fail on forbidden CDP traffic and cloud strings. |

## Threat Model

Browser-harness cannot make an unmodified browser fully stealthy. Its job is narrower:

- avoid adding harness-created leaks,
- keep CDP traffic minimal and intentional,
- support strong local engines and containers through a BYO endpoint contract,
- warn when a local endpoint is unsafe or misconfigured.

Out of scope:

- defeating all behavioral bot detection,
- solving captchas,
- buying or rotating proxies,
- guaranteeing bypass against public anti-bot services,
- fingerprint patching from JavaScript.

In scope:

- no automatic `Runtime.enable`,
- no automatic `Console.enable`,
- no hidden JS marker or init script,
- no accidental public CDP exposure,
- no cloud browser runtime,
- no default hosted network call,
- clear diagnostics when the chosen local browser runtime is weak.

## End-State Architecture

Browser-harness should have four small surfaces:

1. CLI runner: `run.py`
   - manual flag parsing only,
   - `-c` and stdin/heredoc execution,
   - pre-import helpers,
   - daemon auto-start,
   - no provider logic.

2. Admin/bootstrap: `admin.py`
   - daemon lifecycle,
   - local setup guidance,
   - offline doctor orchestration,
   - optional explicit update command,
   - no cloud browser runtime.

3. CDP daemon: `daemon.py`
   - resolve a local/self-hosted endpoint,
   - connect to one browser websocket,
   - attach to a real page target,
   - relay raw CDP requests over a Unix socket,
   - record events without page mutation.

4. Helpers: `helpers.py`
   - short browser primitives,
   - compositor-level input first,
   - explicit JS helper remains available,
   - routine helpers avoid `Runtime.evaluate`.

No new top-level manager, service, queue, database, config package, provider SDK, or browser binary manager should be added.

## Public Contract After Phase 1

The intended user-facing contract after the first two phases is:

Environment:

- `BH_NAME`: optional local daemon namespace. Default `default`.
- `BH_CDP_WS`: optional local/self-hosted CDP endpoint.
- `BH_CDP_ALLOW_REMOTE=1`: explicit unsafe override for non-loopback self-hosted endpoints.
- `BH_DEBUG_CLICKS=1`: explicit debug overlay mode.

Commands:

- `browser-harness <<'PY' ... PY`: execute stdin/heredoc code with helpers pre-imported.
- `browser-harness -c "..."`: execute one command string.
- `browser-harness --doctor [--json] [--network]`: run local diagnostics; external checks only with `--network`.
- `browser-harness --setup`: guide local Chrome/Edge attachment.
- `browser-harness --reload`: stop the local daemon and remove stale socket/pid files.
- `browser-harness --update [-y]`: explicit update path; this may contact GitHub because the user asked for update behavior.

Removed compatibility:

- `BU_NAME`
- `BU_CDP_WS`
- `/tmp/bu-*.sock`
- `/tmp/bu-*.pid`
- `/tmp/bu-*.log`
- implicit normal-run update banner
- hidden tab-title marker

Helper categories:

| Category | Helpers |
| --- | --- |
| Stealth-preserving default helpers | `new_tab`, `goto_url`, `page_info`, `capture_screenshot`, `click_at_xy`, `type_text`, `press_key`, `scroll`, `list_tabs`, `switch_tab`, `current_tab`, `ensure_real_tab` |
| Explicit page-execution helpers | `js`, `dispatch_key`, `upload_file`, `page_info_js`, `wait_for_load_js` if kept |
| Diagnostic helpers | doctor-only probes for webdriver, WebGL, locale/timezone, WebRTC, and network checks |

The default workflow in `SKILL.md` should use only stealth-preserving helpers unless a domain skill explicitly chooses JS/DOM access.

## CDP Method Policy

The policy is intentionally strict. A later implementation should add tests that encode it.

| Category | Methods | Rule |
| --- | --- | --- |
| Allowed on attach | `Target.getTargets`, `Target.attachToTarget`, `Target.createTarget` when no real page exists | Attach must work without enabling page-visible domains. |
| Safe routine helpers | `Target.*`, `Page.navigate`, `Page.captureScreenshot`, `Input.dispatchMouseEvent`, `Input.dispatchKeyEvent`, `Input.insertText`, `Page.getLayoutMetrics` | May be used directly by default helpers. |
| Explicit helper only | `Runtime.evaluate`, `DOM.*`, `Network.*`, `Accessibility.*`, `Page.enable` | Use only inside helpers whose names/docs imply this behavior, or inside diagnostics. |
| Forbidden by default | automatic `Runtime.enable`, automatic `Console.enable`, hidden init scripts, title/document mutation, fingerprint JS patches | Tests must fail if these appear in attach/session-switch/page-info paths. |

Important nuance: `Runtime.evaluate` is not banned globally. It is banned as hidden implementation detail for ordinary attach, page info, tab switch, and load wait behavior.

## Endpoint Contract

`BH_CDP_WS` is the single bring-your-own-endpoint variable.

Accepted values:

- Browser websocket URL:
  - `ws://127.0.0.1:9222/devtools/browser/<id>`
- DevTools HTTP base URL:
  - `http://127.0.0.1:9222`
  - resolved through `/json/version` to `webSocketDebuggerUrl`

Rejected by default:

- non-loopback hosts,
- `0.0.0.0`,
- public IPs,
- arbitrary domain names,
- URLs with unsupported schemes.

Host validation rules:

- Accept literal loopback IPs:
  - `127.0.0.0/8`
  - `::1`
- Accept exact hostnames:
  - `localhost`
  - `localhost.`
- Reject all other hostnames by default without DNS resolution.
- Do not perform DNS lookups as part of normal validation; DNS resolution is a network-capable operation and can make local/offline checks less deterministic.
- Treat `0.0.0.0` as unsafe even though a Docker service may listen on it inside a container. The host-facing URL given to browser-harness should be loopback-bound.

Explicit escape hatch:

- `BH_CDP_ALLOW_REMOTE=1` may allow a non-loopback endpoint for a user-owned self-hosted machine.
- When this is set, doctor must print a high-severity warning that remote CDP is equivalent to browser control.
- There is no silent fallback from rejected remote endpoints.

Scheme rules:

- `ws://` browser websocket URLs are supported.
- `http://` DevTools base URLs are supported through `/json/version`.
- `wss://` and `https://` may be supported only if the implementation adds tests for them; they should still obey the same host/remote-allow policy.
- Any endpoint containing credentials in the URL should be rejected in normal output or redacted in every log/doctor field.

Endpoint metadata contract:

The daemon should keep a small in-memory endpoint record after resolution:

```python
{
    "source": "env" | "devtools_active_port",
    "input": "BH_CDP_WS" | "DevToolsActivePort",
    "resolved_url": "ws://127.0.0.1:9222/devtools/browser/...",
    "http_base": "http://127.0.0.1:9222" | None,
    "host": "127.0.0.1",
    "port": 9222,
    "is_loopback": True,
    "remote_allowed": False,
    "warnings": [],
}
```

Expose this through a daemon meta request such as `{"meta": "endpoint_info"}`. Keep it diagnostic-only; helpers should not depend on provider identity.

Deletion requirements:

- Delete `BU_CDP_WS`; do not support it as an alias.
- Rename `BU_NAME` to `BH_NAME`; do not support it as an alias.
- Rename `/tmp/bu-*` runtime paths to `/tmp/bh-*`.
- `--reload` or setup may remove stale old `/tmp/bu-*` artifacts as cleanup, but runtime must not depend on them.

## Phase 0: Local-Only Naming, CLI, And Offline Defaults

Objective: make the command surface self-hosted and coherent before deeper stealth changes.

Owned files:

- `daemon.py`
- `admin.py`
- `run.py`
- `SKILL.md`
- `install.md`
- `README.md` if present
- tests: `test_run.py`, `test_admin.py`, new `test_daemon.py` if useful

Required changes:

- Replace `BU_CDP_WS` with `BH_CDP_WS`.
- Replace `BU_NAME` with `BH_NAME`.
- Replace `/tmp/bu-*` socket, pid, log, and cache paths with `/tmp/bh-*`.
- Add endpoint resolution helpers:
  - `_is_loopback_host(host)`,
  - `_resolve_devtools_http_base(url)`,
  - `_resolve_cdp_endpoint_from_env()`,
  - `_resolve_cdp_endpoint_from_devtools_active_port()`.
- Support `BH_CDP_WS=http://127.0.0.1:9222` by calling `/json/version`.
- Reject non-loopback endpoint hosts unless `BH_CDP_ALLOW_REMOTE=1`.
- Implement stdin/heredoc execution in `run.py`.
- Keep `-c` execution.
- Remove automatic update banner from normal command execution.
- Make `--doctor` offline by default; it must not call GitHub release APIs unless the user explicitly asks for update information.
- Replace `profile-use`/`browser-use.com/profile.sh` messaging with local setup guidance.
- Replace docs examples that point at Browser Use URLs with neutral local examples.

Detailed deletion map:

| Old name/path | New state |
| --- | --- |
| `BU_CDP_WS` | Deleted. Use `BH_CDP_WS`. |
| `BU_NAME` | Deleted. Use `BH_NAME`. |
| `/tmp/bu-{name}.sock` | Deleted active path. Use `/tmp/bh-{name}.sock`. |
| `/tmp/bu-{name}.pid` | Deleted active path. Use `/tmp/bh-{name}.pid`. |
| `/tmp/bu-{name}.log` | Deleted active path. Use `/tmp/bh-{name}.log`. |
| `/tmp/bu-version-cache.json` | Deleted active path. Use no default version cache, or `/tmp/bh-version-cache.json` only for explicit update checks. |
| `profile-use not installed -- curl -fsSL https://browser-use.com/profile.sh | sh` | Replace with local setup instructions. |
| `docs.browser-use.com` example URL in `SKILL.md` | Replace with a neutral local-safe example, e.g. `https://example.com`. |

Implementation details:

- Keep argument handling simple:
  - special flags first,
  - `--debug-clicks` may set env and continue,
  - `-c CODE` executes `CODE`,
  - otherwise read `sys.stdin.read()` and execute if non-empty,
  - print usage only if neither `-c` nor stdin is supplied.
- Do not add argparse.
- Do not create a config object. Small private helper functions are enough.
- Do not keep `BU_*` compatibility. Breaking the old names is cleaner and matches the local-only contract.
- Keep old path cleanup best-effort only. Do not block startup if stale `/tmp/bu-*` files cannot be removed.
- Redact endpoint URLs in errors/logs if credentials or tokens are ever present.

Tests:

- `test_run.py`
  - `-c` executes and does not read stdin.
  - stdin/heredoc executes when no `-c` is passed.
  - empty stdin prints usage and does not start daemon.
  - normal execution does not call `print_update_banner`.
- `test_admin.py`
  - `_is_local_chrome_mode` respects `BH_CDP_WS`.
  - doctor default does not call `_latest_release_tag`.
  - `profile-use` missing error contains no hosted Browser Use install URL.
- `test_daemon.py`
  - `BH_CDP_WS` websocket URL passes through.
  - `BH_CDP_WS` HTTP base resolves `/json/version`.
  - public endpoint rejects without `BH_CDP_ALLOW_REMOTE`.
  - public endpoint passes with `BH_CDP_ALLOW_REMOTE=1` and records a warning.

Acceptance:

- `rg "BU_CDP_WS|BU_NAME|/tmp/bu-|browser-use.com/profile|api.browser-use|cloud.browser-use" daemon.py admin.py run.py helpers.py SKILL.md install.md README.md pyproject.toml` returns no active runtime/docs references. After Phase 2 creates `docs/`, include `docs` in this check too.
- `printf 'print(1)\\n' | browser-harness` executes through pre-imported helpers.
- `browser-harness -c "print(1)"` still works.
- `BH_CDP_WS=http://127.0.0.1:9222 browser-harness --doctor` attempts `/json/version`.
- `browser-harness --doctor` performs no external network request by default.

Phase 0 implementation checklist:

- Add endpoint parser tests first.
- Rename constants and temp paths.
- Add `BH_CDP_WS` HTTP base resolution.
- Add stdin runner and remove normal update banner.
- Remove Browser Use hosted/profile strings.
- Run static string checks.
- Commit only after tests and static checks pass.

## Phase 1: CDP-Minimal Stealth Contract

Objective: delete browser-harness-created stealth leaks before adding provider docs or diagnostics.

Owned files:

- `daemon.py`
- `helpers.py`
- tests: new `test_daemon_cdp_policy.py`, new/expanded `test_helpers.py`

Required changes:

- In `Daemon.attach_first_page`, stop enabling `Page`, `DOM`, `Runtime`, and `Network`.
- In `Daemon.start`, keep event recording if needed, but delete title marker injection on load/dom events.
- In `Daemon.handle(meta=set_session)`, switch session only; do not enable `Page` and do not evaluate JS.
- Delete `helpers._mark_tab`.
- Remove marker cleanup and marker application from `helpers.switch_tab`.
- Ensure `helpers.new_tab` still creates a tab, attaches to it, navigates when needed, and returns the target id.
- Rewrite `helpers.page_info`:
  - first check pending native dialog,
  - use `Target.getTargetInfo` for URL/title/target id,
  - use `Page.getLayoutMetrics` for viewport and content dimensions,
  - return the same shape as much as possible: `{url, title, w, h, sx, sy, pw, ph}`,
  - do not call `Runtime.evaluate`.
- Add `page_info_js()` only if a JS fallback is still needed.
- Rewrite `wait_for_load` to avoid routine `Runtime.evaluate`.
  - preferred: enable `Page` inside the helper, observe `Page.loadEventFired`/`Page.lifecycleEvent`, and return on a quiet condition.
  - fallback: keep `wait_for_load_js()` as explicit non-stealth helper.
- Keep `js()` and DOM-specific helpers, but make their docstrings explicit about page execution.
- Move any domain enablement to the smallest helper that needs it.
- Never add `Console.enable`.

Implementation details:

- Fake-CDP tests should instantiate the daemon with a stub `send_raw` recorder instead of opening Chrome.
- Helper tests should patch `helpers.cdp` and assert method sequences.
- Static tests may scan for the title marker expression and automatic forbidden enables.
- Do not solve stealth by injecting JavaScript. If a helper needs JS, its name/docs must say so.

Concrete fake-CDP fixture:

```python
class FakeCDP:
    def __init__(self, responses=None):
        self.calls = []
        self.responses = responses or {}

    async def send_raw(self, method, params=None, session_id=None):
        self.calls.append((method, params or {}, session_id))
        if method in self.responses:
            response = self.responses[method]
            return response() if callable(response) else response
        if method == "Target.getTargets":
            return {"targetInfos": [{"targetId": "page-1", "type": "page", "url": "https://example.com"}]}
        if method == "Target.attachToTarget":
            return {"sessionId": "session-1"}
        if method == "Target.createTarget":
            return {"targetId": "page-new"}
        if method == "Target.getTargetInfo":
            return {"targetInfo": {"targetId": "page-1", "type": "page", "url": "https://example.com", "title": "Example"}}
        if method == "Page.getLayoutMetrics":
            return {
                "layoutViewport": {"clientWidth": 1280, "clientHeight": 720, "pageX": 0, "pageY": 0},
                "contentSize": {"width": 1280, "height": 1600},
            }
        return {}
```

Expected attach trace with an existing page:

```python
[
    ("Target.getTargets", {}, None),
    ("Target.attachToTarget", {"targetId": "page-1", "flatten": True}, None),
]
```

Expected attach trace with no page:

```python
[
    ("Target.getTargets", {}, None),
    ("Target.createTarget", {"url": "about:blank"}, None),
    ("Target.attachToTarget", {"targetId": "page-new", "flatten": True}, None),
]
```

Forbidden trace entries anywhere in default attach/session/page-info/tab-switch tests:

```python
{
    "Runtime.enable",
    "Console.enable",
    "DOM.enable",
    "Network.enable",
    "Runtime.evaluate",
}
```

Fake-CDP forbidden method list:

- `Runtime.enable`
- `Console.enable`
- `DOM.enable` on attach
- `Network.enable` on attach
- hidden `Runtime.evaluate` during attach/session switch/tab switch/page info/load wait

Tests:

- Fresh attach sends only `Target.getTargets` and `Target.attachToTarget` when a real page exists.
- Fresh attach may send `Target.createTarget` only when no real page exists.
- `meta=set_session` records no CDP domain enables and no JS evaluation.
- `switch_tab` sends `Target.activateTarget`, `Target.attachToTarget`, and daemon `set_session`; it sends no marker JS.
- `new_tab` works without marker JS.
- `page_info` sends `Target.getTargetInfo` and `Page.getLayoutMetrics`, not `Runtime.evaluate`.
- `wait_for_load` default path does not call `Runtime.evaluate`.
- `js()` tests continue to pass and explicitly cover wrapping behavior.

Acceptance:

- Tests fail if automatic `Runtime.enable` reappears.
- Tests fail if the green-circle title marker or marker cleanup expression reappears.
- Normal core helpers still work: `new_tab`, `goto_url`, `wait_for_load`, `page_info`, `capture_screenshot`, `click_at_xy`, `type_text`, `press_key`, `scroll`, `list_tabs`, `switch_tab`, `current_tab`, `ensure_real_tab`.
- The attach path is CDP-minimal and page-non-mutating.

Phase 1 implementation checklist:

- Add fake-CDP tests that encode the current forbidden method list.
- Delete marker injection from daemon event tap and session switch.
- Delete marker helpers and tab-switch mutation.
- Rewrite `page_info`.
- Split JS-based load/page-info behavior into explicit helper names only if still needed.
- Re-run the full existing helper tests so explicit `js()` behavior remains intact.

## Phase 2: Local Provider Contract And Recipes

Objective: make strong self-hosted browser runtimes easy to use through one endpoint contract, without embedding them.

Owned files:

- new `docs/local-cdp-providers.md`
- `install.md`
- `README.md` if present
- `admin.py` doctor endpoint details

Provider recipe rules:

- Every recipe ends with:
  - set `BH_CDP_WS`,
  - run `browser-harness --doctor`,
  - run a tiny local command such as `browser-harness -c "print(page_info())"`.
- No recipe includes a cloud API key.
- No recipe requires importing a provider SDK into browser-harness.
- Every Docker recipe binds CDP to `127.0.0.1` on the host.
- Every remote/self-hosted machine recipe requires `BH_CDP_ALLOW_REMOTE=1` and documents the risk.

Required provider sections:

1. Local Chrome or Edge
   - existing chrome://inspect flow,
   - optional remote-debugging-port flow,
   - explains that this is a normal browser, not a stealth browser.

2. CloakBrowser
   - preferred Chromium-shaped stealth endpoint,
   - use `cloakserve` or its documented CDP server mode,
   - bind host port to `127.0.0.1`,
   - pass the local DevTools HTTP base or browser websocket through `BH_CDP_WS`,
   - document per-seed/profile behavior as owned by CloakBrowser.

3. Browserless local Docker
   - local Docker endpoint pattern,
   - `/json/version` support,
   - loopback binding,
   - clear warning not to enable public unauthenticated CDP.

4. Steel local Docker
   - local container/session API as an endpoint producer,
   - browser-harness consumes only the returned local websocket/debug URL,
   - Steel session management remains outside core.

5. Kernel Chromium images
   - headful/headless isolated Chromium,
   - `/json/version` on port 9222,
   - optional local VNC/WebRTC viewing remains outside browser-harness.

6. Kameleo local API
   - local API on `localhost:5050`,
   - profile-specific Playwright CDP URL,
   - Kameleo owns fingerprint/profile lifecycle.

7. Camoufox and Clover Camoufox
   - document as engine-level stealth references, not current CDP providers,
   - current browser-harness is Chromium CDP-shaped,
   - any future support would be a separate non-CDP adapter decision.

Provider docs skeleton:

Each provider section should use this exact shape so users can compare options quickly:

```markdown
### Provider Name

Fit:
Local/self-hosted CDP endpoint type and why a user would choose it.

Start locally:
One or two commands, copied from the provider's own local/self-hosted docs and adjusted only to bind host CDP to 127.0.0.1.

Connect browser-harness:
export BH_CDP_WS=http://127.0.0.1:<port>
browser-harness --doctor
browser-harness -c "print(page_info())"

Notes:
- what the provider owns,
- what browser-harness owns,
- known stealth/security caveats.
```

Provider endpoint examples to verify while writing docs:

| Provider | Expected local endpoint shape | Browser-harness role |
| --- | --- | --- |
| Local Chrome/Edge | `ws://127.0.0.1:<port>/devtools/browser/<id>` from `DevToolsActivePort` | Discover and attach. |
| CloakBrowser | `http://127.0.0.1:9222` or browser websocket from `cloakserve` | Consume endpoint only. |
| Browserless Docker | `http://127.0.0.1:3000` or its websocket endpoint | Consume local Docker CDP service only. |
| Steel Docker | local session/debug websocket returned by Steel | Consume returned endpoint only; Steel owns session lifecycle. |
| Kernel images | `http://127.0.0.1:9222` | Consume isolated Chromium CDP endpoint only. |
| Kameleo | `ws://localhost:5050/playwright/<profile-id>` | Consume profile-specific local endpoint only. |
| Camoufox/Clover | Playwright/Juggler server, not Chromium CDP | Document as non-CDP reference only. |

Doctor endpoint details:

- source: `BH_CDP_WS`, DevToolsActivePort discovery, or unknown,
- resolved websocket URL,
- product/version from `/json/version` when available,
- first page target,
- target count,
- local/remote host classification,
- whether remote allowance was required,
- warning list.

Acceptance:

- Provider docs contain no cloud API key instructions.
- Provider docs do not tell users to sign up for hosted browser services.
- `browser-harness --doctor` can explain what endpoint it is attached to.
- No provider SDK is added to `pyproject.toml`.

Phase 2 implementation checklist:

- Create `docs/local-cdp-providers.md`.
- Add docs links from `install.md` and `README.md`.
- Add endpoint info to doctor output using the daemon metadata contract.
- Verify docs include no provider account signup, API key, or hosted browser requirement.
- Verify `pyproject.toml` dependencies are unchanged.

## Phase 3: Local Stealth Doctor

Objective: add diagnostics that catch browser-harness regressions and common endpoint mistakes while staying offline by default.

Owned files:

- `admin.py`
- `daemon.py` if endpoint metadata needs to be exposed
- `helpers.py` only if a diagnostic helper is needed
- tests: new/expanded `test_doctor.py`

Output contract:

Human output by default. JSON output with `--doctor --json`.

Exit codes:

- `0`: all checks pass, or only warnings are present.
- `1`: at least one check fails.
- `2`: doctor invocation is invalid, for example unsupported flags.

Warnings are not failures because remote-allowed self-hosted endpoints and weak local browser fingerprints may still be intentional. Failures are reserved for unsafe defaults, unreachable endpoints, missing daemon/browser state, or policy violations.

Suggested JSON shape:

```json
{
  "status": "pass",
  "checks": [
    {
      "id": "endpoint.loopback",
      "status": "pass",
      "detail": "127.0.0.1:9222",
      "fix": null
    }
  ]
}
```

Statuses:

- `pass`: verified good,
- `warn`: usable but risky or degraded,
- `fail`: browser-harness cannot safely proceed.

Default offline checks:

- endpoint reachable,
- endpoint loopback or explicitly allowed,
- `/json/version` resolves when using HTTP base,
- browser websocket URL exists,
- page target exists or can be created,
- attach path does not enable forbidden domains,
- normal page info does not use `Runtime.evaluate`,
- title marker is absent,
- normal command path does not call release/update network,
- installed files contain no active Browser Use cloud runtime references.

Stable check ids:

| Check id | Default status when bad | Evidence source |
| --- | --- | --- |
| `endpoint.present` | `fail` | endpoint resolver / daemon metadata |
| `endpoint.scheme` | `fail` | parsed `BH_CDP_WS` or resolved endpoint |
| `endpoint.loopback` | `fail` unless remote allowed | host validator |
| `endpoint.remote_allowed` | `warn` | `BH_CDP_ALLOW_REMOTE=1` |
| `endpoint.version` | `warn` | `/json/version` when HTTP base is available |
| `daemon.alive` | `fail` | Unix socket probe |
| `daemon.socket_permissions` | `fail` | socket mode should remain `0600` |
| `cdp.attach_minimal` | `fail` | fake-CDP policy probe or code-level behavior test |
| `cdp.no_console_enable` | `fail` | fake-CDP policy probe |
| `page.no_title_marker` | `fail` | static scan plus fake helper trace |
| `helpers.page_info_no_runtime` | `fail` | fake helper trace |
| `network.default_offline` | `fail` | mocked `urllib.request.urlopen` in tests |
| `strings.no_cloud_runtime` | `fail` | static scan of active files |

Diagnostic page checks:

- Use a local temporary HTML page when page-level checks are needed.
- If the doctor uses `Runtime.evaluate` to inspect `navigator.webdriver`, plugins, languages, WebGL, timezone, or screen metrics, label those checks as diagnostic JS.
- Do not confuse diagnostic JS with normal helper behavior.

Optional network checks:

- Only run with `--doctor --network`.
- External IP check is opt-in.
- WebRTC candidate/IP check is opt-in and clearly labeled.
- Compare public IP, WebRTC IP, locale, timezone, and proxy hints when available.
- Never call public fingerprint/bot-detection sites by default.

Tests:

- `--doctor --json` returns valid JSON with stable check ids.
- Default doctor does not call `urllib.request.urlopen` for public release/network checks.
- Endpoint failures map to `fail`.
- Remote endpoint without allowance maps to `fail`.
- Remote endpoint with allowance maps to `warn`.
- Fake forbidden CDP traffic maps to `fail`.
- Network checks only run when `--network` is present.
- Human output includes the same check ids as JSON output, or enough labels to map back to them.

Acceptance:

- Default doctor is local/offline.
- Doctor reports endpoint, CDP hygiene, and page-mutation hygiene.
- JSON output is stable enough for tests and future automation.
- Every warning/failure includes a local fix.

Phase 3 implementation checklist:

- Add a small `DoctorCheck` data shape only if plain dicts become hard to read.
- Keep check collection separate from printing so JSON and human output use the same results.
- Mock external network APIs in tests and assert they are not called by default.
- Add one fake endpoint fixture for each status: pass, warn, fail.
- Add one test for socket permissions if the platform supports Unix sockets.
- Keep optional network checks isolated behind `--network`.

## Phase 4: Optional Agent Utilities

Objective: borrow useful agent ergonomics only after the CDP-minimal contract is protected by tests.

Allowed utilities:

- Accessibility snapshot helper:
  - explicit function, e.g. `ax_snapshot()`,
  - uses `Accessibility.getFullAXTree`,
  - compact output with stable refs where possible,
  - not enabled on attach.
- Explicit trace capture:
  - opt-in screenshot timeline or CDP trace,
  - no always-on recorder,
  - artifacts written only when requested.
- Local provider discovery:
  - list known loopback DevTools endpoints,
  - no public network scanning,
  - no provider account discovery.
- Optional input humanization:
  - deterministic bounded mouse path/typing jitter,
  - disabled by default,
  - framed as interaction quality, not a full bot-detection solution.

Rejected utilities:

- queueing,
- dashboard,
- REST API server,
- database,
- Redis,
- MCP server,
- browser binary downloader,
- provider account manager,
- captcha workflow,
- proxy rotation service,
- JS fingerprint patch layer.

Acceptance:

- Core attach remains CDP-minimal after utilities exist.
- Utilities are opt-in and named clearly.
- No provider/platform dependency is added.

## Implementation Sequence

Use these as commit boundaries. A phase is not complete until its tests and acceptance checks pass.

1. Commit 1: Phase 0 naming, stdin CLI, offline defaults.
   - This closes the local-only command contract.
   - Verification: targeted unit tests plus static `rg` checks.

2. Commit 2: Phase 1 CDP-minimal attach and helper rewrite.
   - This closes the highest-value stealth gap.
   - Verification: fake-CDP tests plus targeted helper tests.

3. Commit 3: Phase 2 provider docs and endpoint detail in doctor.
   - This makes local providers usable without embedding them.
   - Verification: docs inspection, no SDK dependency, doctor endpoint tests.

4. Commit 4: Phase 3 local stealth doctor.
   - This makes regressions visible.
   - Verification: JSON schema tests, offline/no-network tests, fake pass/warn/fail checks.

5. Commit 5+: Phase 4 utilities, one utility per reviewable boundary.
   - Only start after Phases 0-3 are verified.

## Verification Matrix

| Boundary | Minimum automated checks | Manual/runtime checks | Replacement proof |
| --- | --- | --- | --- |
| Phase 0 | `uv run pytest test_run.py test_admin.py test_daemon.py` | Optional local `browser-harness --doctor` against Chrome | No `BU_*`, old `/tmp/bu-*`, Browser Use cloud/profile URL, or implicit update check in normal path. |
| Phase 1 | fake-CDP daemon tests, helper method-sequence tests, `test_js.py` | Optional live smoke: new tab, screenshot, click/key/page info | No automatic `Runtime.enable`, `Console.enable`, title marker, or hidden page mutation. |
| Phase 2 | docs link/static checks, dependency check, endpoint parser tests | Optional run with one local provider such as Chrome or Browserless | Local provider support is endpoint-only; no SDK or cloud API key. |
| Phase 3 | doctor JSON tests, no-network default test, fake endpoint pass/warn/fail tests | Optional `--doctor --network` only when explicitly requested | Doctor catches forbidden CDP and remote endpoint exposure. |
| Phase 4 | utility-specific unit tests plus Phase 1 regression tests | Utility runtime smoke if available | Utilities do not change default attach behavior. |

Standard commands after each implementation phase:

```bash
uv run pytest
git diff --check
rg "BU_CDP_WS|BU_NAME|/tmp/bu-|browser-use.com/profile|api.browser-use|cloud.browser-use" daemon.py admin.py run.py helpers.py SKILL.md install.md README.md pyproject.toml
rg "Runtime.enable|Console.enable" daemon.py helpers.py
```

The last `rg` command is not enough by itself because explicit docs/tests may mention forbidden methods. The real gate is the fake-CDP behavior tests.

## Risks And Decisions

| Risk | Decision |
| --- | --- |
| Removing the title marker loses visible user feedback. | Accept the break. Page mutation is worse. Use `current_tab()`, screenshots, and explicit terminal output instead. |
| Removing automatic domain enables may break helpers that assumed ready domains. | Fix helpers individually. Domains belong to explicit helpers, not attach. |
| `page_info` without JS may have less exact scroll data on some targets. | Use `Page.getLayoutMetrics` first. If exact JS fields are needed, expose `page_info_js()`. |
| Remote self-hosted CDP may be legitimate for a user-owned server. | Reject by default, allow only with `BH_CDP_ALLOW_REMOTE=1` and loud warnings. |
| Docker providers often bind inside a container to `0.0.0.0`. | Docs must bind the host port to `127.0.0.1`; doctor judges the user-visible endpoint. |
| Doctor fingerprint checks may require JS. | Keep them diagnostic-only and never use them as normal helper implementation. |
| Existing `BU_*` users break. | Intentional. The end-state is clearer and avoids legacy Browser Use naming. |
| GitHub update checks are useful. | Keep only behind explicit update commands or explicit doctor flags; no default hosted network call. |

## Explicit Non-Goals

- No Browser Use Cloud.
- No Browserbase Cloud.
- No Anchor Cloud.
- No Rebrowser Cloud.
- No Steel Cloud.
- No OnKernel Cloud.
- No Hyperbrowser Cloud.
- No hosted browser runtime of any kind.
- No captcha-solving service.
- No residential proxy purchasing or rotation service.
- No JavaScript stealth shims.
- No init-script fingerprint patching.
- No bundled browser binary download manager.
- No Browserless-style concurrency queue.
- No HeadlessX-style dashboard, API-key store, database, Redis worker, or remote MCP endpoint.
- No copying code from SSPL/commercial projects. They are architecture references unless a license review and explicit approval say otherwise.

## Completion Definition

This plan is complete only when every phase selected for implementation is verified against its acceptance checks.

For replacement/deletion items, completion additionally requires replacement proof:

- old `BU_*` runtime names removed,
- old Browser Use hosted/profile instructions removed,
- old `/tmp/bu-*` active runtime paths removed,
- default hosted network calls removed from normal execution and doctor,
- automatic `Runtime.enable` removed from attach,
- automatic `Console.enable` absent,
- title marker and hidden page mutation removed,
- local provider support implemented through endpoint docs/doctor only,
- no cloud provider SDK or runtime path added.

Anything implemented but not verified should be marked `implemented_unverified`, not complete.
