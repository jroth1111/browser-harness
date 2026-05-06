---
name: browser
description: Direct browser control via CDP. Use when the user wants to automate, scrape, test, or interact with web pages. Connects to the user's already-running Chrome.
---

# browser-harness

Direct browser control via CDP. For task-specific edits, use `agent-workspace/agent_helpers.py`. For setup, install, or connection problems, read install.md.

Domain skills (community-contributed per-site playbooks under `domain-skills/`) are off by default. Set `BH_DOMAIN_SKILLS=1` to enable them; see the bottom section.

## Usage

```bash
browser-harness -c '
new_tab("https://docs.browser-use.com")
wait_for_load()
print(page_info())
'
```

- Invoke as browser-harness — it's on $PATH. No cd, no uv run.
- First navigation is new_tab(url), not goto_url(url) — goto runs in the user's active tab and clobbers their work.
- On macOS, `browser-harness --setup --accept-remote-debugging-dialog` can opt into keyboard-only approval for Chrome's remote-debugging consent dialog.
- `browser-harness --launch-profile PATH --port 9222` launches a visible agent-owned Chrome profile with loopback CDP when you need a fresh profile/process.

## Cold-Start Router

Match your task to one row. Open the file in "Go to" — that's your action file.

| Task pattern | Go to | When to escalate |
|---|---|---|
| Install / connect / repair | `install.md` | — |
| Click, screenshot, scroll, type on current page | Playbook below (no file needed) | `interaction-skills/ui-mechanics.md` only for hidden/0×0 targets, iframes, shadow DOM, file uploads |
| Choose backend or test capability for a URL | `interaction-skills/backend-capability.md` | `interaction-skills/cross-domain-control-flow.md` when the task spans 2+ sites, auth states, or source families |
| Site returns 403 / bot detection / WAF block | `interaction-skills/waf-bypass.md` | Diagnose, authorized recovery, or stop |
| CDP path detected or Turnstile unsolvable | `interaction-skills/stealth-browser.md` | `interaction-skills/waf-bypass.md` for diagnosis first |
| Tab control, connection issues, stale tabs | `interaction-skills/tabs.md` | `interaction-skills/connection.md` when `ensure_real_tab()` or `browser-harness --doctor` fails |
| Search products across marketplaces | `interaction-skills/product-search.md` | `interaction-skills/marketplace-search.md` for cross-platform searches spanning 2+ sites |
| Auth wall, login, session reuse | `interaction-skills/session-continuity.md` | `interaction-skills/cookies.md` for cookie extraction/setting mechanics |
| Browser dialog (alert/confirm/prompt) | `interaction-skills/dialogs.md` | — |
| Render data as HTML table/explorer | `interaction-skills/data-display.md` | — |
| Build a scraper for a new site | `domain-skills/README.md` → Creating a New Domain Skill | `interaction-skills/extraction-coverage.md` for selector verification and four-state extraction |
| Audit site APIs / find structured backends | `interaction-skills/api-schema-audit.md` | `interaction-skills/data-source-exploration.md` for source exploration workflow |
| Capture / inspect browser network traffic | NetworkCapture class below | `interaction-skills/api-schema-audit.md` |
| Replay captured requests as plain HTTP | `replay_endpoints()` below | `interaction-skills/api-schema-audit.md` |
| Track crawl completeness metrics | `interaction-skills/coverage-accounting.md` | `interaction-skills/extraction-coverage.md` for field-level coverage |
| Extract data from fetched HTML | `response.py` Response class via `fetch()` | `interaction-skills/data-source-exploration.md` for source strategy |
| Work with a known site (see list below) | `domain-skills/<site>/overview.md` or first .md | `interaction-skills/data-source-exploration.md` if the domain skill lacks the field you need |
| Dating platforms (Tinder, Hinge, Feeld) | `domain-skills/dating/overview.md` | `domain-skills/dating/safety.md` for consent, rate limits, anti-detection |
| Food delivery (Uber Eats, DoorDash) | `domain-skills/food-delivery/overview.md` | `domain-skills/food-delivery/safety.md` for order consent gates, rate limits |
| Promote learned rule into a skill | `interaction-skills/empirical-learning-gate.md` | — |
| Clean up or reorganize a skill | `interaction-skills/cross-domain-control-flow.md` | — |

If nothing matches: scan `domain-skills/` with `rg --files domain-skills/<site>`, or read `interaction-skills/README.md` for the full mechanic index.

