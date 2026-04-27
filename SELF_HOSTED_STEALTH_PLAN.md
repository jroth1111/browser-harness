# Self-Hosted Stealth Improvement Plan

Date: 2026-04-27

Scope: improve `browser-harness` as a local, self-hosted CDP control layer. Do not add cloud browser providers, hosted API dependencies, captcha-solving services, residential proxy services, dashboards, queues, or MCP/server platform features to core.

Reference repos were cloned under `/tmp/browser-harness-reference-repos` and inspected at the revisions listed below.

## Source Inventory

| Reference | Revision | What Browser Harness Should Learn |
| --- | --- | --- |
| `browser-use/benchmark` | `702bf09` | Stealth Bench V1 distinguishes local headful/headless from remote provider adapters. The local adapters are intentionally tiny (`HEADLESS = False/True`), which supports keeping browser-harness local and thin. |
| `steel-dev/steel-browser` | `d6b15d5` (`v0.5.3-beta`) | Strong local session API shape: health, session metadata, debugger URL, live details, structured logs. Too large for core, but useful for doctor output and optional local provider docs. |
| `browserless/browserless` | `b806de6d` (`v2.47.0`) | Mature Docker/CDP service pattern: `/json/version`, websocket proxying, health/pressure checks, local Docker quickstart. Queue and REST service features stay out of browser-harness core. |
| `kernel/kernel-images` | `c058cb0` | Best headful isolated Chromium container pattern: supervised Xorg/Mutter/Chromium, CDP proxy that tracks browser restarts, noVNC/WebRTC view, recording sidecar. Browser-harness should support connecting to it, not embed it. |
| `browserbase/stagehand` | `1fe71b8c` (`v2.2.0`) | Local controller-layer ideas: local CDP URL support, persistent user data dir, action history/cache, lazy CDP session access. Browserbase API paths are out of scope. |
| `hyperbrowserai/HyperAgent` | `336a906` (`v1.0.0`) | Agent-side patterns: local Playwright default, CDP action toggle, accessibility tree snapshots, network-idle wait stats. Its Runtime-heavy paths are a caution for stealth. |
| `daijro/camoufox` | `76c30ac` (`v146-hardware`) | Engine-level fingerprinting and Juggler isolation beat JavaScript stealth. Not a direct Chromium CDP drop-in, but it sets the standard: do not expose automation through page-visible shims. |
| `CloverLabsAI/camoufox` | `61430df` | Camoufox fork with AI-agent framing and per-context/hardware spoofing work. Same lesson as Camoufox: engine-level consistency, not controller-layer JS patches. |
| `CloakHQ/CloakBrowser` | `4459f66` (`v0.3.25`) | Best Chromium-shaped local candidate: source-level fingerprint patches, `cloakserve` local CDP multiplexer, per-seed profiles, SOCKS5/WebRTC/proxy alignment, loopback CDP guidance. |
| `Kaliiiiiiiiii-Vinyzu/patchright` | `748e09d` (`v1.59.x`) | Highest-value leak list for Playwright/CDP: avoid automatic `Runtime.enable`, `Console.enable`, automation flags, closed-shadow-root assumptions. Directly relevant to browser-harness attach behavior. |
| `rebrowser/rebrowser-patches` | `6373894` (`1.0.19`) | Detailed `Runtime.Enable` leak research and mitigation modes. Strong warning that less JS manipulation is better. |
| `kameleo-io/kameleo` | `0f76e3a` (`4.4.1`) | Local API/profile lifecycle model: localhost API, fingerprint search, profile start, Playwright CDP endpoint, blocked switch policy, proxy/fingerprint consistency. Architecture reference, not a dependency target. |
| `jo-inc/camofox-browser` | `923b7be` (`v1.7.4`) | Agent server patterns: stable element refs, accessibility snapshots, per-tab locks, session persistence, structured logs, trace capture, VNC login. Too broad for core; good optional helper inspiration. |
| `saifyxpro/HeadlessX` | `af2bd4b` (`v2.1.2`) | Full platform reference: CLI bootstrap/doctor, Docker/self-host modes, persistent shared browser profile, queues, dashboard, MCP. Useful operationally, but mostly explicit non-scope. |
| `techinz/browsers-benchmark` | `7f14d54` | Best local diagnostic inspiration: browser data targets for CreepJS, IP/WebRTC, reCAPTCHA score, screenshots, proxy fallback accounting, and per-engine result reports. |

