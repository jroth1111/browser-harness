import json
import pathlib
import re

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


def test_load_records_jsonl_skips_bad_lines(tmp_path):
    p = tmp_path / "rows.jsonl"
    p.write_text('{"a":1}\n\nnot-json\n2\n{"b":"x"}\n', encoding="utf-8")
    rows, meta = data_display._load_records(p)
    assert rows == [{"a": 1}, {"value": 2}, {"b": "x"}]
    assert meta["format"] == "jsonl"


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
    assert "kpis" in schema["eligible_views"]
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


def test_render_dataset_smoke_and_payload_keys(tmp_path):
    p = tmp_path / "rows.jsonl"
    p.write_text('{"ts":"2026-04-01","value":1}\n{"ts":"2026-04-02","value":2}\n', encoding="utf-8")
    out = pathlib.Path(data_display.render_dataset(str(p)))
    assert out.exists()
    assert out.name == "rows.html"
    html = out.read_text(encoding="utf-8")
    m = re.search(
        r'<script type="application/json" id="payload-json">(.*?)</script>',
        html,
        flags=re.S,
    )
    assert m is not None
    payload = json.loads(m.group(1).replace("<\\/", "</"))
    assert set(payload.keys()) == {"data", "schema", "aggregates", "meta"}


def test_render_dataset_escapes_script_close(tmp_path):
    p = tmp_path / "rows.json"
    p.write_text(json.dumps([{"text": "</script><img src=x onerror=alert(1)>"}]), encoding="utf-8")
    out = pathlib.Path(data_display.render_dataset(str(p)))
    html = out.read_text(encoding="utf-8")
    assert "<\\/script>" in html
