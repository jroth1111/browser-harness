# Layout Restoration Ledger — 2026-05-07

Base commit: e830627 (main)

## Target
- domain-skills/ at repo root (was agent-workspace/domain-skills/)
- agent_helpers.py inside src/browser_harness/
- All 15 root .py modules inside src/browser_harness/
- All test_*.py moved to tests/
- No agent-workspace/ dir, no py-modules in pyproject.toml, no BH_AGENT_WORKSPACE
- Single PyPI-ready package under src/browser_harness/

## Phase Ledger
| Phase | Status | Commit |
|-------|--------|--------|
| 0 — Preserve in-flight fixes, discard junk | not_started | — |
| 1 — git mv domain-skills + agent_helpers; delete agent-workspace | not_started | — |
| 2 — Absorb youtube_skill into domain-skills/youtube | not_started | — |
| 3 — Move 15 root .py → src/browser_harness/ | not_started | — |
| 4 — Move 48 test_*.py → tests/ | not_started | — |
| 5 — Centralise path refs (116 agent-workspace strings) | not_started | — |
| 6 — Drop BH_AGENT_WORKSPACE; update runtime resolution | not_started | — |
| 7 — Rewrite docs (AGENTS/README/SKILL/install) | not_started | — |
| 8 — Hygiene (.DS_Store, dating.zip, empty dirs, .gitignore) | not_started | — |
| 9 — Layout contract test | not_started | — |
| 10 — Full verify (pytest, pip install -e ., wheel smoke test) | not_started | — |
