# Local CDP Providers

Browser Harness is a local CDP client. It does not manage provider accounts, browser fleets, queues, dashboards, captcha solving, or proxy rotation. Every provider below is used the same way: start a browser endpoint yourself, bind it to loopback when it runs on this machine, set `BH_CDP_WS`, and let browser-harness attach.

Remote CDP is browser control. Use `BH_CDP_ALLOW_REMOTE=1` only for a user-owned self-hosted endpoint that you intentionally expose on a private network.

## Common Connect Pattern

```bash
export BH_CDP_WS=http://127.0.0.1:9222
browser-harness --doctor
browser-harness -c "print(page_info())"
```

`BH_CDP_WS` accepts either a browser websocket URL such as `ws://127.0.0.1:9222/devtools/browser/<id>` or a DevTools HTTP base URL such as `http://127.0.0.1:9222`. HTTP bases are resolved through `/json/version`.

## Local Chrome Or Edge

Fit:
The default local browser. Use this for normal authenticated browsing, local testing, and tasks where your real profile is the desired state. This is not a stealth browser.

Start locally:
Use `browser-harness --setup` and follow the Chrome/Edge remote-debugging prompt if it appears. If you launch Chrome yourself, keep the debugging port loopback-only:

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-address=127.0.0.1 \
  --remote-debugging-port=9222
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
- Do not publish the Browserless port on `0.0.0.0` unless it is protected by your own network controls.

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
