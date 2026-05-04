import json
import os
import pathlib
import re
import subprocess

import pytest

import data_display


def test_load_records_csv_coercion(tmp_path):
    p = tmp_path / "rows.csv"
    p.write_text("a,b,c,d\n1,2.5,true,\n3,4.0,false,hello\n", encoding="utf-8")
    rows, meta = data_display._load_records(p)
    assert rows[0]["a"] == 1
    assert rows[0]["b"] == 2.5
    assert rows[0]["c"] is True
    assert rows[0]["d"] is None
    assert rows[1]["c"] is False
    assert meta["format"] == "csv"


def test_load_records_csv_preserves_js_unsafe_integer_strings(tmp_path):
    p = tmp_path / "rows.csv"
    p.write_text("listing_id,value\n9007199254740993,9007199254740991\n", encoding="utf-8")

    rows, _meta = data_display._load_records(p)

    assert rows[0]["listing_id"] == "9007199254740993"
    assert rows[0]["value"] == 9007199254740991


def test_load_records_csv_preserves_identifier_and_zero_padded_strings(tmp_path):
    p = tmp_path / "rows.csv"
    p.write_text(
        "listing_id,postalCode,sku,value,count\n12345,00123,00077,42,7\n",
        encoding="utf-8",
    )

    rows, _meta = data_display._load_records(p)

    assert rows[0]["listing_id"] == "12345"
    assert rows[0]["postalCode"] == "00123"
    assert rows[0]["sku"] == "00077"
    assert rows[0]["value"] == 42
    assert rows[0]["count"] == 7


def test_load_records_jsonl_skips_bad_lines(tmp_path):
    p = tmp_path / "rows.jsonl"
    p.write_text('{"a":1}\n\nnot-json\n2\n{"b":"x"}\n', encoding="utf-8")
    rows, meta = data_display._load_records(p)
    assert rows == [{"a": 1}, {"value": 2}, {"b": "x"}]
    assert meta["format"] == "jsonl"
    assert meta["jsonl_non_empty_lines"] == 4
    assert meta["jsonl_skipped_lines"] == 1


def test_load_records_json_wrapper_key_precedence(tmp_path):
    p = tmp_path / "rows.json"
    p.write_text(
        json.dumps(
            {
                "rows": [{"id": 10}],
                "records": [{"id": 11}, {"id": 12}],
                "run_id": "abc",
            }
        ),
        encoding="utf-8",
    )
    rows, meta = data_display._load_records(p)
    assert [r["id"] for r in rows] == [11, 12]
    assert meta["records_key"] == "records"
    assert meta["run_id"] == "abc"


def test_find_records_bfs_fallback_largest_list():
    obj = {
        "meta": {"k": 1},
        "nested": {
            "a": [{"id": 1}],
            "b": {"c": [{"id": 2}, {"id": 3}]},
        },
    }
    rows, key = data_display._find_records(obj)
    assert key == "c"
    assert len(rows) == 2


def test_load_records_json_nested_key_removes_discovered_records_from_meta(tmp_path):
    p = tmp_path / "nested.json"
    p.write_text(
        json.dumps(
            {
                "run_id": "abc",
                "payload": {
                    "items": [{"id": 1}, {"id": 2}],
                    "other": {"kept": True},
                },
            }
        ),
        encoding="utf-8",
    )

    rows, meta = data_display._load_records(p)

    assert [row["id"] for row in rows] == [1, 2]
    assert meta["records_key"] == "payload.items"
    assert meta["payload"] == {"other": {"kept": True}}


def test_load_records_unsupported_extension(tmp_path):
    p = tmp_path / "rows.txt"
    p.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError):
        data_display._load_records(p)