## Playbook: What actually works

- Screenshots first: use `capture_screenshot()` to understand the current page quickly, find visible targets, and decide whether you need a click, a selector, or more navigation.
- Clicking: capture_screenshot() → read the pixel off the image → click_at_xy(x, y) → capture_screenshot() to verify. Suppress the Playwright-habit reflex of "locate first, then click" — no getBoundingClientRect, no selector hunt. Drop to DOM only when the target has no visible geometry (hidden input, 0×0 node). Hit-testing happens in Chrome's browser process, so clicks go through iframes / shadow DOM / cross-origin without extra work.
- Bulk HTTP: http_get(url) + ThreadPoolExecutor. No browser for static pages (249 Netflix pages in 2.8s). Automatically uses the attached browser's real User-Agent.
- After goto: `wait_for_content()` is the default — it polls for content AND detects blocks. Prefer it over `wait_for_load()` + fixed delay for any page where you'll run extraction. `wait_for_load()` is fine when you only need the load event (clicking buttons, checking URL redirects).
- Block detection: `wait_for_content()` returns `{ok, reason, text, html, block}`. If `block` is true or `ok` is false, the page is inaccessible — emit `__UNOBSERVABLE__` for extraction fields, don't run extraction JS on a challenge page. See `interaction-skills/extraction-coverage.md` for the full readiness sequence.
- Browser-session HTTP: after a real browser profile has passed a site challenge, `http_get_browser_session(url)` fetches same-domain pages with that browser's user agent and matching cookies; pair it with the domain's parser or embedded-data extractor.
- Robust solved sessions: `seed_browser_session(url)` verifies a headful/profile session, then use `http_get_browser_session(url)` to fetch with the seeded cookies.
- Provider availability: Chrome/Edge is the likely installed CDP baseline. Browser Use exists only inside Codex sessions with the Browser plugin and Node REPL `js`; Lightpanda is optional and may need intentional installation from upstream before use. Do not download optional providers unless the task explicitly needs that backend.
- Headless/backend triage: `diagnose_url_capability(url)` reports backend kind, challenge block state, and recommendation. Use it before spending time on selectors when Lightpanda/headless returns blank content.
- Wrong/stale tab: ensure_real_tab(). Use it when the current tab is stale or internal; the daemon also auto-recovers from stale sessions on the next call.
- DOM reads: use js(...) for inspection and extraction when the screenshot shows that coordinates are the wrong tool.
- Iframe sites (Azure blades, Salesforce): click_at_xy(x, y) passes through; only drop to iframe DOM work when coordinate clicks are the wrong tool.
- Auth wall: redirected to login → stop and ask the user. Don't type credentials from screenshots.
- Raw CDP for anything helpers don't cover: cdp("Domain.method", params).
- Structured fetching: `fetch(url)` returns a `Response` with `.css(selector)`, `.css_text(selector)`, `.xpath(expr)`, `.text`, `.html`, `.next_data()` (Next.js JSON), `.json_ld(type)` (schema.org blocks), `.embedded_json(var)` (window.VAR assignments). Use `source="http"` for static pages, `source="session"` after seeding, `source="browser"` for JS-required pages, `source="auto"` (default) to cascade. The auto cascade also attempts Turnstile solving when Cloudflare blocks the browser path.
- Cloudflare Turnstile: when `wait_for_content()` reports a blocked page on a Cloudflare site, try `detect_turnstile()` → `solve_turnstile()`. Requires a visible browser. Handles non-interactive, interactive, and embedded challenge types.
- Resource blocking: `block_resources()` blocks ad domains via `Network.setBlockedURLs` and optionally blocks resource types (image, font, etc.) via `Fetch.enable`. Call after navigation.
- Network traffic capture: `NetworkCapture()` instruments CDP Network events. `start()` before navigation, `poll()` after to drain events, `endpoints()` for deduped URLs, `responses_for(pattern)` for full request/response pairs. Use `redacted_entries()` / `redacted_responses_for(pattern)` for receipts. Opt-in body capture with `capture_bodies=True`; captured bodies are bounded.
- URL clustering: `url_cluster(urls)` normalizes path segments (numbers → `{id}`, UUIDs → `{uuid}`) and groups URLs by pattern for endpoint discovery.
- API discovery: `discover_api_endpoints(url)` fetches a page's JS assets and extracts fetch/axios/XHR URL patterns without running the browser.
- Request replay: `replay_endpoints(capture)` re-issues captured requests as plain HTTP and compares status/content-type. Promotes browser-discovered APIs to fast HTTP calls.
- Crawl persistence: `state.save("path.json")` and `CrawlState.load("path.json")` serialize/deserialize CrawlState to JSON for resumable crawls.
- Safety limits: `SafetyGate(max_requests=500, max_seconds=300)` enforces crawl budgets. Check `gate.ok()` before each request, call `gate.record(status)` after. Raises on limit hit with `raise_on_fail=True`.
- Google referrer trick: `navigate_via_google(url)` opens Google first, then redirects to the target. Some WAF systems treat search-engine referrals as organic traffic.
- Block detection: `detect_block_page()` now identifies Kasada, Akamai, PerimeterX, Imperva, and generic WAF challenge shells (not just Kasada).

