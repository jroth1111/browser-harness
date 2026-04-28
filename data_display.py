"""Generic data-display renderer for browser-harness scraped artifacts.

Reads a .json / .jsonl / .csv source file, introspects the schema, and emits a
self-contained .html report with auto-detected views (table, line, bar, KPIs,
tree). Cross-domain by design: works on any list-of-dicts dataset.

Public surface: render_dataset(path, out=None, view=None, open_browser=False).
"""
import csv
import json
import pathlib
import re
import webbrowser

_RECORD_KEYS = ("records", "rows", "data", "items", "results")
_TIME_NAME_RE = re.compile(
    r"^(date|ds|.*_at|.*_date|.*_time|timestamp|created|updated|observed)$",
    re.I,
)
_URL_RE = re.compile(r"^https?://", re.I)
_IMG_RE = re.compile(r"\.(jpg|jpeg|png|gif|webp|svg)(\?|$)", re.I)
_LAT_RE = re.compile(r"^(lat|latitude)$", re.I)
_LNG_RE = re.compile(r"^(lng|lon|longitude)$", re.I)
_ISO_DATE_RE = re.compile(r"^\d{4}[-/]\d{2}[-/]\d{2}")

_MAX_EMBEDDED_ROWS = 50000


def render_dataset(path, out=None, view=None, open_browser=False):
    src = pathlib.Path(path).expanduser().resolve()
    if not src.exists():
        raise FileNotFoundError(src)
    records, meta = _load_records(src)
    truncated = False
    if len(records) > _MAX_EMBEDDED_ROWS:
        truncated = True
        records = records[:_MAX_EMBEDDED_ROWS]
    schema = _introspect(records)
    out_path = (
        pathlib.Path(out).expanduser().resolve()
        if out
        else src.with_suffix(src.suffix + ".html") if src.suffix in (".jsonl",)
        else src.with_suffix(".html")
    )
    html = _emit_html(records, schema, meta, src, view, truncated)
    out_path.write_text(html, encoding="utf-8")
    if open_browser:
        webbrowser.open(out_path.as_uri())
    return str(out_path)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def _load_records(path):
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return _load_csv(path)
    if suffix == ".jsonl":
        return _load_jsonl(path)
    if suffix == ".json":
        return _load_json(path)
    raise ValueError(f"unsupported extension {suffix!r}; expected .json/.jsonl/.csv")


def _load_csv(path):
    rows = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({k: _coerce_csv(v) for k, v in row.items()})
    meta = {"source_file": str(path), "row_count": len(rows), "format": "csv"}
    return rows, meta


def _coerce_csv(v):
    if v is None or v == "":
        return None
    s = v.strip()
    if not s:
        return None
    if s.lstrip("-").isdigit():
        try:
            return int(s)
        except ValueError:
            pass
    try:
        f = float(s)
        if "." in s or "e" in s.lower():
            return f
    except ValueError:
        pass
    if s.lower() in ("true", "false"):
        return s.lower() == "true"
    return v


def _load_jsonl(path):
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        rows.append(obj if isinstance(obj, dict) else {"value": obj})
    meta = {"source_file": str(path), "row_count": len(rows), "format": "jsonl"}
    return rows, meta


def _load_json(path):
    obj = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(obj, list):
        rows = [r if isinstance(r, dict) else {"value": r} for r in obj]
        meta = {
            "source_file": str(path),
            "row_count": len(rows),
            "format": "json",
            "records_key": "(top-level)",
        }
        return rows, meta
    if not isinstance(obj, dict):
        rows = [{"value": obj}]
        meta = {"source_file": str(path), "row_count": 1, "format": "json"}
        return rows, meta
    records, key = _find_records(obj)
    wrapper_meta = {k: v for k, v in obj.items() if k != key}
    wrapper_meta.update({
        "source_file": str(path),
        "row_count": len(records),
        "format": "json",
        "records_key": key or "(none)",
    })
    return records, wrapper_meta


def _find_records(obj):
    for k in _RECORD_KEYS:
        v = obj.get(k)
        if isinstance(v, list) and v and all(isinstance(x, dict) for x in v[:5]):
            return v, k
    best = None
    queue = [obj]
    while queue:
        cur = queue.pop(0)
        if isinstance(cur, dict):
            for k, v in cur.items():
                if isinstance(v, list) and v and all(isinstance(x, dict) for x in v[:5]):
                    if best is None or len(v) > len(best[0]):
                        best = (v, k)
                else:
                    queue.append(v)
        elif isinstance(cur, list):
            queue.extend(cur)
    if best:
        return best[0], best[1]
    return [], None


# ---------------------------------------------------------------------------
# Introspection
# ---------------------------------------------------------------------------


def _introspect(records, sample_size=500):
    sample = records[:sample_size]
    field_names = []
    seen = set()
    for r in sample:
        if not isinstance(r, dict):
            continue
        for k in r:
            if k not in seen:
                seen.add(k)
                field_names.append(k)
    fields = [_describe_field(name, sample) for name in field_names]
    return {
        "fields": fields,
        "row_count": len(records),
        "eligible_views": _dataset_eligible_views(fields),
    }