def test_introspect_kinds_and_eligible_views():
    rows = [
        {
            "created_at": f"2026-04-{i + 1:02d}",
            "amount": i + 0.5,
            "status": "ok" if i % 2 == 0 else "warn",
            "url": "https://example.com/x",
            "image": "https://example.com/x.png",
            "nested": {"k": i},
            "body": "lorem ipsum " + str(i),
            "flag": i % 2 == 0,
        }
        for i in range(20)
    ]
    schema = data_display._introspect(rows)
    by_name = {f["name"]: f for f in schema["fields"]}
    assert by_name["created_at"]["kind"] == "time"
    assert by_name["amount"]["kind"] == "numeric"
    assert by_name["amount"]["is_measure"] is True
    assert by_name["status"]["kind"] == "categorical"
    assert by_name["url"]["kind"] == "url"
    assert by_name["image"]["kind"] == "image"
    assert by_name["nested"]["kind"] == "nested"
    assert by_name["flag"]["kind"] == "bool"
    assert "line" in schema["eligible_views"]
    assert "bar" in schema["eligible_views"]
    assert "pivot" in schema["eligible_views"]
    assert "kpis" in schema["eligible_views"]
    assert "profile" in schema["eligible_views"]
    assert "tree" in schema["eligible_views"]


def test_aggregations_round_trip():
    rows = [
        {
            "ts": f"2026-04-{(i % 9) + 1:02d}",
            "category": "a" if i % 2 == 0 else "b",
            "value": float(i + 1),
        }
        for i in range(12)
    ]
    schema = data_display._introspect(rows)
    aggs = data_display._build_aggregates(rows, schema)
    assert "value" in aggs["kpis"]
    assert aggs["kpis"]["value"]["count"] == 12
    assert "category" in aggs["bar"]
    line_key = data_display._line_key("ts", "value", "category")
    assert line_key in aggs["line"]
    assert aggs["line"][line_key]["xs"][:3] == ["2026-04-01", "2026-04-02", "2026-04-03"]
    assert len(aggs["line"][line_key]["xs"]) == 9
    profile = {field["name"]: field for field in aggs["profile"]["fields"]}
    assert profile["value"]["numeric"]["count"] == 12
    assert profile["value"]["numeric"]["max"] == 12.0
    assert profile["category"]["top_values"][0] == {"value": "a", "count": 6}
    assert len(profile["value"]["numeric"]["histogram"]) == 10


def test_series_by_only_exposes_precomputed_low_cardinality_fields():
    rows = [
        {
            "ds": f"2026-04-{(i % 3) + 1:02d}",
            "segment": f"s{i % 9}",
            "value": i + 1,
        }
        for i in range(45)
    ]

    schema = data_display._introspect(rows)
    segment = next(f for f in schema["fields"] if f["name"] == "segment")
    aggs = data_display._build_aggregates(rows, schema)

    assert "series_by" not in segment["eligible_for"]
    assert data_display._line_key("ds", "value", "segment") not in aggs["line"]
    assert data_display._line_key("ds", "value", None) in aggs["line"]


def test_aggregate_line_sorts_iso_dates_then_numeric_then_text():
    rows = [
        {"x": "9", "value": 1.0},
        {"x": "10", "value": 1.0},
        {"x": "2026/04/02", "value": 1.0},
        {"x": "alpha", "value": 1.0},
        {"x": "2026-04-01", "value": 1.0},
    ]
    schema = {
        "fields": [
            {"name": "x", "eligible_for": ["line_x"]},
            {"name": "value", "eligible_for": ["line_y"]},
        ]
    }

    aggs = data_display._aggregate_line(rows, schema)
    line_key = data_display._line_key("x", "value", None)
    assert aggs[line_key]["xs"] == ["2026-04-01", "2026/04/02", "9", "10", "alpha"]


def _extract_payload(html_path):
    html = pathlib.Path(html_path).read_text(encoding="utf-8")
    m = re.search(
        r'<script type="application/json" id="payload-json">(.*?)</script>',
        html,
        flags=re.S,
    )
    assert m is not None
    return json.loads(m.group(1).replace("<\\/", "</"))


def test_render_dataset_smoke_and_payload_keys(tmp_path):
    p = tmp_path / "rows.jsonl"
    p.write_text('{"ts":"2026-04-01","value":1}\n{"ts":"2026-04-02","value":2}\n', encoding="utf-8")
    out = pathlib.Path(data_display.render_dataset(str(p)))
    assert out.exists()
    assert out.name == "rows.html"
    payload = _extract_payload(out)
    assert set(payload.keys()) >= {"datasets", "active_id", "title", "default_view", "multi"}
    assert payload["multi"] is False
    assert len(payload["datasets"]) == 1
    ds = payload["datasets"][0]
    assert set(ds.keys()) >= {"id", "label", "data", "schema", "aggregates", "meta"}
    assert payload["active_id"] == ds["id"]
    assert ds["label"] == "rows"
    assert ds["meta"]["total_rows"] == 2
    assert ds["meta"]["embedded_rows"] == 2
    assert ds["meta"]["aggregate_scope"] == "full"
    assert "profile" in ds["aggregates"]


