# Robustness Surface Map

This is the repo-wide robustness contract for browser-harness. The canonical
machine-readable map is `docs/robustness-surface-map.json`.

Use it when planning or reviewing robustness work:

1. Pick the affected surface by `id`.
2. Check the listed contracts and risks before editing code.
3. Define positive and negative probes from the surface contract.
4. Preserve the thin-harness non-goals: no manager layer, retries framework,
   session manager, daemon supervisor, config system, or logging framework.
5. Record any residual gap against the surface, not as a vague follow-up.

## Surface Inventory

- `cli_entrypoint` — command execution, setup/doctor/update flags, and helper-preloaded code.
- `daemon_socket_lifecycle` — daemon startup, endpoint discovery, Unix socket/pid/log files, and cleanup.
- `cdp_transport` — helper socket client, raw CDP request/response handling, and reconnect semantics.
- `navigation_readiness` — navigation, content readiness, blank renders, and stale tab recovery.
- `block_and_auth_detection` — WAF, bot-detection, auth gates, and authorized recovery boundaries.
- `session_continuity` — authenticated browser profile reuse, redacted manifests, private bundles, and restore proof.
- `fetch_source_selection` — fetch source fallback, source receipts, and field-level canonical-source decisions.
- `network_capture` — CDP Network event capture, endpoint clustering, replay, and API promotion.
- `crawl_safety` — crawl dedupe, saturation, blocked ledgers, request/time limits, and backoff.
- `extraction_contracts` — four-state field semantics, selector probes, primary keys, fixtures, and coverage triage.
- `domain_skill_loading` — root router, domain indexes, packaged skill assets, and empirical skill promotion.
- `report_rendering` — generated HTML reports, assets, disabled states, and browser-visible render checks.
- `packaging_release` — wheel contents, clean install smoke, console scripts, package data, and exclusions.
- `quality_gates` — repo-native verification commands, hygiene scans, optional live gates, and cleanup.

## Acceptance Rule

A robustness change is not verified until the affected surface has:

- implementation evidence mapped to its files or artifacts;
- a positive probe that proves the required path works;
- a negative probe that proves the old, forbidden, unsafe, or ambiguous path does
  not still pass;
- reachability evidence for entry, validation, routing, execution, state effect,
  output, lifecycle, observability, and regression, or an explicit `n/a` reason
  in the machine-readable map.
