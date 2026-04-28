# Data Display

Use this when you want a quick, polished visual of any scraped dataset — a
single self-contained HTML file with tables, charts, KPIs, and a JSON tree
viewer. Works on `.json`, `.jsonl`, and `.csv` files produced by any domain
skill's collection scripts.

## What belongs here

Generalizable:

- file-format detection and record extraction
- schema introspection and field-type inference
- the renderer and its auto-detect rules
- override knobs

Site-specific display logic belongs in `domain-skills/<site>/`:

- which file is the canonical snapshot for a given question
- site-specific field labels or display overrides
- custom chart selections or groupings

## Usage

```bash
browser-harness <<'PY'
from data_display import render_dataset
# Render a listing snapshot and open in browser
print(render_dataset(
    "domain-skills/airbnb/.private-data/listing-collections/airbnb-live-listings-20260427T080658Z.json",
    open_browser=True,
))
PY
```

`render_dataset(path, out=None, view=None, open_browser=False)` returns the
absolute path to the written HTML file.

- `path` — source file (`.json` / `.jsonl` / `.csv`). Required.
- `out` — override the output path. Default: same directory as source, same
  stem, `.html` extension.
- `view` — force the initial view: `table`, `line`, `bar`, `kpis`, `tree`.
  Default: auto-pick the first eligible chart view.
- `open_browser` — `True` to open the result immediately.

## File-format detection

| Suffix | Strategy |
|---|---|
| `.json` | Walk for the records array. Key order: `records`, `rows`, `data`, `items`, `results` — first non-empty list-of-dicts wins. Top-level list treated as the records. Everything else in the wrapper becomes the report header metadata. |
| `.jsonl` | One JSON object per line. Blank lines skipped. Non-dict values wrapped as `{value: …}`. |
| `.csv` | `csv.DictReader`. Numeric and boolean strings auto-coerced. |

## Auto-detect rules

The introspector samples the first 500 rows and tags each top-level field.

| Kind | Rule |
|---|---|
| `time` | Name matches `*_at`, `*_date`, `date`, `ds`, `timestamp`, `created`, `updated`, `observed`, or ≥ 90 % of non-null values start with an ISO date pattern. |
| `numeric` | `int`/`float` in ≥ 90 % of non-null. Distinct > 10 → measure (line-Y, KPIs). Distinct ≤ 10 → categorical-numeric (bar). |
| `categorical` | String, distinct ≤ 30, distinct ≤ 50 % of non-null, non-null ≥ 10. |
| `bool` | Boolean in ≥ 90 % of non-null. |
| `url` | String matching `https?://` in ≥ 90 %. Rendered as link. |
| `image` | URL ending in `.jpg/.jpeg/.png/.gif/.webp/.svg`. Rendered as thumbnail. |
| `nested` | `dict` or `list` in ≥ 50 % of rows. Table cell shows `{N keys}` or `[N items]`. |
| `text` | String otherwise. Truncated to 120 chars in table; full text in row drawer. |

## Views

| View | Eligible when | Description |
|---|---|---|
| Table | always | Sortable columns, full-text search, paginated (200/page). Each row has "view raw" opening a JSON tree drawer. |
| Line | time field + numeric measure | X/Y picker with optional series-by (categorical ≤ 8 values) and aggregate (sum/avg/count/min/max). |
| Bar | categorical or low-cardinality numeric field | Top-N value counts (default top 20). |
| KPIs | at least one numeric measure | Grid of cards with count/sum/mean/median/p90/min/max. |
| Tree | always | Recursive collapsible JSON tree. Choose root: all rows, a single row, or meta only. Also used as the row-detail drawer from table. |

## Keyboard shortcuts

| Key | Action |
|---|---|
| `1`–`5` | Switch view |
| `/` | Focus search (table) |
| `j` / `k` | Next / previous row (table) |
| `esc` | Close drawer |

## Output

A single self-contained `.html` file. External CDNs: Tailwind, ECharts,
Alpine.js. No server required — open with `file://` or any browser.

Theme behavior:

- defaults to system preference (`prefers-color-scheme`)
- toggles between light/dark in the report header
- persists across reloads via `localStorage` key `bh-data-display.theme`

## Limits

- Embed cap: up to 50 000 rows are embedded in the report payload.
- Table cap: table view shows up to 5 000 matched rows at a time with a warning.
- Charts and KPI metrics are aggregated in Python before embedding, so chart
  interactions stay responsive on large datasets.

## URL state

The report keeps interactive state in the URL hash for reload/share continuity:

- `view`
- `q` (search query)
- `sort`
- `dir` (`asc` / `desc`)
- `page`

## Cross-references

- `data_display.render_dataset` — the renderer entry point
- `interaction-skills/data-source-exploration.md` — use that to discover and
  inventory data sources before displaying them
- `domain-skills/<site>/` — site-specific schema and canonical file locations
