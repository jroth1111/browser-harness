# Domain Skills — Discovery Index

This file is a discovery index, not a routing destination. SKILL.md routes
directly to `domain-skills/<site>/overview.md` or the first .md file in a
domain folder. Use this only when you need to discover which domain skills
exist, find the cold-read path for a rich bundle, or understand the full
folder inventory.

## Cold Start

1. Identify the site or domain folder.
2. Open the folder's `overview.md` or `README.md` when present.
3. If no overview exists, open the most specific markdown file in that folder.
4. Use `../interaction-skills/README.md` only for reusable browser mechanics, backend
   selection, session continuity, data display, or skill-learning promotion.
5. Keep `.private-data/`, `.session-store/`, `outputs/`, caches, and generated
   reports out of reusable guidance.

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
| Rich multi-file bundles | `airbnb/`, `youtube/` | Intent routers, workflows, scripts/helpers, fixtures, schemas, receipts, reports |
| Overview-led single bundle | `atlas/overview.md` | Authenticated Atlas routes, filters, GraphQL hints, auth caveats |
| Multi-document small folders | `facebook/`, `github/`, `medium/` | Related task variants under one site family |
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

## Full Domain Folder Inventory

`ai-chat-archive`, `airbnb`, `amazon`, `archive-org`, `arxiv`, `arxiv-bulk`, `atlas`,
`booking-com`, `capterra`, `centilebrain`, `coingecko`, `coinmarketcap`,
`coursera`, `craigslist`, `crossref`, `dev-to`, `duckduckgo`, `ebay`, `etsy`,
`eventbrite`, `facebook`, `framer`, `fred`, `g2`, `genius`, `github`,
`glassdoor`, `gmail`, `goodreads`, `gutenberg`, `hackernews`, `howlongtobeat`,
`imdb`, `itch-io`, `job-boards`, `letterboxd`, `linkedin`, `macrotrends`,
`medium`, `metacritic`, `musicbrainz`, `nasa`, `news-aggregation`,
`open-library`, `openalex`, `openstreetmap`, `package-registries`,
`polymarket`, `producthunt`, `pubmed`, `quora`, `rawg`, `realestate-com-au`,
`reddit`, `rest-countries`, `salesforce`, `sec-edgar`, `soundcloud`,
`spotify`, `spreadshirt`, `stackoverflow`, `steam`, `thetechgeeks`, `tiktok`,
`tradingview`, `trello`, `trustpilot`, `walmart`, `wayback-machine`,
`weather`, `wellfound`, `world-bank`, `youtube`, `zillow`.

## Ownership Rules

- Domain folders own site-specific routes, selectors, APIs, exports, source
  priority, traps, and field semantics.
- Schema or surface-map files own durable row/output contracts.
- Scripts README files own runnable vs helper-only classification where a
  domain bundle has scripts.
- Interaction skills own reusable browser mechanics and cross-domain control
  flow.
- Root `../SKILL.md` owns the whole-harness cold-start router.
