---
name: browser-harness
description: Direct browser control via CDP. Use when the user wants to automate, scrape, test, or interact with web pages. Connects to the user's already-running Chrome.
---

# browser-harness

Direct browser control via CDP. Read helpers.py — that's where the functions live. For setup, install, or connection problems, read install.md.

## Usage

```bash
browser-harness <<'PY'
new_tab("https://example.com")
wait_for_load()
print(page_info())
PY
```

- Invoke as browser-harness — it's on $PATH. No cd, no uv run.
- First navigation is new_tab(url), not goto_url(url) — goto runs in the user's active tab and clobbers their work.
- On macOS, `browser-harness --setup --accept-remote-debugging-dialog` can opt into keyboard-only approval for Chrome's remote-debugging consent dialog.
- `browser-harness --launch-profile PATH --port 9222` launches a visible agent-owned Chrome profile with loopback CDP when you need a fresh profile/process.

Available interaction skills:
- interaction-skills/connection.md — startup sequence, tab visibility, omnibox popup fix
- interaction-skills/backend-capability.md — diagnose loaded-but-empty pages and backend capability
- interaction-skills/cross-domain-control-flow.md — choose source, auth state, and backend across domains
- interaction-skills/data-source-exploration.md — discover public/private data primitives before designing extraction
- interaction-skills/data-display.md — render scraped datasets as self-contained HTML with tables, charts, and tree views (file-based report output, not live CDP tab inspection)
- interaction-skills/empirical-learning-gate.md — promote browser observations into skill updates only after source-context, redaction, canonical-artifact, positive-probe, and negative-probe checks
- interaction-skills/session-continuity.md — persist auth/session continuity metadata safely

Available domain skills:
- airbnb/README.md (folder landing page and fast path)
- airbnb/overview.md (start here — file map, executable scripts, schema index)
- airbnb/scripts/README.md (executable runners, collectors, probes, helpers)
- airbnb/exploration-protocol.md
- airbnb/workflows-current-state.md
- airbnb/market-research-playbook.md
- airbnb/data-inventory.md
- airbnb/session-continuity.md
- airbnb/host-sources.md
- airbnb/public-market.md
- airbnb/operator-insight-workflows.md
- airbnb/content-optimization-playbook.md
- airbnb/visual-revenue-workflows.md
- airbnb/schema-core.md
- airbnb/schema-performance.md
- airbnb/schema-operations.md
- airbnb/schema-public-market.md
- airbnb/schema-market-research.md
- airbnb/schema-finance.md
- airbnb/schema-demand-context.md
- airbnb/analytics-alerts.md
- airbnb/decisioning.md
- airbnb/data-quality.md
- airbnb/pipeline-fulfilment.md (status)
- airbnb/enhancement-roadmap.md (plan)
- airbnb/e2e-insights-data-display-plan.md (plan)
- airbnb/insights-granularity-map.md (fact table)
- realestate-com-au/scraping.md
- tiktok/upload.md
- polymarket/scraping.md
- youtube/scraping.md
- youtube/surface-map.json
- youtube/search.md
- youtube/video-detail.md
- youtube/fallbacks-and-verification.md
- surface-map-pattern.md
- surface-map.schema.json

### Airbnb cold-read path

When the task is about Airbnb host intelligence and you have no prior context,
read progressively:

1. `domain-skills/airbnb/overview.md` — first stop. Use its 90-second cold
   start, source-family route, and task router before opening scripts.
2. `domain-skills/airbnb/scripts/README.md` — only after you know data must be
   collected, probed, validated, or exported.
3. `domain-skills/airbnb/host-sources.md` — logged-in host inventory,
   Insights, reviews, calendar, and export-first workflows.
4. `domain-skills/airbnb/public-market.md` — logged-out guest-visible comps,
   search rank, public listing pages, and deterministic search partitions.
5. `domain-skills/airbnb/data-quality.md` — receipts, source classes,
   quarantine/last-good behavior, redaction, and warehouse provenance.

Do not start from collector code unless the routing docs name a specific script
and you need implementation details.

## Tool call shape

```bash
browser-harness <<'PY'
# any python. helpers pre-imported. daemon auto-starts.
PY
```

run.py calls ensure_daemon() before exec — you never start/stop manually unless you want to.

## Search first

Search domain-skills/ first for the domain you are working on before inventing a new approach.

