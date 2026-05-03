# Local Browser Options And CDP Providers

Browser Harness is a local CDP client. It does not manage provider accounts,
browser fleets, queues, dashboards, captcha solving, or proxy rotation. Every
CDP provider below is used the same way: start a browser endpoint yourself,
bind it to loopback when it runs on this machine, set `BH_CDP_WS`, and let
browser-harness attach.

Remote CDP is browser control. Use `BH_CDP_ALLOW_REMOTE=1` only for a user-owned self-hosted endpoint that you intentionally expose on a private network.

Codex Browser Use is the exception in this document: it is a Codex MCP /
Node REPL browser surface, not a CDP endpoint. Use it from Codex when you want
the in-app browser or the current in-app tab; use the CDP providers below when
you want the `browser-harness` Python helpers and `BH_CDP_WS`.

## Common Connect Pattern

```bash
export BH_CDP_WS=http://127.0.0.1:9222
browser-harness --doctor
browser-harness -c "print(page_info())"
```

`BH_CDP_WS` accepts either a browser websocket URL such as `ws://127.0.0.1:9222/devtools/browser/<id>` or a DevTools HTTP base URL such as `http://127.0.0.1:9222`. HTTP bases are resolved through `/json/version`. `wss://` and `https://` endpoints are accepted for self-hosted TLS setups and follow the same loopback/remote-allow rules, but local loopback endpoints normally use `ws://` or `http://`.

## Provider Availability

Choose from what is actually available before acquiring a new backend:

| Backend | Availability expectation | Selection rule |
|---|---|---|
| Local Chrome/Edge | Usually already installed on developer machines | Default CDP backend for browser-harness helpers |
| Codex Browser Use | Only available inside Codex sessions with the Browser plugin and Node REPL `js` tool | Use for Codex in-app browser/current-tab work, not `BH_CDP_WS` |
| Lightpanda | Optional; may need a binary from upstream GitHub releases, the official install script, or Docker | Use only after install/serve and field capability proof |
| Self-hosted CDP services | User-provided local or explicitly allowed remote endpoint | Consume endpoint only; browser-harness does not manage provider lifecycle |

Do not install, download, or start an optional provider just because it is listed
here. If Chrome can answer the task, use Chrome. Acquire Lightpanda or another
provider only when the user requested that backend, Chrome is insufficient for a
declared reason, or the task is explicitly a backend comparison.

## Codex Browser Use / In-App Browser

Fit:
Codex's built-in browser surface. Use this when the task is specifically about
the Codex in-app browser, the current in-app tab, or local targets such as
`localhost`, `127.0.0.1`, `::1`, and `file://` URLs. It is also the right
surface when the user asks for `browser-use`.

Start locally:
No `BH_CDP_WS` endpoint is involved. Browser Use is exposed by the Codex MCP
runtime through the Node REPL `js` tool and the plugin's `browser-client.mjs`.
It may be unavailable outside Codex, or in Codex sessions where the Browser
plugin or Node REPL `js` tool is not exposed.

Connect from Codex:

```js
const { setupAtlasRuntime } =
  await import("<absolute browser-use plugin root>/scripts/browser-client.mjs");

await setupAtlasRuntime({ globals: globalThis, backend: "iab" });
await agent.browser.nameSession("🔎 browser task");
globalThis.tab = await agent.browser.tabs.selected() ?? await agent.browser.tabs.new();
```

Use the absolute path to the installed Browser Use plugin root; in Codex this is
the directory that contains `scripts/browser-client.mjs`.

Then use the installed surface:

```js
await tab.goto("http://localhost:3000");
console.log(await tab.playwright.domSnapshot());
await display(await tab.playwright.screenshot({ fullPage: false }));
```

Notes:

- Browser Use owns the Codex in-app browser connection and permission flow.
- `browser-harness` owns only CDP control through `BH_CDP_WS`; it cannot attach
  to Browser Use as a DevTools endpoint.
- If Browser Use is unavailable, use local Chrome/Edge through browser-harness
  for CDP tasks instead of trying to emulate the in-app-browser API.
- The useful API surface is `agent.browser.tabs.*`, `tab.goto/reload/back`,
  `tab.playwright.*` for DOM/locator work, `tab.cua.*` for coordinate actions,
  `tab.clipboard.*`, and `tab.dev.logs()`.
- Despite the runtime function name `setupAtlasRuntime`, this is the Codex
  in-app browser backend, not a direct controller for the desktop
  `/Applications/ChatGPT Atlas.app`.

