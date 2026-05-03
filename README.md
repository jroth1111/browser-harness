# Browser Harness

The simplest, thinnest, **self-healing** harness that gives LLM **complete freedom** to complete any browser task. Built directly on CDP.

The agent writes what's missing, mid-task. No framework, no recipes, no rails. One websocket to Chrome, nothing between.

```
  ● agent: wants to upload a file
  │
  ● helpers.py → upload_file() missing
  │
  ● agent edits the harness and writes it    helpers.py   192 → 199 lines
  │                                                       + upload_file()
  ✓ file uploaded
```

**You will never use the browser again.**

## Setup prompt

Paste into Claude Code or Codex:

```text
Set up https://github.com/browser-use/browser-harness for me.

Read `install.md` first to install and connect this repo to my real browser. Then read `SKILL.md` for normal usage. Always read `helpers.py` because that is where the functions are. When you open a setup or verification tab, activate it so I can see the active browser tab. After it is installed, open this repository in my browser and, if I am logged in to GitHub, ask me whether you should star it for me as a quick demo that the interaction works — only click the star if I say yes.
```

When this page appears, tick the checkbox so the agent can connect to your browser:

<img src="docs/setup-remote-debugging.png" alt="Remote debugging setup" width="520" style="border-radius: 12px;" />

See [domain-skills/](domain-skills/) for example tasks.

For browser options such as Codex Browser Use, CloakBrowser, Browserless, Steel,
Kernel Chromium images, and Kameleo, see
[docs/local-cdp-providers.md](docs/local-cdp-providers.md).

## Development

Run the test suite from a clean checkout with:

```bash
uv sync --group dev
uv run --group dev pytest -q
```

If the system-wide `langsmith` pytest plugin is installed and causes a pydantic version conflict, disable it:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q
```

Live/E2E tests that hit Airbnb's API are gated behind environment flags:

| Test file | Gate env var |
|---|---|
| `test_e2e_airbnb_insights_year_view.py` | `AIRBNB_E2E_YEAR_VIEW=1` |
| `test_e2e_airbnb_insights_negative_controls.py` | `AIRBNB_E2E_NEGATIVE_429=1` |
| `test_e2e_airbnb_insights_conversion_display.py` | Runs unconditionally against pre-collected fixtures |

## Project Map

- `SKILL.md` — agent-facing router, workflow map, executable index, and usage rules.
- `install.md` — first-time install, browser bootstrap, maintenance commands, and local architecture.
- `run.py` — `browser-harness` CLI; runs plain Python with helpers preloaded and exposes setup/doctor/update commands.
- `helpers.py` — browser primitives the agent uses inside `browser-harness`.
- `admin.py` + `daemon.py` — daemon bootstrap plus the CDP websocket and socket bridge.
- `interaction-skills/README.md` — reusable browser mechanics and cross-domain workflow index.
- `domain-skills/README.md` — site-specific workflow and source-contract index.
- `data_display.py`, `login_session.py`, `lightpanda_control.py`, `skill_learning_gate.py` — helper modules for reports, session continuity, backend capability, and empirical skill promotion.

## Contributing

PRs and improvements welcome. The best way to help: **contribute a new domain skill** under [domain-skills/](domain-skills/) for a site or task you use often (LinkedIn outreach, ordering on Amazon, filing expenses, etc.). Each skill teaches the agent the selectors, flows, and edge cases it would otherwise have to rediscover.

- **Skills are written by the harness, not by you.** Just run your task with the agent — when it figures something non-obvious out, it files the skill itself (see [SKILL.md](SKILL.md)). Please don't hand-author skill files; agent-generated ones reflect what actually works in the browser.
- Open a PR with the generated `domain-skills/<site>/` folder — small and focused is great.
- Bug fixes, docs tweaks, and helper improvements are equally welcome.
- Browse existing skills (`github/`, `linkedin/`, `amazon/`, ...) to see the shape.

If you're not sure where to start, open an issue and we'll point you somewhere useful.
