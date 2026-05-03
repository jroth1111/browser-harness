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

Match your task to one row. Open the file in "Go to" — that's your action file.

| Task pattern | Go to | When to escalate |
|---|---|---|
| Install / connect / repair | `install.md` | — |
| Click, screenshot, scroll, type on current page | Playbook below (no file needed) | `interaction-skills/ui-mechanics.md` only for hidden/0×0 targets, iframes, shadow DOM, file uploads |
| Choose backend or test capability for a URL | `interaction-skills/backend-capability.md` | `interaction-skills/cross-domain-control-flow.md` when the task spans 2+ sites, auth states, or source families |
| Site returns 403 / bot detection / WAF block | `interaction-skills/waf-bypass.md` | — |
| Tab control, connection issues, stale tabs | `interaction-skills/tabs.md` | `interaction-skills/connection.md` when `ensure_real_tab()` or `browser-harness --doctor` fails |
| Search products across marketplaces | `interaction-skills/product-search.md` | — |
| Auth wall, login, session reuse | `interaction-skills/session-continuity.md` | `interaction-skills/cookies.md` for cookie extraction/setting mechanics |
| Render data as HTML table/explorer | `interaction-skills/data-display.md` | — |
| Build a scraper for a new site | `interaction-skills/data-source-exploration.md` | — |
| Work with a known site (see list below) | `domain-skills/<site>/overview.md` or first .md | `interaction-skills/data-source-exploration.md` if the domain skill lacks the field you need |
| Promote learned rule into a skill | `interaction-skills/empirical-learning-gate.md` | — |
| Clean up or reorganize a skill | `interaction-skills/cross-domain-control-flow.md` | — |

If nothing matches: scan `domain-skills/` with `rg --files domain-skills/<site>`, or read `interaction-skills/README.md` for the full mechanic index.

## Playbook: What actually works

- Screenshots first: use `capture_screenshot()` to understand the current page quickly, find visible targets, and decide whether you need a click, a selector, or more navigation.
- Clicking: capture_screenshot() → read the pixel off the image → click_at_xy(x, y) → capture_screenshot() to verify. Suppress the Playwright-habit reflex of "locate first, then click" — no getBoundingClientRect, no selector hunt. Drop to DOM only when the target has no visible geometry (hidden input, 0×0 node). Hit-testing happens in Chrome's browser process, so clicks go through iframes / shadow DOM / cross-origin without extra work.
- Bulk HTTP: http_get(url) + ThreadPoolExecutor. No browser for static pages (249 Netflix pages in 2.8s).
- After goto: wait_for_load().
- Loaded-but-empty pages: use wait_for_content() when a site may serve a bot/WAF challenge shell. It returns `ok`, `reason`, `text`, `html`, and `block` so you can distinguish real blank content from `kasada_kpsdk` / access-denied pages.
- Browser-session HTTP: after a real browser profile has passed a site challenge, `http_get_browser_session(url)` fetches same-domain pages with that browser's user agent and matching cookies; pair it with the domain's parser or embedded-data extractor.
- Robust solved sessions: `seed_browser_session(url)` verifies a headful/profile session; `fetch_with_browser_session(url, seed_url=...)` retries stale-cookie HTTP fetches by re-seeding in the browser.
- Provider availability: Chrome/Edge is the likely installed CDP baseline. Browser Use exists only inside Codex sessions with the Browser plugin and Node REPL `js`; Lightpanda is optional and may need intentional installation from upstream before use. Do not download optional providers unless the task explicitly needs that backend.
- Headless/backend triage: `diagnose_url_capability(url)` reports backend kind, challenge block state, and recommendation. Use it before spending time on selectors when Lightpanda/headless returns blank content.
- Wrong/stale tab: ensure_real_tab(). Use it when the current tab is stale or internal; the daemon also auto-recovers from stale sessions on the next call.
- DOM reads: use js(...) for inspection and extraction when the screenshot shows that coordinates are the wrong tool.
- Iframe sites (Azure blades, Salesforce): click_at_xy(x, y) passes through; only drop to iframe DOM work when coordinate clicks are the wrong tool.
- Auth wall: redirected to login → stop and ask the user. Don't type credentials from screenshots.
- Raw CDP for anything helpers don't cover: cdp("Domain.method", params).

## Search domain-skills/ first

Before inventing a new approach, check if a domain skill exists:

    rg --files domain-skills/<site>

Rich domain bundles (read overview.md first):
- `airbnb/` — host intelligence, comp analysis, pricing
- `youtube/` — extraction, playlists, channel workflows
- `ai-chat-archive/` — multi-provider chat export
- `atlas/` — recruitment SaaS

Single-file domains: `amazon/`, `ebay/`, `reddit/`, `spotify/`, and 70+ others.
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
browser-harness <<'PY'
# any python. helpers pre-imported. daemon auto-starts.
PY
```

run.py calls ensure_daemon() before exec — you never start/stop manually unless you want to.

## Design constraints

- Coordinate clicks default. Input.dispatchMouseEvent goes through iframes/shadow/cross-origin at the compositor level.
- Default to the user's running Chrome. Only launch Chrome yourself through `--launch-profile` when the task explicitly needs an agent-owned fresh profile/process.
- cdp-use is only for CDPClient.send_raw. Prefer raw CDP strings over typed wrappers.
- run.py stays tiny. No argparse, subcommands, or extra control layer.
- Helpers stay short. Browser primitives in helpers.py; daemon/bootstrap lives in admin.py.
- Don't add a manager layer. No retries framework, session manager, daemon supervisor, config system, or logging framework.