## Current Browser Harness Gaps

These are the highest-value issues visible in the current browser-harness code.

1. Eager CDP domains create stealth leaks.
   `daemon.py` enables `Page`, `DOM`, `Runtime`, and `Network` on attach. Patchright and rebrowser both identify automatic `Runtime.enable` as one of the most important page-observable leaks.

2. The tab title marker mutates the page.
   `daemon.py` and `helpers.py` inject a green-circle title prefix through `Runtime.evaluate` on load, session switch, and tab switch. That is visible to the page, visible to users, and inconsistent with the no-JS-shim direction.

3. The endpoint variable still carries old Browser Use naming.
   `daemon.py` reads `BU_CDP_WS`. For a local-only browser-harness, the endpoint contract should be named `BH_CDP_WS` and should accept only local/self-hosted endpoints.

4. CLI documentation and behavior disagree.
   `run.py` advertises heredoc/stdin usage, but the command currently only accepts `-c`. Either the stdin runner should exist or the docs should be narrowed. The skill workflow expects heredoc support.

5. Doctor is too shallow.
   Current `--doctor` mostly checks whether Chrome/daemon are alive. It does not validate endpoint locality, `/json/version`, browser product/version, page target availability, public binding risk, headless/headful indicators, CDP domain policy, or page mutation risk.

6. Browser Use profile-install messaging remains in local profile discovery.
   `admin.py` still points users at a Browser Use profile installer URL when `profile-use` is absent. That is not a cloud runtime path, but it should be removed or replaced with local browser-harness setup guidance to keep the project fully self-contained.

7. No regression tests protect the local-only and CDP-minimal contract.
   There should be tests proving no cloud endpoints, no automatic `Runtime.enable`, no title-marker injection, and correct `BH_CDP_WS` resolution.

## End-State Design

Browser-harness should be a small, local CDP control tool with a strict boundary:

- It attaches to an already-running local/self-hosted browser endpoint.
- It does not launch, download, or manage stealth browser binaries in core.
- It does not depend on cloud browser APIs or hosted browser providers.
- It prefers engine-level stealth from the chosen browser runtime, such as CloakBrowser, Kameleo, Kernel images, or plain local Chrome, over controller-layer spoofing.
- It sends the minimum CDP traffic required for each helper.
- It does not mutate the page by default.
- It treats `js()` as an explicit power tool, not as a hidden implementation detail for normal operations.
- It documents provider recipes as "bring your own local endpoint", not as embedded provider integrations.

## Phase 0: Local-Only Cleanup And CLI Correctness

Objective: remove old naming and make the local command surface coherent.

Changes:

- Replace `BU_CDP_WS` with `BH_CDP_WS`.
- Support both websocket URLs and DevTools HTTP base URLs in `BH_CDP_WS`:
  - `ws://127.0.0.1:9222/devtools/browser/...`
  - `http://127.0.0.1:9222` resolved through `/json/version`
- Reject or loudly warn on non-loopback CDP endpoints unless an explicit unsafe override is set.
- Implement stdin/heredoc execution in `run.py`, or remove heredoc examples everywhere. Preferred end-state: implement stdin because the skill workflow already depends on it.
- Replace the `profile-use` missing dependency message with browser-harness local setup guidance.
- Remove any Browser Use cloud-hosted URLs or API terminology from browser-harness docs and command output.

Acceptance:

- `rg "api.browser-use|cloud.browser-use|browser-use.com/profile|BU_CDP_WS"` returns no active runtime/docs references.
- `BH_CDP_WS=http://127.0.0.1:9222 browser-harness --doctor` resolves `/json/version`.
- `printf 'print(page_info())\n' | browser-harness` runs through the pre-imported helpers.
- `browser-harness -c "print(page_info())"` still works if kept as a supported command.
- Tests cover stdin, `-c`, `BH_CDP_WS`, HTTP endpoint resolution, and public endpoint rejection.

