"""Generic data-display renderer for browser-harness scraped artifacts.

Reads .json / .jsonl / .csv source file(s), introspects the schema, and emits
a self-contained .html report with auto-detected views (table, line, bar,
KPIs, tree). Cross-domain by design: works on any list-of-dicts dataset.

Public surface: render_dataset(path, out=None, view=None, open_browser=False,
title=None, display=None, privacy_mode=False). `path` is either a single path-like, or an iterable
of paths / (label, path) tuples / {"label", "path", "view", "display"} dicts.
Multiple paths render into one explorer with a sources switcher.
"""
import csv
import json
import pathlib
import re
import statistics
import webbrowser
from importlib import resources

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
_JS_MAX_SAFE_INTEGER = 9007199254740991
_ID_SAFE_RE = re.compile(r"[^a-zA-Z0-9_]+")
_IDENTIFIER_FIELD_RE = re.compile(
    r"(^id$|(^|_)(id|ids|uuid|guid|identifier|account|acct|postal|postcode|zip|zipcode|phone|sku|code)(_|$))",
    re.I,
)
_ASSET_PACKAGE = "browser_harness_assets"
_ECHARTS_ASSET = "echarts-5.5.1.min.js"
_ALPINE_ASSET = "alpinejs-3.14.9-cdn.min.js"


def render_dataset(path, out=None, view=None, open_browser=False, title=None, display=None, privacy_mode=False):
    specs = _normalize_specs(path)
    if not specs:
        raise ValueError("render_dataset requires at least one path")

    datasets = []
    used_ids = set()
    for index, spec in enumerate(specs):
        dataset = _build_dataset(spec, index, used_ids, default_view=view, display=display, privacy_mode=privacy_mode)
        datasets.append(dataset)

    multi = len(datasets) > 1
    out_path = _resolve_out_path(out, datasets, multi)
    overall_title = _resolve_title(title, datasets, out_path, multi)
    html = _emit_html(datasets, overall_title, view, multi)
    out_path.write_text(html, encoding="utf-8")
    if open_browser:
        webbrowser.open(out_path.as_uri())
    return str(out_path)


def _normalize_specs(path):
    if isinstance(path, (str, pathlib.Path)):
        return [{"label": None, "path": pathlib.Path(path), "view": None, "display": None, "key": None}]
    if isinstance(path, dict):
        if "path" in path:
            return [_coerce_spec(path)]
        return [_coerce_spec(item) for item in path.items()]
    try:
        items = list(path)
    except TypeError as exc:
        raise TypeError(
            "path must be a path-like, an iterable of paths, or a mapping"
        ) from exc
    return [_coerce_spec(item) for item in items]


def _coerce_spec(item):
    if isinstance(item, (str, pathlib.Path)):
        return {"label": None, "path": pathlib.Path(item), "view": None, "display": None, "key": None}
    if isinstance(item, dict):
        if "path" not in item:
            raise ValueError(f"dataset spec missing 'path': {item!r}")
        label = item.get("label")
        return {
            "label": str(label) if label is not None else None,
            "path": pathlib.Path(item["path"]),
            "view": item.get("view"),
            "display": item.get("display"),
            "key": item.get("key"),
        }
    if isinstance(item, tuple) and len(item) == 2:
        label, src = item
        return {
            "label": str(label) if label is not None else None,
            "path": pathlib.Path(src),
            "view": None,
            "display": None,
            "key": None,
        }
    raise TypeError(f"unsupported dataset spec: {item!r}")


def _build_dataset(spec, index, used_ids, default_view=None, display=None, privacy_mode=False):
    src = spec["path"].expanduser().resolve()
    if not src.exists():
        raise FileNotFoundError(src)
    all_records, meta = _load_records(src)
    total_rows = len(all_records)
    records = all_records
    truncated = False
    if total_rows > _MAX_EMBEDDED_ROWS:
        truncated = True
        records = all_records[:_MAX_EMBEDDED_ROWS]
    label = spec.get("label") or src.stem
    ds_id = _make_dataset_id(label, index, used_ids)
    used_ids.add(ds_id)
    effective_display = _merge_display(display, spec.get("display"), label, ds_id, src)
    if privacy_mode:
        effective_display = _deep_merge(effective_display, {"privacy_mode": True, "external_assets": False})
    dataset_key = spec.get("key") or effective_display.get("key")
    schema = _apply_display_overrides(_introspect(all_records), effective_display)
    hidden_fields = _hidden_field_names(schema)
    if dataset_key and str(dataset_key) in hidden_fields:
        dataset_key = ""
    visible_schema = _schema_without_hidden_fields(schema)
    records = _records_without_fields(records, hidden_fields)
    aggregate_records = _records_without_fields(all_records, hidden_fields)
    aggregates = _build_aggregates(aggregate_records, visible_schema)
    meta_with_extras = {
        **meta,
        "title": src.name,
        "label": label,
        "truncated": truncated,
        "max_embedded_rows": _MAX_EMBEDDED_ROWS,
        "total_rows": total_rows,
        "embedded_rows": len(records),
        "aggregate_scope": "full",
    }
    return {
        "id": ds_id,
        "label": label,
        "data": records,
        "schema": visible_schema,
        "aggregates": aggregates,
        "meta": meta_with_extras,
        "display": effective_display,
        "key": str(dataset_key) if dataset_key else "",
        "default_view": spec.get("view") or effective_display.get("default_view") or default_view or "",
    }


def _make_dataset_id(label, index, used_ids):
    base = _ID_SAFE_RE.sub("_", label).strip("_").lower() or f"ds_{index}"
    candidate = base
    counter = 2
    while candidate in used_ids:
        candidate = f"{base}_{counter}"
        counter += 1
    return candidate


def _resolve_out_path(out, datasets, multi):
    if out:
        return pathlib.Path(out).expanduser().resolve()
    if multi:
        first_src = pathlib.Path(datasets[0]["meta"]["source_file"])
        return (first_src.parent / "data-explorer.html").resolve()
    first_src = pathlib.Path(datasets[0]["meta"]["source_file"])
    return first_src.with_suffix(".html").resolve()


def _resolve_title(title, datasets, out_path, multi):
    if title:
        return title
    if not multi:
        return datasets[0]["meta"].get("title") or out_path.name
    return f"{len(datasets)} datasets · {out_path.stem}"


def _merge_display(global_display, spec_display, label, ds_id, src):
    merged = _display_without_sources(global_display)
    sources = (global_display or {}).get("sources") if isinstance(global_display, dict) else None
    if isinstance(sources, dict):
        for key in (label, ds_id, src.name, src.stem, str(src)):
            if key in sources:
                merged = _deep_merge(merged, sources[key])
    merged = _deep_merge(merged, spec_display)
    return merged


def _display_without_sources(display):
    if not isinstance(display, dict):
        return {}
    return {k: v for k, v in display.items() if k != "sources"}


def _deep_merge(base, override):
    if not isinstance(base, dict):
        base = {}
    out = dict(base)
    if not isinstance(override, dict):
        return out
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _hidden_field_names(schema):
    return {
        field["name"]
        for field in schema.get("fields", [])
        if field.get("hidden") and "name" in field
    }


def _schema_without_hidden_fields(schema):
    fields = [field for field in schema.get("fields", []) if not field.get("hidden")]
    return {
        **schema,
        "fields": fields,
        "eligible_views": _dataset_eligible_views(fields),
    }


def _records_without_fields(records, field_names):
    if not field_names:
        return records
    return [
        {key: value for key, value in row.items() if key not in field_names}
        if isinstance(row, dict)
        else row
        for row in records
    ]


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
            rows.append(_normalize_csv_row(row))
    meta = {"source_file": str(path), "row_count": len(rows), "format": "csv"}
    return rows, meta


def _normalize_csv_row(row):
    out = {}
    for key, value in row.items():
        if key is None:
            extras = value if isinstance(value, list) else [value]
            for index, extra in enumerate(extras, start=1):
                out[f"_extra_{index}"] = _coerce_csv(extra, f"_extra_{index}")
            continue
        out[key] = _coerce_csv(value, key)
    return out


def _coerce_csv(v, field_name=None):
    if v is None or v == "":
        return None
    s = v.strip()
    if not s:
        return None
    if s.lstrip("-").isdigit():
        if _is_identifier_field(field_name) or _has_leading_zero_digits(s):
            return v
        try:
            i = int(s)
        except ValueError:
            pass
        else:
            if abs(i) <= _JS_MAX_SAFE_INTEGER:
                return i
            return v
    try:
        f = float(s)
        if "." in s or "e" in s.lower():
            return f
    except ValueError:
        pass
    if s.lower() in ("true", "false"):
        return s.lower() == "true"
    return v


def _is_identifier_field(field_name):
    if field_name is None:
        return False
    normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(field_name))
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", normalized).strip("_").lower()
    return bool(_IDENTIFIER_FIELD_RE.search(normalized))


def _has_leading_zero_digits(value):
    digits = value[1:] if value.startswith("-") else value
    return len(digits) > 1 and digits.startswith("0")


def _load_jsonl(path):
    rows = []
    skipped_lines = 0
    non_empty_lines = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        non_empty_lines += 1
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            skipped_lines += 1
            continue
        rows.append(obj if isinstance(obj, dict) else {"value": obj})
    meta = {
        "source_file": str(path),
        "row_count": len(rows),
        "format": "jsonl",
        "jsonl_non_empty_lines": non_empty_lines,
        "jsonl_skipped_lines": skipped_lines,
    }
    return rows, meta


def _load_json(path):
    obj = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(obj, list):
        rows = _normalize_json_rows(obj)
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
    records, key, key_path = _find_records_info(obj)
    rows = _normalize_json_rows(records)
    wrapper_meta = _copy_without_path(obj, key_path) if key_path else dict(obj)
    wrapper_meta.update({
        "source_file": str(path),
        "row_count": len(rows),
        "format": "json",
        "records_key": ".".join(str(part) for part in key_path) if key_path else "(none)",
    })
    return rows, wrapper_meta


def _normalize_json_rows(records):
    return [row if isinstance(row, dict) else {"value": row} for row in records]


def _find_records(obj):
    records, key, _key_path = _find_records_info(obj)
    return records, key


def _find_records_info(obj):
    for k in _RECORD_KEYS:
        v = obj.get(k)
        if isinstance(v, list) and v and all(isinstance(x, dict) for x in v[:5]):
            return v, k, (k,)
    best = None
    queue = [(obj, ())]
    while queue:
        cur, path = queue.pop(0)
        if isinstance(cur, dict):
            for k, v in cur.items():
                if isinstance(v, list) and v and all(isinstance(x, dict) for x in v[:5]):
                    if best is None or len(v) > len(best[0]):
                        best = (v, k, path + (k,))
                else:
                    queue.append((v, path + (k,)))
        elif isinstance(cur, list):
            queue.extend((v, path + (i,)) for i, v in enumerate(cur))
    if best:
        return best[0], best[1], best[2]
    return [], None, None


_REMOVE = object()


