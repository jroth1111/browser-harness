# Interaction Skills

Interaction skills are reusable browser mechanics and cross-domain control
rules. Use them when the task is not yet site-specific, or when a domain skill
hands off to a generic browser, source, session, or output concern.

## Start Here

1. If the question is about backend, source family, auth state, or skill
   hierarchy, start with `cross-domain-control-flow.md`.
2. If the page loaded but required fields are missing, use
   `backend-capability.md`.
3. If the fetch returns 403 / bot detection, use `waf-bypass.md`.
4. If the task is a category search (find all X containing Y) or
   cross-platform comparison, use `data-source-exploration.md`
   (product-vs-category and comparison-requires-detail-pages sections).
5. If designing a scraper or report from scratch, use
   `data-source-exploration.md`.
6. If the problem is a UI mechanic, pick the smallest mechanic doc below.
7. If the task reveals durable cross-domain learning, use
   `empirical-learning-gate.md` before editing shared docs.

## Buckets

| Bucket | Files | Owns |
|---|---|---|
| Backend and source routing | `cross-domain-control-flow.md`, `backend-capability.md`, `data-source-exploration.md`, `network-requests.md` | Source family choice, capability gates, source discovery, category search pattern, cross-platform comparison, network observation |
| Browser state and viewport | `connection.md`, `tabs.md`, `viewport.md`, `screenshots.md`, `scrolling.md` | Tab/session control, geometry, visual verification, scroll ownership |
| UI controls | `dialogs.md`, `dropdowns.md`, `uploads.md`, `drag-and-drop.md`, `iframes.md`, `cross-origin-iframes.md`, `shadow-dom.md`, `print-as-pdf.md`, `downloads.md` | Reusable interaction patterns independent of one site |
| Data and session artifacts | `data-display.md`, `cookies.md`, `session-continuity.md`, `waf-bypass.md`, `empirical-learning-gate.md` | Dataset rendering, cookie safety, redacted continuity manifests, WAF bypass fallback, skill-learning promotion |

## Ownership Rules

- Interaction skills own reusable mechanics and control-plane rules.
- Domain skills own site routes, selectors, source priority, and domain-specific
  field semantics.
- `../SKILL.md` owns the root cold-start router and executable/helper index.
- Private values, cookies, auth headers, raw private payloads, and user-specific
  run data do not belong here.

## Complete File Inventory

- `backend-capability.md`
- `connection.md`
- `cookies.md`
- `cross-domain-control-flow.md`
- `cross-origin-iframes.md`
- `data-display.md`
- `data-source-exploration.md`
- `dialogs.md`
- `downloads.md`
- `drag-and-drop.md`
- `dropdowns.md`
- `empirical-learning-gate.md`
- `iframes.md`
- `network-requests.md`
- `print-as-pdf.md`
- `screenshots.md`
- `scrolling.md`
- `session-continuity.md`
- `shadow-dom.md`
- `tabs.md`
- `uploads.md`
- `viewport.md`
- `waf-bypass.md`
