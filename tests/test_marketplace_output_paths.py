import csv
import importlib.util
import sys
from types import SimpleNamespace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, relative_path):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_z2u_default_csv_path_never_equals_input_without_json_suffix(tmp_path):
    z2u = load_module("z2u_search_paths", "domain-skills/z2u/scripts/search.py")
    input_path = tmp_path / "dump"

    output_path = Path(z2u.derive_output_path(str(input_path), ".json", ".csv"))

    assert output_path == tmp_path / "dump.csv"
    assert output_path != input_path


def test_z2u_product_payload_rejects_unsupported_json_shapes():
    z2u = load_module("z2u_search_payloads", "domain-skills/z2u/scripts/search.py")

    for payload in ("not a payload", {"products": {"title": "not a list"}}, ["not a product"]):
        try:
            z2u.normalize_product_payload(payload)
        except ValueError as exc:
            assert "input JSON" in str(exc)
        else:
            raise AssertionError(f"payload should have been rejected: {payload!r}")


def test_z2u_product_payload_accepts_list_and_wrapped_products():
    z2u = load_module("z2u_search_valid_payloads", "domain-skills/z2u/scripts/search.py")

    rows, coverage = z2u.normalize_product_payload([{"title": "A"}])
    assert rows == [{"title": "A"}]
    assert coverage is None

    rows, coverage = z2u.normalize_product_payload({"products": [{"title": "B"}], "coverage": {"ok": True}})
    assert rows == [{"title": "B"}]
    assert coverage == {"ok": True}


def test_ebay_verified_and_coverage_paths_handle_missing_or_uppercase_suffix(tmp_path):
    ebay = load_module("ebay_search_paths", "domain-skills/ebay/scripts/search.py")

    assert Path(ebay.derive_output_path(str(tmp_path / "results"), ".csv", "-verified.csv")) == (
        tmp_path / "results-verified.csv"
    )
    assert Path(ebay.derive_output_path(str(tmp_path / "RESULTS.CSV"), ".csv", "-coverage.json")) == (
        tmp_path / "RESULTS-coverage.json"
    )


def test_ebay_verify_empty_fieldnames_keep_input_and_trust_columns():
    ebay = load_module("ebay_search_fields", "domain-skills/ebay/scripts/search.py")

    assert ebay.append_missing_fields(["listing_id", "title", "seller_name"], ["seller_name", "trust_flag"]) == [
        "listing_id",
        "title",
        "seller_name",
        "trust_flag",
    ]


def test_ebay_verify_command_writes_header_for_empty_input(tmp_path, monkeypatch):
    ebay = load_module("ebay_search_verify_empty", "domain-skills/ebay/scripts/search.py")
    monkeypatch.setitem(sys.modules, "curl_cffi", SimpleNamespace(requests=SimpleNamespace(get=None)))
    monkeypatch.setattr(ebay, "Session", lambda: SimpleNamespace(cookies={}))
    input_csv = tmp_path / "results"
    output_csv = tmp_path / "results-verified.csv"
    with input_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["listing_id", "title"])
        writer.writeheader()

    ebay.cmd_verify(SimpleNamespace(input=str(input_csv), output=None))

    with output_csv.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        assert list(reader) == [["listing_id", "title", "seller_name", "feedback_pct", "feedback_count", "trust_flag"]]


def test_g2g_sidecar_paths_never_equal_source_without_csv_suffix(tmp_path):
    g2g = load_module("g2g_search_paths", "domain-skills/g2g/scripts/search.py")
    input_path = tmp_path / "results"

    seller_path = Path(g2g.derive_output_path(str(input_path), ".csv", "-seller.csv"))
    coverage_path = Path(g2g.derive_output_path(str(input_path), ".csv", "-coverage.json"))

    assert seller_path == tmp_path / "results-seller.csv"
    assert coverage_path == tmp_path / "results-coverage.json"
    assert seller_path != input_path
    assert coverage_path != input_path