def _copy_without_path(value, path):
    if not path:
        return _REMOVE
    head, *tail = path
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if k == head:
                if not tail:
                    continue
                child = _copy_without_path(v, tuple(tail))
                if child is not _REMOVE:
                    out[k] = child
            else:
                out[k] = v
        return out
    if isinstance(value, list):
        out = []
        for i, v in enumerate(value):
            if i == head:
                if not tail:
                    continue
                child = _copy_without_path(v, tuple(tail))
                if child is not _REMOVE:
                    out.append(child)
            else:
                out.append(v)
        return out
    return value


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

    distinct = _bounded_distinct_count(non_null, cap=200)

    if not non_null:
        kind = "empty"
    elif nested_share >= 0.5:
        kind = "nested"
    elif bool_share >= 0.9:
        kind = "bool"
    elif numeric_share >= 0.9:
        kind = "numeric"
    elif string_share >= 0.9:
        kind = _classify_string(name, non_null, distinct)
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
        eligible_for.append("bar_x")
        if distinct <= 8:
            eligible_for.append("series_by")
    if kind == "time":
        eligible_for.append("line_x")
    if kind == "nested":
        eligible_for.append("tree")
    if kind == "bool":
        eligible_for.append("bar_x")

    return {
        "name": name,
        "display_name": name,
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


def _apply_display_overrides(schema, display):
    if not display:
        return schema
    labels = display.get("labels") or {}
    hidden = set(display.get("hidden_fields") or [])
    forced_kinds = display.get("field_kinds") or {}
    formats = display.get("formats") or display.get("value_formats") or {}
    renderers = display.get("renderers") or {}
    fields_config = display.get("fields") or {}
    fields = []
    for field in schema.get("fields", []):
        out = dict(field)
        config = fields_config.get(out["name"], {}) if isinstance(fields_config, dict) else {}
        if not isinstance(config, dict):
            config = {}
        forced_kind = config.get("kind") or forced_kinds.get(out["name"])
        if forced_kind:
            out["kind"] = str(forced_kind)
            out["is_measure"] = out["kind"] == "numeric" and not config.get("categorical", False)
            out["is_categorical_numeric"] = bool(config.get("categorical", False))
            out["eligible_for"] = _eligible_roles_for_field(out)
        out["display_name"] = str(config.get("label") or labels.get(out["name"]) or out.get("display_name") or out["name"])
        out["hidden"] = bool(config.get("hidden") or out["name"] in hidden)
        field_format = config.get("format") or formats.get(out["name"])
        if field_format:
            out["format"] = str(field_format)
        renderer = config.get("renderer") or renderers.get(out["name"])
        if renderer:
            out["renderer"] = str(renderer)
        fields.append(out)
    visible_fields = [field for field in fields if not field.get("hidden")]
    return {
        **schema,
        "fields": fields,
        "eligible_views": _dataset_eligible_views(visible_fields),
        "display": display,
    }


def _eligible_roles_for_field(field):
    roles = ["table"]
    kind = field.get("kind")
    if field.get("is_measure"):
        roles.extend(["line_y", "kpi"])
    if field.get("is_categorical_numeric"):
        roles.append("bar_x")
    if kind == "categorical":
        roles.append("bar_x")
        if field.get("distinct", 0) <= 8:
            roles.append("series_by")
    if kind == "time":
        roles.append("line_x")
    if kind == "nested":
        roles.append("tree")
    if kind == "bool":
        roles.append("bar_x")
    return roles


def _classify_string(name, values, distinct_hint=None):
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
    distinct = distinct_hint if distinct_hint is not None else _bounded_distinct_count(values, cap=200)
    n = len(values)
    if n >= 5 and distinct <= 30 and distinct <= max(n * 0.5, 1):
        return "categorical"
    return "text"


def _bounded_distinct_count(values, cap=200):
    distinct_set = set()
    for v in values:
        try:
            distinct_set.add(v)
        except TypeError:
            distinct_set.add(repr(v))
        if len(distinct_set) > cap:
            break
    return len(distinct_set)


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
    has_group = any(f["kind"] in ("categorical", "bool", "time") or f.get("is_categorical_numeric") for f in fields)
    eligible = ["table"]
    if fields:
        eligible.append("profile")
    if has_time and has_measure:
        eligible.append("line")
    if has_bar_x:
        eligible.append("bar")
    if has_group and has_measure:
        eligible.append("pivot")
    if has_measure:
        eligible.append("kpis")
    if has_nested or fields:
        eligible.append("tree")
    return eligible


def _build_aggregates(records, schema):
    return {
        "kpis": _aggregate_kpis(records, schema),
        "bar": _aggregate_bar(records, schema),
        "line": _aggregate_line(records, schema),
        "profile": _aggregate_profile(records, schema),
    }


def _aggregate_profile(records, schema):
    fields = []
    for field in schema.get("fields", []):
        name = field["name"]
        values = [row.get(name) for row in records if isinstance(row, dict)]
        non_null = [value for value in values if value is not None]
        distinct = _bounded_distinct_count(non_null, cap=1000)
        field_profile = {
            "name": name,
            "display_name": field.get("display_name", name),
            "kind": field.get("kind", "text"),
            "hidden": bool(field.get("hidden")),
            "count": len(values),
            "non_null": len(non_null),
            "null_count": len(values) - len(non_null),
            "null_pct": round(100 * (len(values) - len(non_null)) / max(len(values), 1), 1),
            "distinct": min(distinct, 1000),
            "distinct_limited": distinct > 1000,
            "examples": field.get("examples", []),
            "top_values": _top_values(non_null, limit=10),
        }
        if field.get("kind") == "numeric":
            field_profile["numeric"] = _numeric_profile(non_null)
        elif field.get("kind") == "time":
            time_values = sorted(str(value) for value in non_null)
            if time_values:
                field_profile["time"] = {"min": time_values[0], "max": time_values[-1]}
        fields.append(field_profile)
    return {"fields": fields}


def _top_values(values, limit=10):
    counts = {}
    for value in values:
        key = _stringify_key(value)
        counts[key] = counts.get(key, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
    return [{"value": key, "count": count} for key, count in ranked]


def _numeric_profile(values):
    vals = sorted(
        float(value)
        for value in values
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    )
    if not vals:
        return None
    count = len(vals)
    total = sum(vals)
    return {
        "count": count,
        "sum": total,
        "mean": total / count,
        "median": float(statistics.median(vals)),
        "p90": _percentile(vals, 0.9),
        "min": vals[0],
        "max": vals[-1],
        "histogram": _histogram(vals),
    }


def _histogram(sorted_values, bins=10):
    if not sorted_values:
        return []
    low = sorted_values[0]
    high = sorted_values[-1]
    if low == high:
        return [{"min": low, "max": high, "count": len(sorted_values)}]
    width = (high - low) / bins
    counts = [0 for _ in range(bins)]
    for value in sorted_values:
        idx = min(int((value - low) / width), bins - 1)
        counts[idx] += 1
    return [
        {"min": low + width * i, "max": low + width * (i + 1), "count": count}
        for i, count in enumerate(counts)
    ]


def _aggregate_kpis(records, schema):
    out = {}
    measure_fields = [f["name"] for f in schema.get("fields", []) if f.get("is_measure")]
    for field in measure_fields:
        vals = []
        for row in records:
            v = row.get(field) if isinstance(row, dict) else None
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                vals.append(float(v))
        if not vals:
            continue
        vals_sorted = sorted(vals)
        count = len(vals_sorted)
        total = sum(vals_sorted)
        out[field] = {
            "count": count,
            "sum": total,
            "mean": total / count,
            "median": float(statistics.median(vals_sorted)),
            "p90": _percentile(vals_sorted, 0.9),
            "min": vals_sorted[0],
            "max": vals_sorted[-1],
        }
    return out


def _aggregate_bar(records, schema, top_n=50):
    out = {}
    bar_fields = [f["name"] for f in schema.get("fields", []) if "bar_x" in f.get("eligible_for", [])]
    for field in bar_fields:
        counts = {}
        for row in records:
            if not isinstance(row, dict):
                continue
            value = row.get(field)
            key = "∅" if value is None else _stringify_key(value)
            counts[key] = counts.get(key, 0) + 1
        ranked = sorted(counts.items(), key=lambda item: item[1], reverse=True)[:top_n]
        out[field] = [[k, v] for k, v in ranked]
    return out


def _aggregate_line(records, schema):
    out = {}
    fields = schema.get("fields", [])
    line_x_fields = [f["name"] for f in fields if "line_x" in f.get("eligible_for", [])]
    line_y_fields = [f["name"] for f in fields if "line_y" in f.get("eligible_for", [])]
    series_fields = [f["name"] for f in fields if "series_by" in f.get("eligible_for", []) and f.get("distinct", 0) <= 8]
    series_options = [None] + series_fields

    for x_field in line_x_fields:
        for y_field in line_y_fields:
            for series_field in series_options:
                key = _line_key(x_field, y_field, series_field)
                buckets = {}
                for row in records:
                    if not isinstance(row, dict):
                        continue
                    x_value = row.get(x_field)
                    y_value = row.get(y_field)
                    if x_value is None or not isinstance(y_value, (int, float)) or isinstance(y_value, bool):
                        continue
                    x_key = str(x_value)
                    s_key = str(row.get(series_field) if series_field else "__total__")
                    if s_key == "None":
                        s_key = "∅"
                    x_bucket = buckets.setdefault(x_key, {})
                    arr = x_bucket.setdefault(s_key, [])
                    arr.append(float(y_value))

                if not buckets:
                    continue

                xs = sorted(buckets.keys(), key=_line_x_sort_key)
                all_series = set()
                for x in xs:
                    all_series.update(buckets[x].keys())
                if series_field:
                    ordered_series = sorted(all_series)[:8]
                else:
                    ordered_series = ["__total__"]

                series = []
                for series_name in ordered_series:
                    sum_values = []
                    count_values = []
                    min_values = []
                    max_values = []
                    for x in xs:
                        vals = buckets[x].get(series_name, [])
                        if not vals:
                            sum_values.append(None)
                            count_values.append(0)
                            min_values.append(None)
                            max_values.append(None)
                            continue
                        sum_values.append(sum(vals))
                        count_values.append(len(vals))
                        min_values.append(min(vals))
                        max_values.append(max(vals))
                    series.append(
                        {
                            "name": f"{series_name}" if series_name != "__total__" else "__total__",
                            "sum": sum_values,
                            "count": count_values,
                            "min": min_values,
                            "max": max_values,
                        }
                    )
                out[key] = {"xs": xs, "series": series}
    return out


def _percentile(sorted_values, fraction):
    if not sorted_values:
        return None
    idx = int((len(sorted_values) - 1) * fraction)
    return float(sorted_values[idx])


def _line_key(x_field, y_field, series_field):
    return f"{x_field}||{y_field}||{series_field or ''}"


def _line_x_sort_key(value):
    text = str(value)
    if _ISO_DATE_RE.match(text):
        normalized = text.replace("/", "-")
        return (0, normalized)
    try:
        numeric = float(text)
    except ValueError:
        return (2, text)
    return (1, numeric)


def _stringify_key(value):
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return str(value)


# ---------------------------------------------------------------------------
# HTML emission
# ---------------------------------------------------------------------------


def _emit_html(datasets, title, default_view, multi):
    payload = {
        "datasets": datasets,
        "active_id": datasets[0]["id"],
        "title": title,
        "default_view": default_view or "",
        "multi": multi,
    }
    return (
        _TEMPLATE.replace("__TITLE__", _escape_html(title))
        .replace("__TAILWIND_CSS__", _TAILWIND_CSS)
        .replace("__ECHARTS_JS__", _escape_for_script_tag(_asset_text(_ECHARTS_ASSET)))
        .replace("__ALPINE_JS__", _escape_for_script_tag(_asset_text(_ALPINE_ASSET)))
        .replace("__PAYLOAD__", _escape_for_script_tag(json.dumps(payload, default=str, ensure_ascii=False)))
    )


def _asset_text(name):
    try:
        return resources.files(_ASSET_PACKAGE).joinpath(name).read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError):
        return (pathlib.Path(__file__).with_name(_ASSET_PACKAGE) / name).read_text(encoding="utf-8")


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


# How to regenerate _TAILWIND_CSS:
# 1) Write _TEMPLATE to /tmp/tpl.html
# 2) Create /tmp/base.css with @tailwind base/components/utilities directives
# 3) Create /tmp/tailwind.config.js with darkMode='class' and content=['/tmp/tpl.html']
# 4) Run: npm exec --yes --package=tailwindcss@3.4.14 -- tailwindcss -c /tmp/tailwind.config.js -i /tmp/base.css -o /tmp/out.css --minify
# 5) Paste /tmp/out.css into _TAILWIND_CSS below

_TAILWIND_CSS = r"""*,:after,:before{--tw-border-spacing-x:0;--tw-border-spacing-y:0;--tw-translate-x:0;--tw-translate-y:0;--tw-rotate:0;--tw-skew-x:0;--tw-skew-y:0;--tw-scale-x:1;--tw-scale-y:1;--tw-pan-x: ;--tw-pan-y: ;--tw-pinch-zoom: ;--tw-scroll-snap-strictness:proximity;--tw-gradient-from-position: ;--tw-gradient-via-position: ;--tw-gradient-to-position: ;--tw-ordinal: ;--tw-slashed-zero: ;--tw-numeric-figure: ;--tw-numeric-spacing: ;--tw-numeric-fraction: ;--tw-ring-inset: ;--tw-ring-offset-width:0px;--tw-ring-offset-color:#fff;--tw-ring-color:rgba(59,130,246,.5);--tw-ring-offset-shadow:0 0 #0000;--tw-ring-shadow:0 0 #0000;--tw-shadow:0 0 #0000;--tw-shadow-colored:0 0 #0000;--tw-blur: ;--tw-brightness: ;--tw-contrast: ;--tw-grayscale: ;--tw-hue-rotate: ;--tw-invert: ;--tw-saturate: ;--tw-sepia: ;--tw-drop-shadow: ;--tw-backdrop-blur: ;--tw-backdrop-brightness: ;--tw-backdrop-contrast: ;--tw-backdrop-grayscale: ;--tw-backdrop-hue-rotate: ;--tw-backdrop-invert: ;--tw-backdrop-opacity: ;--tw-backdrop-saturate: ;--tw-backdrop-sepia: ;--tw-contain-size: ;--tw-contain-layout: ;--tw-contain-paint: ;--tw-contain-style: }::backdrop{--tw-border-spacing-x:0;--tw-border-spacing-y:0;--tw-translate-x:0;--tw-translate-y:0;--tw-rotate:0;--tw-skew-x:0;--tw-skew-y:0;--tw-scale-x:1;--tw-scale-y:1;--tw-pan-x: ;--tw-pan-y: ;--tw-pinch-zoom: ;--tw-scroll-snap-strictness:proximity;--tw-gradient-from-position: ;--tw-gradient-via-position: ;--tw-gradient-to-position: ;--tw-ordinal: ;--tw-slashed-zero: ;--tw-numeric-figure: ;--tw-numeric-spacing: ;--tw-numeric-fraction: ;--tw-ring-inset: ;--tw-ring-offset-width:0px;--tw-ring-offset-color:#fff;--tw-ring-color:rgba(59,130,246,.5);--tw-ring-offset-shadow:0 0 #0000;--tw-ring-shadow:0 0 #0000;--tw-shadow:0 0 #0000;--tw-shadow-colored:0 0 #0000;--tw-blur: ;--tw-brightness: ;--tw-contrast: ;--tw-grayscale: ;--tw-hue-rotate: ;--tw-invert: ;--tw-saturate: ;--tw-sepia: ;--tw-drop-shadow: ;--tw-backdrop-blur: ;--tw-backdrop-brightness: ;--tw-backdrop-contrast: ;--tw-backdrop-grayscale: ;--tw-backdrop-hue-rotate: ;--tw-backdrop-invert: ;--tw-backdrop-opacity: ;--tw-backdrop-saturate: ;--tw-backdrop-sepia: ;--tw-contain-size: ;--tw-contain-layout: ;--tw-contain-paint: ;--tw-contain-style: }/*! tailwindcss v3.4.14 | MIT License | https://tailwindcss.com*/*,:after,:before{box-sizing:border-box;border:0 solid #e5e7eb}:after,:before{--tw-content:""}:host,html{line-height:1.5;-webkit-text-size-adjust:100%;-moz-tab-size:4;-o-tab-size:4;tab-size:4;font-family:ui-sans-serif,system-ui,sans-serif,Apple Color Emoji,Segoe UI Emoji,Segoe UI Symbol,Noto Color Emoji;font-feature-settings:normal;font-variation-settings:normal;-webkit-tap-highlight-color:transparent}body{margin:0;line-height:inherit}hr{height:0;color:inherit;border-top-width:1px}abbr:where([title]){-webkit-text-decoration:underline dotted;text-decoration:underline dotted}h1,h2,h3,h4,h5,h6{font-size:inherit;font-weight:inherit}a{color:inherit;text-decoration:inherit}b,strong{font-weight:bolder}code,kbd,pre,samp{font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,Liberation Mono,Courier New,monospace;font-feature-settings:normal;font-variation-settings:normal;font-size:1em}small{font-size:80%}sub,sup{font-size:75%;line-height:0;position:relative;vertical-align:baseline}sub{bottom:-.25em}sup{top:-.5em}table{text-indent:0;border-color:inherit;border-collapse:collapse}button,input,optgroup,select,textarea{font-family:inherit;font-feature-settings:inherit;font-variation-settings:inherit;font-size:100%;font-weight:inherit;line-height:inherit;letter-spacing:inherit;color:inherit;margin:0;padding:0}button,select{text-transform:none}button,input:where([type=button]),input:where([type=reset]),input:where([type=submit]){-webkit-appearance:button;background-color:transparent;background-image:none}:-moz-focusring{outline:auto}:-moz-ui-invalid{box-shadow:none}progress{vertical-align:baseline}::-webkit-inner-spin-button,::-webkit-outer-spin-button{height:auto}[type=search]{-webkit-appearance:textfield;outline-offset:-2px}::-webkit-search-decoration{-webkit-appearance:none}::-webkit-file-upload-button{-webkit-appearance:button;font:inherit}summary{display:list-item}blockquote,dd,dl,figure,h1,h2,h3,h4,h5,h6,hr,p,pre{margin:0}fieldset{margin:0}fieldset,legend{padding:0}menu,ol,ul{list-style:none;margin:0;padding:0}dialog{padding:0}textarea{resize:vertical}input::-moz-placeholder,textarea::-moz-placeholder{opacity:1;color:#9ca3af}input::placeholder,textarea::placeholder{opacity:1;color:#9ca3af}[role=button],button{cursor:pointer}:disabled{cursor:default}audio,canvas,embed,iframe,img,object,svg,video{display:block;vertical-align:middle}img,video{max-width:100%;height:auto}[hidden]:where(:not([hidden=until-found])){display:none}.fixed{position:fixed}.absolute{position:absolute}.relative{position:relative}.sticky{position:sticky}.inset-0{inset:0}.left-3{left:.75rem}.right-0{right:0}.top-0{top:0}.top-1\/2{top:50%}.z-30{z-index:30}.z-40{z-index:40}.mb-2{margin-bottom:.5rem}.mb-3{margin-bottom:.75rem}.ml-1{margin-left:.25rem}.ml-2{margin-left:.5rem}.ml-auto{margin-left:auto}.mt-2{margin-top:.5rem}.mt-3{margin-top:.75rem}.block{display:block}.inline-block{display:inline-block}.flex{display:flex}.table{display:table}.grid{display:grid}.contents{display:contents}.h-12{height:3rem}.h-\[60vh\]{height:60vh}.h-full{height:100%}.max-h-\[calc\(100vh-12rem\)\]{max-height:calc(100vh - 12rem)}.min-h-\[calc\(100vh-3rem\)\]{min-height:calc(100vh - 3rem)}.min-h-screen{min-height:100vh}.w-12{width:3rem}.w-24{width:6rem}.w-4{width:1rem}.w-56{width:14rem}.w-8{width:2rem}.w-full{width:100%}.min-w-0{min-width:0}.min-w-\[10rem\]{min-width:10rem}.min-w-\[12rem\]{min-width:12rem}.max-w-\[16rem\]{max-width:16rem}.max-w-xl{max-width:36rem}.max-w-xs{max-width:20rem}.flex-1{flex:1 1 0%}.shrink-0{flex-shrink:0}.-translate-y-1\/2{--tw-translate-y:-50%}.-translate-y-1\/2,.translate-x-0{transform:translate(var(--tw-translate-x),var(--tw-translate-y)) rotate(var(--tw-rotate)) skewX(var(--tw-skew-x)) skewY(var(--tw-skew-y)) scaleX(var(--tw-scale-x)) scaleY(var(--tw-scale-y))}.translate-x-0{--tw-translate-x:0px}.translate-x-full{--tw-translate-x:100%}.transform,.translate-x-full{transform:translate(var(--tw-translate-x),var(--tw-translate-y)) rotate(var(--tw-rotate)) skewX(var(--tw-skew-x)) skewY(var(--tw-skew-y)) scaleX(var(--tw-scale-x)) scaleY(var(--tw-scale-y))}.cursor-not-allowed{cursor:not-allowed}.cursor-pointer{cursor:pointer}.select-none{-webkit-user-select:none;-moz-user-select:none;user-select:none}.resize{resize:both}.grid-cols-2{grid-template-columns:repeat(2,minmax(0,1fr))}.flex-col{flex-direction:column}.flex-wrap{flex-wrap:wrap}.items-end{align-items:flex-end}.items-center{align-items:center}.justify-between{justify-content:space-between}.gap-1{gap:.25rem}.gap-2{gap:.5rem}.gap-3{gap:.75rem}.gap-4{gap:1rem}.gap-x-4{-moz-column-gap:1rem;column-gap:1rem}.gap-x-5{-moz-column-gap:1.25rem;column-gap:1.25rem}.gap-y-1{row-gap:.25rem}.space-y-1>:not([hidden])~:not([hidden]){--tw-space-y-reverse:0;margin-top:calc(.25rem*(1 - var(--tw-space-y-reverse)));margin-bottom:calc(.25rem*var(--tw-space-y-reverse))}.divide-y>:not([hidden])~:not([hidden]){--tw-divide-y-reverse:0;border-top-width:calc(1px*(1 - var(--tw-divide-y-reverse)));border-bottom-width:calc(1px*var(--tw-divide-y-reverse))}.divide-zinc-200>:not([hidden])~:not([hidden]){--tw-divide-opacity:1;border-color:rgb(228 228 231/var(--tw-divide-opacity))}.overflow-auto{overflow:auto}.truncate{overflow:hidden;text-overflow:ellipsis}.truncate,.whitespace-nowrap{white-space:nowrap}.rounded{border-radius:.25rem}.rounded-md{border-radius:.375rem}.border{border-width:1px}.border-b{border-bottom-width:1px}.border-l{border-left-width:1px}.border-r{border-right-width:1px}.border-t{border-top-width:1px}.border-indigo-500\/30{border-color:rgba(99,102,241,.3)}.border-transparent{border-color:transparent}.border-zinc-200{--tw-border-opacity:1;border-color:rgb(228 228 231/var(--tw-border-opacity))}.border-zinc-300{--tw-border-opacity:1;border-color:rgb(212 212 216/var(--tw-border-opacity))}.bg-black\/50{background-color:rgba(0,0,0,.5)}.bg-indigo-500\/15{background-color:rgba(99,102,241,.15)}.bg-white{--tw-bg-opacity:1;background-color:rgb(255 255 255/var(--tw-bg-opacity))}.bg-white\/80{background-color:hsla(0,0%,100%,.8)}.bg-zinc-50{--tw-bg-opacity:1;background-color:rgb(250 250 250/var(--tw-bg-opacity))}.bg-zinc-50\/95{background-color:hsla(0,0%,98%,.95)}.object-cover{-o-object-fit:cover;object-fit:cover}.p-2{padding:.5rem}.p-3{padding:.75rem}.p-4{padding:1rem}.p-5{padding:1.25rem}.px-1{padding-left:.25rem;padding-right:.25rem}.px-2{padding-left:.5rem;padding-right:.5rem}.px-3{padding-left:.75rem;padding-right:.75rem}.px-4{padding-left:1rem;padding-right:1rem}.px-5{padding-left:1.25rem;padding-right:1.25rem}.py-1{padding-top:.25rem;padding-bottom:.25rem}.py-1\.5{padding-top:.375rem;padding-bottom:.375rem}.py-2{padding-top:.5rem;padding-bottom:.5rem}.py-3{padding-top:.75rem;padding-bottom:.75rem}.py-8{padding-top:2rem;padding-bottom:2rem}.pb-1{padding-bottom:.25rem}.pb-2{padding-bottom:.5rem}.pb-3{padding-bottom:.75rem}.pl-9{padding-left:2.25rem}.pr-3{padding-right:.75rem}.pt-1{padding-top:.25rem}.pt-3{padding-top:.75rem}.text-left{text-align:left}.text-center{text-align:center}.text-right{text-align:right}.align-top{vertical-align:top}.font-mono{font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,Liberation Mono,Courier New,monospace}.text-\[10px\]{font-size:10px}.text-\[11px\]{font-size:11px}.text-\[13px\]{font-size:13px}.text-sm{font-size:.875rem;line-height:1.25rem}.text-xs{font-size:.75rem;line-height:1rem}.font-medium{font-weight:500}.font-semibold{font-weight:600}.uppercase{text-transform:uppercase}.italic{font-style:italic}.leading-relaxed{line-height:1.625}.tracking-tight{letter-spacing:-.025em}.tracking-wide{letter-spacing:.025em}.text-amber-400{--tw-text-opacity:1;color:rgb(251 191 36/var(--tw-text-opacity))}.text-emerald-400{--tw-text-opacity:1;color:rgb(52 211 153/var(--tw-text-opacity))}.text-indigo-400{--tw-text-opacity:1;color:rgb(129 140 248/var(--tw-text-opacity))}.text-indigo-700{--tw-text-opacity:1;color:rgb(67 56 202/var(--tw-text-opacity))}.text-sky-300{--tw-text-opacity:1;color:rgb(125 211 252/var(--tw-text-opacity))}.text-zinc-200{--tw-text-opacity:1;color:rgb(228 228 231/var(--tw-text-opacity))}.text-zinc-400{--tw-text-opacity:1;color:rgb(161 161 170/var(--tw-text-opacity))}.text-zinc-500{--tw-text-opacity:1;color:rgb(113 113 122/var(--tw-text-opacity))}.text-zinc-600{--tw-text-opacity:1;color:rgb(82 82 91/var(--tw-text-opacity))}.text-zinc-700{--tw-text-opacity:1;color:rgb(63 63 70/var(--tw-text-opacity))}.text-zinc-900{--tw-text-opacity:1;color:rgb(24 24 27/var(--tw-text-opacity))}.antialiased{-webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale}.opacity-30{opacity:.3}.opacity-50{opacity:.5}.opacity-60{opacity:.6}.opacity-80{opacity:.8}.shadow-2xl{--tw-shadow:0 25px 50px -12px rgba(0,0,0,.25);--tw-shadow-colored:0 25px 50px -12px var(--tw-shadow-color);box-shadow:var(--tw-ring-offset-shadow,0 0 #0000),var(--tw-ring-shadow,0 0 #0000),var(--tw-shadow)}.blur{--tw-blur:blur(8px)}.blur,.filter{filter:var(--tw-blur) var(--tw-brightness) var(--tw-contrast) var(--tw-grayscale) var(--tw-hue-rotate) var(--tw-invert) var(--tw-saturate) var(--tw-sepia) var(--tw-drop-shadow)}.backdrop-blur{--tw-backdrop-blur:blur(8px)}.backdrop-blur,.backdrop-filter{-webkit-backdrop-filter:var(--tw-backdrop-blur) var(--tw-backdrop-brightness) var(--tw-backdrop-contrast) var(--tw-backdrop-grayscale) var(--tw-backdrop-hue-rotate) var(--tw-backdrop-invert) var(--tw-backdrop-opacity) var(--tw-backdrop-saturate) var(--tw-backdrop-sepia);backdrop-filter:var(--tw-backdrop-blur) var(--tw-backdrop-brightness) var(--tw-backdrop-contrast) var(--tw-backdrop-grayscale) var(--tw-backdrop-hue-rotate) var(--tw-backdrop-invert) var(--tw-backdrop-opacity) var(--tw-backdrop-saturate) var(--tw-backdrop-sepia)}.transition{transition-property:color,background-color,border-color,text-decoration-color,fill,stroke,opacity,box-shadow,transform,filter,-webkit-backdrop-filter;transition-property:color,background-color,border-color,text-decoration-color,fill,stroke,opacity,box-shadow,transform,filter,backdrop-filter;transition-property:color,background-color,border-color,text-decoration-color,fill,stroke,opacity,box-shadow,transform,filter,backdrop-filter,-webkit-backdrop-filter;transition-timing-function:cubic-bezier(.4,0,.2,1);transition-duration:.15s}.duration-100{transition-duration:.1s}.duration-150{transition-duration:.15s}.ease-in{transition-timing-function:cubic-bezier(.4,0,1,1)}.ease-out{transition-timing-function:cubic-bezier(0,0,.2,1)}.hover\:bg-zinc-100:hover{--tw-bg-opacity:1;background-color:rgb(244 244 245/var(--tw-bg-opacity))}.hover\:text-indigo-400:hover{--tw-text-opacity:1;color:rgb(129 140 248/var(--tw-text-opacity))}.hover\:text-zinc-900:hover{--tw-text-opacity:1;color:rgb(24 24 27/var(--tw-text-opacity))}.hover\:underline:hover{text-decoration-line:underline}.focus\:border-indigo-500:focus{--tw-border-opacity:1;border-color:rgb(99 102 241/var(--tw-border-opacity))}.focus\:outline-none:focus{outline:2px solid transparent;outline-offset:2px}@supports ((-webkit-backdrop-filter:var(--tw )) or (backdrop-filter:var(--tw ))){.supports-\[backdrop-filter\]\:bg-white\/60{background-color:hsla(0,0%,100%,.6)}}.dark\:divide-zinc-900:is(.dark *)>:not([hidden])~:not([hidden]){--tw-divide-opacity:1;border-color:rgb(24 24 27/var(--tw-divide-opacity))}.dark\:border-zinc-700:is(.dark *){--tw-border-opacity:1;border-color:rgb(63 63 70/var(--tw-border-opacity))}.dark\:border-zinc-800:is(.dark *){--tw-border-opacity:1;border-color:rgb(39 39 42/var(--tw-border-opacity))}.dark\:border-zinc-800\/70:is(.dark *){border-color:rgba(39,39,42,.7)}.dark\:bg-zinc-900:is(.dark *){--tw-bg-opacity:1;background-color:rgb(24 24 27/var(--tw-bg-opacity))}.dark\:bg-zinc-900\/40:is(.dark *){background-color:rgba(24,24,27,.4)}.dark\:bg-zinc-900\/95:is(.dark *){background-color:rgba(24,24,27,.95)}.dark\:bg-zinc-950:is(.dark *){--tw-bg-opacity:1;background-color:rgb(9 9 11/var(--tw-bg-opacity))}.dark\:bg-zinc-950\/80:is(.dark *){background-color:rgba(9,9,11,.8)}.dark\:text-indigo-300:is(.dark *){--tw-text-opacity:1;color:rgb(165 180 252/var(--tw-text-opacity))}.dark\:text-zinc-100:is(.dark *){--tw-text-opacity:1;color:rgb(244 244 245/var(--tw-text-opacity))}.dark\:text-zinc-200:is(.dark *){--tw-text-opacity:1;color:rgb(228 228 231/var(--tw-text-opacity))}.dark\:text-zinc-300:is(.dark *){--tw-text-opacity:1;color:rgb(212 212 216/var(--tw-text-opacity))}.dark\:text-zinc-400:is(.dark *){--tw-text-opacity:1;color:rgb(161 161 170/var(--tw-text-opacity))}.dark\:text-zinc-500:is(.dark *){--tw-text-opacity:1;color:rgb(113 113 122/var(--tw-text-opacity))}.dark\:hover\:bg-zinc-800:hover:is(.dark *){--tw-bg-opacity:1;background-color:rgb(39 39 42/var(--tw-bg-opacity))}.dark\:hover\:bg-zinc-900:hover:is(.dark *){--tw-bg-opacity:1;background-color:rgb(24 24 27/var(--tw-bg-opacity))}.dark\:hover\:bg-zinc-900\/40:hover:is(.dark *){background-color:rgba(24,24,27,.4)}.dark\:hover\:bg-zinc-900\/60:hover:is(.dark *){background-color:rgba(24,24,27,.6)}.dark\:hover\:text-zinc-100:hover:is(.dark *){--tw-text-opacity:1;color:rgb(244 244 245/var(--tw-text-opacity))}.dark\:hover\:text-zinc-200:hover:is(.dark *){--tw-text-opacity:1;color:rgb(228 228 231/var(--tw-text-opacity))}@supports ((-webkit-backdrop-filter:var(--tw )) or (backdrop-filter:var(--tw ))){.dark\:supports-\[backdrop-filter\]\:bg-zinc-950\/60:is(.dark *){background-color:rgba(9,9,11,.6)}}@media (min-width:640px){.sm\:w-\[36rem\]{width:36rem}}"""


_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__ — data display</title>
<script>
  (function () {
    var t = localStorage.getItem('bh-data-display.theme') ||
      (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    if (t === 'dark') document.documentElement.classList.add('dark');
  })();
</script>
<style>__TAILWIND_CSS__</style>
<script>__ECHARTS_JS__</script>
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
  .app-shell { display: grid; grid-template-columns: 17rem minmax(0, 1fr); }
  .app-sidebar { border-right: 1px solid rgba(127,127,127,.18); min-height: calc(100vh - var(--header-h, 5rem)); background: rgba(255,255,255,.72); }
  .dark .app-sidebar { background: rgba(9,9,11,.72); }
  .mobile-bar { display: none; }
  .mobile-disabled-reason { display: none; }
  .mobile-menu-button { display: none; }
  .facet-panel { padding: .75rem .5rem 1rem; border-top: 1px solid rgba(127,127,127,.16); }
  .facet-card { border: 1px solid rgba(127,127,127,.18); border-radius: 6px; padding: .55rem; margin-bottom: .5rem; background: rgba(127,127,127,.04); }
  .facet-values { max-height: 12rem; overflow: auto; margin-top: .4rem; display: grid; gap: .2rem; }
  .facet-value-button { width: 100%; display: flex; align-items: center; justify-content: space-between; gap: .5rem; padding: .28rem .38rem; border-radius: 4px; font-size: 12px; text-align: left; }
  .facet-value-button:hover { background: rgba(99,102,241,.1); }
  .facet-value-button.active { color: rgb(129 140 248); background: rgba(99,102,241,.16); }
  .filter-chip { display: inline-flex; align-items: center; gap: .35rem; padding: .2rem .45rem; border: 1px solid rgba(99,102,241,.35); border-radius: 999px; background: rgba(99,102,241,.11); font-size: 11px; }
  .relationship-map { padding: .65rem .5rem .8rem; border-bottom: 1px solid rgba(127,127,127,.16); }
  .source-graph { display: grid; gap: .35rem; margin-bottom: .55rem; }
  .source-graph-row { width: 100%; display: grid; grid-template-columns: minmax(0, 1fr) 2.5rem minmax(0, 1fr); align-items: center; gap: .25rem; padding: .25rem; border-radius: 6px; }
  .source-graph-row:hover { background: rgba(99,102,241,.08); }
  .source-graph-node { min-width: 0; border: 1px solid rgba(127,127,127,.22); border-radius: 999px; padding: .25rem .4rem; font-size: 11px; text-align: center; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; background: rgba(255,255,255,.45); }
  .dark .source-graph-node { background: rgba(9,9,11,.45); }
  .source-graph-node.active { border-color: rgba(99,102,241,.55); background: rgba(99,102,241,.14); color: rgb(129 140 248); }
  .source-graph-line { position: relative; display: flex; justify-content: center; color: rgb(113 113 122); font-size: 9px; line-height: 1; }
  .source-graph-line::before { content: ""; position: absolute; left: 0; right: 0; top: 50%; border-top: 1px solid rgba(99,102,241,.42); }
  .source-graph-line span { position: relative; z-index: 1; max-width: 2.5rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; padding: 0 .15rem; background: white; }
  .dark .source-graph-line span { background: rgb(9 9 11); }
  .source-node { border: 1px solid rgba(127,127,127,.2); border-radius: 6px; padding: .45rem .55rem; font-size: 12px; }
  .source-node.active { border-color: rgba(99,102,241,.45); background: rgba(99,102,241,.14); color: rgb(129 140 248); }
  .source-edge { width: 100%; display: flex; align-items: center; justify-content: space-between; gap: .5rem; padding: .35rem .45rem; border-radius: 5px; font-size: 11px; color: rgb(113 113 122); }
  .source-edge:hover { background: rgba(99,102,241,.1); color: rgb(129 140 248); }
  .disabled-reason { display: block; margin-top: .15rem; padding-left: 1.6rem; font-size: 10px; line-height: 1.25; color: rgb(113 113 122); }
  .column-menu { position: absolute; z-index: 35; min-width: 14rem; top: calc(100% + .25rem); left: 0; border: 1px solid rgba(127,127,127,.24); border-radius: 6px; padding: .45rem; background: white; color: rgb(24 24 27); box-shadow: 0 16px 40px rgba(0,0,0,.18); }
  .dark .column-menu { background: rgb(9 9 11); color: rgb(244 244 245); }
  .column-menu button, .column-menu select, .column-menu input { width: 100%; }
  .menu-row { display: grid; gap: .3rem; margin-bottom: .35rem; }
  .menu-action { padding: .35rem .45rem; border-radius: 4px; text-align: left; font-size: 12px; }
  .menu-action:hover { background: rgba(99,102,241,.1); }
  .col-resize { display: inline-block; width: 5px; align-self: stretch; cursor: col-resize; border-radius: 4px; }
  .col-resize:hover { background: rgba(99,102,241,.35); }
  .table-wrap .wrap-cell { white-space: normal; word-break: break-word; }
  .table-compact td { padding-top: .22rem; padding-bottom: .22rem; }
  .table-comfortable td { padding-top: .45rem; padding-bottom: .45rem; }
  .table-scroll-hint { display: inline-flex; align-items: center; gap: .35rem; font-size: 11px; color: rgb(113 113 122); }
  .sticky-col { position: sticky; left: 0; z-index: 2; background: rgb(250 250 250); box-shadow: 1px 0 0 rgba(127,127,127,.16); }
  .dark .sticky-col { background: rgb(9 9 11); }
  .chart-presets { display: flex; flex-wrap: wrap; gap: .4rem; margin-bottom: .75rem; }
  .chart-preset { padding: .35rem .55rem; border: 1px solid rgba(127,127,127,.2); border-radius: 999px; font-size: 12px; }
  .chart-preset:hover { border-color: rgba(99,102,241,.45); background: rgba(99,102,241,.1); color: rgb(129 140 248); }
  .mobile-overlay { display: none; }
  @media (max-width: 760px) {
    .app-shell { display: block; }
    .app-sidebar { position: fixed; z-index: 45; inset: 0 auto 0 0; width: min(86vw, 20rem); transform: translateX(-105%); transition: transform .16s ease; overflow: auto; border-right: 1px solid rgba(127,127,127,.22); }
    .app-sidebar.open { transform: translateX(0); }
    .mobile-overlay { display: block; position: fixed; z-index: 44; inset: 0; background: rgba(0,0,0,.45); }
    .mobile-bar { display: flex; gap: .4rem; overflow-x: auto; padding: .6rem .75rem; border-bottom: 1px solid rgba(127,127,127,.16); background: rgba(250,250,250,.92); position: sticky; top: var(--header-h, 4rem); z-index: 25; }
    .dark .mobile-bar { background: rgba(9,9,11,.92); }
    .mobile-disabled-reason { display: inline-flex; align-items: center; min-width: 12rem; color: rgb(113 113 122); font-size: 11px; }
    .mobile-menu-button { display: inline-flex; }
    .desktop-nav-hint { display: none; }
    header .meta-wide { display: none; }
    .content-section { padding: .75rem; }
  }
</style>
</head>
<body class="bg-white text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100 antialiased min-h-screen" x-data="app()" x-init="init()" x-cloak>

<header x-ref="header" class="sticky top-0 z-30 border-b border-zinc-200 dark:border-zinc-800/70 bg-white/80 dark:bg-zinc-950/80 backdrop-blur supports-[backdrop-filter]:bg-white/60 dark:supports-[backdrop-filter]:bg-zinc-950/60">
  <div class="px-5 py-3 flex items-center gap-4">
    <button @click="mobileNavOpen = true" class="mobile-menu-button px-2 py-1 rounded border border-zinc-200 dark:border-zinc-800 text-sm" title="Open navigation">☰</button>
    <div class="flex items-center gap-2 text-indigo-400">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><path d="m19 9-5 5-4-4-3 3"/></svg>
      <span class="font-semibold tracking-tight">data display</span>
    </div>
    <!-- Single dataset: plain title -->
    <div x-show="!hasMultiple" class="text-zinc-700 dark:text-zinc-300 truncate" x-text="meta.title"></div>
    <!-- Multi-dataset: switcher -->
    <div x-show="hasMultiple" class="flex items-center gap-2 min-w-0">
      <button @click="prevDataset()" class="px-2 py-1 rounded border border-zinc-200 dark:border-zinc-800 hover:bg-zinc-100 dark:hover:bg-zinc-900 text-sm" title="Previous source ([)">←</button>
      <select :value="activeId" @change="setActive($event.target.value)"
              class="bg-zinc-50 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded px-2 py-1.5 text-sm max-w-xs truncate">
        <template x-for="(ds, i) in datasets" :key="ds.id">
          <option :value="ds.id" x-text="(i+1) + '. ' + ds.label + '  (' + (ds.schema.row_count || 0).toLocaleString() + ' rows)'"></option>
        </template>
      </select>
      <button @click="nextDataset()" class="px-2 py-1 rounded border border-zinc-200 dark:border-zinc-800 hover:bg-zinc-100 dark:hover:bg-zinc-900 text-sm" title="Next source (])">→</button>
      <span class="text-xs text-zinc-500 num whitespace-nowrap"><span x-text="activeIndex + 1"></span>/<span x-text="datasets.length"></span></span>
    </div>
    <div class="ml-auto flex items-center gap-3 text-xs text-zinc-500 dark:text-zinc-400 meta-wide">
      <span class="num"><span x-text="schema.row_count.toLocaleString()"></span> rows</span>
      <span x-show="meta.records_key" x-text="'records: ' + (meta.records_key || '')"></span>
      <span class="num" x-text="schema.fields.length + ' fields'"></span>
      <span x-show="meta.truncated" class="text-amber-400" x-text="'truncated to ' + meta.max_embedded_rows.toLocaleString()"></span>
      <button @click="toggleTheme()" class="ml-2 px-2 py-1 rounded border border-zinc-300 dark:border-zinc-700 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition" title="Toggle theme">
        <span x-show="theme==='dark'">☾</span>
        <span x-show="theme==='light'">☀</span>
      </button>
    </div>
  </div>
  <!-- meta strip -->
  <div x-show="metaSummary.length" class="px-5 pb-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-zinc-500 dark:text-zinc-400">
    <template x-for="kv in metaSummary" :key="kv.k">
      <div><span class="text-zinc-500 dark:text-zinc-500" x-text="kv.k + ':'"></span> <span class="text-zinc-700 dark:text-zinc-200 num" x-text="kv.v"></span></div>
    </template>
  </div>
</header>

<div x-show="mobileNavOpen" @click="mobileNavOpen = false" class="mobile-overlay"></div>
<div class="mobile-bar">
  <button @click="mobileNavOpen = true" class="px-2 py-1 rounded border border-zinc-200 dark:border-zinc-800 text-sm">☰</button>
  <template x-for="v in views" :key="v.id">
    <button @click="selectMobileView(v)" :aria-disabled="!isEligible(v.id)"
            :class="[view === v.id ? 'bg-indigo-500/15 text-indigo-700 dark:text-indigo-300 border-indigo-500/30' : 'border-zinc-200 dark:border-zinc-800', isEligible(v.id) ? '' : 'opacity-30', 'px-2 py-1 rounded border text-xs whitespace-nowrap']"
            :title="viewReason(v.id)">
      <span x-text="v.label"></span>
    </button>
  </template>
  <span x-show="mobileDisabledReason" class="mobile-disabled-reason" x-text="mobileDisabledReason"></span>
</div>

<main class="app-shell">
  <aside :class="mobileNavOpen ? 'app-sidebar open' : 'app-sidebar'">
    <nav class="p-2 space-y-1 sticky" style="top: var(--header-h, 5rem);">
      <div class="flex items-center justify-between px-3 py-2">
        <span class="text-[10px] uppercase tracking-wide font-semibold text-zinc-500">Explore</span>
        <button @click="mobileNavOpen = false" class="mobile-menu-button px-2 py-1 rounded border border-zinc-200 dark:border-zinc-800 text-xs">close</button>
      </div>
      <div x-show="hasMultiple" class="relationship-map">
        <div class="px-1 pb-2 text-[10px] uppercase tracking-wide font-semibold text-zinc-500 flex items-center justify-between">
          <span>Source map</span>
          <span class="num" x-text="relationshipEdges.length + ' links'"></span>
        </div>
        <div class="source-graph" x-show="relationshipEdges.length">
          <template x-for="edge in relationshipEdges" :key="'graph-' + edge.id">
            <button @click="openRelationship(edge)" class="source-graph-row" :title="edge.reason">
              <span :class="activeId === edge.from ? 'source-graph-node active' : 'source-graph-node'" x-text="edge.fromLabel"></span>
              <span class="source-graph-line"><span x-text="edge.key"></span></span>
              <span :class="activeId === edge.to ? 'source-graph-node active' : 'source-graph-node'" x-text="edge.toLabel"></span>
            </button>
          </template>
        </div>
        <div class="grid gap-1 mb-2">
          <template x-for="ds in datasets" :key="ds.id">
            <button @click="setActive(ds.id); mobileNavOpen = false"
                    :class="activeId === ds.id ? 'source-node active' : 'source-node'"
                    :title="ds.meta.source_file || ds.label">
              <div class="flex items-center justify-between gap-2">
                <span class="truncate" x-text="ds.label"></span>
                <span class="num text-zinc-500" x-text="(ds.schema.row_count || 0).toLocaleString()"></span>
              </div>
            </button>
          </template>
        </div>
        <div class="grid gap-1">
          <template x-for="edge in relationshipEdges" :key="edge.id">
            <button @click="openRelationship(edge)" class="source-edge" :title="edge.reason">
              <span class="truncate" x-text="edge.fromLabel + ' → ' + edge.toLabel"></span>
              <span class="kbd" x-text="edge.key"></span>
            </button>
          </template>
          <div x-show="!relationshipEdges.length" class="px-1 text-[11px] text-zinc-500">No shared keys detected.</div>
        </div>
      </div>
      <!-- Sources section (multi-dataset only) -->
      <div x-show="hasMultiple" class="pb-2 mb-2 border-b border-zinc-200 dark:border-zinc-800/70">
        <div class="px-3 pt-1 pb-2 text-[10px] uppercase tracking-wide font-semibold text-zinc-500 flex items-center justify-between">
          <span>Sources</span>
          <span class="text-zinc-500"><span class="kbd">[</span><span class="kbd">]</span></span>
        </div>
        <template x-for="(ds, i) in datasets" :key="ds.id">
          <button @click="setActive(ds.id)"
                  :class="[
                    activeId === ds.id ? 'bg-indigo-500/15 text-indigo-700 dark:text-indigo-300 border-indigo-500/30' : 'text-zinc-700 dark:text-zinc-300 border-transparent hover:bg-zinc-100 dark:hover:bg-zinc-900',
                    'w-full flex items-center gap-2 px-3 py-2 rounded-md border text-sm transition text-left'
                  ]"
                  :title="ds.meta.source_file || ds.label">
            <span class="text-[10px] text-zinc-500 num w-4 text-right" x-text="i + 1"></span>
            <span class="flex-1 min-w-0">
              <span class="block truncate" x-text="ds.label"></span>
              <span class="block text-[10px] text-zinc-500 num">
                <span x-text="(ds.schema.row_count || 0).toLocaleString()"></span> rows
                <span class="opacity-60 ml-1" x-text="ds.meta.format || ''"></span>
              </span>
            </span>
          </button>
        </template>
      </div>
      <!-- Views section -->
      <div x-show="hasMultiple" class="px-3 text-[10px] uppercase tracking-wide font-semibold text-zinc-500 pb-1">Views</div>
      <template x-for="v in views" :key="v.id">
        <div>
          <button @click="setView(v.id)"
                  :disabled="!isEligible(v.id)"
                  :title="viewReason(v.id)"
                  :class="[
                    view === v.id ? 'bg-indigo-500/15 text-indigo-700 dark:text-indigo-300 border-indigo-500/30' : 'text-zinc-700 dark:text-zinc-300 border-transparent hover:bg-zinc-100 dark:hover:bg-zinc-900',
                    isEligible(v.id) ? '' : 'opacity-30 cursor-not-allowed',
                    'w-full flex items-center justify-between px-3 py-2 rounded-md border text-sm transition'
                  ]">
            <span class="flex items-center gap-2">
              <span class="opacity-80" x-html="iconFor(v.id)"></span>
              <span x-text="v.label"></span>
            </span>
            <span class="kbd" x-text="v.key"></span>
          </button>
          <span x-show="!isEligible(v.id)" class="disabled-reason" x-text="viewReason(v.id)"></span>
        </div>
      </template>
      <div class="facet-panel" x-show="facetFields.length">
        <div class="flex items-center justify-between gap-2 mb-2">
          <div class="text-[10px] uppercase tracking-wide font-semibold text-zinc-500">Facets</div>
          <button x-show="hasActiveFilters" @click="clearFilters()" class="text-[11px] text-indigo-400 hover:underline">clear all</button>
        </div>
        <div x-show="activeFilterChips.length" class="flex flex-wrap gap-1 mb-2">
          <template x-for="chip in activeFilterChips" :key="chip.field">
            <button @click="clearFilter(chip.field)" class="filter-chip" :title="'Remove ' + chip.label">
              <span x-text="chip.label + ': ' + chip.value"></span>
              <span>×</span>
            </button>
          </template>
        </div>
        <template x-for="f in facetFields" :key="f.name">
          <div class="facet-card">
            <div class="flex items-center justify-between gap-2">
              <div class="text-xs font-semibold truncate" x-text="fieldLabel(f)"></div>
              <span class="text-[10px] text-zinc-500 uppercase" x-text="f.kind"></span>
            </div>
            <input :placeholder="'search ' + fieldLabel(f)"
                   x-model="facetSearch[f.name]"
                   class="mt-2 w-full bg-zinc-50 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded px-2 py-1 text-xs focus:outline-none focus:border-indigo-500">
            <div class="facet-values">
              <button @click="clearFilter(f.name)"
                      :class="!filters[f.name] ? 'facet-value-button active' : 'facet-value-button'">
                <span>all</span>
                <span class="num" x-text="data.length.toLocaleString()"></span>
              </button>
              <template x-for="item in visibleFacetValues(f)" :key="item.value">
                <button @click="setFilter(f.name, item.value)"
                        :class="filters[f.name] === item.value ? 'facet-value-button active' : 'facet-value-button'"
                        :title="item.label">
                  <span class="truncate" x-text="item.label"></span>
                  <span class="num text-zinc-500" x-text="item.count.toLocaleString()"></span>
                </button>
              </template>
            </div>
          </div>
        </template>
      </div>
      <div class="pt-3 mt-3 border-t border-zinc-200 dark:border-zinc-800/70 text-[11px] text-zinc-500 px-3 leading-relaxed desktop-nav-hint">
        <div><span class="kbd">/</span> search</div>
        <div><span class="kbd">j</span>/<span class="kbd">k</span> next/prev row</div>
        <div x-show="hasMultiple"><span class="kbd">[</span>/<span class="kbd">]</span> prev/next source</div>
        <div><span class="kbd">esc</span> close drawer</div>
      </div>
    </nav>
  </aside>

  <section class="flex-1 min-w-0">
    <!-- TABLE -->
    <div x-show="view==='table'" :aria-hidden="view!=='table'" :inert="view!=='table'" class="p-5 content-section">
      <div class="flex items-center gap-3 mb-3">
        <div class="flex-1 relative max-w-xl">
          <span class="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>
          </span>
          <input id="search-box" x-model="q" @input.debounce.150="page = 0; writeHash()" placeholder="search rows…  (press / to focus)"
            class="w-full pl-9 pr-3 py-2 bg-zinc-50 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-md text-sm focus:outline-none focus:border-indigo-500 transition">
        </div>
        <div class="text-xs text-zinc-500 num">
          <span x-text="filteredRows.length.toLocaleString()"></span> match · rows
          <span x-text="visibleStart.toLocaleString()"></span>-<span x-text="visibleEnd.toLocaleString()"></span> · page
          <span x-text="page + 1"></span>/<span x-text="totalPages"></span>
        </div>
        <select x-model.number="pageSize" @change="page = 0; writeHash()" class="bg-zinc-50 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded px-2 py-1 text-xs num">
          <option :value="100">100</option>
          <option :value="200">200</option>
          <option :value="500">500</option>
          <option :value="1000">1000</option>
        </select>
        <div class="flex items-center gap-1 text-xs">
          <button @click="rowDensity = 'compact'; writeHash()" :class="rowDensity === 'compact' ? 'px-2 py-1 rounded border border-indigo-500/30 bg-indigo-500/15 text-indigo-400' : 'px-2 py-1 rounded border border-zinc-200 dark:border-zinc-800'">compact</button>
          <button @click="rowDensity = 'comfortable'; writeHash()" :class="rowDensity === 'comfortable' ? 'px-2 py-1 rounded border border-indigo-500/30 bg-indigo-500/15 text-indigo-400' : 'px-2 py-1 rounded border border-zinc-200 dark:border-zinc-800'">comfort</button>
          <button @click="wrapCells = !wrapCells; writeHash()" :class="wrapCells ? 'px-2 py-1 rounded border border-indigo-500/30 bg-indigo-500/15 text-indigo-400' : 'px-2 py-1 rounded border border-zinc-200 dark:border-zinc-800'">wrap</button>
        </div>
        <div class="flex items-center gap-1">
          <button @click="setPage(Math.max(0, page-1))" class="px-2 py-1 rounded border border-zinc-200 dark:border-zinc-800 hover:bg-zinc-100 dark:hover:bg-zinc-900 text-sm">←</button>
          <button @click="setPage(Math.min(totalPages-1, page+1))" class="px-2 py-1 rounded border border-zinc-200 dark:border-zinc-800 hover:bg-zinc-100 dark:hover:bg-zinc-900 text-sm">→</button>
        </div>
      </div>
      <div class="flex items-center justify-between gap-2 mb-2">
        <div class="text-[11px] text-zinc-500">Column menus provide sort, filter, pin, hide, profile, copy, format, and resize controls. Drag the small handle beside a header to resize.</div>
        <div class="table-scroll-hint shrink-0"><span>←</span><span>scroll</span><span>→</span></div>
      </div>
      <div x-show="hiddenColumnList.length" class="flex flex-wrap gap-1 mb-2 text-xs">
        <span class="text-zinc-500">hidden</span>
        <template x-for="f in hiddenColumnList" :key="f.name">
          <button @click="showColumn(f.name)" class="filter-chip" :title="'Show ' + fieldLabel(f)">
            <span x-text="fieldLabel(f)"></span>
            <span>＋</span>
          </button>
        </template>
      </div>
      <div class="border border-zinc-200 dark:border-zinc-800 rounded-md overflow-auto max-h-[calc(100vh-12rem)]">
        <table :class="'text-sm w-full ' + (wrapCells ? 'table-wrap ' : '') + (rowDensity === 'compact' ? 'table-compact' : 'table-comfortable')">
          <thead class="sticky top-0 bg-zinc-50/95 dark:bg-zinc-900/95 backdrop-blur scroll-shadow text-zinc-500 dark:text-zinc-400">
            <tr>
              <th class="px-2 py-2 text-left font-medium w-8">#</th>
              <template x-for="f in tableFields" :key="f.name">
                <th class="px-2 py-2 text-left font-medium whitespace-nowrap relative"
                    :class="isPinned(f.name) ? 'sticky-col' : ''"
                    :style="columnStyle(f)">
                  <div class="flex items-center gap-1">
                    <button @click="sortBy(f.name)" class="flex items-center gap-1 hover:text-zinc-900 dark:hover:text-zinc-200 transition min-w-0">
                      <span class="truncate" x-text="fieldLabel(f)"></span>
                      <span class="text-indigo-400" x-show="sortKey === f.name" x-text="sortDir === 'asc' ? '▲' : '▼'"></span>
                      <span class="text-[10px] uppercase opacity-50" x-text="f.kind"></span>
                    </button>
                    <button @click.stop="toggleColumnMenu(f)" class="px-1 rounded hover:bg-zinc-100 dark:hover:bg-zinc-900" title="Column actions">⋯</button>
                    <span class="col-resize" @mousedown.prevent="startColumnResize($event, f)" title="Resize column"></span>
                  </div>
                  <div x-show="openColumnMenu === f.name" @click.outside="openColumnMenu = null" class="column-menu">
                    <div class="text-xs font-semibold mb-2 truncate" x-text="fieldLabel(f)"></div>
                    <div class="menu-row">
                      <button class="menu-action" @click.stop="sortColumn(f.name, 'asc')">Sort ascending</button>
                      <button class="menu-action" @click.stop="sortColumn(f.name, 'desc')">Sort descending</button>
                    </div>
                    <div class="menu-row">
                      <input x-model="columnMenuFilterValue" placeholder="exact filter value"
                             class="bg-zinc-50 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded px-2 py-1 text-xs focus:outline-none focus:border-indigo-500">
                      <button class="menu-action" @click.stop="applyColumnFilter(f)">Apply filter</button>
                      <button class="menu-action" @click.stop="facetByField(f)">Facet by this</button>
                    </div>
                    <div class="menu-row">
                      <button class="menu-action" @click.stop="togglePinned(f.name)" x-text="isPinned(f.name) ? 'Unpin column' : 'Pin column'"></button>
                      <button class="menu-action" @mousedown.prevent.stop="hideColumn(f.name)" @click.prevent.stop>Hide column</button>
                      <button class="menu-action" @click.stop="profileColumn(f)">Profile column</button>
                      <button class="menu-action" @click.stop="copyColumnValues(f)" x-text="copiedColumn === f.name ? 'Copied values' : 'Copy column values'"></button>
                    </div>
                    <div class="menu-row">
                      <select :value="formatFor(f)" @change="setFormat(f.name, $event.target.value)"
                              class="bg-zinc-50 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded px-2 py-1 text-xs">
                        <option value="">auto format</option>
                        <option value="integer">integer</option>
                        <option value="percent">percent</option>
                        <option value="currency">currency</option>
                      </select>
                      <div class="flex gap-1">
                        <button class="menu-action" @click.stop="resizeColumn(f.name, -24)">Narrow</button>
                        <button class="menu-action" @click.stop="resizeColumn(f.name, 24)">Widen</button>
                      </div>
                    </div>
                  </div>
                </th>
              </template>
              <th class="px-2 py-2 text-left font-medium w-12"></th>
            </tr>
          </thead>
          <tbody class="divide-y divide-zinc-200 dark:divide-zinc-900">
            <template x-for="(row, i) in pagedRows" :key="page * pageSize + i">
              <tr class="row-link hover:bg-zinc-100 dark:hover:bg-zinc-900/60">
                <td class="px-2 py-1.5 text-zinc-600 num text-xs" x-text="page * pageSize + i + 1"></td>
                <template x-for="f in tableFields" :key="f.name">
                  <td class="px-2 align-top max-w-xs"
                      :class="cellClass(row[f.name], f) + (isPinned(f.name) ? ' sticky-col' : '') + (wrapCells ? ' wrap-cell' : '')"
                      :style="columnStyle(f)">
                    <template x-if="isUrlField(f) && row[f.name]">
                      <a :href="row[f.name]" target="_blank" rel="noopener" class="text-indigo-400 hover:underline truncate inline-block max-w-[16rem]" x-text="row[f.name]"></a>
                    </template>
                    <template x-if="isImageField(f) && row[f.name]">
                      <img :src="row[f.name]" loading="lazy" class="h-12 w-12 object-cover rounded">
                    </template>
                    <template x-if="!isUrlField(f) && !isImageField(f)">
                      <span x-text="formatCell(row, f)" :title="cellTitle(row, f.name)"></span>
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

    <!-- COMPARE -->
    <div x-show="view==='compare'" :aria-hidden="view!=='compare'" :inert="view!=='compare'" class="p-5">
      <div class="mb-3 text-sm text-zinc-500">
        <span x-text="'key: ' + activeKey"></span> · <span x-text="compareRows.length.toLocaleString()"></span> linked values
      </div>
      <div class="border border-zinc-200 dark:border-zinc-800 rounded-md overflow-auto max-h-[calc(100vh-12rem)]">
        <table class="text-sm w-full">
          <thead class="sticky top-0 bg-zinc-50/95 dark:bg-zinc-900/95 backdrop-blur text-zinc-500 dark:text-zinc-400">
            <tr>
              <th class="px-2 py-2 text-left font-medium" x-text="activeKey || 'key'"></th>
              <template x-for="ds in comparableDatasets" :key="ds.id"><th class="px-2 py-2 text-right font-medium" x-text="ds.label"></th></template>
            </tr>
          </thead>
          <tbody class="divide-y divide-zinc-200 dark:divide-zinc-900">
            <template x-for="row in compareRows.slice(0, 1000)" :key="row.key">
              <tr>
                <td class="px-2 py-1.5 num" x-text="row.key"></td>
                <template x-for="ds in comparableDatasets" :key="ds.id">
                  <td class="px-2 py-1.5 text-right num" x-text="row.counts[ds.id] || 0"></td>
                </template>
              </tr>
            </template>
            <tr x-show="!compareRows.length"><td class="px-3 py-8 text-center text-zinc-500" :colspan="comparableDatasets.length + 1">No comparable keyed rows.</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- LINE -->
    <div x-show="view==='line'" :aria-hidden="view!=='line'" :inert="view!=='line'" class="p-5 content-section">
      <div class="chart-presets" x-show="chartPresets('line').length">
        <template x-for="preset in chartPresets('line')" :key="preset.id">
          <button @click="applyChartPreset(preset)" class="chart-preset" x-text="preset.label"></button>
        </template>
      </div>
      <div class="flex flex-wrap gap-4 mb-3 text-sm items-end">
        <label class="flex flex-col gap-1">
          <span class="text-xs text-zinc-500 uppercase tracking-wide">x · time</span>
          <select x-model="lineXField" class="bg-zinc-50 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded px-2 py-1.5 min-w-[10rem]">
            <template x-for="f in fieldsForRole('line_x')" :key="f.name"><option :value="f.name" x-text="fieldLabel(f)"></option></template>
          </select>
        </label>
        <label class="flex flex-col gap-1">
          <span class="text-xs text-zinc-500 uppercase tracking-wide">y · measure</span>
          <select x-model="lineYField" class="bg-zinc-50 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded px-2 py-1.5 min-w-[10rem]">
            <template x-for="f in fieldsForRole('line_y')" :key="f.name"><option :value="f.name" x-text="fieldLabel(f)"></option></template>
          </select>
        </label>
        <label class="flex flex-col gap-1">
          <span class="text-xs text-zinc-500 uppercase tracking-wide">series&nbsp;by · optional</span>
          <select x-model="lineSeriesField" class="bg-zinc-50 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded px-2 py-1.5 min-w-[10rem]">
            <option value="">(none)</option>
            <template x-for="f in fieldsForRole('series_by')" :key="f.name"><option :value="f.name" x-text="fieldLabel(f)"></option></template>
          </select>
        </label>
        <label class="flex flex-col gap-1">
          <span class="text-xs text-zinc-500 uppercase tracking-wide">aggregate</span>
          <select x-model="lineAgg" class="bg-zinc-50 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded px-2 py-1.5">
            <option value="sum">sum</option><option value="avg">avg</option><option value="count">count</option><option value="min">min</option><option value="max">max</option>
          </select>
        </label>
      </div>
      <div id="line-chart" class="w-full border border-zinc-200 dark:border-zinc-800 rounded" style="height: 60vh"></div>
      <div x-show="!fieldsForRole('line_x').length || !fieldsForRole('line_y').length" class="text-xs text-zinc-500 mt-2">No time field paired with a numeric measure.</div>
    </div>

    <!-- BAR -->
    <div x-show="view==='bar'" :aria-hidden="view!=='bar'" :inert="view!=='bar'" class="p-5 content-section">
      <div class="chart-presets" x-show="chartPresets('bar').length">
        <template x-for="preset in chartPresets('bar')" :key="preset.id">
          <button @click="applyChartPreset(preset)" class="chart-preset" x-text="preset.label"></button>
        </template>
      </div>
      <div class="flex flex-wrap gap-4 mb-3 text-sm items-end">
        <label class="flex flex-col gap-1">
          <span class="text-xs text-zinc-500 uppercase tracking-wide">field</span>
          <select x-model="barField" class="bg-zinc-50 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded px-2 py-1.5 min-w-[10rem]">
            <template x-for="f in fieldsForRole('bar_x')" :key="f.name"><option :value="f.name" x-text="fieldLabel(f)"></option></template>
          </select>
        </label>
        <label class="flex flex-col gap-1">
          <span class="text-xs text-zinc-500 uppercase tracking-wide">top N</span>
          <input type="number" min="1" max="50" x-model.number="barTopN" class="bg-zinc-50 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded px-2 py-1.5 w-24 num">
        </label>
      </div>
      <div id="bar-chart" class="w-full border border-zinc-200 dark:border-zinc-800 rounded" style="height: 60vh"></div>
    </div>

    <!-- PIVOT -->
    <div x-show="view==='pivot'" :aria-hidden="view!=='pivot'" :inert="view!=='pivot'" class="p-5 content-section">
      <div class="chart-presets" x-show="chartPresets('pivot').length">
        <template x-for="preset in chartPresets('pivot')" :key="preset.id">
          <button @click="applyChartPreset(preset)" class="chart-preset" x-text="preset.label"></button>
        </template>
      </div>
      <div class="flex flex-wrap gap-4 mb-3 text-sm items-end">
        <label class="flex flex-col gap-1">
          <span class="text-xs text-zinc-500 uppercase tracking-wide">group by</span>
          <select x-model="pivotGroupField" @change="$nextTick(() => renderCharts())" class="bg-zinc-50 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded px-2 py-1.5 min-w-[10rem]">
            <template x-for="f in pivotGroupFields" :key="f.name"><option :value="f.name" x-text="fieldLabel(f)"></option></template>
          </select>
        </label>
        <label class="flex flex-col gap-1">
          <span class="text-xs text-zinc-500 uppercase tracking-wide">measure</span>
          <select x-model="pivotMeasureField" @change="$nextTick(() => renderCharts())" class="bg-zinc-50 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded px-2 py-1.5 min-w-[10rem]">
            <template x-for="f in measureFields" :key="f.name"><option :value="f.name" x-text="fieldLabel(f)"></option></template>
          </select>
        </label>
        <label class="flex flex-col gap-1">
          <span class="text-xs text-zinc-500 uppercase tracking-wide">aggregate</span>
          <select x-model="pivotAgg" @change="$nextTick(() => renderCharts())" class="bg-zinc-50 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded px-2 py-1.5">
            <option value="sum">sum</option><option value="avg">avg</option><option value="count">count</option><option value="min">min</option><option value="max">max</option>
          </select>
        </label>
      </div>
      <div id="pivot-chart" class="w-full border border-zinc-200 dark:border-zinc-800 rounded mb-3" style="height: 40vh"></div>
      <div class="border border-zinc-200 dark:border-zinc-800 rounded-md overflow-auto" style="max-height: calc(100vh - 20rem)">
        <table class="text-sm w-full">
          <thead class="sticky top-0 bg-zinc-50/95 dark:bg-zinc-900/95 backdrop-blur text-zinc-500 dark:text-zinc-400">
            <tr><th class="px-2 py-2 text-left font-medium">group</th><th class="px-2 py-2 text-right font-medium">value</th><th class="px-2 py-2 text-right font-medium">rows</th></tr>
          </thead>
          <tbody class="divide-y divide-zinc-200 dark:divide-zinc-900">
            <template x-for="row in pivotRows" :key="row.group">
              <tr><td class="px-2 py-1.5 truncate" x-text="row.group"></td><td class="px-2 py-1.5 text-right num" x-text="_fmtNum(row.value)"></td><td class="px-2 py-1.5 text-right num text-zinc-500" x-text="row.count.toLocaleString()"></td></tr>
            </template>
            <tr x-show="!pivotRows.length"><td class="px-3 py-8 text-center text-zinc-500" colspan="3">No groups available.</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- KPIS -->
    <div x-show="view==='kpis'" :aria-hidden="view!=='kpis'" :inert="view!=='kpis'" class="p-5">
      <div class="grid gap-3" style="grid-template-columns: repeat(auto-fill, minmax(220px, 1fr))">
        <template x-for="f in measureFields" :key="f.name">
          <div class="border border-zinc-200 dark:border-zinc-800 rounded-md p-4 bg-zinc-50 dark:bg-zinc-900/40">
            <div class="text-[11px] text-zinc-500 uppercase tracking-wide" x-text="fieldLabel(f)"></div>
            <div class="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
              <template x-for="kv in kpisFor(f)" :key="kv.k">
                <div class="contents">
                  <div class="text-zinc-500" x-text="kv.k"></div>
                  <div class="text-right num text-zinc-900 dark:text-zinc-100" x-text="kv.v"></div>
                </div>
              </template>
            </div>
          </div>
        </template>
        <div x-show="!measureFields.length" class="text-zinc-500 text-sm">No numeric measures detected.</div>
      </div>
    </div>

    <!-- PROFILE -->
    <div x-show="view==='profile'" :aria-hidden="view!=='profile'" :inert="view!=='profile'" class="p-5">
      <div class="grid gap-3" style="grid-template-columns: repeat(auto-fill, minmax(300px, 1fr))">
        <template x-for="f in profileFields" :key="f.name">
          <div class="border border-zinc-200 dark:border-zinc-800 rounded-md p-4 bg-zinc-50 dark:bg-zinc-900/40" :data-profile-field="f.name">
            <div class="flex items-center justify-between gap-3">
              <div class="min-w-0">
                <div class="text-sm font-semibold truncate" x-text="fieldLabel(f)"></div>
                <div class="text-[11px] text-zinc-500 uppercase tracking-wide" x-text="f.kind"></div>
              </div>
              <div class="text-right text-xs text-zinc-500 num">
                <div><span x-text="f.non_null.toLocaleString()"></span> filled</div>
                <div><span x-text="f.null_pct"></span>% null</div>
              </div>
            </div>
            <div class="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
              <div class="text-zinc-500">distinct</div>
              <div class="text-right num" x-text="f.distinct.toLocaleString() + (f.distinct_limited ? '+' : '')"></div>
              <template x-if="f.numeric">
                <div class="contents">
                  <div class="text-zinc-500">min / max</div>
                  <div class="text-right num" x-text="_fmtNum(f.numeric.min) + ' / ' + _fmtNum(f.numeric.max)"></div>
                  <div class="text-zinc-500">mean</div>
                  <div class="text-right num" x-text="_fmtNum(f.numeric.mean)"></div>
                  <div class="text-zinc-500">median</div>
                  <div class="text-right num" x-text="_fmtNum(f.numeric.median)"></div>
                </div>
              </template>
              <template x-if="f.time">
                <div class="contents">
                  <div class="text-zinc-500">range</div>
                  <div class="text-right num truncate" x-text="f.time.min + ' → ' + f.time.max"></div>
                </div>
              </template>
            </div>
            <div x-show="f.numeric && f.numeric.histogram && f.numeric.histogram.length" class="mt-3 space-y-1">
              <template x-for="bin in ((f.numeric && f.numeric.histogram) || [])" :key="bin.min + '-' + bin.max">
                <div class="flex items-center gap-2 text-[11px] num">
                  <div class="w-24 text-zinc-500 truncate" x-text="_fmtNum(bin.min)"></div>
                  <div class="flex-1 rounded" style="background: rgba(113,113,122,.22)">
                    <div class="rounded" :style="'height: 0.45rem; width: ' + profileBarWidth(bin, (f.numeric && f.numeric.histogram) || []) + '%; background: #6366f1'"></div>
                  </div>
                  <div class="w-8 text-right text-zinc-500" x-text="bin.count"></div>
                </div>
              </template>
            </div>
            <div x-show="f.top_values && f.top_values.length" class="mt-3 divide-y divide-zinc-200 dark:divide-zinc-900">
              <template x-for="item in f.top_values.slice(0, 5)" :key="item.value">
                <div class="flex items-center gap-2 py-1 text-xs">
                  <div class="flex-1 truncate" x-text="item.value"></div>
                  <div class="text-zinc-500 num" x-text="item.count.toLocaleString()"></div>
                </div>
              </template>
            </div>
          </div>
        </template>
        <div x-show="!profileFields.length" class="text-zinc-500 text-sm">No fields detected.</div>
      </div>
    </div>

    <!-- TREE -->
    <div x-show="view==='tree'" :aria-hidden="view!=='tree'" :inert="view!=='tree'" class="p-5">
      <div class="flex flex-wrap gap-4 mb-3 text-sm items-end">
        <label class="flex flex-col gap-1">
          <span class="text-xs text-zinc-500 uppercase tracking-wide">root</span>
          <select x-model.number="treeRowIdx" class="bg-zinc-50 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded px-2 py-1.5 min-w-[12rem]">
            <option value="-1">all rows (array)</option>
            <option value="-2">meta only</option>
            <template x-for="(row, i) in data.slice(0, 200)" :key="i"><option :value="i" x-text="'row ' + (i+1) + treeRowLabel(row)"></option></template>
          </select>
        </label>
      </div>
      <div class="border border-zinc-200 dark:border-zinc-800 rounded p-3 max-h-[calc(100vh-12rem)] overflow-auto font-mono text-[13px] leading-relaxed" x-ref="treeRoot" x-effect="renderTree($refs.treeRoot, treeRoot())"></div>
    </div>
  </section>
