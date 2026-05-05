# Domain Skills — Discovery Index

This file serves two purposes: a discovery index for existing domain skills,
and the routed destination for "Build a scraper for a new site" (see "Creating
a New Domain Skill" below). SKILL.md also routes directly to
`domain-skills/<site>/overview.md` or the first .md file in a domain folder for
known sites. Use the discovery index when you need to find which domain skills
exist, the cold-read path for a rich bundle, or the full folder inventory.

## Cold Start

1. Identify the site or domain folder.
2. Open the folder's `overview.md` or `README.md` when present.
3. If no overview exists, open the most specific markdown file in that folder.
4. Use `../interaction-skills/README.md` only for reusable browser mechanics, backend
   selection, session continuity, data display, or skill-learning promotion.
5. Keep `.private-data/`, `.session-store/`, `outputs/`, caches, and generated
   reports out of reusable guidance.
6. Use `maturity-tiers.md` and `domain_skill_maturity.evaluate_domain_skill(...)`
   when deciding whether a domain skill is documented, scripted, fixture-tested,
   live-smoked, or packaged-safe.

## Creating a New Domain Skill

Follow these phases in order. Each phase produces committed output before the
next begins.

### Phase 1: Explore

Follow `../interaction-skills/data-source-exploration.md` — it defines the full
source discovery order (backend testing, export/API candidates, browser
extraction, selector discovery). Its step 5 covers selector discovery and
four-state extraction for browser-based extraction.

### Phase 2: Build

1. Create `domain-skills/<site>/` with `overview.md` containing confirmed URL
   patterns, source classification, DOM selectors, anti-bot classification, and
   gotchas.

   **Anti-bot classification.** Record what protection the site uses (Cloudflare
   Turnstile, Datadome, Akamai, Kasada, none detected) and which backend path
   works. Three tiers:

   ```
   1. curl_cffi(url)                    # impersonates real TLS fingerprint
      ok? done. blocked? → 2

   2. CDP browser + wait_for_content()  # full Chrome rendering
      ok? done. turnstile? → solve_turnstile() (fix within this tier)
      turnstile unsolved or bot detected? → 3

   3. patchright stealth_session()       # different browser backend entirely
      ok? done. failed? → stop, report
   ```

   Record the result as a dated finding in overview.md:

   ```
   Field-tested against example.com on 2026-05-05.
   No anti-bot protection detected. curl_cffi sufficient for all pages.
   ```

   or:

   ```
   Field-tested against example.com on 2026-05-05.
   Cloudflare Turnstile on all routes. CDP path blocked. stealth_session() required.
   ```

   The domain skill imports only the backend that works — no runtime cascade.
2. If the skill has scripts, create `scripts/search.py` (or equivalent) with
   JS snippet generation, merge/filter, and CSV export commands. For the
   localStorage accumulation pattern (accumulate results across paginated
   page loads, dedup by URL), see `aliexpress/scripts/search.py` for the
   plan/extract-js/merge command pattern, or `ebay/scripts/search.py`
   for a self-contained batch orchestrator.
3. Add a `scripts/README.md` documenting commands, CSV columns, and invocation.
4. Add a `README.md` with quick-start usage examples.
5. Add the site name to the "Full Domain Folder Inventory" list below, in
   alphabetical order. This makes the site discoverable by future agents
   scanning the index.

### Phase 3: Test

1. Run the skill end-to-end on a real query. Use `wait_for_content()` after
   each navigation — check the `block` field before running extraction JS.
2. After the first page of each type: validate primary key fields have non-null
   values. Stop and redo selector discovery if the primary field is all-null.
3. For browser-based extraction: run coverage probes and field triage per
   `../interaction-skills/extraction-coverage.md` Phase 3 section. Fix BROKEN
   selectors before declaring done.
4. Verify CSV output has correct columns and filtering.
5. Record the anti-bot classification in overview.md: protection type, working
   backend path, and date of observation. This is the persistent finding that
   prevents future sessions from re-discovering it.

### Phase 4: Extract Generalizable Lessons

This phase runs after the skill is complete and tested. Its goal is to find
improvements that apply to *any* future domain skill, not just the one you
built.

**Step 1: Inventory and group.** Review the full session transcript — this is
the current conversation, or the JSONL file at
`~/.claude/projects/<project-hash>/<session-id>.jsonl` if the session was
compacted or resumed. List every mistake, discovery, and workaround. Then
group related items that share a root cause into lesson clusters. Each cluster
may contain multiple types:

- **Conceptual insight** — a mental model or framing that changes how you
  approach a class of problems (e.g., "empty string is ambiguous between
  absent and failed")
- **Procedural fix** — a step that should be added to an existing workflow
  (e.g., "probe CSS selectors via js() before writing extraction JS")
- **Gotcha** — a tool/API/platform-specific trap that will bite you again
  (e.g., "js() args are element UIDs, not function parameters")

A single root cause can produce all three types. Group them into one cluster
rather than splitting across categories.

For each cluster, ask: "Would this happen again when building a domain skill
for a completely different site?" If it depends on this site's specific DOM
structure, URL patterns, or page layout, mark it site-specific. If it applies
regardless of the site, mark it generalizable.

If nothing is generalizable, stop here. Document site-specific learnings in the
domain skill files instead.

**Step 2: Check existing coverage.** For each generalizable cluster, grep for
keywords related to that lesson across `interaction-skills/`:

```bash
rg -i "keyword1\|keyword2" interaction-skills/
```

Check: is any part already covered? Does anything contradict it? Is there a
natural home for it in an existing file? Also read `surface-map-pattern.md` if
the lesson relates to surface maps or verification. Note what's already there
before writing anything new.

**Step 3: Write.** For each generalizable cluster not already covered, write
one document per cluster regardless of how many types it contains:

- If the cluster has a conceptual insight, it becomes a standalone document in
  `interaction-skills/`. Structure: the problem, when it happens, how to
  recognize it, the fix. Name the file after the problem domain, not the
  solution. Include procedural fixes and gotchas from the same cluster as
  sections within this document.
- If the cluster is purely procedural (no conceptual insight), add it to the
  existing workflow document where the step naturally fits (e.g.,
  `data-source-exploration.md` for source discovery steps,
  `product-search.md` for marketplace search steps).
- If the cluster is purely a gotcha, add it to the most specific reference file
  where the reader would encounter that tool/API. If no file fits, add to
  `../interaction-skills/README.md`.

**Step 4: Cold-read gate.** Before placing cross-references, cold-read
everything you wrote. For each new document or edit, ask: "If I arrived at this
file with zero context about the session that produced it, would I understand
why this exists, when to apply it, and what to do?" If the answer is no for any
piece, rewrite that piece. Do not proceed until every piece passes.

**Step 5: Cross-reference.** Place short pointers (one sentence, file name
only) in the existing files where a reader would naturally need this lesson. Do
not inline the lesson content. Verify each cross-reference makes sense in
context by reading the surrounding paragraph.

**Step 6: Update indexes.** If you created a new file in
`../interaction-skills/`, add it to the "Complete File Inventory" list in
`../interaction-skills/README.md` and to the "Buckets" table if it fits a new
or existing category. Also add it to the router table in `../SKILL.md` if it
matches an existing task pattern.

**Step 7: Commit.** One commit per new document, one commit for all
cross-references and index updates together.

For the exhaustive top-level inventory, run:

```bash
find domain-skills -mindepth 1 -maxdepth 1 -type d | sort
```

For one site, run:

```bash
rg --files domain-skills/<site>
```

## Buckets

| Bucket | Folders/files | Owns |
|---|---|---|
| Shared contracts | `surface-map-pattern.md`, `surface-map.schema.json`, `skill-learning-candidate.schema.json` | Cross-domain schema/process contracts |
| Rich multi-file bundles | `airbnb/`, `dating/`, `food-delivery/`, `youtube/`, `ai-chat-archive/` | Intent routers, workflows, scripts/helpers, fixtures, schemas, receipts, reports |
| Overview-led single bundle | `atlas/overview.md` | Authenticated Atlas routes, filters, GraphQL hints, auth caveats |
| Multi-document small folders | `facebook/`, `github/`, `medium/`, `z2u/` | Related task variants or multi-file site skills with scripts |
| Single-file site skills | Most remaining folders | One concise scraping/action workflow for the site |
| Placeholders | `salesforce/`, `spreadshirt/` | Reserved folders with no reusable workflow yet |
| Private/generated local state | `.private-data/`, `.session-store/`, `outputs/`, `__pycache__/` | Local run artifacts only; never authoritative reusable guidance |

## Rich Bundle Cold-Read Paths

When landing on a rich domain with no prior context, read progressively.

### Airbnb (`airbnb/`)
1. `overview.md` — intent router, source guardrails, expanded routing matrix
2. `scripts/README.md` — only when you need to run, probe, or validate
3. `host-sources.md` — logged-in host inventory and export workflows
4. `public-market.md` — logged-out guest-visible comps and search rank
5. `data-quality.md` — receipts, source classes, quarantine, provenance

### YouTube (`youtube/`)
1. `overview.md` — operating rules, primitive selection, surface-map registry
2. `scraping.md` — extraction workflows by data type
3. `generated-surfaces.md` — machine-readable surface summary
4. `scripts/` — only when a script is named by the workflow docs

### AI Chat Archive (`ai-chat-archive/`)
1. `overview.md` — provider router, required run shape, completion rules
2. `storage-decision.md` — SQLite canonical store decisions
3. `archive-layout.md` — database schema and export layout
4. `provider-surfaces.md` — provider-specific discovery rules
5. `sync-strategy.md` — resume, incremental, delta behavior
6. `verification.md` — completion and integrity probes

### Atlas (`atlas/`)
1. `overview.md` — routes, filters, GraphQL bootstrap, auth notes

### Dating (`dating/`)
1. `overview.md` — intent router, pipeline summary, cold-start guide
2. `references/copilot-instructions.md` — AI personality, objectives, quality contract
3. `onboarding.md` — user interview flow (run before any platform automation)
4. `chat-audit.md` — extract voiceprint and outcome patterns from existing Tinder/Hinge/Feeld conversations
5. `references/research-user.md` — deep research prompt for user profiling from digital footprint
6. `pipeline.md` — 7-stage pipeline definitions and state transitions
7. `references/scoring.md` — rubric scoring for profiles and conversations
8. `safety.md` — consent gates, rate limits, anti-detection protocols
9. `platforms/tinder.md` — Tinder-specific selectors and flows
10. `references/` — 12 copilot reference files for AI decision layer
11. `evals/` — regression prompts for behavior testing

### Food Delivery (`food-delivery/`)
1. `overview.md` — intent router, cross-platform comparison workflow, cold-start guide
2. `safety.md` — consent gates for orders, rate limits, anti-detection
3. `platforms/ubereats.md` — Uber Eats specific selectors and flows
4. `platforms/doordash.md` — DoorDash specific selectors and flows

## Full Domain Folder Inventory

`ai-chat-archive`, `airbnb`, `aliexpress`, `amazon`, `archive-org`, `arxiv`, `arxiv-bulk`, `atlas`,
`booking-com`, `capterra`, `centilebrain`, `coingecko`, `coinmarketcap`, `coles_card`, `coursera`, `craigslist`,
`crossref`, `dating`, `dev-to`, `duckduckgo`, `ebay`, `etsy`,
`eventbrite`, `facebook`, `food-delivery`, `framer`, `fred`, `g2`, `g2g`, `genius`, `github`,
`glassdoor`, `gmail`, `goodreads`, `gutenberg`, `hackernews`, `howlongtobeat`,
`imdb`, `itch-io`, `job-boards`, `letterboxd`, `linkedin`, `macrotrends`,
`medium`, `metacritic`, `musicbrainz`, `nasa`, `news-aggregation`,
`open-library`, `openalex`, `openstreetmap`, `package-registries`,
`polymarket`, `producthunt`, `pubmed`, `quora`, `rawg`, `realestate-com-au`,
`reddit`, `rest-countries`, `salesforce`, `sec-edgar`, `soundcloud`,
`spotify`, `spreadshirt`, `stackoverflow`, `steam`, `thetechgeeks`, `tiktok`,
`tradingview`, `trello`, `trustpilot`, `walmart`, `wayback-machine`,
`weather`, `wellfound`, `world-bank`, `youtube`, `z2u`, `zillow`.

## Ownership Rules

- Domain folders own site-specific routes, selectors, APIs, exports, source
  priority, traps, and field semantics.
- Schema or surface-map files own durable row/output contracts.
- Scripts README files own runnable vs helper-only classification where a
  domain bundle has scripts.
- Interaction skills own reusable browser mechanics and cross-domain control
  flow.
- Root `../SKILL.md` owns the whole-harness cold-start router.
