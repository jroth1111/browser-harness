import importlib.util
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


def test_ebay_verified_and_coverage_paths_handle_missing_or_uppercase_suffix(tmp_path):
    ebay = load_module("ebay_search_paths", "domain-skills/ebay/scripts/search.py")

    assert Path(ebay.derive_output_path(str(tmp_path / "results"), ".csv", "-verified.csv")) == (
        tmp_path / "results-verified.csv"
    )
    assert Path(ebay.derive_output_path(str(tmp_path / "RESULTS.CSV"), ".csv", "-coverage.json")) == (
        tmp_path / "RESULTS-coverage.json"
    )


def test_g2g_sidecar_paths_never_equal_source_without_csv_suffix(tmp_path):
    g2g = load_module("g2g_search_paths", "domain-skills/g2g/scripts/search.py")
    input_path = tmp_path / "results"

    seller_path = Path(g2g.derive_output_path(str(input_path), ".csv", "-seller.csv"))
    coverage_path = Path(g2g.derive_output_path(str(input_path), ".csv", "-coverage.json"))

    assert seller_path == tmp_path / "results-seller.csv"
    assert coverage_path == tmp_path / "results-coverage.json"
    assert seller_path != input_path
    assert coverage_path != input_path
