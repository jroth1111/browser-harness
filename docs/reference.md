# Reference

Architecture, hierarchy, and index material for the browser-harness skill. Read
this when you need to understand the full skill structure or discover a helper
function. For task routing, use `SKILL.md`.

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

## Evidence Families

| Evidence family | Logical layer | Primary owners |
|---|---|---|
| Browser visual/UI state | screenshots, coordinate clicks, tabs, viewport, dialogs, uploads | `helpers.py`, `interaction-skills/ui-mechanics.md` |
| DOM/CDP runtime state | JS evaluation, page info, AX tree, raw CDP | `helpers.py`, `daemon.py` |
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