</main>

<!-- Row drawer -->
<div x-show="selectedRow !== null" x-transition.opacity class="fixed inset-0 z-40 bg-black/50" @click="selectedRow = null"></div>
<aside x-show="selectedRow !== null" x-transition:enter="transition ease-out duration-150" x-transition:enter-start="translate-x-full" x-transition:enter-end="translate-x-0"
       x-transition:leave="transition ease-in duration-100" x-transition:leave-start="translate-x-0" x-transition:leave-end="translate-x-full"
       class="fixed top-0 right-0 z-40 h-full w-full sm:w-[36rem] bg-white dark:bg-zinc-950 border-l border-zinc-200 dark:border-zinc-800 shadow-2xl flex flex-col">
  <div class="flex items-center justify-between px-4 py-3 border-b border-zinc-200 dark:border-zinc-800">
    <div class="text-sm text-zinc-400"><span x-text="drawerTitle()"></span> · <span class="kbd">esc</span> to close</div>
    <button @click="selectedRow = null" class="text-zinc-500 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-100">✕</button>
  </div>
  <div x-show="relatedLinks.length" class="px-4 py-3 border-b border-zinc-200 dark:border-zinc-800 text-xs">
    <div class="text-zinc-500 uppercase tracking-wide mb-2">related rows</div>
    <div class="flex flex-wrap gap-2">
      <template x-for="link in relatedLinks" :key="link.id">
        <button @click="openRelated(link)" class="px-2 py-1 rounded border border-zinc-200 dark:border-zinc-800 hover:bg-zinc-100 dark:hover:bg-zinc-900">
          <span x-text="link.label"></span>
          <span class="num text-zinc-500" x-text="'(' + link.count + ')'"></span>
        </button>
      </template>
    </div>
  </div>
  <div class="flex-1 overflow-auto p-4 font-mono text-[13px] leading-relaxed" x-ref="drawerRoot" x-effect="if (selectedRow !== null) renderTree($refs.drawerRoot, selectedRow)"></div>