Only if you start struggling with a specific mechanic while navigating, look in interaction-skills/ for helpers. The available interaction skills are:
- backend-capability.md
- cross-domain-control-flow.md
- cookies.md
- data-display.md
- data-source-exploration.md
- cross-origin-iframes.md
- dialogs.md
- downloads.md
- drag-and-drop.md
- dropdowns.md
- iframes.md
- network-requests.md
- print-as-pdf.md
- screenshots.md
- scrolling.md
- session-continuity.md
- shadow-dom.md
- tabs.md
- uploads.md
- viewport.md

Useful commands:

```bash
rg --files domain-skills
rg -n "tiktok|upload" domain-skills
```

## Always contribute back

If you learned anything non-obvious about how a site works, open a PR to domain-skills/<site>/ before you finish. Default to contributing. The harness gets better only because agents file what they learn. If figuring something out cost you a few steps, the next run should not pay the same tax.

For browser-backed workflows, follow the empirical skill update rule in
`interaction-skills/cross-domain-control-flow.md`: run against the real site
surface and source context the workflow depends on, then preserve durable
findings in the relevant domain skill. Logged-in, logged-out, fresh-profile,
persistent-profile, and mixed-state runs are workflow- and site-dependent source
contexts, not universal defaults.

For non-trivial or cross-domain learning, use
`interaction-skills/empirical-learning-gate.md` before promoting the observation
into a shared skill. The gate requires source context, evidence references,
redaction checks, canonical final-state wording, and positive/negative probes.

Shared skill artifacts are canonical final-state manuals. Put durable rules,
source context, confidence caveats, selectors, routes, waits, and traps in the
skill. Keep edit chronology, update notes, preservation markers, replacement
instructions, and task narration in the chat, patch envelope, PR description, or
an explicit history/audit artifact.

Examples of what's worth a PR:

- A private API the page calls (XHR/fetch endpoint, request shape, auth) — often 10× faster than DOM scraping.
- A stable selector that beats the obvious one, or an obfuscated CSS-module class to avoid.
- A framework quirk — "the dropdown is a React combobox that only commits on Escape", "this Vue list only renders rows inside its own scroll container, so scrollIntoView on the row doesn't work — you have to scroll the container".
- A URL pattern — direct route, required query params (?lang=en, ?th=1), a variant that skips a loader.
- A wait that wait_for_load() misses, with the reason.
- A trap — stale drafts, legacy IDs that now return null, unicode quirks, beforeunload dialogs, CAPTCHA surfaces.

### What a domain skill should capture

The *durable* shape of the site — the map, not the diary. Focus on what the next agent on this site needs to know before it starts:

- URL patterns and query params.
- Private APIs and their payload shape.
- Stable selectors (data-*, aria-*, role, semantic classes).
- Site structure — containers, items per page, framework, where state lives.
- Framework/interaction quirks unique to this site.
- Waits and the reasons they're needed.
- Traps and the selectors that *don't* work.

### Do not write

- Raw pixel coordinates. They break on viewport, zoom, and layout changes. Describe how to *locate* the target (selector, scrollIntoView, aria-label, visible text) — never where it happened to be on your screen.
- Run narration or step-by-step of the specific task you just did.
- Secrets, cookies, session tokens, user-specific state. domain-skills/ is shared and public.

## What actually works

