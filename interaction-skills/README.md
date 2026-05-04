# Interaction Skills — Help Index

This file is a discovery index, not a routing destination. SKILL.md routes
directly to individual files. Use this only when no row in SKILL.md matched
your task, you need to discover which mechanic file covers an unusual edge
case, or you want to understand the full file inventory.

## Start Here

1. If the question is about backend, source family, auth state, or skill
   hierarchy, start with `cross-domain-control-flow.md`.
2. If the page loaded but required fields are missing, use
   `backend-capability.md`.
3. If the fetch returns 403 / bot detection, use `waf-bypass.md`.
4. If the task is a product search across marketplace platforms (AliExpress,
   eBay, Walmart, Amazon), use `product-search.md`.
5. If the task is a category search (find all X containing Y) or
   cross-platform comparison, use `product-search.md`
   (marketplace search strategy and marketplace trust/fraud sections).
6. If designing a scraper or report from scratch, use
   `data-source-exploration.md`.
7. If the problem is a UI mechanic (scrolling, dropdowns, iframes, etc.), use
   `ui-mechanics.md`.
8. If the task reveals durable cross-domain learning, use
   `empirical-learning-gate.md` before editing shared docs.

## Buckets

| Bucket | Files | Owns |
|---|---|---|
| Backend and source routing | `cross-domain-control-flow.md`, `backend-capability.md`, `data-source-exploration.md`, `source-selection-receipts.md` | Source family choice, capability gates, source discovery, source decision receipts |
| Product search and marketplace | `product-search.md`, `marketplace-search.md` | Cross-platform product search, category search, marketplace fraud, seller trust |
| Browser state | `connection.md`, `tabs.md` | Tab/session control, startup sequence |
| UI mechanics | `dialogs.md`, `ui-mechanics.md` | Screenshots, scrolling, dropdowns, iframes, shadow DOM, uploads, downloads, drag-and-drop, viewport, print-as-PDF, network observation |
| Data and session artifacts | `data-display.md`, `cookies.md`, `session-continuity.md`, `waf-bypass.md`, `empirical-learning-gate.md` | Dataset rendering, cookie safety, redacted continuity manifests, WAF bypass fallback, skill-learning promotion |
| API extraction and coverage | `api-schema-audit.md`, `coverage-accounting.md`, `extraction-coverage.md` | API schema comparison, data threading, static asset discovery, coverage edge cases, field triage |

## Ownership Rules

- Interaction skills own reusable mechanics and control-plane rules.
- Domain skills own site routes, selectors, source priority, and domain-specific
  field semantics.
- `../SKILL.md` owns the root cold-start router.
- Private values, cookies, auth headers, raw private payloads, and user-specific
  run data do not belong here.

## Field-tested gotchas

- Omnibox popups are fake page targets. Filter `chrome://omnibox-popup...` and other internals when you need a real tab.
- CDP target order != Chrome's visible tab-strip order. Use UI automation when the user means "the first/second tab I can see"; `Target.activateTarget` only shows a known target.
- Default daemon sessions can go stale. `ensure_real_tab()` re-attaches to a real page.
- If you need framework-specific DOM tricks, check `ui-mechanics.md` first.

## Complete File Inventory

- `api-schema-audit.md`
- `backend-capability.md`
- `connection.md`
- `cookies.md`
- `coverage-accounting.md`
- `cross-domain-control-flow.md`
- `data-display.md`
- `data-source-exploration.md`
- `dialogs.md`
- `empirical-learning-gate.md`
- `extraction-coverage.md`
- `marketplace-search.md`
- `product-search.md`
- `session-continuity.md`
- `source-selection-receipts.md`
- `tabs.md`
- `ui-mechanics.md`
- `waf-bypass.md`
