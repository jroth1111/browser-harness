# Food Delivery Bulk Extraction Scripts

Extract all vendors, products, and prices from DoorDash and Uber Eats.

## Prerequisites

- SeleniumBase installed in `.venv/` (run from repo root)
- Authenticated cookies in `.private-data/` (captured via `overview.md` session flow)
- Both platforms require SeleniumBase UC Mode — standard CDP/browser-harness cannot access them

## Quick Start

```bash
# From repo root:
REPO=/Users/gwizz/.claude/skills/browser-harness
PYTHON=$REPO/.venv/bin/python3
SCRIPTS=$REPO/domain-skills/food-delivery/scripts

# Phase 2: Enumerate restaurants
$PYTHON $SCRIPTS/enumerate_restaurants.py --platform doordash --output dd_restaurants.json
$PYTHON $SCRIPTS/enumerate_restaurants.py --platform ubereats --output ue_restaurants.json

# Phase 3: Extract menus (start small with --limit)
$PYTHON $SCRIPTS/extract_menus.py --input dd_restaurants.json --output dd_menus.json --limit 5
$PYTHON $SCRIPTS/extract_menus.py --input ue_restaurants.json --output ue_menus.json --limit 5

# Phase 4: Export
$PYTHON $SCRIPTS/export.py --restaurants dd_restaurants.json ue_restaurants.json --menus dd_menus.json ue_menus.json --output food_data
```

## Commands

### `discover_apis.py` — Phase 1: API Discovery

Discovers internal JSON APIs. Already run — results in `lib/api_discovery_*.json`.

```bash
$PYTHON $SCRIPTS/discover_apis.py --platform doordash
$PYTHON $SCRIPTS/discover_apis.py --platform ubereats
$PYTHON $SCRIPTS/discover_apis.py --platform both
```

Result: Both platforms have private APIs requiring POST + CSRF tokens. DOM extraction path confirmed.

### `enumerate_restaurants.py` — Phase 2: Restaurant Enumeration

Searches by cuisine and scrolls through results to find all restaurants.

```bash
$PYTHON $SCRIPTS/enumerate_restaurants.py --platform doordash --output dd.json
$PYTHON $SCRIPTS/enumerate_restaurants.py --platform ubereats --query "pizza burgers thai" --output ue.json
$PYTHON $SCRIPTS/enumerate_restaurants.py --platform doordash --output dd.json --resume checkpoint.json
```

**Options:**
- `--query` — Search terms (default: 10 popular cuisines)
- `--resume` — Resume from checkpoint file
- `--output` — Output JSON path

**CSV columns:** platform, store_id, slug, url, name, rating, delivery_time_min, delivery_time_max, delivery_fee, promo_badge, discovered_at

### `extract_menus.py` — Phase 3: Menu Extraction

Navigates to each restaurant and extracts all menu items.

```bash
$PYTHON $SCRIPTS/extract_menus.py --input dd.json --output dd_menus.json
$PYTHON $SCRIPTS/extract_menus.py --input dd.json --output dd_menus.json --limit 10
$PYTHON $SCRIPTS/extract_menus.py --input dd.json --output dd_menus.json --resume menu_checkpoint.json
```

**Options:**
- `--input` — Restaurant list JSON from Phase 2
- `--limit` — Max restaurants to process (for testing)
- `--resume` — Resume from checkpoint
- `--output` — Output JSON path

**CSV columns:** platform, store_id, store_name, category, item_name, item_price, description, popular_badge, customization_count, image_url, extracted_at

### `export.py` — Phase 4: Export

Merges, deduplicates, and exports data from both platforms.

```bash
$PYTHON $SCRIPTS/export.py --restaurants dd.json ue.json --menus dd_m.json ue_m.json --output food_data
```

**Output files:**
- `food_data.csv` — Flat CSV, one row per menu item joined with restaurant metadata
- `food_data.json` — Structured JSON with restaurants as keys, menus nested
- `food_data_coverage.json` — Field fill rates

## Rate Limits

| Action | Delay |
|---|---|
| Between search pages | 2-5s random |
| Between menu scrolls | 1-3s random |
| Between restaurant pages | 2-5s random |
| Every 15 restaurants | 10-30s break |
| Session limit | 100 restaurants, 60 min |

## Resumption

Both `enumerate_restaurants.py` and `extract_menus.py` support `--resume` with checkpoint files. If a session is interrupted (cookie expiry, block, ctrl-c), re-run with the same checkpoint to continue.

Cookies are re-harvested at the end of each script run. If cookies expire mid-run, the script will detect the block and skip to the next item.