## Search domain-skills/ first

Before inventing a new approach, check if a domain skill exists. A site is
"known" when it has a folder under `domain-skills/<site>/`:

    rg --files domain-skills/<site>

Rich domain bundles (read overview.md first):
- `airbnb/` — host intelligence, comp analysis, pricing
- `dating/` — automated dating pipeline (Tinder, Hinge, Feeld), user interview, rubric scoring, swipe/message automation
- `food-delivery/` — restaurant browsing, menu extraction, order placement, delivery tracking, cross-platform price comparison (Uber Eats, DoorDash)
- `youtube/` — extraction, playlists, channel workflows
- `ai-chat-archive/` — multi-provider chat export

Multi-file site skills with scripts:
- `ebay/` — batch search orchestrator, URL generation, product classification
- `aliexpress/` — plan/extract/merge search pipeline
- `g2g/` — 4-wave exhaustive crawl, coverage accounting
- `z2u/` — exhaustive product search, 3-level crawl

Single-file domains: `amazon/`, `reddit/`, `spotify/`, and 70+ others.
Full list: `find domain-skills -mindepth 1 -maxdepth 1 -type d | sort`

## Contribute back

If you learned anything non-obvious about a site, update the domain skill before
finishing. Default to contributing.

Capture: URL patterns, private APIs and payload shape, stable selectors
(data-*, aria-*, role), site structure (containers, items per page, framework,
where state lives), framework/interaction quirks, waits and why they're needed,
traps and selectors that *don't* work.

Do not write: raw pixel coordinates (describe how to locate, not where it was),
run narration or step-by-step of your specific task, secrets/cookies/session
tokens/user-specific state (domain-skills/ is shared and public).

For the empirical learning gate and skill update rules, see
`docs/contributing-guide.md`.

## Tool call shape

```bash
browser-harness -c '
# any python. helpers pre-imported. daemon auto-starts.
'
```

run.py calls ensure_daemon() before exec — you never start/stop manually unless you want to.

### Remote browsers

Use remote for parallel sub-agents (each gets its own isolated browser via a distinct BH_NAME) or on a headless server. BROWSER_USE_API_KEY must be set. start_remote_daemon, list_cloud_profiles, list_local_profiles, sync_local_profile are pre-imported.

```bash
browser-harness -c '
start_remote_daemon("work")                               # default — clean browser, no profile
# start_remote_daemon("work", profileName="my-work")      # reuse a cloud profile (already logged in)
# start_remote_daemon("work", profileId="<uuid>")         # same, but by UUID
# start_remote_daemon("work", proxyCountryCode="de", timeout=120)   # DE proxy, 2-hour timeout
# start_remote_daemon("work", proxyCountryCode=None)      # disable the Browser Use proxy
'

BH_NAME=work browser-harness -c '
new_tab("https://example.com")
print(page_info())
'
```

start_remote_daemon prints liveUrl and auto-opens it in the local browser (if a GUI is detected) so the user can watch along. Headless servers print only — share the URL with the user. The daemon PATCHes the cloud browser to stop on shutdown, which persists profile state. Running remote daemons bill until timeout.

Profiles (cookies-only login state) live in interaction-skills/profile-sync.md — covers list_cloud_profiles(), the chat-driven "which profile?" pattern, and sync_local_profile() for uploading a local Chrome profile.

## Interaction skills

