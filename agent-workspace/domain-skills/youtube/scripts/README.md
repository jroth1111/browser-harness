# YouTube Scripts

This is the executable index for `domain-skills/youtube/scripts/`. The workflow
and source semantics live in `../overview.md`, `../workflows.md`, and
`../surface-map.json`; this file owns what is runnable, what each script
produces, and when not to run it.

## Script Index

| Script | Role | Control-flow stage | Source/evidence family | Direct run? | Produces | Refuse/avoid when |
|---|---|---|---|---|---|---|
| `assert_no_forbidden_paths.py` | guard | validation/provenance | control-plane safety | yes, `python3 domain-skills/youtube/scripts/assert_no_forbidden_paths.py` | Pass/fail scan for forbidden YouTube paths | Do not treat a pass as live source proof; it only checks committed artifacts |
| `live_smoke.py` | probe/runner | capability check | public YouTube signed-out browser/API evidence | yes, through `browser-harness < domain-skills/youtube/scripts/live_smoke.py` | Redacted live-smoke receipt under `../receipts/` | Do not run for account-bound, private, age-gated, mutating, or media-download tasks |
| `render_docs.py` | exporter | normalization/document generation | surface-map contract | yes, `python3 domain-skills/youtube/scripts/render_docs.py` | Regenerated `../generated-surfaces.md` from `../surface-map.json` | Do not edit generated tables by hand after running |
| `summarize_reports.py` | exporter | outcome review/reporting | receipts and surface-map summary | yes, `python3 domain-skills/youtube/scripts/summarize_reports.py` | Stable JSON summary under `../reports/` | Do not use as collection proof when no live receipt exists |

## Ownership

- These scripts do not own YouTube workflow policy or source priority.
- `../surface-map.json` owns primitive IDs, fallback DAGs, execution policy, and
  verification probes.
- `../workflows.md` owns task-level judgement rules and unsafe paths.
- `../overview.md` owns the human cold-start decision tree.
- `../receipts/` and `../reports/` contain reusable redacted evidence, not raw
  cookies, visitor IDs, playback URLs, caption base URLs, API keys, or account
  payloads.