def _describe_field(name, sample):
    values = [r.get(name) for r in sample if isinstance(r, dict)]
    non_null = [v for v in values if v is not None]
    null_pct = round(100 * (len(values) - len(non_null)) / max(len(values), 1), 1)
    type_counts = {"int": 0, "float": 0, "str": 0, "bool": 0, "dict": 0, "list": 0}
    for v in non_null:
        if isinstance(v, bool):
            type_counts["bool"] += 1
        elif isinstance(v, int):
            type_counts["int"] += 1
        elif isinstance(v, float):
            type_counts["float"] += 1
        elif isinstance(v, str):
            type_counts["str"] += 1
        elif isinstance(v, dict):
            type_counts["dict"] += 1
        elif isinstance(v, list):
            type_counts["list"] += 1
    n = max(len(non_null), 1)
    nested_share = (type_counts["dict"] + type_counts["list"]) / n
    numeric_share = (type_counts["int"] + type_counts["float"]) / n
    string_share = type_counts["str"] / n
    bool_share = type_counts["bool"] / n

    distinct_set = set()
    for v in non_null:
        try:
            distinct_set.add(v)
        except TypeError:
            distinct_set.add(repr(v))
        if len(distinct_set) > 200:
            break
    distinct = len(distinct_set)

    if not non_null:
        kind = "empty"
    elif nested_share >= 0.5:
        kind = "nested"
    elif bool_share >= 0.9:
        kind = "bool"
    elif numeric_share >= 0.9:
        kind = "numeric"
    elif string_share >= 0.9:
        kind = _classify_string(name, non_null)
    else:
        kind = "text"

    is_measure = kind == "numeric" and distinct > 10
    is_categorical_numeric = kind == "numeric" and 2 <= distinct <= 10
    is_geo_lat = bool(_LAT_RE.match(name)) and kind == "numeric"
    is_geo_lng = bool(_LNG_RE.match(name)) and kind == "numeric"

    eligible_for = ["table"]
    if is_measure:
        eligible_for.extend(["line_y", "kpi"])
    if is_categorical_numeric:
        eligible_for.append("bar_x")
    if kind == "categorical":
        eligible_for.extend(["bar_x", "series_by"])
    if kind == "time":
        eligible_for.append("line_x")
    if kind == "nested":
        eligible_for.append("tree")
    if kind == "bool":
        eligible_for.append("bar_x")

    return {
        "name": name,
        "kind": kind,
        "distinct": distinct,
        "non_null": len(non_null),
        "null_pct": null_pct,
        "is_measure": is_measure,
        "is_categorical_numeric": is_categorical_numeric,
        "is_geo_lat": is_geo_lat,
        "is_geo_lng": is_geo_lng,
        "examples": [_truncate_example(v) for v in non_null[:3]],
        "eligible_for": eligible_for,
    }


def _classify_string(name, values):
    if _TIME_NAME_RE.match(name):
        return "time"
    head = values[:50]
    parsed = sum(1 for v in head if isinstance(v, str) and _ISO_DATE_RE.match(v))
    if head and parsed / len(head) >= 0.9:
        return "time"
    url_share = sum(1 for v in head if isinstance(v, str) and _URL_RE.match(v))
    if head and url_share / len(head) >= 0.9:
        if all(isinstance(v, str) and _IMG_RE.search(v) for v in head):
            return "image"
        return "url"
    distinct = len(set(values))
    n = len(values)
    if n >= 5 and distinct <= 30 and distinct <= max(n * 0.5, 1):
        return "categorical"
    return "text"


def _truncate_example(v, limit=120):
    if isinstance(v, dict):
        if len(v) > 4:
            return f"{{{len(v)} keys}}"
        return v
    if isinstance(v, list):
        if len(v) > 6:
            return f"[{len(v)} items]"
        return v
    if isinstance(v, str) and len(v) > limit:
        return v[:limit] + "…"
    return v


def _dataset_eligible_views(fields):
    has_time = any(f["kind"] == "time" for f in fields)
    has_measure = any(f.get("is_measure") for f in fields)
    has_bar_x = any("bar_x" in f["eligible_for"] for f in fields)
    has_nested = any(f["kind"] == "nested" for f in fields)
    eligible = ["table"]
    if has_time and has_measure:
        eligible.append("line")
    if has_bar_x:
        eligible.append("bar")
    if has_measure:
        eligible.append("kpis")
    if has_nested or fields:
        eligible.append("tree")
    return eligible


# ---------------------------------------------------------------------------
# HTML emission
# ---------------------------------------------------------------------------


def _emit_html(records, schema, meta, src_path, view, truncated):
    title = src_path.name
    payload = {
        "data": records,
        "schema": schema,
        "meta": {
            **meta,
            "title": title,
            "default_view": view or "",
            "truncated": truncated,
            "max_embedded_rows": _MAX_EMBEDDED_ROWS,
        },
    }
    return _TEMPLATE.replace("__TITLE__", _escape_html(title)).replace(
        "__PAYLOAD__", _escape_for_script_tag(json.dumps(payload, default=str, ensure_ascii=False))
    )


def _escape_for_script_tag(s):
    # Inside <script type="application/json"> only </ needs neutralizing.
    return s.replace("</", "<\\/")


def _escape_html(s):
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ---------------------------------------------------------------------------
# HTML / JS template
# ---------------------------------------------------------------------------


_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en" class="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__ — data display</title>
<script src="https://cdn.tailwindcss.com"></script>
<script>
  tailwind.config = {
    darkMode: 'class',
    theme: { extend: { fontFamily: { sans: ['ui-sans-serif','system-ui','-apple-system','Segoe UI','Roboto','Helvetica Neue','Arial','sans-serif'], mono: ['ui-monospace','SFMono-Regular','Menlo','Consolas','monospace'] } } }
  };