def test_render_dataset_profile_view_payload_and_markup(tmp_path):
    p = tmp_path / "rows.json"
    p.write_text(
        json.dumps(
            [
                {"category": "a", "score": 1.5, "created_at": "2026-04-01", "missing": None},
                {"category": "a", "score": 2.5, "created_at": "2026-04-02", "missing": None},
                {"category": "b", "score": 3.5, "created_at": "2026-04-03", "missing": "x"},
            ]
        ),
        encoding="utf-8",
    )

    out = pathlib.Path(data_display.render_dataset(str(p), view="profile"))
    payload = _extract_payload(out)
    ds = payload["datasets"][0]
    html = out.read_text(encoding="utf-8")
    profile = {field["name"]: field for field in ds["aggregates"]["profile"]["fields"]}

    assert ds["default_view"] == "profile"
    assert "profile" in ds["schema"]["eligible_views"]
    assert "Profile" in html
    assert "profileFields" in html
    assert profile["category"]["top_values"][0] == {"value": "a", "count": 2}
    assert profile["score"]["numeric"]["mean"] == 2.5
    assert profile["created_at"]["time"] == {"min": "2026-04-01", "max": "2026-04-03"}
    assert profile["missing"]["null_pct"] == 66.7


def test_render_dataset_applies_display_overrides(tmp_path):
    p = tmp_path / "rows.json"
    p.write_text(
        json.dumps(
            [
                {
                    "raw_name": "alpha" if i < 6 else "beta",
                    "score": (i + 1) / 100,
                    "image_url": f"https://example.com/{i}",
                }
                for i in range(12)
            ]
        ),
        encoding="utf-8",
    )

    out = pathlib.Path(
        data_display.render_dataset(
            {"label": "Rows", "path": str(p), "display": {"fields": {"raw_name": {"hidden": True}}}},
            display={
                "default_view": "profile",
                "labels": {"score": "Conversion rate"},
                "field_kinds": {"image_url": "image"},
                "formats": {"score": "percent"},
                "chart": {"bar": "raw_name"},
            },
        )
    )
    payload = _extract_payload(out)
    ds = payload["datasets"][0]
    fields = {field["name"]: field for field in ds["schema"]["fields"]}
    html = out.read_text(encoding="utf-8")

    assert ds["default_view"] == "profile"
    assert ds["display"]["labels"]["score"] == "Conversion rate"
    assert ds["display"]["fields"]["raw_name"]["hidden"] is True
    assert fields["score"]["display_name"] == "Conversion rate"
    assert fields["score"]["format"] == "percent"
    assert "raw_name" not in fields
    assert "raw_name" not in ds["data"][0]
    assert "raw_name" not in ds["aggregates"]["bar"]
    assert "raw_name" not in {field["name"] for field in ds["aggregates"]["profile"]["fields"]}
    assert fields["image_url"]["kind"] == "image"
    assert "bar" not in ds["schema"]["eligible_views"]
    assert "fieldLabel" in html
    assert "formatCell(row, f)" in html


