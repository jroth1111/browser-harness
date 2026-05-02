# Domain Skills

Domain skills are site-specific operating manuals. Use them after
`../SKILL.md` decides the task is about a known site, or after an interaction
skill discovers that a source, selector, route, or workflow is site-specific.

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

## Rich Bundle Entry Points

| Folder | Start here | Notes |
|---|---|---|
| `airbnb/` | `airbnb/overview.md` | Intent-first host intelligence router, workflow docs, schema docs, script index, fixtures, and private/session separation |
| `youtube/` | `youtube/overview.md` | YouTube workflow routing, primitives, surface map, fixtures, receipts, reports, and scripts |
| `ai-chat-archive/` | `ai-chat-archive/overview.md` | Logged-in AI chat archive workflow, SQLite-only canonical layout, incremental sync, and verification rules |
| `atlas/` | `atlas/overview.md` | Authenticated recruitment SaaS notes; single overview rather than a script bundle |

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
- Root `../SKILL.md` owns the whole-harness cold-start router and executable index.