## Local Chrome Or Edge

Fit:
The default local browser. Use this for normal authenticated browsing, local testing, and tasks where your real profile is the desired state. Chrome is the likely installed baseline on macOS and many developer machines. This is not a stealth browser.

Start locally:
Use `browser-harness --setup` and follow the Chrome/Edge remote-debugging prompt if it appears. If you launch Chrome yourself, keep the debugging port loopback-only:

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-address=127.0.0.1 \
  --remote-debugging-port=9222
```

On macOS, the setup flow can opt into keyboard-only consent for Chrome's native
remote-debugging dialog:

```bash
browser-harness --setup --accept-remote-debugging-dialog
```

For an agent-owned headful profile with no inspect-page prompt, launch visible
Chrome directly:

```bash
browser-harness --launch-profile /tmp/browser-harness-profile --port 9222
export BH_CDP_WS=http://127.0.0.1:9222
```

Connect browser-harness:

```bash
export BH_CDP_WS=http://127.0.0.1:9222
browser-harness --doctor
browser-harness -c "print(page_info())"
```

Notes:

- Chrome/Edge owns the browser profile, cookies, and fingerprint.
- Browser-harness owns only the CDP control layer.
- Do not expose port `9222` on public interfaces.

## CloakBrowser

Fit:
Best Chromium-shaped local stealth candidate. CloakBrowser owns source-level Chromium fingerprint behavior, profiles, SOCKS5/WebRTC/proxy alignment, and the `cloakserve` CDP multiplexer.

Start locally:

```bash
docker run -d --name cloak \
  -p 127.0.0.1:9222:9222 \
  cloakhq/cloakbrowser cloakserve
```

Connect browser-harness:

```bash
export BH_CDP_WS=http://127.0.0.1:9222
browser-harness --doctor
browser-harness -c "print(page_info())"
```

Notes:

- CloakBrowser owns fingerprint and profile lifecycle.
- Browser-harness consumes the local CDP endpoint only.
- If using CloakBrowser proxy flags, keep WebRTC, timezone, locale, and proxy settings consistent inside CloakBrowser.

## Browserless Local Docker

Fit:
Mature local Docker CDP service. Use it when you want a stable local browser service with a known CDP endpoint.

Start locally:

```bash
docker run --rm \
  -p 127.0.0.1:3000:3000 \
  ghcr.io/browserless/chromium
```

Connect browser-harness:

```bash
export BH_CDP_WS=ws://127.0.0.1:3000
browser-harness --doctor
browser-harness -c "print(page_info())"
```

Notes:

- Browserless owns browser process management.
- Browser-harness consumes the local websocket endpoint only.
- Keep the host binding on `127.0.0.1`; browser-harness rejects user-facing `0.0.0.0` CDP endpoints.

## Lightpanda

Fit:
Fast DOM and JavaScript extraction for sites that do not require Chrome's full rendering/fingerprint surface. Lightpanda is built from scratch for headless automation and has no graphical rendering engine, which is the source of its performance and also an important capability boundary.

Availability:
Lightpanda is optional. Check `command -v lightpanda` or use a known absolute
binary path before selecting it. If it is absent, obtain it intentionally from
the upstream Lightpanda GitHub releases/nightly builds, the official install
script, or Docker image; do not add Lightpanda as a hidden browser-harness
dependency.

Start locally:

```bash
lightpanda serve --host 127.0.0.1 --port 9222
```

Connect browser-harness:

```bash
export BH_CDP_WS=http://127.0.0.1:9222
browser-harness --doctor
browser-harness -c "print(page_info_js())"
```

Programmatic control:

```python
from lightpanda_control import LightpandaServer

with LightpandaServer("/path/to/lightpanda") as server:
    client = server.client
    print(client.send_raw("Browser.getVersion"))
    print(client.send_raw("Runtime.evaluate", {
        "expression": "document.body.innerText",
        "returnByValue": True,
    }))