def test_render_dataset_redacts_hidden_fields_from_browser_payload_and_aggregates(tmp_path):
    p = tmp_path / "rows.json"
    p.write_text(
        json.dumps(
            [
                {
                    "ds": f"2026-04-{(i % 3) + 1:02d}",
                    "segment": "a" if i % 2 == 0 else "b",
                    "public_value": i + 1,
                    "secret_score": 1000 + i,
                    "secret_category": "private-a" if i % 2 == 0 else "private-b",
                }
                for i in range(12)
            ]
        ),
        encoding="utf-8",
    )

    out = pathlib.Path(
        data_display.render_dataset(
            str(p),
            display={"hidden_fields": ["secret_score", "secret_category"]},
        )
    )
    ds = _extract_payload(out)["datasets"][0]
    field_names = {field["name"] for field in ds["schema"]["fields"]}
    profile_names = {field["name"] for field in ds["aggregates"]["profile"]["fields"]}

    assert "secret_score" not in field_names
    assert "secret_category" not in field_names
    assert all("secret_score" not in row and "secret_category" not in row for row in ds["data"])
    assert "secret_score" not in ds["aggregates"]["kpis"]
    assert "secret_category" not in ds["aggregates"]["bar"]
    assert "secret_score" not in profile_names
    assert "secret_category" not in profile_names
    assert all("secret_score" not in key and "secret_category" not in key for key in ds["aggregates"]["line"])


def test_render_dataset_preserves_null_missing_and_unobservable_states(tmp_path):
    p = tmp_path / "rows.json"
    p.write_text(
        json.dumps(
            [
                {"id": 1, "status": "__UNOBSERVABLE__", "score": None},
                {"id": 2, "status": "", "note": "present"},
            ]
        ),
        encoding="utf-8",
    )

    out = pathlib.Path(data_display.render_dataset(str(p)))
    payload = _extract_payload(out)
    html = out.read_text(encoding="utf-8")
    ds = payload["datasets"][0]

    assert ds["data"][0]["status"] == "__UNOBSERVABLE__"
    assert ds["data"][0]["score"] is None
    assert "score" not in ds["data"][1]
    assert ds["data"][1]["status"] == ""
    assert "display = '(missing)'" in html
    assert "title = 'field missing from this row'" in html
    assert "display = 'null'" in html


def test_render_dataset_includes_faceted_filtering_controls(tmp_path):
    p = tmp_path / "rows.json"
    p.write_text(
        json.dumps(
            [
                {"ds": "2026-04-01", "category": "a", "flag": True, "value": 11},
                {"ds": "2026-04-02", "category": "b", "flag": False, "value": 12},
                {"ds": "2026-04-03", "category": "a", "flag": True, "value": 13},
                {"ds": "2026-04-04", "category": "b", "flag": False, "value": 14},
                {"ds": "2026-04-05", "category": "a", "flag": True, "value": 15},
            ]
        ),
        encoding="utf-8",
    )

    out = pathlib.Path(data_display.render_dataset(str(p)))
    payload = _extract_payload(out)
    ds = payload["datasets"][0]
    fields = {field["name"]: field for field in ds["schema"]["fields"]}
    html = out.read_text(encoding="utf-8")

    assert fields["category"]["kind"] == "categorical"
    assert fields["flag"]["kind"] == "bool"
    assert "facetFields" in html
    assert "facet-panel" in html
    assert "facetSearch" in html
    assert "activeFilterChips" in html
    assert "visibleFacetValues(f)" in html
    assert "setFilter(field, value)" in html
    assert "clearFilter(field)" in html
    assert "clear all" in html
    assert "filters[f.name]" in html
    assert "clearFilters()" in html
    assert "facetByField(field)" in html
    assert "facets" in html
    assert "filterKey" in html
    assert "_barCountsFromRows" in html
    assert "_lineBundleFromRows" in html
    assert "f.' + field" in html


def test_render_dataset_includes_column_menu_density_and_responsive_controls(tmp_path):
    p = tmp_path / "rows.json"
    p.write_text(
        json.dumps(
            [
                {"ds": "2026-04-01", "category": "a", "status": "new", "value": 11},
                {"ds": "2026-04-02", "category": "b", "status": "done", "value": 12},
            ]
        ),
        encoding="utf-8",
    )

    out = pathlib.Path(data_display.render_dataset(str(p)))
    html = out.read_text(encoding="utf-8")

    assert "column-menu" in html
    assert "toggleColumnMenu(f)" in html
    assert "Sort ascending" in html
    assert "Facet by this" in html
    assert "hideColumn(f.name)" in html
    assert "togglePinned(f.name)" in html
    assert "copyColumnValues(f)" in html
    assert "Copied values" in html
    assert "setFormat(f.name" in html
    assert "startColumnResize($event, f)" in html
    assert "table-scroll-hint" in html
    assert "rowDensity" in html
    assert "wrapCells" in html
    assert "mobile-bar" in html
    assert "selectMobileView(v)" in html
    assert "mobileDisabledReason" in html
    assert "mobile-disabled-reason" in html
    assert "mobileNavOpen" in html
    assert "viewReason(v.id)" in html
    assert "disabled-reason" in html
    assert "@media (max-width: 760px)" in html