If you start struggling with a specific mechanic while navigating, look in interaction-skills/ for helpers. They cover reusable UI mechanics like dialogs, tabs, dropdowns, iframes, and uploads. The available interaction skills are:
- connection.md
- cookies.md
- cross-origin-iframes.md
- dialogs.md
- downloads.md
- drag-and-drop.md
- dropdowns.md
- iframes.md
- network-requests.md
- print-as-pdf.md
- profile-sync.md
- screenshots.md
- scrolling.md
- shadow-dom.md
- tabs.md
- uploads.md
- viewport.md

## What actually works

- Screenshots first: use capture_screenshot() to understand the current page quickly, find visible targets, and decide whether you need a click, a selector, or more navigation.
- Clicking: capture_screenshot() → read the pixel off the image → click_at_xy(x, y) → capture_screenshot() to verify. Suppress the Playwright-habit reflex of "locate first, then click" — no getBoundingClientRect, no selector hunt. Drop to DOM only when the target has no visible geometry (hidden input, 0×0 node). Hit-testing happens in Chrome's browser process, so clicks go through iframes / shadow DOM / cross-origin without extra work.
- Bulk HTTP: http_get(url) + ThreadPoolExecutor. No browser for static pages (249 Netflix pages in 2.8s).
- After goto: wait_for_load().
- Wrong/stale tab: ensure_real_tab(). Use it when the current tab is stale or internal; the daemon also auto-recovers from stale sessions on the next call.
- Verification: print(page_info()) is the simplest "is this alive?" check, but screenshots are the default way to verify whether a visible action actually worked.
- DOM reads: use js(...) for inspection and extraction when the screenshot shows that coordinates are the wrong tool.
- Iframe sites (Azure blades, Salesforce): click_at_xy(x, y) passes through; only drop to iframe DOM work when coordinate clicks are the wrong tool.
- Auth wall: redirected to login → stop and ask the user. Don't type credentials from screenshots.
- Raw CDP for anything helpers don't cover: cdp("Domain.method", params).

## Design constraints

- Coordinate clicks default. Input.dispatchMouseEvent goes through iframes/shadow/cross-origin at the compositor level.
- Connect to the user's running Chrome. Don't launch your own browser.
- cdp-use is only for CDPClient.send_raw. Prefer raw CDP strings over typed wrappers.
- run.py stays tiny. No argparse, subcommands, or extra control layer.
- Core helpers stay short. Put task-specific helper additions in `agent-workspace/agent_helpers.py`; daemon/bootstrap and remote session admin live in the core package.
- Don't add a manager layer. No retries framework, session manager, daemon supervisor, config system, or logging framework.

## Gotchas (field-tested)

- Omnibox popups are fake page targets. Filter chrome://omnibox-popup... and other internals when you need a real tab.
- CDP target order != Chrome's visible tab-strip order. Use UI automation when the user means "the first/second tab I can see"; Target.activateTarget only shows a known target.
- Default daemon sessions can go stale. ensure_real_tab() re-attaches to a real page.
- Browser Use API is camelCase on the wire. cdpUrl, proxyCountryCode, etc.
- Remote cdpUrl is HTTPS, not ws. Resolve the websocket URL via /json/version.
- Stop cloud browsers with PATCH /browsers/{id} + {"action":"stop"}.
- After every meaningful action, re-screenshot before assuming it worked. Use the image to verify changed state, open menus, navigation, visible errors, and whether the page is in the state you expected.
- Use screenshots to drive exploration. They are often the fastest way to find the next click target, notice hidden blockers, and decide if a selector is even worth writing.
- Prefer compositor-level actions over framework hacks. Try screenshots, coordinate clicks, and raw key input before adding DOM-specific workarounds.
- If you need framework-specific DOM tricks, check interaction-skills/ first. That is where dropdown, dialog, iframe, shadow DOM, and form-specific guidance belongs.

## Domain skills (opt-in)

Only applies when `BH_DOMAIN_SKILLS=1`. Otherwise ignore — `domain-skills/` is dormant and `goto_url` won't surface skill files.

When enabled, search `domain-skills/<host>/` before inventing an approach. `goto_url` returns up to 10 skill filenames for the navigated host.

If you learn anything non-obvious — a private API, stable selector, framework quirk, URL pattern, hidden wait, or site-specific trap — open a PR to `domain-skills/<site>/`. Capture the durable shape of the site (the map, not the diary). Don't write pixel coordinates (break on layout), task narration, or secrets — the directory is public.