```

`LightpandaCDP` is a tiny translation layer for Lightpanda's CDP shape. It
creates and attaches a target for page commands, routes `Page.*`, `Runtime.*`,
and `Network.*` through that target session, and leaves `Browser.*`,
`Target.*`, and `Storage.*` at browser scope.

Notes:

- Lightpanda is useful when the task needs HTML, DOM queries, and JavaScript execution without Chrome's memory cost.
- If Lightpanda is not installed and Chrome can satisfy the task, use Chrome
  and record Lightpanda as unavailable instead of downloading it mid-task.
- It is not a headful Chrome replacement for heavily protected sites. Domains that depend on GPU/WebGL/canvas/font/layout/plugin/profile signals can serve challenge shells even though CDP is connected successfully.
- Some cookie bulk APIs may be absent or return `NotImplemented`.
  `login_session.restore_cookies()` falls back from bulk setters to per-cookie
  `Network.setCookie`. Site-specific restore receipts belong in the relevant
  domain skill.
- Use `diagnose_url_capability()` to distinguish "backend connected" from
  "target content served."
- Use field-level contracts to distinguish "target content served" from
  "workflow data is present." Non-empty page text is not enough when the
  workflow needs specific links, prices, rows, buttons, downloads, or embedded
  payloads.
- A Lightpanda result should be canonical-record compatible with headful Chrome
  or another trusted source for the same context. If the fields differ, classify
  the Lightpanda result as `backend_capability_failed` for that source family
  and fall back instead of emitting a weaker dataset.
- `lightpanda_control.evaluate_field_contract()` and
  `wait_for_field_contract()` provide reusable named field gates for direct
  Lightpanda CDP tests.
- If a headful profile has already solved a protected domain, use `seed_browser_session(url)` then `http_get_browser_session(url)` to gather HTML/data, then pass the extracted results to Lightpanda-only workflows.
- Example: for `realestate.com.au`, observed Lightpanda behavior on 2026-04-27 was a Kasada/KPSDK challenge document with empty body text; the REA-specific workflow lives in `domain-skills/realestate-com-au/scraping.md`.

## Steel Local Docker

Fit:
Local agent-oriented browser server. Use it when you want Steel to own session lifecycle and browser-harness to attach to the returned local websocket URL.

Start locally:

```bash
docker run --rm \
  -p 127.0.0.1:3000:3000 \
  -p 127.0.0.1:9223:9223 \
  ghcr.io/steel-dev/steel-browser
```

Create a local session and export its websocket URL:

```bash
SESSION_JSON=$(curl -sS -X POST http://127.0.0.1:3000/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{}')

export BH_CDP_WS=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["websocketUrl"])' <<<"$SESSION_JSON")
```

Connect browser-harness:

```bash
browser-harness --doctor
browser-harness -c "print(page_info())"
```

Notes:

- Steel owns sessions, live view, logs, and browser process lifecycle.
- Browser-harness consumes only the returned local CDP websocket.
- Do not add Steel SDKs or session state to browser-harness core.

## Kernel Chromium Images

Fit:
Isolated local Chromium in Docker with headful/headless recipes, optional local GUI viewing, and restart-aware CDP proxying.

Start locally:

```bash
cd images/chromium-headful
IMAGE=kernel-docker ./build-docker.sh
IMAGE=kernel-docker ENABLE_WEBRTC=true ./run-docker.sh
```

Connect browser-harness:

```bash
export BH_CDP_WS=http://127.0.0.1:9222
browser-harness --doctor
browser-harness -c "print(page_info())"
```

Notes:

- Kernel owns the container, display server, optional live view, and recording sidecars.
- Browser-harness consumes the CDP endpoint only.
- If you wrap the Docker run command yourself, bind host port `9222` to `127.0.0.1`.

## Kameleo Local API

Fit:
Local/on-prem profile lifecycle and fingerprint management. Use it when Kameleo owns profile creation and browser-harness attaches to the local profile-specific CDP endpoint.

Start locally:
Start the Kameleo local API so it listens on `http://localhost:5050`, then create and start a profile with Kameleo's own local tooling.

Connect browser-harness:

```bash
export BH_CDP_WS=ws://localhost:5050/playwright/<profile-id>
browser-harness --doctor
browser-harness -c "print(page_info())"
```

Notes:

- Kameleo owns fingerprint selection, profile lifecycle, and proxy consistency.
- Browser-harness consumes the profile-specific Playwright CDP endpoint only.
- Do not add Kameleo SDKs or profile lifecycle code to browser-harness core.

## Camoufox And Clover Camoufox

Fit:
Strong engine-level stealth references with Firefox/Juggler/Playwright shape. They are not Chromium CDP drop-ins for the current browser-harness core.

Start locally:
Use their own Playwright-compatible launch/server workflow.

Connect browser-harness:
No direct browser-harness CDP recipe exists today.

Notes:

- Camoufox/Clover own engine-level fingerprinting and Playwright/Juggler isolation.
- Browser-harness remains Chromium CDP-shaped.
- Any future support should be a separate non-CDP adapter decision, not a hidden dependency in core.