def test_render_dataset_includes_guided_chart_presets(tmp_path):
    p = tmp_path / "rows.json"
    p.write_text(
        json.dumps(
            [
                {"ds": "2026-04-01", "category": "a", "score": 11, "price": 101},
                {"ds": "2026-04-02", "category": "b", "score": 12, "price": 102},
                {"ds": "2026-04-03", "category": "a", "score": 13, "price": 103},
                {"ds": "2026-04-04", "category": "b", "score": 14, "price": 104},
                {"ds": "2026-04-05", "category": "a", "score": 15, "price": 105},
                {"ds": "2026-04-06", "category": "b", "score": 16, "price": 106},
                {"ds": "2026-04-07", "category": "a", "score": 17, "price": 107},
                {"ds": "2026-04-08", "category": "b", "score": 18, "price": 108},
                {"ds": "2026-04-09", "category": "a", "score": 19, "price": 109},
                {"ds": "2026-04-10", "category": "b", "score": 20, "price": 110},
                {"ds": "2026-04-11", "category": "a", "score": 21, "price": 111},
            ]
        ),
        encoding="utf-8",
    )

    out = pathlib.Path(data_display.render_dataset(str(p)))
    html = out.read_text(encoding="utf-8")

    assert "chart-presets" in html
    assert "chartPresets('line')" in html
    assert "chartPresets('bar')" in html
    assert "chartPresets('pivot')" in html
    assert "applyChartPreset(preset)" in html
    assert "Rows by ${this.fieldLabel(groups[0])}" in html


def test_render_dataset_includes_pivot_view(tmp_path):
    p = tmp_path / "rows.json"
    p.write_text(
        json.dumps(
            [
                {"ds": f"2026-04-{i + 1:02d}", "category": "a" if i % 2 == 0 else "b", "value": i + 1}
                for i in range(12)
            ]
        ),
        encoding="utf-8",
    )

    out = pathlib.Path(data_display.render_dataset(str(p), view="pivot"))
    payload = _extract_payload(out)
    ds = payload["datasets"][0]
    html = out.read_text(encoding="utf-8")

    assert ds["default_view"] == "pivot"
    assert "pivot" in ds["schema"]["eligible_views"]
    assert "Pivot" in html
    assert "pivotRows" in html
    assert "pivotGroupField" in html
    assert "pivotMeasureField" in html
    assert "pivot-chart" in html
    assert "_renderPivot" in html
    assert "visibleFields" in html
    assert "h-[40vh]" not in html
    assert 'style="height: 40vh"' in html
    assert "max-h-[calc(100vh-20rem)]" not in html
    assert 'style="max-height: calc(100vh - 20rem)"' in html
    assert "'4': 'pivot'" in html
    assert "'7': 'compare'" in html
    assert "'8': 'tree'" in html


def test_render_dataset_aggregates_use_full_dataset_when_embedding_is_capped(tmp_path, monkeypatch):
    monkeypatch.setattr(data_display, "_MAX_EMBEDDED_ROWS", 3)
    p = tmp_path / "rows.jsonl"
    p.write_text(
        "\n".join(
            json.dumps(
                {
                    "ts": f"2026-04-{(i % 3) + 1:02d}",
                    "segment": "shown" if i < 3 else "hidden",
                    "value": i + 1,
                }
            )
            for i in range(12)
        ),
        encoding="utf-8",
    )

    out = pathlib.Path(data_display.render_dataset(str(p)))
    payload = _extract_payload(out)
    ds = payload["datasets"][0]
    line_key = data_display._line_key("ts", "value", "segment")

    assert len(ds["data"]) == 3
    assert ds["schema"]["row_count"] == 12
    assert ds["meta"]["total_rows"] == 12
    assert ds["meta"]["embedded_rows"] == 3
    assert ds["meta"]["truncated"] is True
    assert ds["meta"]["max_embedded_rows"] == 3
    assert ds["meta"]["aggregate_scope"] == "full"
    assert ds["aggregates"]["kpis"]["value"]["count"] == 12
    assert ds["aggregates"]["kpis"]["value"]["sum"] == 78.0
    assert dict(ds["aggregates"]["bar"]["segment"]) == {"hidden": 9, "shown": 3}
    assert line_key in ds["aggregates"]["line"]