</aside>

<script type="application/json" id="payload-json">__PAYLOAD__</script>
<script>
function app() {
  return {
    datasets: [],
    activeId: null,
    data: [],
    aggregates: { kpis: {}, bar: {}, line: {}, profile: { fields: [] } },
    schema: { fields: [], row_count: 0, eligible_views: ['table'] },
    meta: { title: '', source_file: '', records_key: '' },
    display: {},
    view: 'table',
    q: '',
    filters: {},
    facetSearch: {},
    manualFacetFields: [],
    openColumnMenu: null,
    columnMenuFilterValue: '',
    copiedColumn: '',
    hiddenColumns: {},
    pinnedColumns: [],
    columnWidths: {},
    formatOverrides: {},
    rowDensity: 'comfortable',
    wrapCells: false,
    mobileNavOpen: false,
    mobileDisabledReason: '',
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
    pivotGroupField: null,
    pivotMeasureField: null,
    pivotAgg: 'sum',
    treeRowIdx: -1,
    theme: document.documentElement.classList.contains('dark') ? 'dark' : 'light',
    _resizeHandlers: [],
    _sortedCacheKey: null,
    _sortedCacheRows: [],
    _cellCache: new WeakMap(),
    _perDatasetState: {},
    _switching: false,

    init() {
      const payload = JSON.parse(document.getElementById('payload-json').textContent);
      const rawDatasets = Array.isArray(payload.datasets) ? payload.datasets : [];
      this.datasets = rawDatasets.map(ds => ({
        id: ds.id,
        label: ds.label || ds.id,
        data: Array.isArray(ds.data) ? Object.freeze(ds.data.slice()) : [],
        schema: ds.schema || { fields: [], row_count: 0, eligible_views: ['table'] },
        aggregates: ds.aggregates || { kpis: {}, bar: {}, line: {}, profile: { fields: [] } },
        meta: ds.meta || {},
        display: ds.display || {},
        key: ds.key || '',
        default_view: ds.default_view || '',
      }));
      if (!this.datasets.length) {
        this.datasets = [{
          id: 'empty', label: 'empty', data: [],
          schema: { fields: [], row_count: 0, eligible_views: ['table'] },
          aggregates: { kpis: {}, bar: {}, line: {}, profile: { fields: [] } },
          meta: { title: payload.title || '' },
          display: {},
          key: '',
          default_view: '',
        }];
      }
      this.activeId = payload.active_id || this.datasets[0].id;
      this._loadActive(this.activeId, { initial: true });
      this._restoreFromHash();
      this._bindKeys();
      this._installResize();
      this.$nextTick(() => this._syncHeaderOffset());
      this.$watch('view', () => { if (!this._switching) { this.writeHash(); this.$nextTick(() => this.renderCharts()); } });
      this.$watch('lineXField', () => { if (!this._switching) this.$nextTick(() => this.renderCharts()); });
      this.$watch('lineYField', () => { if (!this._switching) this.$nextTick(() => this.renderCharts()); });
      this.$watch('lineSeriesField', () => { if (!this._switching) this.$nextTick(() => this.renderCharts()); });
      this.$watch('lineAgg', () => { if (!this._switching) this.$nextTick(() => this.renderCharts()); });
      this.$watch('barField', () => { if (!this._switching) this.$nextTick(() => this.renderCharts()); });
      this.$watch('barTopN', () => { if (!this._switching) this.$nextTick(() => this.renderCharts()); });
      this.$nextTick(() => this.renderCharts());
    },

    get hasMultiple() { return this.datasets.length > 1; },

    get activeDataset() {
      return this.datasets.find(d => d.id === this.activeId) || this.datasets[0];
    },

    get activeKey() {
      return (this.activeDataset || {}).key || '';
    },

    get comparableDatasets() {
      if (!this.activeKey) return [];
      return this.datasets.filter(ds => ds.key === this.activeKey);
    },

    get compareRows() {
      if (this.comparableDatasets.length < 2) return [];
      const byKey = {};
      for (const ds of this.comparableDatasets) {
        for (const row of ds.data || []) {
          const key = this.filterKey(row[ds.key]);
          if (!key || key === '∅') continue;
          const entry = byKey[key] || (byKey[key] = { key, counts: {} });
          entry.counts[ds.id] = (entry.counts[ds.id] || 0) + 1;
        }
      }
      return Object.values(byKey).sort((a, b) => a.key.localeCompare(b.key));
    },

    get activeIndex() {
      const i = this.datasets.findIndex(d => d.id === this.activeId);
      return i < 0 ? 0 : i;
    },

    setActive(id) {
      if (id === this.activeId) return;
      const ds = this.datasets.find(d => d.id === id);
      if (!ds) return;
      this._saveActiveState();
      this._loadActive(id);
      this.writeHash();
      this.$nextTick(() => this.renderCharts());
    },

    nextDataset() {
      if (!this.hasMultiple) return;
      const i = (this.activeIndex + 1) % this.datasets.length;
      this.setActive(this.datasets[i].id);
    },

    prevDataset() {
      if (!this.hasMultiple) return;
      const n = this.datasets.length;
      const i = (this.activeIndex - 1 + n) % n;
      this.setActive(this.datasets[i].id);
    },

    _saveActiveState() {
      if (!this.activeId) return;
      this._perDatasetState[this.activeId] = {
        view: this.view,
        q: this.q,
        filters: { ...this.filters },
        facetSearch: { ...this.facetSearch },
        manualFacetFields: this.manualFacetFields.slice(),
        hiddenColumns: { ...this.hiddenColumns },
        pinnedColumns: this.pinnedColumns.slice(),
        columnWidths: { ...this.columnWidths },
        formatOverrides: { ...this.formatOverrides },
        rowDensity: this.rowDensity,
        wrapCells: this.wrapCells,
        sortKey: this.sortKey,
        sortDir: this.sortDir,
        page: this.page,
        pageSize: this.pageSize,
        lineXField: this.lineXField,
        lineYField: this.lineYField,
        lineSeriesField: this.lineSeriesField,
        lineAgg: this.lineAgg,
        barField: this.barField,
        barTopN: this.barTopN,
        pivotGroupField: this.pivotGroupField,
        pivotMeasureField: this.pivotMeasureField,
        pivotAgg: this.pivotAgg,
        treeRowIdx: this.treeRowIdx,
      };
    },

    _loadActive(id, opts) {
      const initial = opts && opts.initial;
      this._switching = true;
      try {
        const ds = this.datasets.find(d => d.id === id) || this.datasets[0];
        this.activeId = ds.id;
        this.data = ds.data;
        this.schema = ds.schema;
        this.aggregates = ds.aggregates;
        this.meta = ds.meta;
        this.display = ds.display || {};
        this._sortedCacheKey = null;
        this._sortedCacheRows = [];
        this._cellCache = new WeakMap();
        this.selectedRow = null;
        const saved = this._perDatasetState[id];
        if (saved) {
          this.view = this.isEligible(saved.view) ? saved.view : this._pickInitialView();
          this.q = saved.q || '';
          this.filters = { ...(saved.filters || {}) };
          this.facetSearch = { ...(saved.facetSearch || {}) };
          this.manualFacetFields = Array.isArray(saved.manualFacetFields) ? saved.manualFacetFields.slice() : [];
          this.hiddenColumns = { ...(saved.hiddenColumns || {}) };
          this.pinnedColumns = Array.isArray(saved.pinnedColumns) ? saved.pinnedColumns.slice() : [];
          this.columnWidths = { ...(saved.columnWidths || {}) };
          this.formatOverrides = { ...(saved.formatOverrides || {}) };
          this.rowDensity = saved.rowDensity || 'comfortable';
          this.wrapCells = !!saved.wrapCells;
          this.sortKey = saved.sortKey || null;
          this.sortDir = saved.sortDir || 'asc';
          this.page = saved.page || 0;
          this.pageSize = saved.pageSize || 200;
          this.lineXField = saved.lineXField || null;
          this.lineYField = saved.lineYField || null;
          this.lineSeriesField = saved.lineSeriesField || '';
          this.lineAgg = saved.lineAgg || 'sum';
          this.barField = saved.barField || null;
          this.barTopN = saved.barTopN || 20;
          this.pivotGroupField = saved.pivotGroupField || null;
          this.pivotMeasureField = saved.pivotMeasureField || null;
          this.pivotAgg = saved.pivotAgg || 'sum';
          this.treeRowIdx = (saved.treeRowIdx === undefined ? -1 : saved.treeRowIdx);
          this._validateFieldsForActive();
        } else {
          this.q = '';
          this.filters = {};
          this.facetSearch = {};
          this.manualFacetFields = [];
          this.hiddenColumns = {};
          this.pinnedColumns = [];
          this.columnWidths = {};
          this.formatOverrides = {};
          this.rowDensity = 'comfortable';
          this.wrapCells = false;
          this.sortKey = null;
          this.sortDir = 'asc';
          this.page = 0;
          this.pageSize = 200;
          this.treeRowIdx = -1;
          this.lineSeriesField = '';
          this.lineAgg = 'sum';
          this.barTopN = 20;
          this.pivotAgg = 'sum';
          this._setupChartDefaults();
          this.view = initial ? this._pickInitialView() : (this.isEligible(this.view) ? this.view : this._pickInitialView());
        }
      } finally {
        this._switching = false;
      }
    },

    _validateFieldsForActive() {
      const fields = this.visibleFields;
      const fieldNames = new Set(fields.map(f => f.name));
      const fieldByName = new Map(fields.map(f => [f.name, f]));
      const ensureFieldForRole = (cur, role) => {
        const f = cur && fieldByName.get(cur);
        if (f && (f.eligible_for || []).includes(role)) return cur;
        const fallback = this.fieldsForRole(role)[0];
        return fallback ? fallback.name : null;
      };
      this.lineXField = ensureFieldForRole(this.lineXField, 'line_x');
      this.lineYField = ensureFieldForRole(this.lineYField, 'line_y');
      if (this.lineSeriesField) {
        const seriesNames = new Set(this.fieldsForRole('series_by').map(f => f.name));
        if (!seriesNames.has(this.lineSeriesField)) this.lineSeriesField = '';
      }
      this.barField = ensureFieldForRole(this.barField, 'bar_x');
      const groupNames = new Set(this.pivotGroupFields.map(f => f.name));
      if (!groupNames.has(this.pivotGroupField)) this.pivotGroupField = (this.pivotGroupFields[0] || {}).name || null;
      this.pivotMeasureField = ensureFieldForRole(this.pivotMeasureField, 'line_y');
      if (this.sortKey && !fieldNames.has(this.sortKey)) {
        this.sortKey = null;
        this.sortDir = 'asc';
      }
      for (const key of Object.keys(this.filters || {})) {
        if (!fieldNames.has(key)) delete this.filters[key];
      }
      this.manualFacetFields = this.manualFacetFields.filter(name => fieldNames.has(name));
      this.pinnedColumns = this.pinnedColumns.filter(name => fieldNames.has(name));
      for (const key of Object.keys(this.hiddenColumns || {})) {
        if (!fieldNames.has(key)) delete this.hiddenColumns[key];
      }
      for (const key of Object.keys(this.columnWidths || {})) {
        if (!fieldNames.has(key)) delete this.columnWidths[key];
      }
      for (const key of Object.keys(this.formatOverrides || {})) {
        if (!fieldNames.has(key)) delete this.formatOverrides[key];
      }
      const totalRows = (this.data || []).length;
      const maxPage = Math.max(0, Math.ceil(totalRows / this.pageSize) - 1);
      if (this.page > maxPage) this.page = maxPage;
    },

    _disposeCharts() {
      ['line-chart', 'bar-chart', 'pivot-chart'].forEach(id => {
        const el = document.getElementById(id);
        if (!el) return;
        const inst = echarts.getInstanceByDom(el);
        if (inst) inst.dispose();
      });
    },

    get views() {
      return [
        { id: 'table', label: 'Table', key: '1' },
        { id: 'line',  label: 'Line',  key: '2' },
        { id: 'bar',   label: 'Bar',   key: '3' },
        { id: 'pivot', label: 'Pivot', key: '4' },
        { id: 'kpis',  label: 'KPIs',  key: '5' },
        { id: 'profile', label: 'Profile', key: '6' },
        { id: 'compare', label: 'Compare', key: '7' },
        { id: 'tree',  label: 'Tree',  key: '8' },
      ];
    },

    iconFor(id) {
      const map = {
        table: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M3 15h18M9 3v18M15 3v18"/></svg>',
        line:  '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><path d="m4 17 5-7 4 4 7-9"/></svg>',
        bar:   '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><rect x="6" y="11" width="3" height="7"/><rect x="11" y="7" width="3" height="11"/><rect x="16" y="13" width="3" height="5"/></svg>',
        pivot: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4h16v16H4z"/><path d="M4 10h16M10 4v16"/></svg>',
        kpis:  '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12 2 3 7 7 .5-5.5 4.5L18 22l-6-4-6 4 1.5-8L2 9.5 9 9z"/></svg>',
        profile: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5h16"/><path d="M4 12h16"/><path d="M4 19h16"/><circle cx="8" cy="5" r="2"/><circle cx="14" cy="12" r="2"/><circle cx="10" cy="19" r="2"/></svg>',
        compare: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 7h10M7 17h10"/><path d="M8 7a3 3 0 1 1-3-3M16 17a3 3 0 1 0 3 3"/></svg>',
        tree:  '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12h4M3 6h4M3 18h4M11 6h10M11 12h10M11 18h10"/></svg>',
      };
      return map[id] || '';
    },

    isEligible(v) {
      if (v === 'compare') return this.comparableDatasets.length > 1;
      return (this.schema.eligible_views || []).includes(v);
    },
    viewReason(v) {
      if (this.isEligible(v)) return '';
      if (v === 'line') return 'Line needs one time field and one numeric measure.';
      if (v === 'bar') return 'Bar needs a categorical, boolean, or low-cardinality numeric field.';
      if (v === 'pivot') return 'Pivot needs one group field and one numeric measure.';
      if (v === 'kpis') return 'KPIs need at least one numeric measure.';
      if (v === 'compare') return 'Compare needs two sources with the same relationship key.';
      if (v === 'profile') return 'Profile needs at least one visible field.';
      if (v === 'tree') return 'Tree needs rows or metadata to inspect.';
      return 'This view is not available for the active source.';
    },
    setView(v) {
      if (!this.isEligible(v)) return;
      this.mobileDisabledReason = '';
      this.view = v;
      this.$nextTick(() => {
        this.renderCharts();
        window.setTimeout(() => this.renderCharts(), 50);
      });
    },

    selectMobileView(v) {
      if (!v || !v.id) return;
      if (!this.isEligible(v.id)) {
        this.mobileDisabledReason = this.viewReason(v.id);
        return;
      }
      this.setView(v.id);
    },

    fieldsForRole(role) {
      return this.visibleFields.filter(f => (f.eligible_for || []).includes(role));
    },

    get visibleFields() {
      return (this.schema.fields || []).filter(f => !f.hidden);
    },

    get tableFields() {
      const hidden = this.hiddenColumns || {};
      const fields = this.visibleFields.filter(f => !hidden[f.name]);
      const pinned = new Set(this.pinnedColumns || []);
      return [
        ...fields.filter(f => pinned.has(f.name)),
        ...fields.filter(f => !pinned.has(f.name)),
      ];
    },

    get hiddenColumnList() {
      return this.visibleFields.filter(f => this.hiddenColumns[f.name]);
    },

    get measureFields() {
      return this.visibleFields.filter(f => f.is_measure);
    },

    get facetFields() {
      const names = new Set(this.manualFacetFields || []);
      const fields = this.visibleFields.filter(f => f.kind === 'categorical' || f.kind === 'bool' || f.is_categorical_numeric || names.has(f.name));
      return fields.filter(f => !this.hiddenColumns[f.name]);
    },

    get pivotGroupFields() {
      return this.visibleFields.filter(f => f.kind === 'categorical' || f.kind === 'bool' || f.kind === 'time' || f.is_categorical_numeric);
    },

    get hasActiveFilters() {
      return Object.values(this.filters || {}).some(Boolean);
    },

    get activeFilterChips() {
      return Object.entries(this.filters || {})
        .filter(([, value]) => value !== undefined && value !== null && value !== '')
        .map(([field, value]) => {
          const f = this.visibleFields.find(item => item.name === field) || { name: field };
          return { field, value, label: this.fieldLabel(f) };
        });
    },

    get relationshipEdges() {
      const edges = [];
      for (let i = 0; i < this.datasets.length; i++) {
        for (let j = i + 1; j < this.datasets.length; j++) {
          const a = this.datasets[i], b = this.datasets[j];
          const key = this._relationshipKey(a, b);
          if (!key) continue;
          edges.push({
            id: a.id + '::' + b.id + '::' + key,
            from: a.id,
            to: b.id,
            fromLabel: a.label,
            toLabel: b.label,
            key,
            reason: 'Shared key ' + key,
          });
        }
      }
      return edges;
    },

    _relationshipKey(a, b) {
      if (a.key && b.key && a.key === b.key) return a.key;
      const aFields = new Set(((a.schema || {}).fields || []).map(f => f.name));
      const bFields = new Set(((b.schema || {}).fields || []).map(f => f.name));
      const candidates = Array.from(aFields).filter(name => bFields.has(name)).sort((x, y) => {
        const sx = /(^id$|_id$|key$)/i.test(x) ? 0 : 1;
        const sy = /(^id$|_id$|key$)/i.test(y) ? 0 : 1;
        return sx - sy || x.localeCompare(y);
      });
      for (const name of candidates) {
        const aVals = new Set((a.data || []).slice(0, 500).map(row => this.filterKey(row[name])).filter(v => v && v !== '∅'));
        if (!aVals.size) continue;
        let overlap = 0;
        for (const row of (b.data || []).slice(0, 500)) {
          if (aVals.has(this.filterKey(row[name]))) overlap += 1;
          if (overlap >= 2) return name;
        }
      }
      return '';
    },

    openRelationship(edge) {
      if (!edge) return;
      const left = this.datasets.find(item => item.id === edge.from);
      const right = this.datasets.find(item => item.id === edge.to);
      if (left && !left.key) left.key = edge.key;
      if (right && !right.key) right.key = edge.key;
      this.setActive(edge.from);
      this.view = 'compare';
      this.mobileNavOpen = false;
      this.writeHash();
    },

    get profileFields() {
      return (((this.aggregates || {}).profile || {}).fields || []).filter(f => !f.hidden);
    },

    get pivotRows() {
      if (!this.pivotGroupField || !this.pivotMeasureField) return [];
      const buckets = {};
      for (const row of this.filteredRows || []) {
        const group = this.filterKey(row[this.pivotGroupField]);
        const value = row[this.pivotMeasureField];
        const bucket = buckets[group] || (buckets[group] = []);
        if (typeof value === 'number' && !Number.isNaN(value)) bucket.push(value);
      }
      return Object.entries(buckets).map(([group, values]) => ({
        group,
        value: this._aggregate(values, this.pivotAgg),
        count: values.length,
      })).filter(row => row.value !== null).sort((a, b) => b.value - a.value || a.group.localeCompare(b.group));
    },

    fieldLabel(field) {
      if (!field) return '';
      return field.display_name || field.name || '';
    },

    isUrlField(field) {
      return !this.privacyMode && field && (field.renderer === 'url' || (!field.renderer && field.kind === 'url'));
    },

    isImageField(field) {
      return !this.privacyMode && field && (field.renderer === 'image' || (!field.renderer && field.kind === 'image'));
    },

    get privacyMode() {
      return !!(this.display && (this.display.privacy_mode || this.display.external_assets === false));
    },

    get metaSummary() {
      const out = [];
      const meta = this.meta || {};
      const skip = new Set(['title', 'label', 'default_view', 'truncated', 'max_embedded_rows', 'records_key', 'source_file', 'row_count', 'format']);
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
      const ds = this.datasets.find(d => d.id === this.activeId);
      const dsDefault = ds && ds.default_view;
      if (dsDefault && this.isEligible(dsDefault)) return dsDefault;
      for (const v of ['line', 'bar', 'kpis', 'profile', 'table']) {
        if (this.isEligible(v)) return v;
      }
      return 'table';
    },

    _setupChartDefaults() {
      const fields = this.visibleFields;
      const chart = this.display.chart || {};
      const fieldByName = new Map(fields.map(f => [f.name, f]));
      const roleName = (name, role) => {
        const f = name && fieldByName.get(name);
        return f && (f.eligible_for || []).includes(role) ? name : null;
      };
      const existingName = (name, candidates) => {
        const allowed = new Set(candidates.map(f => f.name));
        return allowed.has(name) ? name : null;
      };
      this.lineXField = roleName(chart.line_x, 'line_x') || (fields.find(f => f.kind === 'time') || {}).name || null;
      const measures = fields.filter(f => f.is_measure);
      this.lineYField = roleName(chart.line_y, 'line_y') || (measures[0] || {}).name || null;
      this.lineSeriesField = roleName(chart.series_by, 'series_by') || '';
      const cat = fields.find(f => f.kind === 'categorical' || f.is_categorical_numeric);
      this.barField = roleName(chart.bar, 'bar_x') || (cat || measures[0] || fields[0] || {}).name || null;
      const groups = this.pivotGroupFields;
      this.pivotGroupField = existingName(chart.group_by, groups) || (groups[0] || {}).name || null;
      this.pivotMeasureField = roleName(chart.measure, 'line_y') || (measures[0] || {}).name || null;
    },

    _rowsForFacet(fieldName) {
      const q = this.q.trim().toLowerCase();
      const activeFilters = Object.entries(this.filters || {}).filter(([field, value]) => field !== fieldName && value !== undefined && value !== null && value !== '');
      return (this.data || []).filter(row => {
        for (const [field, expected] of activeFilters) {
          if (this.filterKey(row[field]) !== expected) return false;
        }
        if (!q) return true;
        for (const k in row) {
          const v = row[k];
          if (v == null) continue;
          const s = (typeof v === 'object') ? JSON.stringify(v) : String(v);
          if (s.toLowerCase().includes(q)) return true;
        }
        return false;
      });
    },

    visibleFacetValues(field) {
      const term = String((this.facetSearch || {})[field.name] || '').trim().toLowerCase();
      return this.facetValues(field).filter(item => !term || item.label.toLowerCase().includes(term)).slice(0, 60);
    },

    setFilter(field, value) {
      if (!field) return;
      const next = { ...(this.filters || {}) };
      if (value === undefined || value === null || value === '') delete next[field];
      else next[field] = String(value);
      this.filters = next;
      this.page = 0;
      this.writeHash();
      this.$nextTick(() => this.renderCharts());
    },

    clearFilter(field) {
      if (!field) return;
      this.setFilter(field, '');
    },

    toggleColumnMenu(field) {
      this.openColumnMenu = this.openColumnMenu === field.name ? null : field.name;
      this.columnMenuFilterValue = this.filters[field.name] || '';
    },

    sortColumn(field, dir) {
      this.sortKey = field;
      this.sortDir = dir === 'desc' ? 'desc' : 'asc';
      this.openColumnMenu = null;
      this.writeHash();
    },

    applyColumnFilter(field) {
      const value = String(this.columnMenuFilterValue || '').trim();
      this.facetByField(field);
      if (value) this.setFilter(field.name, value);
      else this.clearFilter(field.name);
      this.openColumnMenu = null;
    },

    facetByField(field) {
      if (!this.manualFacetFields.includes(field.name) && !this.facetFields.some(f => f.name === field.name)) {
        this.manualFacetFields = [...this.manualFacetFields, field.name];
      }
      this.openColumnMenu = null;
      this.writeHash();
    },

    hideColumn(name) {
      this.hiddenColumns = { ...(this.hiddenColumns || {}), [name]: true };
      this.pinnedColumns = this.pinnedColumns.filter(item => item !== name);
      this.openColumnMenu = null;
      this.writeHash();
    },

    showColumn(name) {
      const next = { ...(this.hiddenColumns || {}) };
      delete next[name];
      this.hiddenColumns = next;
      this.writeHash();
    },

    togglePinned(name) {
      if (this.isPinned(name)) this.pinnedColumns = this.pinnedColumns.filter(item => item !== name);
      else this.pinnedColumns = [...this.pinnedColumns, name];
      this.writeHash();
    },

    isPinned(name) {
      return (this.pinnedColumns || []).includes(name);
    },

    profileColumn(field) {
      this.view = 'profile';
      this.openColumnMenu = null;
      this.writeHash();
      this.$nextTick(() => {
        const el = document.querySelector('[data-profile-field="' + CSS.escape(field.name) + '"]');
        if (el) el.scrollIntoView({ block: 'center', behavior: 'smooth' });
      });
    },

    copyColumnValues(field) {
      const text = this.sortedRows.map(row => {
        const value = row[field.name];
        return value == null ? '' : (typeof value === 'object' ? JSON.stringify(value) : String(value));
      }).join('\n');
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text)
          .then(() => { this.copiedColumn = field.name; window.setTimeout(() => { if (this.copiedColumn === field.name) this.copiedColumn = ''; }, 1200); })
          .catch(() => {});
      }
      this.openColumnMenu = null;
    },

    formatFor(field) {
      return (this.formatOverrides || {})[field.name] || field.format || '';
    },

    setFormat(name, format) {
      const next = { ...(this.formatOverrides || {}) };
      if (format) next[name] = format;
      else delete next[name];
      this.formatOverrides = next;
      this.writeHash();
    },

    resizeColumn(name, delta) {
      const current = Number(this.columnWidths[name] || 160);
      this.columnWidths = { ...(this.columnWidths || {}), [name]: Math.max(80, Math.min(520, current + delta)) };
      this.writeHash();
    },

    columnStyle(field) {
      const width = Number(this.columnWidths[field.name] || 160);
      const parts = [`width:${width}px`, `min-width:${Math.min(width, 320)}px`];
      if (this.isPinned(field.name)) parts.push(`left:${this.pinnedLeft(field.name)}px`);
      return parts.join(';');
    },

    pinnedLeft(name) {
      let left = 32;
      for (const fieldName of this.pinnedColumns || []) {
        if (fieldName === name) return left;
        left += Number(this.columnWidths[fieldName] || 160);
      }
      return left;
    },

    startColumnResize(event, field) {
      const startX = event.clientX;
      const startWidth = Number(this.columnWidths[field.name] || 160);
      const move = (e) => {
        const width = Math.max(80, Math.min(520, startWidth + e.clientX - startX));
        this.columnWidths = { ...(this.columnWidths || {}), [field.name]: width };
      };
      const up = () => {
        window.removeEventListener('mousemove', move);
        window.removeEventListener('mouseup', up);
        this.writeHash();
      };
      window.addEventListener('mousemove', move);
      window.addEventListener('mouseup', up);
    },

    chartPresets(kind) {
      const fields = this.visibleFields;
      const measures = fields.filter(f => f.is_measure);
      const groups = fields.filter(f => f.kind === 'categorical' || f.kind === 'bool' || f.is_categorical_numeric);
      const times = fields.filter(f => f.kind === 'time');
      const presets = [];
      if (kind === 'line' && times.length && measures.length) {
        presets.push({ id: 'line-primary', kind: 'line', label: `${this.fieldLabel(measures[0])} over time`, x: times[0].name, y: measures[0].name, series: '' });
        const series = groups.find(f => f.distinct <= 8);
        if (series) presets.push({ id: 'line-series', kind: 'line', label: `${this.fieldLabel(measures[0])} by ${this.fieldLabel(series)}`, x: times[0].name, y: measures[0].name, series: series.name });
      }
      if (kind === 'bar' && groups.length) {
        presets.push({ id: 'bar-counts', kind: 'bar', label: `Rows by ${this.fieldLabel(groups[0])}`, field: groups[0].name });
        if (groups[1]) presets.push({ id: 'bar-alt', kind: 'bar', label: `Rows by ${this.fieldLabel(groups[1])}`, field: groups[1].name });
      }
      if (kind === 'pivot' && groups.length && measures.length) {
        presets.push({ id: 'pivot-primary', kind: 'pivot', label: `${this.fieldLabel(measures[0])} by ${this.fieldLabel(groups[0])}`, group: groups[0].name, measure: measures[0].name });
        if (measures[1]) presets.push({ id: 'pivot-second', kind: 'pivot', label: `${this.fieldLabel(measures[1])} by ${this.fieldLabel(groups[0])}`, group: groups[0].name, measure: measures[1].name });
      }
      return presets;
    },

    applyChartPreset(preset) {
      if (!preset) return;
      if (preset.kind === 'line') {
        this.lineXField = preset.x;
        this.lineYField = preset.y;
        this.lineSeriesField = preset.series || '';
      } else if (preset.kind === 'bar') {
        this.barField = preset.field;
      } else if (preset.kind === 'pivot') {
        this.pivotGroupField = preset.group;
        this.pivotMeasureField = preset.measure;
      }
      this.$nextTick(() => this.renderCharts());
      this.writeHash();
    },

    get filteredRows() {
      const q = this.q.trim().toLowerCase();
      const activeFilters = Object.entries(this.filters || {}).filter(([, v]) => v !== undefined && v !== null && v !== '');
      if (!q && !activeFilters.length) return this.data;
      const out = [];
      for (const r of this.data) {
        let matchedFilters = true;
        for (const [field, expected] of activeFilters) {
          if (this.filterKey(r[field]) !== expected) { matchedFilters = false; break; }
        }
        if (!matchedFilters) continue;
        if (!q) { out.push(r); continue; }
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
      const cacheKey = JSON.stringify([this.q, this.filters, this.sortKey, this.sortDir, this.data.length]);
      if (this._sortedCacheKey === cacheKey) return this._sortedCacheRows;
      let rows = this.filteredRows;
      if (this.sortKey) {
        const k = this.sortKey, dir = this.sortDir === 'asc' ? 1 : -1;
        rows = [...rows].sort((a, b) => {
          const av = a[k], bv = b[k];
          if (av == null && bv == null) return 0;
          if (av == null) return 1;
          if (bv == null) return -1;
          if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * dir;
          return String(av).localeCompare(String(bv)) * dir;
        });
      }
      this._sortedCacheKey = cacheKey;
      this._sortedCacheRows = rows;
      return rows;
    },

    get pagedRows() {
      const start = this.page * this.pageSize;
      return this.sortedRows.slice(start, start + this.pageSize);
    },

    get totalPages() {
      const total = this.sortedRows.length;
      return Math.max(1, Math.ceil(total / this.pageSize));
    },

    get visibleStart() {
      if (!this.sortedRows.length) return 0;
      return this.page * this.pageSize + 1;
    },

    get visibleEnd() {
      return Math.min((this.page + 1) * this.pageSize, this.sortedRows.length);
    },

    setPage(nextPage) {
      this.page = nextPage;
      this.writeHash();
    },

    sortBy(key) {
      if (this.sortKey === key) this.sortDir = this.sortDir === 'asc' ? 'desc' : 'asc';
      else { this.sortKey = key; this.sortDir = 'asc'; }
      this.writeHash();
    },

    filterKey(value) {
      if (value == null) return '∅';
      if (typeof value === 'object') return JSON.stringify(value);
      return String(value);
    },

    facetValues(field) {
      const counts = {};
      for (const row of this._rowsForFacet(field.name) || []) {
        const key = this.filterKey(row[field.name]);
        counts[key] = (counts[key] || 0) + 1;
      }
      return Object.entries(counts)
        .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
        .slice(0, 50)
        .map(([value, count]) => ({ value, label: value, count }));
    },

    clearFilters() {
      this.filters = {};
      this.page = 0;
      this.writeHash();
      this.$nextTick(() => this.renderCharts());
    },

    _cellMeta(row, fieldName) {
      if (!row || typeof row !== 'object') return { display: '', title: '' };
      let rowCache = this._cellCache.get(row);
      if (!rowCache) {
        rowCache = new Map();
        this._cellCache.set(row, rowCache);
      }
      if (rowCache.has(fieldName)) return rowCache.get(fieldName);
      const v = row[fieldName];
      let display = '';
      let title = '';
      if (v === undefined) {
        display = '(missing)';
        title = 'field missing from this row';
      } else if (v === null) {
        display = 'null';
        title = 'null';
      } else if (typeof v === 'object') {
        display = Array.isArray(v) ? '[' + v.length + ' items]' : '{' + Object.keys(v).length + ' keys}';
        title = JSON.stringify(v).slice(0, 1000);
      } else {
        const s = String(v);
        display = s.length > 120 ? s.slice(0, 120) + '…' : s;
        title = s.slice(0, 1000);
      }
      const meta = { display, title };
      rowCache.set(fieldName, meta);
      return meta;
    },

    formatCell(row, field) {
      const meta = this._cellMeta(row, field.name);
      const value = row ? row[field.name] : null;
      if (value == null || typeof value === 'object') return meta.display;
      const format = this.formatFor(field);
      if (format && typeof value === 'number') return this._formatNumber(value, format);
      return meta.display;
    },

    cellTitle(row, fieldName) {
      return this._cellMeta(row, fieldName).title;
    },

    cellClass(v, field) {
      if (typeof v === 'number') return 'num text-right text-zinc-900 dark:text-zinc-100';
      if (field.kind === 'time') return 'num text-zinc-700 dark:text-zinc-200 whitespace-nowrap';
      if (field.kind === 'categorical' || field.kind === 'bool') return 'whitespace-nowrap';
      return '';
    },

    _formatNumber(value, format) {
      if (format === 'integer') return Math.round(value).toLocaleString();
      if (format === 'percent') return (value * 100).toLocaleString(undefined, { maximumFractionDigits: 2 }) + '%';
      if (format === 'currency') return value.toLocaleString(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 2 });
      return this._fmtNum(value);
    },

    showRow(row) { this.selectedRow = row; },

    drawerTitle() {
      if (this.selectedRow == null) return 'row detail';
      const idx = this.data.indexOf(this.selectedRow);
      if (idx < 0) return 'row detail';
      return `row detail · row ${idx + 1} of ${this.data.length}`;
    },

    get relatedLinks() {
      if (!this.selectedRow || !this.activeKey) return [];
      const keyValue = this.filterKey(this.selectedRow[this.activeKey]);
      if (!keyValue || keyValue === '∅') return [];
      return this.datasets
        .filter(ds => ds.id !== this.activeId && ds.key === this.activeKey)
        .map(ds => ({
          id: ds.id,
          label: ds.label,
          field: ds.key,
          key: keyValue,
          count: (ds.data || []).filter(row => this.filterKey(row[ds.key]) === keyValue).length,
        }))
        .filter(link => link.count > 0);
    },

    openRelated(link) {
      this.selectedRow = null;
      this.setActive(link.id);
      const target = this.datasets.find(ds => ds.id === link.id);
      const field = link.field || (target && target.key);
      this.q = '';
      this.filters = field ? { [field]: link.key } : {};
      this.view = 'table';
      this.page = 0;
      this.writeHash();
      this.$nextTick(() => this.renderCharts());
    },

    kpisFor(field) {
      const stats = this.aggregates.kpis[field.name];
      if (!stats) return [{ k: 'count', v: '0' }];
      const count = stats.count || 0;
      if (!count) return [{ k: 'count', v: '0' }];
      return [
        { k: 'count',  v: count.toLocaleString() },
        { k: 'sum',    v: this._fmtNum(stats.sum) },
        { k: 'mean',   v: this._fmtNum(stats.mean) },
        { k: 'median', v: this._fmtNum(stats.median) },
        { k: 'p90',    v: this._fmtNum(stats.p90) },
        { k: 'min',    v: this._fmtNum(stats.min) },
        { k: 'max',    v: this._fmtNum(stats.max) },
      ];
    },

    _fmtNum(n) {
      const value = Number(n);
      if (n == null || !Number.isFinite(value)) return '';
      if (value === 0) return '0';
      if (Math.abs(value) >= 1000) return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
      if (Math.abs(value) < 0.001) return value.toExponential(2);
      return Number(value.toFixed(4)).toString();
    },

    profileBarWidth(bin, bins) {
      const max = Math.max(...(bins || []).map(b => b.count || 0), 1);
      return Math.max(2, Math.round(((bin.count || 0) / max) * 100));
    },

    renderCharts() {
      if (this.view === 'line') this._renderLine();
      if (this.view === 'bar') this._renderBar();
      if (this.view === 'pivot') this._renderPivot();
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
        case 'min': return values.reduce((acc, val) => (val < acc ? val : acc), values[0]);
        case 'max': return values.reduce((acc, val) => (val > acc ? val : acc), values[0]);
        case 'sum': default: return values.reduce((a, b) => a + b, 0);
      }
    },

    _renderLine() {
      const chart = this._ensureChart('line-chart');
      if (!chart) return;
      if (!this.lineXField || !this.lineYField) { chart.clear(); return; }
      const xf = this.lineXField, yf = this.lineYField, sf = this.lineSeriesField;
      const lineKey = `${xf}||${yf}||${sf || ''}`;
      const bundle = (this.hasActiveFilters || this.q.trim()) ? this._lineBundleFromRows(this.filteredRows, xf, yf, sf) : this.aggregates.line[lineKey];
      if (!bundle) { chart.clear(); return; }
      const xs = bundle.xs || [];
      const xField = (this.schema.fields || []).find(f => f.name === xf) || {};
      const sortedIdx = xs.map((_, idx) => idx).sort((a, b) => {
        if (xField.kind === 'numeric') {
          return Number(xs[a]) - Number(xs[b]);
        }
        if (xField.kind === 'time') {
          const ta = Date.parse(xs[a]);
          const tb = Date.parse(xs[b]);
          if (Number.isFinite(ta) && Number.isFinite(tb)) return ta - tb;
        }
        return String(xs[a]).localeCompare(String(xs[b]));
      });
      const sortedXs = sortedIdx.map(i => xs[i]);
      const series = (bundle.series || []).map(s => ({
        name: s.name === '__total__' ? `${this.lineAgg}(${yf})` : s.name,
        type: 'line',
        showSymbol: sortedXs.length <= 60,
        smooth: false,
        data: sortedIdx.map(i => this._seriesAggValue(s, i, this.lineAgg)),
      }));
      chart.setOption({
        backgroundColor: 'transparent',
        animation: false,
        grid: { left: 60, right: 30, top: 36, bottom: 50, containLabel: true },
        xAxis: { type: 'category', data: sortedXs, axisLabel: { rotate: sortedXs.length > 12 ? 30 : 0 } },
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
      const ranked = (this.hasActiveFilters || this.q.trim()) ? this._barCountsFromRows(this.filteredRows, this.barField) : (this.aggregates.bar[this.barField] || []);
      const sorted = ranked.slice(0, this.barTopN || 20);
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

    _renderPivot() {
      const chart = this._ensureChart('pivot-chart');
      if (!chart) return;
      const rows = this.pivotRows.slice(0, 30).reverse();
      chart.setOption({
        backgroundColor: 'transparent',
        animation: false,
        grid: { left: 140, right: 30, top: 16, bottom: 24, containLabel: true },
        xAxis: { type: 'value' },
        yAxis: { type: 'category', data: rows.map(row => row.group) },
        tooltip: { trigger: 'axis' },
        series: [{ type: 'bar', data: rows.map(row => row.value), itemStyle: { color: '#6366f1' } }],
      }, true);
    },

    _barCountsFromRows(rows, field) {
      const counts = {};
      for (const row of rows || []) {
        const key = this.filterKey(row[field]);
        counts[key] = (counts[key] || 0) + 1;
      }
      return Object.entries(counts).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
    },

    _lineBundleFromRows(rows, xField, yField, seriesField) {
      const buckets = {};
      for (const row of rows || []) {
        const x = row[xField];
        const y = row[yField];
        if (x == null || typeof y !== 'number') continue;
        const xKey = String(x);
        const sKey = seriesField ? this.filterKey(row[seriesField]) : '__total__';
        const xBucket = buckets[xKey] || (buckets[xKey] = {});
        const arr = xBucket[sKey] || (xBucket[sKey] = []);
        arr.push(y);
      }
      const xs = Object.keys(buckets).sort();
      const allSeries = new Set();
      for (const x of xs) for (const s of Object.keys(buckets[x])) allSeries.add(s);
      const orderedSeries = seriesField ? Array.from(allSeries).sort().slice(0, 8) : ['__total__'];
      return {
        xs,
        series: orderedSeries.map(name => ({
          name,
          sum: xs.map(x => { const vals = buckets[x][name] || []; return vals.length ? vals.reduce((a, b) => a + b, 0) : null; }),
          count: xs.map(x => (buckets[x][name] || []).length),
          min: xs.map(x => { const vals = buckets[x][name] || []; return vals.length ? Math.min(...vals) : null; }),
          max: xs.map(x => { const vals = buckets[x][name] || []; return vals.length ? Math.max(...vals) : null; }),
        })),
      };
    },

    _seriesAggValue(series, idx, agg) {
      if (agg === 'count') return (series.count || [])[idx] || 0;
      if (agg === 'avg') {
        const count = (series.count || [])[idx] || 0;
        const total = (series.sum || [])[idx];
        if (!count || total == null) return null;
        return total / count;
      }
      if (agg === 'min') return (series.min || [])[idx];
      if (agg === 'max') return (series.max || [])[idx];
      return (series.sum || [])[idx];
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
      const autoOpenDepth = this._treeAutoOpenDepth();
      host.appendChild(this._buildTreeNode('$', value, 0, true, autoOpenDepth));
    },

    _treeAutoOpenDepth() {
      return this.data.length <= 5 ? 2 : 1;
    },

    _buildTreeNode(key, value, depth, openByDefault, autoOpenDepth) {
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
      summary.className = 'cursor-pointer select-none hover:bg-zinc-100 dark:hover:bg-zinc-900/40 rounded px-1';
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
            children.appendChild(this._buildTreeNode(k, v, depth + 1, false, autoOpenDepth));
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
      if (openByDefault && entries.length <= 40 && depth < autoOpenDepth) open(); else close();
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
      localStorage.setItem('bh-data-display.theme', this.theme);
      ['line-chart', 'bar-chart', 'pivot-chart'].forEach(id => {
        const el = document.getElementById(id);
        if (!el) return;
        const inst = echarts.getInstanceByDom(el);
        if (inst) inst.dispose();
      });
      this.$nextTick(() => this.renderCharts());
    },

    writeHash() {
      const h = new URLSearchParams();
      if (this.hasMultiple) h.set('ds', this.activeId);
      h.set('view', this.view);
      if (this.q) h.set('q', this.q);
      for (const [field, value] of Object.entries(this.filters || {})) {
        if (value) h.set('f.' + field, value);
      }
      if (this.sortKey) { h.set('sort', this.sortKey); h.set('dir', this.sortDir); }
      if (this.page > 0) h.set('page', String(this.page));
      if (this.pageSize !== 200) h.set('page_size', String(this.pageSize));
      if (this.rowDensity !== 'comfortable') h.set('density', this.rowDensity);
      if (this.wrapCells) h.set('wrap', '1');
      if ((this.pinnedColumns || []).length) h.set('pin', this.pinnedColumns.join(','));
      const hidden = Object.keys(this.hiddenColumns || {}).filter(k => this.hiddenColumns[k]);
      if (hidden.length) h.set('hide', hidden.join(','));
      if ((this.manualFacetFields || []).length) h.set('facets', this.manualFacetFields.join(','));
      const formats = Object.entries(this.formatOverrides || {}).filter(([, value]) => value);
      if (formats.length) h.set('fmt', formats.map(([key, value]) => key + ':' + value).join(','));
      const s = h.toString();
      history.replaceState(null, '', s ? '#' + s : location.pathname);
    },

    _restoreFromHash() {
      const h = new URLSearchParams((location.hash || '').slice(1));
      const ds = h.get('ds');
      if (ds && this.datasets.some(d => d.id === ds) && ds !== this.activeId) {
        this._loadActive(ds);
      }
      const v = h.get('view'); if (v && this.isEligible(v)) this.view = v;
      const q = h.get('q'); if (q) this.q = q;
      const nextFilters = {};
      for (const [key, value] of h.entries()) {
        if (key.startsWith('f.') && value) nextFilters[key.slice(2)] = value;
      }
      this.filters = nextFilters;
      const sk = h.get('sort');
      if (sk && this.visibleFields.some(f => f.name === sk)) {
        this.sortKey = sk;
        this.sortDir = h.get('dir') === 'desc' ? 'desc' : 'asc';
      }
      const page = Number(h.get('page')); if (Number.isFinite(page) && page >= 0) this.page = page;
      const pageSize = Number(h.get('page_size'));
      if ([100, 200, 500, 1000].includes(pageSize)) this.pageSize = pageSize;
      const density = h.get('density'); if (density === 'compact' || density === 'comfortable') this.rowDensity = density;
      this.wrapCells = h.get('wrap') === '1';
      const fieldNames = new Set(this.visibleFields.map(f => f.name));
      const pins = (h.get('pin') || '').split(',').filter(name => fieldNames.has(name));
      if (pins.length) this.pinnedColumns = pins;
      const hidden = (h.get('hide') || '').split(',').filter(name => fieldNames.has(name));
      if (hidden.length) this.hiddenColumns = Object.fromEntries(hidden.map(name => [name, true]));
      const manual = (h.get('facets') || '').split(',').filter(name => fieldNames.has(name));
      if (manual.length) this.manualFacetFields = manual;
      const formats = {};
      for (const pair of (h.get('fmt') || '').split(',')) {
        const [name, fmt] = pair.split(':');
        if (fieldNames.has(name) && ['integer', 'percent', 'currency'].includes(fmt)) formats[name] = fmt;
      }
      this.formatOverrides = formats;
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
        if (e.key === '[') { e.preventDefault(); this.prevDataset(); return; }
        if (e.key === ']') { e.preventDefault(); this.nextDataset(); return; }
        const map = { '1': 'table', '2': 'line', '3': 'bar', '4': 'pivot', '5': 'kpis', '6': 'profile', '7': 'compare', '8': 'tree' };
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

    _syncHeaderOffset() {
      const header = this.$refs.header;
      if (!header) return;
      document.documentElement.style.setProperty('--header-h', header.getBoundingClientRect().height + 'px');
    },

    _installResize() {
      const onResize = () => {
        this._syncHeaderOffset();
        ['line-chart', 'bar-chart', 'pivot-chart'].forEach(id => {
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
<script>__ALPINE_JS__</script>
</body>
</html>
"""