</script>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
<style>
  html, body { height: 100%; }
  body { font-feature-settings: "ss01","cv11"; }
  .scroll-shadow { box-shadow: inset 0 -1px 0 rgba(255,255,255,0.06); }
  .num { font-variant-numeric: tabular-nums; }
  .tree-toggle { width: 1rem; display: inline-block; transition: transform .12s ease; user-select: none; }
  .tree-toggle.open { transform: rotate(90deg); }
  .row-link:hover { background: rgba(99,102,241,0.08); }
  .kbd { font-family: ui-monospace, monospace; font-size: 11px; padding: 1px 5px; border: 1px solid currentColor; border-radius: 4px; opacity: .6; }
  details > summary::-webkit-details-marker { display: none; }
  ::-webkit-scrollbar { width: 10px; height: 10px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: rgba(127,127,127,.25); border-radius: 6px; }
  ::-webkit-scrollbar-thumb:hover { background: rgba(127,127,127,.4); }
  [x-cloak] { display: none !important; }
</style>
</head>
<body class="bg-zinc-950 text-zinc-100 dark:bg-zinc-950 dark:text-zinc-100 light:bg-white light:text-zinc-900 antialiased min-h-screen" x-data="app()" x-init="init()" x-cloak>

<header class="sticky top-0 z-30 border-b border-zinc-800/70 bg-zinc-950/80 backdrop-blur supports-[backdrop-filter]:bg-zinc-950/60">
  <div class="px-5 py-3 flex items-center gap-4">
    <div class="flex items-center gap-2 text-indigo-400">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><path d="m19 9-5 5-4-4-3 3"/></svg>
      <span class="font-semibold tracking-tight">data display</span>
    </div>
    <div class="text-zinc-300 truncate" x-text="meta.title"></div>
    <div class="ml-auto flex items-center gap-3 text-xs text-zinc-400">
      <span class="num"><span x-text="schema.row_count.toLocaleString()"></span> rows</span>
      <span x-show="meta.records_key" x-text="'records: ' + (meta.records_key || '')"></span>
      <span class="num" x-text="schema.fields.length + ' fields'"></span>
      <span x-show="meta.truncated" class="text-amber-400" x-text="'truncated to ' + meta.max_embedded_rows.toLocaleString()"></span>
      <button @click="toggleTheme()" class="ml-2 px-2 py-1 rounded border border-zinc-700 hover:bg-zinc-800 transition" title="Toggle theme">
        <span x-show="theme==='dark'">☾</span>
        <span x-show="theme==='light'">☀</span>
      </button>
    </div>
  </div>
  <!-- meta strip -->
  <div x-show="metaSummary.length" class="px-5 pb-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-zinc-400">
    <template x-for="kv in metaSummary" :key="kv.k">
      <div><span class="text-zinc-500" x-text="kv.k + ':'"></span> <span class="text-zinc-200 num" x-text="kv.v"></span></div>
    </template>
  </div>
</header>

