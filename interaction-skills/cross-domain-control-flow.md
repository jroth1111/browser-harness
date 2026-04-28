# Cross-Domain Control Flow

Use this before acting across multiple site domains, source families, auth
states, or browser backends. The goal is to keep provider choice from leaking
into data semantics: a backend is acceptable only when it can prove the same
canonical fields for the same source context.

## First Split

Classify the requested target before opening a browser:

| Target | First control surface | Reason |
|---|---|---|
| Static public docs/API | `http_get()` or direct API | No browser state required |
| Codex in-app browser/current tab | Browser Use `setupAtlasRuntime({ backend: "iab" })` | Not a CDP endpoint |
| Public dynamic page | Cheapest CDP backend with capability gates | Fast if fields render |
| Public visual/rank/price task | Fresh logged-out headful Chrome | Screenshots and rendered order matter |
| Authenticated UI/export/download | Persistent headful Chrome profile | Login, MFA, device trust, files |
| Same-origin follow-up fetches | `fetch_with_browser_session()` after headful seed | Faster than rendering every page |
| Cross-origin iframe interaction | Compositor click first; iframe target only for JS inspection | Page DOM cannot pierce cross-origin frames |

When a domain skill exists, read it before choosing the backend. Domain skills
override generic preferences because backend capability is site-specific.

## Provider Availability Preflight

Provider choice has two gates: semantic fit and local availability. Do not let
an unavailable optional backend block a task that Chrome can handle.

1. Prefer already-available local surfaces before acquiring a new browser.
2. Treat Chrome/Edge as the likely baseline. If the task needs CDP helpers, run
   `browser-harness --setup` or `browser-harness --launch-profile ...` before
   looking for optional providers.
3. Treat Browser Use as Codex-client-only. Use it only when the Browser plugin
   and Node REPL `js` surface are available in the current Codex session. If it
   is missing, fall back to CDP Chrome for browser-harness work instead of
   trying to emulate Browser Use.
4. Treat Lightpanda as optional. Check `command -v lightpanda` or use a known
   local binary path before selecting it. If absent, do not install or download
   it as a side effect of scraping; record that the backend is unavailable and
   use Chrome unless the user explicitly wants Lightpanda acquisition or a
   backend comparison.
5. If Lightpanda acquisition is requested, use the upstream GitHub release,
   official install script, or Docker image, bind any CDP service to
   `127.0.0.1`, then rerun `browser-harness --doctor` before using it.
6. Remote/self-hosted endpoints require an explicit endpoint and the normal
   `BH_CDP_ALLOW_REMOTE=1` risk posture; never silently choose a remote browser
   because a local optional backend is missing.

## Routing Ladder

1. Record the task context: target domain/origin, public or private state, user
   account scope, dates/filters/currency/device, and required output fields.
2. Check whether an export, direct API, bootstrap JSON, or static HTML source can
   provide the required fields with stable IDs and counts.
3. If a browser is required, apply the provider availability preflight, then test
   the cheapest available appropriate backend with `diagnose_url_capability()`
   before selectors.
4. Prove field-level capability, not just page load. Required fields must appear
   and normalize to the target schema.
5. If the backend loads a challenge shell, no-JS shell, empty page, or misses
   required fields, stop selector debugging and switch backend/source.
6. Use headful Chrome as the reference backend whenever the task depends on
   auth, downloads, visual state, ranking, prices, maps, modals, lazy cards, or
   anti-bot/device reputation.
7. Use `fetch_with_browser_session()` only after a headful seed proves useful
   content for the target site/session. Treat it as cookie reuse, not a challenge
   solver.
8. Store a capability receipt for every backend attempted: source context,
   backend kind, fields found, fields missing, block state, fallback reason, and
   whether the output was canonical or diagnostic-only.

## Auth And Origin Boundaries

- Do not reuse private account state for public market observations unless the
  user explicitly asks to compare logged-in personalization.
- Do not merge logged-out and logged-in observations into one dataset. Record
  auth state as part of the source context.
- Do not copy cookies, tokens, storage values, auth headers, or raw private
  payloads into shared domain skills.
- If a flow redirects to an identity provider, let the user complete login/MFA.
  After return, verify the target site origin and required fields before using
  the session.
- For cross-origin iframes, prefer coordinate clicks for interaction. Use
  `iframe_target(url_substr)` and `js(..., target_id=...)` only when the iframe
  exposes a target and DOM inspection is necessary.

## Backend Promotion Rules

A cheaper backend can become the default for a source family only when a receipt
shows:

- the same source context as the target workflow,
- required fields are present,
- record counts/order/IDs reconcile with the reference backend or export,
- no challenge/no-JS shell is being parsed as content,
- failure mode and fallback path are documented.

Do not promote a backend from one domain to another domain by analogy. A
Lightpanda pass on static docs says nothing about a protected marketplace search
page; a headful login pass says nothing about logged-out public rankings.

## Airbnb Example

For Airbnb public market work:

- Help and Resource Centre pages can use direct HTTP or Lightpanda when static
  content is present.
- Public search pages may try Lightpanda first, but only a field contract with
  `/rooms/` links, total price evidence, and result-card ordering makes it
  usable.
- If Lightpanda returns generic text, no room links, or no AUD totals, keep that
  result only as a capability receipt and rerun in fresh logged-out headful
  Chrome.
- Public comp data must normally be logged out. Do not reuse the host account
  profile for public guest-market ranking or prices.
- Host dashboard, Insights, earnings, exports, listing editor, and reservations
  require persistent logged-in headful Chrome; prefer exports or authenticated
  APIs after the browser session is valid.
