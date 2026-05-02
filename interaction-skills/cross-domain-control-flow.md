# Cross-Domain Control Flow

Use this before acting across multiple site domains, source families, auth
states, browser backends, or skill hierarchy boundaries. The goal is to keep
provider choice and document layout from leaking into data semantics: a backend
or artifact home is acceptable only when it can prove the same canonical fields
for the same source context.

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

**HTTP extraction caveat**: Many sites block non-browser HTTP even when content
appears static. If `http_get()` returns 403, don't assume the content requires
authentication — it may be UA or WAF blocking. Run `diagnose_url_capability()`
before escalating to browser. Observed: Letterboxd sub-pages, Capterra, and
OpenStreetMap all block HTTP with 403 despite serving public content to browsers.

**User-Agent variation**: Some sites require specific UAs:
- Sites that block browser UAs (Capterra requires ClaudeBot UA)
- Sites that block bare UAs (Walmart requires full Mozilla/5.0)
- `diagnose_url_capability()` tests with the default UA; if it fails, try
  alternative UAs before escalating to browser

**Rate limiting models**: Rate limiting varies by dimension across sites:
- Requests per second (e.g., 3 req/s sustained)
- Concurrent connection slots (e.g., 2 concurrent per IP)
- Query complexity quotas (reset over time, not per request)
Domain skills should document which model their site uses. Generic backoff
strategy: start with 3-5s delay, exponential backoff on 429/block responses.

When a domain skill exists, read it before choosing the backend. Domain skills
override generic preferences because backend capability is site-specific.

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

## Example: multi-surface site with public and authenticated surfaces

Many sites have distinct public and authenticated surfaces with different backend
requirements. The pattern:

- Static public pages (help, docs, resource centres) → direct HTTP or lightweight
  backend when static content is present.
- Dynamic public pages (search, listings) → try lightweight backend first; accept
  only when a field contract proves required data is present. If the lightweight
  backend returns generic text or missing fields, keep the result only as a
  capability receipt and rerun with a heavier backend.
- Public comp data must normally be collected logged-out. Do not reuse an
  authenticated profile for public-market ranking or price data.
- Authenticated surfaces (dashboards, exports, editors, reports) → persistent
  headful browser profile; prefer exports or authenticated APIs after the browser
  session is valid.

Site-specific routing for this pattern lives in `domain-skills/<site>/`.

---

## Empirical Skill Update Rule

For any browser-backed workflow, treat the documented workflow as a hypothesis
until it has been exercised against the real site surface it claims to control
or extract from.

During execution:

- Run the workflow against the live page, backend source family, browser
  backend, and auth/session context that the workflow actually depends on.
- Choose logged-in, logged-out, fresh-profile, persistent-profile, or mixed
  state from the site and workflow requirements. These states are source
  contexts, not universal defaults.
- Compare the workflow's assumptions against observed site behavior before
  relying on extracted fields or actions.
- Record durable findings in the domain skill, not task narration.
- Preserve source context: origin, URL pattern, auth/session state, UI surface,
  backend route, required fields, confidence limits, and failure modes.
- If a field cannot be observed reliably, document the degraded confidence rule.
- If a browser/backend path fails but another source works, document source
  priority and rejection criteria.
- Do not store secrets, cookies, storage values, auth headers, raw private
  payloads, or user-specific state in shared skills.

A finding is worth adding when it would save the next agent from rediscovering a
selector, route, wait condition, source priority, auth-state trap, UI quirk,
backend limitation, or confidence caveat.

The artifact should describe the final reusable rule, not the history of how it
was discovered.

## Canonical Skill Artifacts

Shared skill files are final-state operating manuals. Write the reusable rule
that should guide the next run, with enough source context to apply it safely.

Skill artifacts may include:

- current URL patterns, selectors, backend routes, source priority, and field
  contracts
- auth/session context required by the workflow
- confidence caveats and degraded-evidence rules
- failure modes, traps, and rejection criteria
- comments that explain behavior, invariants, or source semantics

Keep edit chronology, update notes, preservation markers, replacement
instructions, and run narration outside shared skill artifacts. Put those in the
chat response, patch envelope, PR description, or a file whose purpose is
history or audit logging.

## Domain Skill Reorganization Workflow

Use this when a domain or interaction skill is hard to read cold, has unclear
workflow/source/schema/script ownership, or the user asks to clean up a skill's
logical structure. The objective is to make the skill answer a new agent's first
questions without changing the intended workflow unless the task explicitly
authorizes behavior changes.