def test_render_dataset_multi_paths_emits_dataset_list(tmp_path):
    a = tmp_path / "alpha.json"
    a.write_text(json.dumps([{"x": 1}, {"x": 2}]), encoding="utf-8")
    b = tmp_path / "beta.csv"
    b.write_text("name,score\nfoo,10\nbar,20\n", encoding="utf-8")

    out_path = pathlib.Path(data_display.render_dataset([str(a), str(b)]))
    assert out_path.name == "data-explorer.html"
    payload = _extract_payload(out_path)

    assert payload["multi"] is True
    assert len(payload["datasets"]) == 2
    labels = [d["label"] for d in payload["datasets"]]
    assert labels == ["alpha", "beta"]
    ids = [d["id"] for d in payload["datasets"]]
    assert ids == ["alpha", "beta"]
    assert payload["active_id"] == "alpha"
    assert payload["datasets"][0]["meta"]["format"] == "json"
    assert payload["datasets"][1]["meta"]["format"] == "csv"
    assert "2 datasets" in payload["title"]


def test_render_dataset_multi_with_explicit_labels_and_views(tmp_path):
    a = tmp_path / "a.jsonl"
    a.write_text('{"ts":"2026-04-01","v":1}\n', encoding="utf-8")
    b = tmp_path / "b.jsonl"
    b.write_text('{"ts":"2026-04-01","v":2}\n', encoding="utf-8")

    out_path = pathlib.Path(
        data_display.render_dataset(
            [
                ("Listings", str(a)),
                {"label": "Insights", "path": str(b), "view": "table"},
            ],
            out=str(tmp_path / "explorer.html"),
            title="Custom Explorer",
        )
    )
    payload = _extract_payload(out_path)
    assert payload["title"] == "Custom Explorer"
    assert [d["label"] for d in payload["datasets"]] == ["Listings", "Insights"]
    assert [d["id"] for d in payload["datasets"]] == ["listings", "insights"]
    assert payload["datasets"][1]["default_view"] == "table"


def test_render_dataset_multi_sources_support_relationship_keys_and_compare_view(tmp_path):
    listings = tmp_path / "listings.json"
    listings.write_text(json.dumps([{"listing_id": "L1", "name": "A"}, {"listing_id": "L2", "name": "B"}]), encoding="utf-8")
    insights = tmp_path / "insights.json"
    insights.write_text(json.dumps([{"listing_id": "L1", "value": 12}, {"listing_id": "L1", "value": 14}]), encoding="utf-8")

    out_path = pathlib.Path(
        data_display.render_dataset(
            [
                {"label": "Listings", "path": str(listings), "key": "listing_id"},
                {"label": "Insights", "path": str(insights), "key": "listing_id"},
            ],
            view="compare",
        )
    )
    payload = _extract_payload(out_path)
    html = out_path.read_text(encoding="utf-8")

    assert [ds["key"] for ds in payload["datasets"]] == ["listing_id", "listing_id"]
    assert payload["datasets"][0]["default_view"] == "compare"
    assert "Compare" in html
    assert "compareRows" in html
    assert "comparableDatasets" in html
    assert "relatedLinks" in html
    assert "openRelated" in html
    assert "Source map" in html
    assert "source-graph" in html
    assert "source-graph-node" in html
    assert "source-graph-line" in html
    assert "relationshipEdges" in html
    assert "openRelationship(edge)" in html
    assert "_relationshipKey(a, b)" in html
    assert "field: ds.key" in html
    assert "this.q = link.key" not in html
    assert "this.filters = field ? { [field]: link.key } : {}" in html