## Phase 1: CDP-Minimal Stealth Contract

Objective: remove the browser-harness-controlled leaks before adding any new features.

Changes:

- Stop enabling `Runtime` on attach.
- Stop enabling `DOM` and `Network` on attach. Enable domains only inside helpers that actually need them.
- Keep `Page.enable` only if dialog/load event handling needs it; otherwise make event subscriptions opt-in.
- Never enable `Console` in core.
- Delete the default title marker and all hidden `Runtime.evaluate` calls that exist only to mark tabs.
- Make `page_info()` use non-JS CDP where possible:
  - `Target.getTargetInfo` for URL/title when sufficient.
  - `Page.getLayoutMetrics` for viewport, scroll, and page dimensions.
  - Keep a clearly named `page_info_js()` only if a JS fallback is unavoidable.
- Keep `js()` available, but document it as explicit non-stealth page execution.
- Add a small CDP policy table near the helpers:
  - safe-by-default: `Target.*`, `Page.captureScreenshot`, `Input.dispatch*`, selected `Page.*`
  - explicit-use: `Runtime.evaluate`, `DOM.*`, `Network.*`, `Accessibility.*`
  - forbidden-by-default: automatic `Runtime.enable`, `Console.enable`, hidden init scripts, page-visible markers
- Add fake-CDP tests that fail if attach, tab switching, or `page_info()` sends `Runtime.enable` or the title-marker expression.

Acceptance:

- Fresh daemon attach sends no `Runtime.enable`, `DOM.enable`, `Network.enable`, or `Console.enable`.
- Switching tabs sends no title mutation and no marker cleanup.
- `page_info()` works without `Runtime.evaluate` on normal Chrome targets.
- Existing core helpers still work: navigate, screenshot, coordinate click, text entry, key press, scroll, tab list/switch/new tab.
- Tests assert the above CDP methods are absent from the attach path.

## Phase 2: Local Provider Contract And Recipes

Objective: make self-hosted browser endpoints easy to use without embedding provider SDKs.

Changes:

- Add `docs/local-cdp-providers.md` with explicit recipes for:
  - Local Chrome via `chrome://inspect/#remote-debugging`.
  - CloakBrowser `cloakserve` bound to `127.0.0.1`.
  - Browserless local Docker, bound to `127.0.0.1`.
  - Steel local Docker/session API, using the returned local websocket URL.
  - Kernel Chromium headful/headless Docker, using `/json/version` on port `9222`.
  - Kameleo local API on `localhost:5050` and its profile-specific Playwright CDP URL.
- Document Camoufox and Clover Camoufox as non-CDP references:
  - excellent engine-level stealth,
  - not a direct Chromium CDP endpoint for current browser-harness,
  - possible future Playwright/Juggler sidecar only if browser-harness intentionally grows a non-CDP adapter.
- Add provider endpoint diagnostics to `--doctor`:
  - endpoint source: discovered Chrome profile, `BH_CDP_WS`, or DevTools HTTP base
  - product/version from `/json/version`
  - websocket URL shape
  - target count and first real page
  - local bind check
  - obvious headless/headful signals when available

Acceptance:

- Each documented provider recipe ends with the same browser-harness command shape: set `BH_CDP_WS`, then run `browser-harness --doctor`.
- Provider docs contain no cloud API key instructions.
- Doctor output clearly marks remote/public CDP endpoints as unsafe.
- No provider SDK is imported by browser-harness core.

## Phase 3: Local Stealth Doctor

Objective: add a local diagnostic suite that catches browser-harness regressions and common endpoint misconfiguration.

Doctor checks:

- CDP endpoint:
  - reachable,
  - loopback-bound,
  - `/json/version` available for HTTP endpoints,
  - browser websocket URL is usable,
  - no public host unless explicitly allowed.
