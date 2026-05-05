# Food Delivery Bulk Extraction Scripts

Extract all vendors, products, and prices from DoorDash and Uber Eats.

## Prerequisites

- SeleniumBase installed in `.venv/` (run from repo root)
- Authenticated cookies in `.private-data/` (captured via `overview.md` session flow)
- Both platforms require SeleniumBase UC Mode — standard CDP/browser-harness cannot access them

## Quick Start

```bash
REPO=/Users/gwizz/.claude/skills/browser-harness
PY=$REPO/.venv/bin/python3
S=$REPO/agent-workspace/domain-skills/food-delivery/scripts

# Phase 2: Enumerate restaurants (browse-all mode, covers all categories)
$PY $S/enumerate_restaurants.py --platform doordash --output $S/dd_restaurants.json
$PY $S/enumerate_restaurants.py --platform ubereats --output $S/ue_restaurants.json

# Phase 3: Extract menus (start with --limit for testing)
$PY $S/extract_menus.py --input $S/dd_restaurants.json --output $S/dd_menus.json --limit 5
$PY $S/extract_menus.py --input $S/ue_restaurants.json --output $S/ue_menus.json --limit 5

# Phase 3 continued: full extraction with checkpointing
$PY $S/extract_menus.py --input $S/dd_restaurants.json --output $S/dd_menus.json --resume $S/dd_menu_checkpoint.json

# Phase 4: Export
$PY $S/export.py --restaurants $S/dd_restaurants.json $S/ue_restaurants.json \
                  --menus $S/dd_menus.json $S/ue_menus.json --output $S/food_data
```

## Commands

### `enumerate_restaurants.py` — Phase 2: Restaurant Enumeration

Two modes:
- `--mode browse` (default): Single "food" query, scroll through all categories. Most efficient.
- `--mode search`: Search by individual cuisine queries. Legacy, higher dedup overhead.

```bash
# Browse all (default, recommended)
$PY $S/enumerate_restaurants.py --platform doordash --output dd.json

# Search mode with specific queries
$PY $S/enumerate_restaurants.py --platform doordash --mode search --query pizza burgers thai --output dd.json

# Resume from checkpoint
$PY $S/enumerate_restaurants.py --platform doordash --output dd.json --resume checkpoint.json
```

**Options:**
- `--mode browse|search` — browse=all categories via "food" query (default), search=by cuisine terms
- `--query` — Search terms (only used with `--mode search`)
- `--resume` — Resume from checkpoint file
- `--output` — Output JSON path

**Output fields:** platform, store_id, slug, url, name, rating, delivery_time_min, delivery_time_max, delivery_fee, promo_badge, discovered_at

**Proven results (DoorDash, Melbourne AU):**
- 743 restaurants in 216s via browse mode
- 100% name fill, 100% delivery_fee, 60% rating, 47% delivery_time
- Chao1 estimator suggests ~2000+ unseen — search results likely capped

### `extract_menus.py` — Phase 3: Menu Extraction

DoorDash: Extracts from Next.js embedded `StorePageCarouselItem` data in page source.
Uber Eats: DOM scraping fallback.

```bash
# Test on a few restaurants first
$PY $S/extract_menus.py --input dd.json --output dd_menus.json --limit 5

# Full extraction with checkpointing
$PY $S/extract_menus.py --input dd.json --output dd_menus.json --resume menu_checkpoint.json

# Resume after interruption
$PY $S/extract_menus.py --input dd.json --output dd_menus.json --resume menu_checkpoint.json
```

**Options:**
- `--input` — Restaurant list JSON from Phase 2
- `--limit` — Max restaurants to process (for testing)
- `--resume` — Resume from checkpoint
- `--output` — Output JSON path

**Output fields:** platform, store_id, store_name, category, item_name, item_price, description, popular_badge, customization_count, image_url, extracted_at

**Proven results (DoorDash, 50 restaurants):**
- 1,099 menu items in 670s (~13s per restaurant)
- 100% fill rate on name, price, description, image
- ~22 items per restaurant average
- No scrolling needed — all data in initial page source

### `export.py` — Phase 4: Export

Merges, deduplicates, and exports data from both platforms.

```bash
$PY $S/export.py --restaurants dd.json ue.json --menus dd_m.json ue_m.json --output food_data
```

**Output files:**
- `food_data.csv` — Flat CSV, one row per menu item joined with restaurant metadata
- `food_data.json` — Structured JSON with restaurants as keys, menus nested
- `food_data_coverage.json` — Field fill rates

**Dedup keys:** restaurants by `(platform, store_id)`, menus by `(platform, store_id, item_name)`

### `discover_apis.py` — Phase 1: API Discovery (already run)

Both platforms have private APIs requiring POST + CSRF tokens. No HTTP-replayable endpoints. DOM/Next.js extraction path confirmed.

## Rate Limits

| Action | Delay |
|---|---|
| Between search pages | 2-5s random |
| Between restaurant pages | 2-5s random |
| Every 15 restaurants | 10-30s break |
| Menu extraction per restaurant | ~13s (no scroll needed for DoorDash) |
| Session limit | 200 requests / 3600s (browse), 100 requests / 3600s (menus) |

## Resumption

Both `enumerate_restaurants.py` and `extract_menus.py` support `--resume` with checkpoint files. If interrupted (cookie expiry, block, ctrl-c), re-run with the same checkpoint to continue.

Cookies are re-harvested at the end of each script run. DoorDash `cf_clearance` expires ~30min — for runs exceeding 50 restaurants, expect at least one cookie refresh cycle.