<main class="flex">
  <aside class="w-44 shrink-0 border-r border-zinc-800/70 min-h-[calc(100vh-3rem)]">
    <nav class="p-2 space-y-1 sticky top-20">
      <template x-for="v in views" :key="v.id">
        <button @click="setView(v.id)"
                :disabled="!isEligible(v.id)"
                :class="[
                  view === v.id ? 'bg-indigo-500/15 text-indigo-300 border-indigo-500/30' : 'text-zinc-300 border-transparent hover:bg-zinc-900',
                  isEligible(v.id) ? '' : 'opacity-30 cursor-not-allowed',
                  'w-full flex items-center justify-between px-3 py-2 rounded-md border text-sm transition'
                ]">
          <span class="flex items-center gap-2">
            <span class="opacity-80" x-html="iconFor(v.id)"></span>
            <span x-text="v.label"></span>
          </span>
          <span class="kbd" x-text="v.key"></span>
        </button>
      </template>
      <div class="pt-3 mt-3 border-t border-zinc-800/70 text-[11px] text-zinc-500 px-3 leading-relaxed">
        <div><span class="kbd">/</span> search</div>
        <div><span class="kbd">j</span>/<span class="kbd">k</span> next/prev row</div>
        <div><span class="kbd">esc</span> close drawer</div>
      </div>
    </nav>
  </aside>

  <section class="flex-1 min-w-0">
    <!-- TABLE -->
    <div x-show="view==='table'" class="p-5">
      <div class="flex items-center gap-3 mb-3">
        <div class="flex-1 relative max-w-xl">
          <span class="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>
          </span>
          <input id="search-box" x-model="q" @input.debounce.150="page = 0; writeHash()" placeholder="search rows…  (press / to focus)"
            class="w-full pl-9 pr-3 py-2 bg-zinc-900 border border-zinc-800 rounded-md text-sm focus:outline-none focus:border-indigo-500 transition">
        </div>
        <div class="text-xs text-zinc-500 num">
          <span x-text="filteredRows.length.toLocaleString()"></span> match · page
          <span x-text="page + 1"></span>/<span x-text="totalPages"></span>
        </div>
        <div class="flex items-center gap-1">
          <button @click="page = Math.max(0, page-1)" class="px-2 py-1 rounded border border-zinc-800 hover:bg-zinc-900 text-sm">←</button>
          <button @click="page = Math.min(totalPages-1, page+1)" class="px-2 py-1 rounded border border-zinc-800 hover:bg-zinc-900 text-sm">→</button>
        </div>
      </div>
      <div x-show="filteredRows.length > 5000" class="mb-2 text-xs text-amber-400">
        Showing the first 5000 of <span x-text="filteredRows.length.toLocaleString()"></span> matched rows. Narrow the search or use a chart view for the full set.
      </div>
      <div class="border border-zinc-800 rounded-md overflow-auto max-h-[calc(100vh-12rem)]">
        <table class="text-sm w-full">
          <thead class="sticky top-0 bg-zinc-900/95 backdrop-blur scroll-shadow text-zinc-400">
            <tr>
              <th class="px-2 py-2 text-left font-medium w-8">#</th>
              <template x-for="f in tableFields" :key="f.name">
                <th class="px-2 py-2 text-left font-medium whitespace-nowrap">
                  <button @click="sortBy(f.name)" class="flex items-center gap-1 hover:text-zinc-200 transition">
                    <span x-text="f.name"></span>
                    <span class="text-indigo-400" x-show="sortKey === f.name" x-text="sortDir === 'asc' ? '▲' : '▼'"></span>
                    <span class="text-[10px] uppercase opacity-50" x-text="f.kind"></span>
                  </button>
                </th>
              </template>
              <th class="px-2 py-2 text-left font-medium w-12"></th>
            </tr>
          </thead>
          <tbody class="divide-y divide-zinc-900">
            <template x-for="(row, i) in pagedRows" :key="page * pageSize + i">
              <tr class="row-link hover:bg-zinc-900/60">
                <td class="px-2 py-1.5 text-zinc-600 num text-xs" x-text="page * pageSize + i + 1"></td>
                <template x-for="f in tableFields" :key="f.name">
                  <td class="px-2 py-1.5 align-top max-w-xs"
                      :class="cellClass(row[f.name], f)">
                    <template x-if="f.kind === 'url' && row[f.name]">
                      <a :href="row[f.name]" target="_blank" rel="noopener" class="text-indigo-400 hover:underline truncate inline-block max-w-[16rem]" x-text="row[f.name]"></a>
                    </template>
                    <template x-if="f.kind === 'image' && row[f.name]">
                      <img :src="row[f.name]" loading="lazy" class="h-12 w-12 object-cover rounded">
                    </template>
                    <template x-if="f.kind !== 'url' && f.kind !== 'image'">
                      <span x-text="formatCell(row[f.name])" :title="cellTitle(row[f.name])"></span>
                    </template>
                  </td>
                </template>
                <td class="px-2 py-1.5">
                  <button @click="showRow(row)" class="text-zinc-500 hover:text-indigo-400 text-xs">view&nbsp;raw</button>
                </td>
              </tr>
            </template>
            <tr x-show="pagedRows.length === 0">
              <td class="px-3 py-8 text-center text-zinc-500" :colspan="tableFields.length + 2">no rows match</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- LINE -->
    <div x-show="view==='line'" class="p-5">
      <div class="flex flex-wrap gap-4 mb-3 text-sm items-end">
        <label class="flex flex-col gap-1">
          <span class="text-xs text-zinc-500 uppercase tracking-wide">x · time</span>
          <select x-model="lineXField" class="bg-zinc-900 border border-zinc-800 rounded px-2 py-1.5 min-w-[10rem]">
            <template x-for="f in fieldsForRole('line_x')" :key="f.name"><option :value="f.name" x-text="f.name"></option></template>
          </select>
        </label>
        <label class="flex flex-col gap-1">
          <span class="text-xs text-zinc-500 uppercase tracking-wide">y · measure</span>
          <select x-model="lineYField" class="bg-zinc-900 border border-zinc-800 rounded px-2 py-1.5 min-w-[10rem]">
            <template x-for="f in fieldsForRole('line_y')" :key="f.name"><option :value="f.name" x-text="f.name"></option></template>
          </select>
        </label>
        <label class="flex flex-col gap-1">
          <span class="text-xs text-zinc-500 uppercase tracking-wide">series&nbsp;by · optional</span>
          <select x-model="lineSeriesField" class="bg-zinc-900 border border-zinc-800 rounded px-2 py-1.5 min-w-[10rem]">
            <option value="">(none)</option>
            <template x-for="f in fieldsForRole('series_by')" :key="f.name"><option :value="f.name" x-text="f.name"></option></template>
          </select>
        </label>
        <label class="flex flex-col gap-1">
          <span class="text-xs text-zinc-500 uppercase tracking-wide">aggregate</span>
          <select x-model="lineAgg" class="bg-zinc-900 border border-zinc-800 rounded px-2 py-1.5">
            <option value="sum">sum</option><option value="avg">avg</option><option value="count">count</option><option value="min">min</option><option value="max">max</option>
          </select>
        </label>
      </div>
      <div id="line-chart" class="w-full h-[60vh] border border-zinc-800 rounded"></div>
      <div x-show="!fieldsForRole('line_x').length || !fieldsForRole('line_y').length" class="text-xs text-zinc-500 mt-2">No time field paired with a numeric measure.</div>
    </div>

    <!-- BAR -->
    <div x-show="view==='bar'" class="p-5">
      <div class="flex flex-wrap gap-4 mb-3 text-sm items-end">
        <label class="flex flex-col gap-1">
          <span class="text-xs text-zinc-500 uppercase tracking-wide">field</span>
          <select x-model="barField" class="bg-zinc-900 border border-zinc-800 rounded px-2 py-1.5 min-w-[10rem]">
            <template x-for="f in fieldsForRole('bar_x')" :key="f.name"><option :value="f.name" x-text="f.name"></option></template>
          </select>
        </label>
        <label class="flex flex-col gap-1">
          <span class="text-xs text-zinc-500 uppercase tracking-wide">top N</span>
          <input type="number" min="1" max="100" x-model.number="barTopN" class="bg-zinc-900 border border-zinc-800 rounded px-2 py-1.5 w-24 num">
        </label>
      </div>
      <div id="bar-chart" class="w-full h-[60vh] border border-zinc-800 rounded"></div>
    </div>

    <!-- KPIS -->
    <div x-show="view==='kpis'" class="p-5">
      <div class="grid gap-3" style="grid-template-columns: repeat(auto-fill, minmax(220px, 1fr))">
        <template x-for="f in measureFields" :key="f.name">
          <div class="border border-zinc-800 rounded-md p-4 bg-zinc-900/40">
            <div class="text-[11px] text-zinc-500 uppercase tracking-wide" x-text="f.name"></div>
            <div class="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
              <template x-for="kv in kpisFor(f)" :key="kv.k">
                <div class="contents">
                  <div class="text-zinc-500" x-text="kv.k"></div>
                  <div class="text-right num text-zinc-100" x-text="kv.v"></div>
                </div>
              </template>
            </div>
          </div>
        </template>
        <div x-show="!measureFields.length" class="text-zinc-500 text-sm">No numeric measures detected.</div>
      </div>
    </div>

    <!-- TREE -->
    <div x-show="view==='tree'" class="p-5">
      <div class="flex flex-wrap gap-4 mb-3 text-sm items-end">
        <label class="flex flex-col gap-1">
          <span class="text-xs text-zinc-500 uppercase tracking-wide">root</span>
          <select x-model.number="treeRowIdx" class="bg-zinc-900 border border-zinc-800 rounded px-2 py-1.5 min-w-[12rem]">
            <option value="-1">all rows (array)</option>
            <option value="-2">meta only</option>
            <template x-for="(row, i) in data.slice(0, 200)" :key="i"><option :value="i" x-text="'row ' + (i+1) + treeRowLabel(row)"></option></template>
          </select>
        </label>
      </div>
      <div class="border border-zinc-800 rounded p-3 max-h-[calc(100vh-12rem)] overflow-auto font-mono text-[13px] leading-relaxed" x-ref="treeRoot" x-effect="renderTree($refs.treeRoot, treeRoot())"></div>
    </div>
  </section>