- Screenshots first: use capture_screenshot() to understand the current page quickly, find visible targets, and decide whether you need a click, a selector, or more navigation.
- Clicking: capture_screenshot() → read the pixel off the image → click_at_xy(x, y) → capture_screenshot() to verify. Suppress the Playwright-habit reflex of "locate first, then click" — no getBoundingClientRect, no selector hunt. Drop to DOM only when the target has no visible geometry (hidden input, 0×0 node). Hit-testing happens in Chrome's browser process, so clicks go through iframes / shadow DOM / cross-origin without extra work.
- Bulk HTTP: http_get(url) + ThreadPoolExecutor. No browser for static pages (249 Netflix pages in 2.8s).
- After goto: wait_for_load().
- Loaded-but-empty pages: use wait_for_content() when a site may serve a bot/WAF challenge shell. It returns `ok`, `reason`, `text`, `html`, and `block` so you can distinguish real blank content from `kasada_kpsdk` / access-denied pages.
- Browser-session HTTP: after a real browser profile has passed a site challenge, `http_get_browser_session(url)` fetches same-domain pages with that browser's user agent and matching cookies; pair it with the domain's parser or embedded-data extractor.
- Robust solved sessions: `seed_browser_session(url)` verifies a headful/profile session; `fetch_with_browser_session(url, seed_url=...)` retries stale-cookie HTTP fetches by re-seeding in the browser.
- Cross-domain control flow: read `interaction-skills/cross-domain-control-flow.md` before mixing domains, auth states, source families, or browser backends. Backend choice is diagnostic until required fields match the source context.
- Generic login/session module: use `login_session.py` when you need the same user-login/session primitives with another CDP client. It never types credentials; it opens login pages, waits for the user, builds redacted manifests, and reuses browser cookies for same-domain HTTP.
- Provider availability: Chrome/Edge is the likely installed CDP baseline. Browser Use exists only inside Codex sessions with the Browser plugin and Node REPL `js`; Lightpanda is optional and may need intentional installation from upstream before use. Do not download optional providers unless the task explicitly needs that backend.
- Codex Browser Use / in-app browser: when the user explicitly asks for `browser-use`, Atlas runtime, or the Codex in-app browser and the Browser plugin is available, use the Browser plugin's Node REPL surface (`setupAtlasRuntime({ backend: "iab" })`) instead of `BH_CDP_WS`. See docs/local-cdp-providers.md.
- Lightpanda control: use `lightpanda_control.py` when testing Lightpanda directly. It launches/connects to Lightpanda, creates and attaches a page target, and routes page-scoped CDP calls through the target session while keeping browser/storage calls at browser scope.
- Lightpanda field gates: `evaluate_field_contract()` and `wait_for_field_contract()` verify named workflow fields so a loaded page is not mistaken for usable data.
- Headless/backend triage: `diagnose_url_capability(url)` reports backend kind, challenge block state, and recommendation. Use it before spending time on selectors when Lightpanda/headless returns blank content.
- Wrong/stale tab: ensure_real_tab(). Use it when the current tab is stale or internal; the daemon also auto-recovers from stale sessions on the next call.
- Verification: print(page_info()) is the simplest "is this alive?" check, but screenshots are the default way to verify whether a visible action actually worked.
- DOM reads: use js(...) for inspection and extraction when the screenshot shows that coordinates are the wrong tool.
- Iframe sites (Azure blades, Salesforce): click_at_xy(x, y) passes through; only drop to iframe DOM work when coordinate clicks are the wrong tool.
- Auth wall: redirected to login → stop and ask the user. Don't type credentials from screenshots.
- Raw CDP for anything helpers don't cover: cdp("Domain.method", params).

## Design constraints

- Coordinate clicks default. Input.dispatchMouseEvent goes through iframes/shadow/cross-origin at the compositor level.
- Default to the user's running Chrome. Only launch Chrome yourself through `--launch-profile` when the task explicitly needs an agent-owned fresh profile/process.
- cdp-use is only for CDPClient.send_raw. Prefer raw CDP strings over typed wrappers.
- run.py stays tiny. No argparse, subcommands, or extra control layer.
- Helpers stay short. Browser primitives in helpers.py; daemon/bootstrap lives in admin.py.
- Don't add a manager layer. No retries framework, session manager, daemon supervisor, config system, or logging framework.

## Gotchas (field-tested)

- Omnibox popups are fake page targets. Filter chrome://omnibox-popup... and other internals when you need a real tab.
- CDP target order != Chrome's visible tab-strip order. Use UI automation when the user means "the first/second tab I can see"; Target.activateTarget only shows a known target.
- Default daemon sessions can go stale. ensure_real_tab() re-attaches to a real page.
- After every meaningful action, re-screenshot before assuming it worked. Use the image to verify changed state, open menus, navigation, visible errors, and whether the page is in the state you expected.
- Use screenshots to drive exploration. They are often the fastest way to find the next click target, notice hidden blockers, and decide if a selector is even worth writing.
- Prefer compositor-level actions over framework hacks. Try screenshots, coordinate clicks, and raw key input before adding DOM-specific workarounds.
- If you need framework-specific DOM tricks, check interaction-skills/ first. That is where dropdown, dialog, iframe, shadow DOM, and form-specific guidance belongs.

## Interaction notes

- interaction-skills/ holds reusable UI mechanics such as dialogs, tabs, dropdowns, iframes, and uploads.
- domain-skills/ holds site-specific workflows and should be updated when you discover reusable patterns for a website.
