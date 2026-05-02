---
name: browser-harness
description: Direct browser control via CDP. Use when the user wants to automate, scrape, test, or interact with web pages. Connects to the user's already-running Chrome.
---

# browser-harness

Direct browser control via CDP. `SKILL.md` is the agent router. For setup,
install, or connection problems, read `install.md`. For executable browser
primitives, use `browser-harness` with the helpers preloaded from `helpers.py`.

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

## Cold-Start Router

Start from the user intent, then pick the control path and evidence family. Do
not start from provider choice or collector code unless the router names it.

| User intent | First doc | Run path | Evidence/source owner | Output rule |
|---|---|---|---|---|
| Install, connect, repair local browser access | `install.md` | `browser-harness --setup`, `--doctor`, `--launch-profile` | `admin.py`, `daemon.py`, `docs/local-cdp-providers.md` | Local daemon/socket/log state stays outside skill docs |
| Execute a browser action or inspect a page | This file, then relevant interaction skill if mechanics get hard | `browser-harness <<'PY' ... PY` | `helpers.py` over CDP through `run.py` and `daemon.py` | Use screenshots/page info as verification evidence |
| Choose backend, auth state, or source family | `interaction-skills/cross-domain-control-flow.md` | Capability probe, then selected browser/API/export path | Source context and required field contract | Capability receipts can be stored in local/session artifacts, not shared secrets |
| Discover a scraper/data model | `interaction-skills/data-source-exploration.md`, then `domain-skills/<site>/` | Export/API/static/browser path selected by field proof | Domain skill owns site semantics and source priority | Persist only reusable routes/selectors/contracts |
| Search for products across marketplaces | `interaction-skills/product-search.md` | Composable layered queries per platform, parallel http_get + sequential CDP | Domain skill owns transport and extractors | Normalize to common schema, dedup by platform ID |
| Use a known site workflow | `domain-skills/<site>/...` | Domain-specific script or browser flow named by that skill | Domain workflow and schema/contract docs | Private run data stays in ignored local paths |
| Render a collected dataset | `interaction-skills/data-display.md` | `from data_display import render_dataset` | Input file schema from the producing workflow | HTML output is generated; keep sensitive inputs private |
| Preserve or reuse auth safely | `interaction-skills/session-continuity.md` | `login_session.py` helpers through a CDP client | Redacted manifest plus private auth bundle | `.session-store/` is redacted; `.private-data/` is secret |
| Promote a learned rule into a skill | `interaction-skills/empirical-learning-gate.md` | `browser-harness --skill-learning-gate CANDIDATE.json` | `domain-skills/skill-learning-candidate.schema.json` | Candidate evidence must pass redaction and negative-probe checks |
| Clean up or reorganize a skill | `interaction-skills/cross-domain-control-flow.md` | Domain Skill Reorganization Workflow | Root/domain router owns handoffs; schema docs own contracts | Exclude `.private-data/`, `.session-store/`, `outputs/`, caches |

## Hierarchy Map

Level 0 is the browser-harness skill root.

| Level | Buckets | Concrete homes |
|---|---|---|
| 1 | Root harness, interaction skills, domain skills, provider docs, package/tests, generated/private artifacts | `SKILL.md`, `interaction-skills/`, `domain-skills/`, `docs/`, `pyproject.toml`, `test_*.py`, ignored local dirs |
| 2 under root harness | install/control plane, command runner, CDP daemon, helper primitives, data display, session/auth helpers, skill-learning gate | `install.md`, `run.py`, `admin.py`, `daemon.py`, `helpers.py`, `data_display.py`, `login_session.py`, `skill_learning_gate.py` |
| 2 under interaction skills | backend/source control, browser mechanics, data display, session continuity, empirical learning | `interaction-skills/README.md`, `interaction-skills/*.md` |
| 2 under domain skills | site workflows, surface-map contracts, rich domain bundles, fixtures/receipts/reports | `domain-skills/README.md`, `domain-skills/<site>/`, `domain-skills/surface-map*.json`, `domain-skills/surface-map-pattern.md` |
| 3 under rich domain bundles | overview/router, workflows/playbooks, schema/contracts, scripts, fixtures, receipts/reports, private/generated local stores | Airbnb and YouTube are the current multi-file bundles |

Control-flow hierarchy:
`user intent -> root router -> workflow/mechanic/domain doc -> run path -> evidence/source contract -> output/provenance -> skill update or action`.

Source-family hierarchy:
`browser-harness -> evidence family -> logical layer -> artifact bucket -> concrete doc/script/schema/artifact`.

Canonical evidence families:

| Evidence family | Logical layer | Primary owners |
|---|---|---|
| Browser visual/UI state | screenshots, coordinate clicks, tabs, viewport, dialogs, uploads | `helpers.py`, `interaction-skills/screenshots.md`, mechanics docs |
| DOM/CDP runtime state | JS evaluation, page info, AX tree, raw CDP | `helpers.py`, `daemon.py`, mechanics docs |
| Same-origin browser-session HTTP | cookies, user agent, seeded fetches | `helpers.py`, `login_session.py`, `interaction-skills/cookies.md` |
| Static HTTP/API/export | direct fetches, exports, embedded data | `helpers.py`, `interaction-skills/data-source-exploration.md`, domain skills |
| Provider/backend capability | Chrome/Edge, Browser Use, Lightpanda, remote/self-hosted CDP | `interaction-skills/cross-domain-control-flow.md`, `docs/local-cdp-providers.md` |
| Domain-specific evidence | site URLs, selectors, source priority, workflow semantics | `domain-skills/<site>/` |
| Local data/report artifacts | JSON/JSONL/CSV inputs and generated HTML explorers | `data_display.py`, `interaction-skills/data-display.md`, ignored `outputs/` or private domain stores |
| Skill-learning evidence | observed surface, positive/negative probes, redaction status | `interaction-skills/empirical-learning-gate.md`, `skill_learning_gate.py`, candidate schema |