- Harness CDP hygiene:
  - attach path does not enable `Runtime`,
  - attach path does not enable `Console`,
  - no default page mutation/title marker,
  - `page_info()` uses non-JS CDP.
- Browser automation signals:
  - `navigator.webdriver`,
  - headless user-agent strings,
  - plugin/mime/language presence,
  - screen/viewport consistency,
  - timezone/locale/geolocation consistency,
  - WebGL renderer availability.
- Network/proxy consistency:
  - optional external IP check only with `--doctor --network`,
  - optional WebRTC candidate check only with explicit user opt-in,
  - compare public IP, WebRTC IP, timezone, locale, and proxy configuration when available.
- Output format:
  - human text by default,
  - `--json` for machine-readable pass/warn/fail results,
  - every warning includes a concrete local fix.

Implementation notes:

- Keep the default doctor local and offline.
- Do not call public fingerprinting sites by default.
- Use temporary local diagnostic pages for CDP/page-mutation checks.
- Treat any `Runtime.evaluate` used by doctor itself as diagnostic-only and isolate it from normal helper behavior.

Acceptance:

- `browser-harness --doctor --json` returns structured checks.
- Default doctor performs no external network requests.
- `--doctor --network` is the only path that calls external IP/WebRTC diagnostics.
- A fake browser endpoint test can force pass/warn/fail outcomes.

## Phase 4: Optional Agent Utilities

Objective: selectively borrow agent ergonomics without turning browser-harness into a platform.

Candidate utilities:

- Accessibility snapshot helper:
  - use `Accessibility.getFullAXTree` and optional DOM backend IDs,
  - return compact text plus stable refs,
  - do not run by default on attach.
- Explicit trace capture:
  - opt-in session trace or screenshot timeline,
  - no always-on recording sidecar.
- Local provider discovery:
  - list nearby DevTools endpoints on loopback,
  - never scan public networks.
- Optional input humanization:
  - deterministic, bounded motion path for `click_at_xy` and typing,
  - disabled by default,
  - intended for interaction quality rather than pretending to solve full behavioral detection.

Acceptance:

- Utilities are opt-in.
- Core attach remains CDP-minimal after utilities are installed.
- No queue, dashboard, persistent server API, MCP endpoint, or provider account layer is introduced.

## Explicit Non-Goals

- No Browser Use Cloud, Browserbase Cloud, Anchor Cloud, Rebrowser Cloud, Steel Cloud, OnKernel Cloud, or any other hosted browser runtime in browser-harness core.
- No captcha-solving service integration.
- No residential proxy purchasing or proxy rotation service integration.
- No JavaScript stealth shims or init-script fingerprint patching.
- No bundled browser binary download manager in core.
- No browserless-style concurrency queue in core.
- No HeadlessX-style dashboard, API-key store, database, Redis worker, or remote MCP endpoint in core.
- No copying code from SSPL/commercial projects. Browserless, Kameleo, and other projects are architecture references only unless their license allows reuse and the dependency is explicitly approved.

## Implementation Order

1. Phase 0 and Phase 1 together. The environment name, CLI runner, and CDP leak fixes are the highest-value work and easiest to verify.
2. Phase 2 docs and endpoint doctor. This makes CloakBrowser, Browserless, Steel, Kernel, and Kameleo usable through one local contract.
3. Phase 3 stealth doctor. This prevents regressions after the attach path is fixed.
4. Phase 4 optional utilities only after the CDP-minimal contract is protected by tests.

## Verification Ledger For Future Implementation

Each implementation phase should record:

- implementation evidence: changed files and relevant functions,
- verification method: automated, manual runtime, inspection, or mixed,
- verification evidence: exact commands and pass/fail summaries,
- replacement proof: old Browser Use naming, cloud paths, page mutations, or eager CDP enables removed from active runtime behavior,
- residual gap: any helper that still requires explicit JS or domain enablement.

Completion is only valid when all scoped phase acceptance checks pass and legacy cloud-hosted or page-mutating runtime paths no longer define browser-harness behavior.