def test_render_dataset_hiding_relationship_key_disables_compare_key(tmp_path):
    listings = tmp_path / "listings.json"
    listings.write_text(
        json.dumps(
            [
                {"listing_id": "L1", "name": "A"},
                {"listing_id": "L2", "name": "B"},
            ]
        ),
        encoding="utf-8",
    )
    insights = tmp_path / "insights.json"
    insights.write_text(
        json.dumps(
            [
                {"listing_id": "L1", "value": 12},
                {"listing_id": "L1", "value": 14},
            ]
        ),
        encoding="utf-8",
    )

    out_path = pathlib.Path(
        data_display.render_dataset(
            [
                {"label": "Listings", "path": str(listings), "key": "listing_id"},
                {"label": "Insights", "path": str(insights), "key": "listing_id"},
            ],
            view="compare",
            display={"hidden_fields": ["listing_id"]},
        )
    )
    payload = _extract_payload(out_path)

    assert [ds["key"] for ds in payload["datasets"]] == ["", ""]
    for ds in payload["datasets"]:
        assert "listing_id" not in {field["name"] for field in ds["schema"]["fields"]}
        assert all("listing_id" not in row for row in ds["data"])


def test_render_dataset_accepts_top_level_dict_spec(tmp_path):
    p = tmp_path / "rows.json"
    p.write_text(json.dumps([{"x": 1}]), encoding="utf-8")

    out_path = pathlib.Path(
        data_display.render_dataset({"label": 123, "path": str(p), "view": "table"})
    )
    payload = _extract_payload(out_path)
    ds = payload["datasets"][0]

    assert out_path.name == "rows.html"
    assert ds["label"] == "123"
    assert ds["id"] == "123"
    assert ds["default_view"] == "table"


def test_render_dataset_dedupes_label_collisions(tmp_path):
    a = tmp_path / "first" ; a.mkdir()
    b = tmp_path / "second" ; b.mkdir()
    p1 = a / "rows.json"
    p2 = b / "rows.json"
    p1.write_text(json.dumps([{"x": 1}]), encoding="utf-8")
    p2.write_text(json.dumps([{"x": 2}]), encoding="utf-8")

    out_path = pathlib.Path(data_display.render_dataset([str(p1), str(p2)]))
    payload = _extract_payload(out_path)
    ids = [d["id"] for d in payload["datasets"]]
    assert ids == ["rows", "rows_2"]


def test_render_dataset_missing_path_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        data_display.render_dataset(str(tmp_path / "does-not-exist.json"))


def test_render_dataset_empty_list_raises():
    with pytest.raises(ValueError):
        data_display.render_dataset([])


def test_render_dataset_multi_html_includes_switcher_markup(tmp_path):
    a = tmp_path / "a.json"
    a.write_text(json.dumps([{"x": 1}]), encoding="utf-8")
    b = tmp_path / "b.json"
    b.write_text(json.dumps([{"x": 2}]), encoding="utf-8")
    out_path = pathlib.Path(data_display.render_dataset([str(a), str(b)]))
    html = out_path.read_text(encoding="utf-8")
    assert "Sources" in html
    assert "prevDataset" in html
    assert "nextDataset" in html
    assert "setActive" in html


def test_render_dataset_sidebar_width_does_not_depend_on_missing_tailwind_class(tmp_path):
    p = tmp_path / "rows.json"
    p.write_text(json.dumps([{"x": 1}]), encoding="utf-8")
    out_path = pathlib.Path(data_display.render_dataset(str(p)))
    html = out_path.read_text(encoding="utf-8")

    assert "w-44" not in html
    assert "hasMultiple ? 'w-56' : 'w-44'" not in html
    assert ".app-shell { display: grid; grid-template-columns: 17rem minmax(0, 1fr); }" in html
    assert ".app-sidebar { border-right:" in html


def test_render_dataset_table_pages_all_embedded_rows_without_5000_cap(tmp_path):
    p = tmp_path / "rows.json"
    p.write_text(json.dumps([{"x": i} for i in range(10)]), encoding="utf-8")
    out_path = pathlib.Path(data_display.render_dataset(str(p)))
    html = out_path.read_text(encoding="utf-8")

    assert "Showing the first 5000" not in html
    assert "const cap = 5000" not in html
    assert "this.sortedRows.slice(start, start + this.pageSize)" in html
    assert "visibleStart" in html
    assert "page_size" in html
    assert '<option :value="1000">1000</option>' in html


