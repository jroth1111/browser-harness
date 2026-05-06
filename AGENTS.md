browser-harness is a thin layer that connects agents to browsers via an editable CDP harness.

# Code priorities
- Clarity
- Precision
- Low verbosity
- Versatility

# Overview
All code lives in `src/browser_harness/`:
- `helpers.py` — CDP wrapper and core browser primitives auto-imported into `-c` scripts
- `daemon.py` — the long-lived middleman process between the browser and the agent
- `admin.py` — daemon lifecycle, diagnostics, updates, profile management
- `run.py` — the `browser-harness` CLI
- `agent_helpers.py` — task-specific browser helpers the agent adds (edit this freely)

`domain-skills/` — community-contributed per-site playbooks at the repo root (edit freely).

`SKILL.md` tells agents how to use the harness and CLI.
`install.md` tells agents how to install it, attach a browser, and troubleshoot.

# Contributing
Consider what is really needed. Prefer the smallest diff that fixes the bug.