</main>

<!-- Row drawer -->
<div x-show="selectedRow !== null" x-transition.opacity class="fixed inset-0 z-40 bg-black/50" @click="selectedRow = null"></div>
<aside x-show="selectedRow !== null" x-transition:enter="transition ease-out duration-150" x-transition:enter-start="translate-x-full" x-transition:enter-end="translate-x-0"
       x-transition:leave="transition ease-in duration-100" x-transition:leave-start="translate-x-0" x-transition:leave-end="translate-x-full"
       class="fixed top-0 right-0 z-40 h-full w-full sm:w-[36rem] bg-zinc-950 border-l border-zinc-800 shadow-2xl flex flex-col">
  <div class="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
    <div class="text-sm text-zinc-400">row detail · <span class="kbd">esc</span> to close</div>
    <button @click="selectedRow = null" class="text-zinc-400 hover:text-zinc-100">✕</button>
  </div>
  <div class="flex-1 overflow-auto p-4 font-mono text-[13px] leading-relaxed" x-ref="drawerRoot" x-effect="if (selectedRow !== null) renderTree($refs.drawerRoot, selectedRow)"></div>
</aside>

<script type="application/json" id="payload-json">__PAYLOAD__</script>
<script>
function app() {
  return {
    data: [],
    schema: { fields: [], row_count: 0, eligible_views: ['table'] },
    meta: { title: '', source_file: '', records_key: '' },
    view: 'table',
    q: '',
    sortKey: null,
    sortDir: 'asc',
    page: 0,
    pageSize: 200,
    selectedRow: null,
    lineXField: null,
    lineYField: null,
    lineSeriesField: '',
    lineAgg: 'sum',
    barField: null,
    barTopN: 20,
    treeRowIdx: -1,
    theme: 'dark',
    _resizeHandlers: [],

    init() {
      const payload = JSON.parse(document.getElementById('payload-json').textContent);
      this.data = Array.isArray(payload.data) ? payload.data : [];
      this.schema = payload.schema || this.schema;
      this.meta = payload.meta || this.meta;
      this.view = this._pickInitialView();
      this._setupChartDefaults();
      this._restoreFromHash();
      this._bindKeys();
      this._installResize();
      this.$watch('view', () => { this.writeHash(); this.$nextTick(() => this.renderCharts()); });
      this.$watch('lineXField', () => this.$nextTick(() => this.renderCharts()));
      this.$watch('lineYField', () => this.$nextTick(() => this.renderCharts()));
      this.$watch('lineSeriesField', () => this.$nextTick(() => this.renderCharts()));
      this.$watch('lineAgg', () => this.$nextTick(() => this.renderCharts()));
      this.$watch('barField', () => this.$nextTick(() => this.renderCharts()));
      this.$watch('barTopN', () => this.$nextTick(() => this.renderCharts()));
      this.$nextTick(() => this.renderCharts());
    },

    get views() {
      return [
        { id: 'table', label: 'Table', key: '1' },
        { id: 'line',  label: 'Line',  key: '2' },
        { id: 'bar',   label: 'Bar',   key: '3' },
        { id: 'kpis',  label: 'KPIs',  key: '4' },
        { id: 'tree',  label: 'Tree',  key: '5' },
      ];
    },

    iconFor(id) {
      const map = {
        table: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M3 15h18M9 3v18M15 3v18"/></svg>',
        line:  '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><path d="m4 17 5-7 4 4 7-9"/></svg>',
        bar:   '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><rect x="6" y="11" width="3" height="7"/><rect x="11" y="7" width="3" height="11"/><rect x="16" y="13" width="3" height="5"/></svg>',
        kpis:  '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12 2 3 7 7 .5-5.5 4.5L18 22l-6-4-6 4 1.5-8L2 9.5 9 9z"/></svg>',
        tree:  '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12h4M3 6h4M3 18h4M11 6h10M11 12h10M11 18h10"/></svg>',
      };
      return map[id] || '';
    },

    isEligible(v) { return (this.schema.eligible_views || []).includes(v); },
    setView(v) { if (this.isEligible(v)) this.view = v; },

    fieldsForRole(role) {
      return (this.schema.fields || []).filter(f => (f.eligible_for || []).includes(role));
    },

    get tableFields() {
      // Hide deeply-nested fields' raw object value in table headers? Keep them, format as {N keys}.
      return this.schema.fields || [];
    },

    get measureFields() {
      return (this.schema.fields || []).filter(f => f.is_measure);
    },

    get metaSummary() {
      const out = [];
      const meta = this.meta || {};
      const skip = new Set(['title', 'default_view', 'truncated', 'max_embedded_rows', 'records_key', 'source_file', 'row_count', 'format']);
      for (const k of Object.keys(meta)) {
        if (skip.has(k)) continue;
        const v = meta[k];
        if (v == null) continue;
        let display;
        if (typeof v === 'object') {
          if (Array.isArray(v)) display = '[' + v.length + ']';
          else display = Object.entries(v).map(([kk, vv]) => kk + ':' + (typeof vv === 'object' ? JSON.stringify(vv) : vv)).slice(0, 6).join(', ');
        } else {
          display = String(v);
          if (display.length > 80) display = display.slice(0, 80) + '…';
        }
        out.push({ k, v: display });
        if (out.length > 10) break;
      }
      return out;
    },

    _pickInitialView() {
      if (this.meta.default_view && this.isEligible(this.meta.default_view)) return this.meta.default_view;
      for (const v of ['line', 'bar', 'kpis', 'table']) {
        if (this.isEligible(v)) return v;
      }
      return 'table';
    },

    _setupChartDefaults() {
      const fields = this.schema.fields || [];
      this.lineXField = (fields.find(f => f.kind === 'time') || {}).name || null;
      const measures = fields.filter(f => f.is_measure);
      this.lineYField = (measures[0] || {}).name || null;
      const cat = fields.find(f => f.kind === 'categorical' || f.is_categorical_numeric);
      this.barField = (cat || measures[0] || fields[0] || {}).name || null;
    },

    get filteredRows() {
      const q = this.q.trim().toLowerCase();
      if (!q) return this.data;
      const out = [];
      for (const r of this.data) {
        for (const k in r) {
          const v = r[k];
          if (v == null) continue;
          const s = (typeof v === 'object') ? JSON.stringify(v) : String(v);
          if (s.toLowerCase().includes(q)) { out.push(r); break; }
        }
      }
      return out;
    },

    get sortedRows() {
      if (!this.sortKey) return this.filteredRows;
      const k = this.sortKey, dir = this.sortDir === 'asc' ? 1 : -1;
      return [...this.filteredRows].sort((a, b) => {
        const av = a[k], bv = b[k];
        if (av == null && bv == null) return 0;
        if (av == null) return 1;
        if (bv == null) return -1;
        if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * dir;
        return String(av).localeCompare(String(bv)) * dir;
      });
    },

    get pagedRows() {
      const cap = 5000;
      const rows = this.sortedRows.slice(0, cap);
      const start = this.page * this.pageSize;
      return rows.slice(start, start + this.pageSize);
    },

    get totalPages() {
      const total = Math.min(this.sortedRows.length, 5000);
      return Math.max(1, Math.ceil(total / this.pageSize));
    },

    sortBy(key) {
      if (this.sortKey === key) this.sortDir = this.sortDir === 'asc' ? 'desc' : 'asc';
      else { this.sortKey = key; this.sortDir = 'asc'; }
    },

    formatCell(v) {
      if (v == null) return '';
      if (typeof v === 'object') {
        return Array.isArray(v) ? '[' + v.length + ' items]' : '{' + Object.keys(v).length + ' keys}';
      }
      const s = String(v);
      return s.length > 120 ? s.slice(0, 120) + '…' : s;
    },

    cellTitle(v) {
      if (v == null) return '';
      if (typeof v === 'object') return JSON.stringify(v).slice(0, 1000);
      return String(v).slice(0, 1000);
    },

    cellClass(v, field) {
      if (typeof v === 'number') return 'num text-right text-zinc-100';
      if (field.kind === 'time') return 'num text-zinc-200 whitespace-nowrap';
      if (field.kind === 'categorical' || field.kind === 'bool') return 'whitespace-nowrap';
      return '';
    },

    showRow(row) { this.selectedRow = row; },

    kpisFor(field) {
      const vals = [];
      for (const r of this.data) {
        const v = r[field.name];
        if (typeof v === 'number' && !Number.isNaN(v)) vals.push(v);
      }
      if (!vals.length) return [{ k: 'count', v: '0' }];
      const sorted = [...vals].sort((a, b) => a - b);
      const sum = vals.reduce((a, b) => a + b, 0);
      return [
        { k: 'count',  v: vals.length.toLocaleString() },
        { k: 'sum',    v: this._fmtNum(sum) },
        { k: 'mean',   v: this._fmtNum(sum / vals.length) },
        { k: 'median', v: this._fmtNum(sorted[Math.floor(sorted.length / 2)]) },
        { k: 'p90',    v: this._fmtNum(sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * 0.9))]) },
        { k: 'min',    v: this._fmtNum(sorted[0]) },
        { k: 'max',    v: this._fmtNum(sorted[sorted.length - 1]) },
      ];
    },

    _fmtNum(n) {
      if (n === 0) return '0';
      if (Math.abs(n) >= 1000) return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
      if (Math.abs(n) < 0.001) return n.toExponential(2);
      return Number(n.toFixed(4)).toString();
    },

    renderCharts() {
      if (this.view === 'line') this._renderLine();
      if (this.view === 'bar') this._renderBar();
    },

    _chartTheme() { return this.theme === 'dark' ? 'dark' : undefined; },

    _ensureChart(id) {
      const el = document.getElementById(id);
      if (!el || el.offsetWidth === 0) return null;
      let inst = echarts.getInstanceByDom(el);
      const theme = this._chartTheme();
      if (inst && inst._bhTheme !== theme) { inst.dispose(); inst = null; }
      if (!inst) { inst = echarts.init(el, theme); inst._bhTheme = theme; }
      return inst;
    },

    _aggregate(values, kind) {
      if (!values.length) return null;
      switch (kind) {
        case 'avg': return values.reduce((a, b) => a + b, 0) / values.length;
        case 'count': return values.length;
        case 'min': return Math.min(...values);
        case 'max': return Math.max(...values);
        case 'sum': default: return values.reduce((a, b) => a + b, 0);
      }
    },

    _renderLine() {
      const chart = this._ensureChart('line-chart');
      if (!chart) return;
      if (!this.lineXField || !this.lineYField) { chart.clear(); return; }
      const xf = this.lineXField, yf = this.lineYField, sf = this.lineSeriesField;
      const groups = {};
      for (const r of this.data) {
        const x = r[xf];
        const y = r[yf];
        if (x == null || (this.lineAgg !== 'count' && typeof y !== 'number')) continue;
        const xKey = String(x);
        const sKey = sf ? String(r[sf] ?? '∅') : '__total__';
        groups[xKey] = groups[xKey] || {};
        groups[xKey][sKey] = groups[xKey][sKey] || [];
        groups[xKey][sKey].push(typeof y === 'number' ? y : 0);
      }
      const xs = Object.keys(groups).sort();
      let seriesKeys;
      if (sf) {
        const all = new Set();
        xs.forEach(x => Object.keys(groups[x]).forEach(k => all.add(k)));
        seriesKeys = [...all].slice(0, 8);
      } else {
        seriesKeys = ['__total__'];
      }
      const series = seriesKeys.map(sk => ({
        name: sk === '__total__' ? `${this.lineAgg}(${yf})` : sk,
        type: 'line',
        showSymbol: xs.length <= 60,
        smooth: false,
        data: xs.map(x => {
          const arr = (groups[x] && groups[x][sk]) || [];
          return arr.length ? this._aggregate(arr, this.lineAgg) : null;
        }),
      }));
      chart.setOption({
        backgroundColor: 'transparent',
        animation: false,
        grid: { left: 60, right: 30, top: 36, bottom: 50, containLabel: true },
        xAxis: { type: 'category', data: xs, axisLabel: { rotate: xs.length > 12 ? 30 : 0 } },
        yAxis: { type: 'value' },
        tooltip: { trigger: 'axis' },
        legend: { top: 4, type: 'scroll' },
        series,
      }, true);
    },

    _renderBar() {
      const chart = this._ensureChart('bar-chart');
      if (!chart) return;
      if (!this.barField) { chart.clear(); return; }
      const counts = {};
      for (const r of this.data) {
        const v = r[this.barField];
        const k = v == null ? '∅' : (typeof v === 'object' ? JSON.stringify(v) : String(v));
        counts[k] = (counts[k] || 0) + 1;
      }
      const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, this.barTopN || 20);
      const cats = sorted.map(s => s[0]).reverse();
      const vals = sorted.map(s => s[1]).reverse();
      chart.setOption({
        backgroundColor: 'transparent',
        animation: false,
        grid: { left: 140, right: 30, top: 16, bottom: 24, containLabel: true },
        xAxis: { type: 'value' },
        yAxis: { type: 'category', data: cats },
        tooltip: { trigger: 'axis' },
        series: [{ type: 'bar', data: vals, itemStyle: { color: '#6366f1' } }],
      }, true);
    },

    treeRoot() {
      if (this.treeRowIdx === -1) return this.data;
      if (this.treeRowIdx === -2) return this.meta;
      const idx = Math.max(0, Math.min(this.data.length - 1, this.treeRowIdx));
      return this.data[idx];
    },

    treeRowLabel(row) {
      if (!row || typeof row !== 'object') return '';
      for (const k of ['title', 'name', 'listing_name', 'id', 'listing_id', 'run_id']) {
        if (row[k] != null) {
          const s = String(row[k]);
          return ' · ' + (s.length > 30 ? s.slice(0, 30) + '…' : s);
        }
      }
      return '';
    },

    renderTree(host, value) {
      if (!host) return;
      host.innerHTML = '';
      host.appendChild(this._buildTreeNode('$', value, 0, true));
    },

    _buildTreeNode(key, value, depth, openByDefault) {
      const el = document.createElement('div');
      el.style.paddingLeft = (depth === 0 ? 0 : 4) + 'px';
      const isObj = value !== null && typeof value === 'object';
      if (!isObj) {
        const k = document.createElement('span'); k.className = 'text-zinc-500'; k.textContent = key + ': ';
        const v = document.createElement('span'); v.className = this._scalarClass(value); v.textContent = this._scalarLabel(value);
        el.appendChild(k); el.appendChild(v);
        return el;
      }
      const isArr = Array.isArray(value);
      const entries = isArr ? value.map((v, i) => [i, v]) : Object.entries(value);
      const summary = document.createElement('div');
      summary.className = 'cursor-pointer select-none hover:bg-zinc-900/40 rounded px-1';
      const tri = document.createElement('span'); tri.className = 'tree-toggle text-zinc-500'; tri.textContent = '▶';
      const lab = document.createElement('span');
      lab.innerHTML = `<span class="text-zinc-400">${this._htmlEscape(String(key))}</span><span class="text-zinc-500"> ${isArr ? '[' + entries.length + ']' : '{' + entries.length + '}'}</span>`;
      summary.appendChild(tri); summary.appendChild(document.createTextNode(' ')); summary.appendChild(lab);
      const children = document.createElement('div');
      children.style.marginLeft = '1rem';
      children.style.borderLeft = '1px dashed rgba(127,127,127,.18)';
      children.style.paddingLeft = '0.5rem';
      let loaded = false;
      const open = () => {
        if (!loaded) {
          loaded = true;
          for (const [k, v] of entries) {
            children.appendChild(this._buildTreeNode(k, v, depth + 1, false));
          }
        }
        children.style.display = '';
        tri.classList.add('open');
      };
      const close = () => { children.style.display = 'none'; tri.classList.remove('open'); };
      summary.addEventListener('click', () => {
        if (children.style.display === 'none') open(); else close();
      });
      el.appendChild(summary);
      el.appendChild(children);
      if (openByDefault && entries.length <= 40 && depth < 1) open(); else close();
      return el;
    },

    _scalarLabel(v) {
      if (v === null) return 'null';
      if (v === undefined) return 'undefined';
      if (typeof v === 'string') return JSON.stringify(v);
      return String(v);
    },

    _scalarClass(v) {
      if (v === null || v === undefined) return 'text-zinc-500 italic';
      if (typeof v === 'number') return 'text-emerald-400 num';
      if (typeof v === 'boolean') return 'text-amber-400';
      if (typeof v === 'string') return 'text-sky-300';
      return 'text-zinc-200';
    },

    _htmlEscape(s) {
      return s.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    },

    toggleTheme() {
      this.theme = this.theme === 'dark' ? 'light' : 'dark';
      document.documentElement.classList.toggle('dark', this.theme === 'dark');
      ['line-chart', 'bar-chart'].forEach(id => {
        const el = document.getElementById(id);
        if (!el) return;
        const inst = echarts.getInstanceByDom(el);
        if (inst) inst.dispose();
      });
      this.$nextTick(() => this.renderCharts());
    },

    writeHash() {
      const h = new URLSearchParams();
      h.set('view', this.view);
      if (this.q) h.set('q', this.q);
      if (this.sortKey) { h.set('sort', this.sortKey); h.set('dir', this.sortDir); }
      const s = h.toString();
      history.replaceState(null, '', s ? '#' + s : location.pathname);
    },

    _restoreFromHash() {
      const h = new URLSearchParams((location.hash || '').slice(1));
      const v = h.get('view'); if (v && this.isEligible(v)) this.view = v;
      const q = h.get('q'); if (q) this.q = q;
      const sk = h.get('sort'); if (sk) { this.sortKey = sk; this.sortDir = h.get('dir') === 'desc' ? 'desc' : 'asc'; }
    },

    _bindKeys() {
      window.addEventListener('keydown', (e) => {
        const tag = (e.target.tagName || '').toLowerCase();
        const inField = tag === 'input' || tag === 'textarea' || tag === 'select';
        if (e.key === 'Escape') {
          if (this.selectedRow !== null) { this.selectedRow = null; e.preventDefault(); return; }
          if (inField) { e.target.blur(); return; }
          return;
        }
        if (inField) return;
        if (e.key === '/') { e.preventDefault(); const sb = document.getElementById('search-box'); if (sb) { this.setView('table'); sb.focus(); } return; }
        const map = { '1': 'table', '2': 'line', '3': 'bar', '4': 'kpis', '5': 'tree' };
        if (map[e.key]) { this.setView(map[e.key]); return; }
        if (this.view === 'table' && (e.key === 'j' || e.key === 'k')) {
          const rows = this.pagedRows;
          if (!rows.length) return;
          let i = rows.indexOf(this.selectedRow);
          i = e.key === 'j' ? Math.min(rows.length - 1, i + 1) : Math.max(0, i < 0 ? 0 : i - 1);
          this.selectedRow = rows[i];
        }
      });
    },

    _installResize() {
      const onResize = () => {
        ['line-chart', 'bar-chart'].forEach(id => {
          const el = document.getElementById(id);
          if (!el) return;
          const inst = echarts.getInstanceByDom(el);
          if (inst) inst.resize();
        });
      };
      window.addEventListener('resize', onResize);
    },
  };
}
</script>
</body>
</html>
"""