def test_render_dataset_facet_markup_does_not_depend_on_missing_padding_class(tmp_path):
    p = tmp_path / "rows.json"
    p.write_text(json.dumps([{"category": "a"}, {"category": "b"}]), encoding="utf-8")
    out_path = pathlib.Path(data_display.render_dataset(str(p)))
    html = out_path.read_text(encoding="utf-8")

    assert "pt-4" not in html
    assert ".facet-panel { padding: .75rem .5rem 1rem;" in html


def test_render_dataset_escapes_script_close(tmp_path):
    p = tmp_path / "rows.json"
    p.write_text(json.dumps([{"text": "</script><img src=x onerror=alert(1)>"}]), encoding="utf-8")
    out = pathlib.Path(data_display.render_dataset(str(p)))
    html = out.read_text(encoding="utf-8")
    assert "<\\/script>" in html


def test_render_dataset_inlines_browser_runtime_assets(tmp_path):
    p = tmp_path / "rows.json"
    p.write_text(json.dumps([{"value": 1}]), encoding="utf-8")
    out = pathlib.Path(data_display.render_dataset(str(p)))
    html = out.read_text(encoding="utf-8")
    assert "cdn.tailwindcss.com" not in html
    assert "cdn.jsdelivr.net" not in html
    assert "<script src=" not in html
    assert "<style>" in html
    assert "tailwindcss v3.4.14" in html
    assert data_display._asset_text(data_display._ECHARTS_ASSET)[:80] in html
    assert data_display._asset_text(data_display._ALPINE_ASSET)[:80] in html
    assert "<script defer>" not in html
    assert html.index("function app()") < html.index(data_display._asset_text(data_display._ALPINE_ASSET)[:80])


def test_render_dataset_privacy_mode_disables_external_url_and_image_rendering(tmp_path):
    p = tmp_path / "rows.json"
    p.write_text(
        json.dumps(
            [
                {
                    "url": "https://example.com/page",
                    "image": "https://example.com/image.png",
                }
            ]
        ),
        encoding="utf-8",
    )

    out = pathlib.Path(data_display.render_dataset(str(p), privacy_mode=True))
    payload = _extract_payload(out)
    html = out.read_text(encoding="utf-8")
    ds = payload["datasets"][0]

    assert ds["display"]["privacy_mode"] is True
    assert ds["display"]["external_assets"] is False
    assert "privacyMode" in html
    assert "return !this.privacyMode && field" in html


@pytest.mark.skipif(
    os.environ.get("BROWSER_HARNESS_DATA_DISPLAY_BROWSER_SMOKE") != "1",
    reason="requires a configured browser-harness browser session",
)
def test_render_dataset_browser_smoke_table_profile_and_chart(tmp_path):
    p = tmp_path / "rows.json"
    p.write_text(
        json.dumps(
            [
                {
                    "ds": f"2026-04-{(i % 4) + 1:02d}",
                    "category": "a" if i % 2 == 0 else "b",
                    "value": i + 1,
                }
                for i in range(12)
            ]
        ),
        encoding="utf-8",
    )
    out = pathlib.Path(data_display.render_dataset(str(p), privacy_mode=True))
    script = f"""python3 run.py <<'PY'
from pathlib import Path
new_tab(Path({json.dumps(str(out))}).as_uri())
wait_for_load()
wait(1)
result = js(\"\"\"(() => {{
  const payload = JSON.parse(document.querySelector('#payload-json').textContent);
  const buttons = [...document.querySelectorAll('button')].map(b => b.textContent);
  return {{
    rows: payload.datasets[0].data.length,
    hasProfile: buttons.some(t => t.includes('Profile')),
    hasPivot: buttons.some(t => t.includes('Pivot')),
    hasSearch: !!document.querySelector('#search-box')
  }};
}})()\"\"\")
print(result)
PY"""
    output = subprocess.check_output(script, shell=True, text=True)
    assert "'rows': 12" in output or '"rows": 12' in output
    assert "True" in output or "true" in output