Start with a full reusable-surface inventory, not a sample:

1. Read the skill entry point, overview/router docs, workflow/playbook docs,
   schema or contract docs, script indexes, local guidance files, status docs,
   plans, and package metadata.
2. Exclude `.private-data/`, `.session-store/`, generated `outputs/`, caches,
   and build artifacts from broad searches. Inspect them only when a specific
   run-artifact question requires it, and never move private details into shared
   docs.
3. Classify every file by responsibility: router, workflow/playbook, schema or
   row contract, executable index, runnable script, helper script, fixture,
   status, plan, generated artifact, or private artifact.
4. Build an evidence-backed map before proposing edits. Do not assume the
   current hierarchy is wrong just because it is unfamiliar.

Analyze two hierarchies independently, then reconcile them:

| Hierarchy | Preferred shape | Owns |
|---|---|---|
| Control flow | `skill -> user intent -> desired outcome -> workflow doc -> run path -> evidence rows -> decision helper -> recommendation/action -> experiment/outcome review` | What the agent should do next |
| Source/evidence family | `skill -> source/evidence family -> logical layer -> artifact bucket -> concrete doc/script/schema/artifact` | Which source is allowed to prove which facts |

For cold LLM use, user intent should usually be the first router. Source or
evidence family is a guardrail after the task is understood, not the first thing
the agent must guess. Expanded matrices are useful only when subordinate to the
canonical cold-start router.

Use these ownership rules to remove duplicated authority:

| Artifact type | Authoritative for | Not authoritative for |
|---|---|---|
| Skill entry point | Where to start, major task buckets, safety boundaries | Detailed row contracts or script internals |
| Overview/router | Intent routing, cross-file handoffs, hierarchy map, common entry points | Exhaustive executable inventory |
| Workflow/playbook docs | Control paths, refusal guards, judgement rules, next hops | Durable schema contracts |
| Schema/contract docs | Durable row/output contracts, field meanings, row ownership | Collection strategy or business judgement |
| Scripts README/index | Runnable vs helper-only classification, invocation, prerequisites, outputs, refusal modes | Workflow policy or schema semantics |
| Data-quality/provenance docs | Source compatibility, receipts, joins, freshness, quarantine, redaction | Accepted recommendations or experiments |
| Decisioning/experiment docs | Accepted recommendations, action logs, rollback, experiment design, outcome review | Collection, schema, or source authority |

When scripts exist, normalize the executable index around operational questions:

- script role: runner, collector, probe, guard, exporter, or helper-only
- control-flow stage: intake, source selection, capability check, collection,
  validation/provenance, normalization, decision gate, brief, action,
  experiment, or outcome review
- source/evidence family or `n/a` for control-plane tools
- governing workflow doc
- reads, produces, and refusal conditions

If a script is imported by other scripts, label it helper-only unless it has a
documented safe direct invocation. If an output row, artifact, or receipt has no
durable schema home, either move the contract to the right schema doc or mark it
as an explicit exception with an owner and reason.

Prefer logical reorganization over path migration unless the task explicitly
authorizes file moves. Existing scripts, tests, package data, and references
often assume flat markdown files or stable `scripts/*.py` paths.

For each major workflow or playbook, add a short ownership header when missing:

- `Use this when`: the user intent or desired outcome that enters the doc
- `Owns`: the control paths, judgement rules, or evidence decisions it owns
- `Does not own`: the schema, script, data-quality, or decision layer it should
  hand off to
- `Next hop`: the likely router, schema, script index, or decision doc after it

Before finishing, verify the reorganization with targeted checks:

- markdown references resolve for the touched reusable docs
- every script is represented in the executable index or explicitly excluded
- every documented row/output resolves through a schema/contract index or named
  exception
- stale first-step language is gone, especially source-first wording that
  conflicts with the cold-start router
- ambiguous source labels map to a canonical evidence family or a control-plane
  tool bucket
- redaction/private-data scans pass when the skill provides them
- ignored/private/generated directories remain outside reusable guidance
- `git diff --check` passes

Report the result as an architecture map, findings with file/line evidence,
cleanup performed, level-by-level control-flow and source-family buckets, and
verification evidence. If de-duplication or merging was part of the cleanup,
name exactly which authority moved and which file now owns it.
