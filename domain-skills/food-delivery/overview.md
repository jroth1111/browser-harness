# Food Delivery — Overview

Automated extraction from Uber Eats and DoorDash via the Patchright stealth session helper.
Enumerate restaurants, extract full menus (name, price, description, image), compare across platforms.

## Prerequisites

- Stealth browser dependencies in `.venv/` at repo root. Run scripts via `.venv/bin/python3`.
- Authenticated cookies in `.private-data/` (see session management below).
- Both platforms block standard CDP-connected browsers — use the food-delivery stealth session helper.

## Cold-start sequence

1. Check cookies exist in `.private-data/`. If not, run cookie capture below.
2. Identify platform. Read `platforms/<platform>.md` for extraction details.
3. Identify intent. Bulk extraction uses `scripts/` pipeline. Interactive use goes through the stealth session helper.
4. Execute.

## Bulk extraction pipeline

Four phases, each a standalone script with checkpoint/resume:

```
Phase 1: API Discovery (already run — no public APIs, DOM path confirmed)
Phase 2: Restaurant enumeration  ->  dd_restaurants.json / ue_restaurants.json
Phase 3: Menu extraction         ->  dd_menus.json / ue_menus.json
Phase 4: Export CSV + JSON        ->  food_data.csv / food_data.json
```

```bash
REPO=/Users/gwizz/.claude/skills/browser-harness
PY=$REPO/.venv/bin/python3
S=$REPO/domain-skills/food-delivery/scripts

# Phase 2: Enumerate (browse-all mode, single query covers all categories)
$PY $S/enumerate_restaurants.py --platform doordash --output $S/dd_restaurants.json
$PY $S/enumerate_restaurants.py --platform ubereats --output $S/ue_restaurants.json

# Phase 3: Extract menus (--limit for testing, --resume for checkpointing)
$PY $S/extract_menus.py --input $S/dd_restaurants.json --output $S/dd_menus.json --limit 5
$PY $S/extract_menus.py --input $S/ue_restaurants.json --output $S/ue_menus.json

# Phase 4: Export
$PY $S/export.py --restaurants $S/dd_restaurants.json $S/ue_restaurants.json \
                  --menus $S/dd_menus.json $S/ue_menus.json --output $S/food_data
```

### Proven performance

| Metric | DoorDash | Uber Eats |
|---|---|---|
| Restaurants enumerated | 743 in 216s | 82 in 37s |
| Menu items (50 restaurants) | 1,099 in 670s | Not yet tested |
| Avg items/restaurant | 22 | — |
| Name fill rate | 100% | 99% |
| Price fill rate (menus) | 100% | — |
| Description fill rate (menus) | 100% | — |
| Image fill rate (menus) | 100% | — |

### Timing

- Menu extraction: ~13s per restaurant (no scrolling needed for DoorDash)
- Restaurant enumeration: ~16s per restaurant for browse+scroll
- Cookies expire ~30min (DD `cf_clearance`), scripts re-harvest at end
- Checkpoint every 5 restaurants, break every 15 restaurants

## Key invariants

- Never place an order without explicit user confirmation.
- Never handle login credentials or payment information.
- Stop on any block, CAPTCHA, or auth redirect.
- Human-like timing between all automated actions.
- Delivery address is location-dependent — all data is for the address in the user's account.

## File map

```
overview.md              <- you are here
platforms/doordash.md    <- DoorDash extraction details (field-tested)
platforms/ubereats.md    <- Uber Eats extraction details
scripts/
  enumerate_restaurants.py   Phase 2: browse-all + scroll enumeration
  extract_menus.py           Phase 3: Next.js data + DOM fallback
  export.py                  Phase 4: merge, dedup, CSV/JSON
  discover_apis.py           Phase 1: already run, no public APIs
  README.md                  Full command reference
  lib/
    doordash.py               URLs, browse_url(), search_url()
    ubereats.py               URLs, browse_url(), search_url()
    stealth_session.py        Patchright session, cookie inject/harvest, auth check
    crawl_state.py            CrawlState dedup + SafetyGate rate limits
.private-data/               Session cookies (gitignored)
  doordash_cookies.json
  ubereats_cookies.json
```

## Accessing platforms

Both platforms block standard CDP-connected browsers (browser-harness, MCP DevTools). Use the Patchright stealth helper.

```python
from lib.stealth_session import create_stealth_session

s = create_stealth_session("doordash")
try:
    print(s.js("document.title"))
finally:
    s.close()
```

### Critical: stealth JS uses browser expressions or IIFEs

Patchright's `page.evaluate()` accepts expressions and functions. Wrap multi-statement JavaScript in an IIFE:

```python
# Good:
js = '(() => { const items = []; return JSON.stringify(items); })()'

# Also good:
js = 'document.title'
```

Variables that need dynamic values must be baked into the string via `.replace()`:
```python
js = 'var baseUrl = BASEURL; ...'.replace("BASEURL", json.dumps(base_url))
raw = s.js(js)
```

## Session management

### First-time setup: capture cookies

```python
import json, time, os
from pathlib import Path
from lib.stealth_session import create_stealth_session

s = create_stealth_session("doordash")
try:
    time.sleep(2)
    # User logs in manually, then: touch /tmp/dd_done
    while not os.path.exists("/tmp/dd_done"):
        time.sleep(1)
    os.remove("/tmp/dd_done")
    cookies = s.cookies()
    Path(".private-data/doordash_cookies.json").write_text(json.dumps(cookies))
finally:
    s.close()
```

Same pattern for Uber Eats with `/tmp/ue_done` signal file.
`input()` does not work from heredoc stdin — use signal files.

### Restoring a session

Handled by `lib/stealth_session.py:create_stealth_session(platform)` — opens platform, injects cookies, and supports auth checks.

### Cookie expiry

- DoorDash `cf_clearance` expires ~30min. Other session cookies may last longer.
- Uber Eats session cookies typically last days.
- Scripts re-harvest cookies at end of each run. Use `--resume` to continue if interrupted.