## Executable And Helper Index

| Artifact | Role | Control-flow stage | Direct run? | Owner |
|---|---|---|---|---|
| `browser-harness` / `run.py` | runner | execution | yes | CLI, helper preload, daemon auto-start |
| `browser-harness --doctor` | guard/probe | capability check | yes | local daemon, endpoint, CDP hygiene |
| `browser-harness --setup` | runner | intake/setup | yes | interactive browser attach |
| `browser-harness --launch-profile PATH` | runner | source/backend selection | yes | agent-owned headful profile |
| `browser-harness --skill-learning-gate` | guard | validation/provenance | yes | empirical skill promotion gate |
| `browser-harness --update -y` | runner | maintenance | yes, only when user asks | update then restart daemon |
| `helpers.py` | helper module | browser execution/evidence | preloaded, not standalone | CDP/browser primitives |
| `admin.py` | helper module | setup/maintenance | through `run.py` | daemon setup, doctor, launch, update |
| `daemon.py` | service module | execution transport | indirect | CDP websocket and socket bridge |
| `data_display.py` | helper module | generated report output | import `render_dataset` | self-contained HTML explorers |
| `login_session.py` | helper module | auth/session continuity | import from workflows | redacted manifests, cookie/header helpers |
| `lightpanda_control.py` | helper module | backend capability | import from workflows | direct Lightpanda CDP control and field gates |
| `skill_learning_gate.py` | guard module | validation/provenance | direct via CLI wrapper | candidate schema, redaction, promotion checks |
| `tools/render_airbnb_fixtures.py` | local helper | generated report refresh | helper-only | Airbnb private local fixture rendering |

## Reusable Interaction Buckets

Use these when the task is cross-domain, mechanical, or not yet tied to one
site. The full interaction inventory is `interaction-skills/README.md`.

| Bucket | Docs | Owns |
|---|---|---|
| Backend/source routing | `interaction-skills/cross-domain-control-flow.md`, `interaction-skills/backend-capability.md`, `interaction-skills/data-source-exploration.md`, `interaction-skills/network-requests.md` | Source family, auth/backend choice, capability gates, source discovery |
| Browser mechanics | `interaction-skills/connection.md`, `interaction-skills/tabs.md`, `interaction-skills/viewport.md`, `interaction-skills/screenshots.md`, `interaction-skills/scrolling.md` | Stable tab/session control and visual verification |
| UI controls | `interaction-skills/dialogs.md`, `interaction-skills/dropdowns.md`, `interaction-skills/uploads.md`, `interaction-skills/drag-and-drop.md`, `interaction-skills/iframes.md`, `interaction-skills/cross-origin-iframes.md`, `interaction-skills/shadow-dom.md`, `interaction-skills/print-as-pdf.md`, `interaction-skills/downloads.md` | Reusable interaction patterns that are not site-specific |
| Data/session outputs | `interaction-skills/data-display.md`, `interaction-skills/cookies.md`, `interaction-skills/session-continuity.md`, `interaction-skills/empirical-learning-gate.md` | Reports, cookie/session safety, redacted manifests, promotion checks |

## Domain Skill Buckets

Domain skills are site-specific. Use `domain-skills/README.md` for the
directory-level router. For the exhaustive top-level inventory, run:

```bash
find domain-skills -mindepth 1 -maxdepth 1 -type d | sort
```

For a selected site, run `rg --files domain-skills/<site>`.

| Bucket | Start here | Notes |
|---|---|---|
| Rich multi-file domain bundles | `domain-skills/airbnb/overview.md`, `domain-skills/youtube/overview.md`, `domain-skills/ai-chat-archive/overview.md` | Have routers, workflow docs, scripts/helpers, fixtures, schemas or surface maps |
| Single-file site skills | `domain-skills/<site>/*.md` | Usually one concise scraping/action workflow for the site |
| Shared domain contracts | `domain-skills/surface-map-pattern.md`, `domain-skills/surface-map.schema.json`, `domain-skills/skill-learning-candidate.schema.json` | Schema/process contracts reused by domain bundles |
| Private/generated local artifacts | `domain-skills/<site>/.private-data/`, `domain-skills/<site>/.session-store/`, `domain-skills/<site>/outputs/` | Ignored or package-excluded local state; never broad-search or copy into reusable docs |

High-signal domain entry points:

- `domain-skills/airbnb/overview.md` — Airbnb host intelligence router.
- `domain-skills/youtube/overview.md` — YouTube workflow/router bundle.
- `domain-skills/ai-chat-archive/overview.md` — SQLite-only logged-in AI chat archive workflow for ChatGPT, Claude, Gemini, Grok, and Perplexity.
- `domain-skills/realestate-com-au/scraping.md` — REA public scraping workflow.
- `domain-skills/tiktok/upload.md` — TikTok upload workflow.
- `domain-skills/polymarket/scraping.md` — Polymarket scraping workflow.

### Airbnb cold-read path

When the task is about Airbnb host intelligence and you have no prior context,
read progressively:

1. `domain-skills/airbnb/overview.md` — first stop. Use its 90-second cold
   start, Intent Router, source guardrails, and Expanded Routing Matrix before
   opening scripts.
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

If the task is to clean up or reorganize a domain skill, use
`interaction-skills/cross-domain-control-flow.md` and its Domain Skill
Reorganization Workflow before editing shared docs.

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
