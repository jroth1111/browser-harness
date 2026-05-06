import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SHARED_SCHEMA = ROOT / "agent-workspace/domain-skills" / "surface-map.schema.json"
ALLOWED_PATH_TYPES = {"api", "browser", "hybrid", "static", "local"}
FILTER_STATUSES = {"available", "default", "disabled", "selected"}
REQUIRED_TOP_LEVEL = {
    "schema_version",
    "domain",
    "path_types",
    "forbidden",
    "execution_policy",
    "primitives",
    "fallback_nodes",
    "fallback_dags",
    "verification_probes",
}
REQUIRED_POLICY = {"stop_on", "fallback_on", "never_fallback_to", "receipt_required"}
REQUIRED_PRIMITIVE = {"id", "path_type", "primary", "fallback_chain", "inputs", "outputs", "evidence"}
REQUIRED_RECEIPTS = {"primitive_id", "path_type", "fallback_attempts"}


def surface_maps():
    return sorted((ROOT / "agent-workspace/domain-skills").glob("*/surface-map.json"))


def helpers_defined():
    tree = ast.parse((ROOT / "helpers.py").read_text(encoding="utf-8"))
    return {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_shared_surface_map_schema_exists_and_matches_contract():
    schema = load_json(SHARED_SCHEMA)
    assert set(schema["required"]) == REQUIRED_TOP_LEVEL
    assert set(schema["properties"]["path_types"]["items"]["enum"]) == ALLOWED_PATH_TYPES
    assert set(schema["properties"]["execution_policy"]["required"]) == REQUIRED_POLICY
    assert set(schema["properties"]["primitives"]["items"]["required"]) == REQUIRED_PRIMITIVE
    probes = schema["properties"]["verification_probes"]
    assert probes["type"] == "object"
    assert set(probes["additionalProperties"]["required"]) == {"positive", "negative"}


def test_domain_surface_maps_have_no_dangling_fallback_references():
    for path in surface_maps():
        data = load_json(path)
        primitive_ids = {primitive["id"] for primitive in data.get("primitives", [])}
        fallback_ids = {node["id"] for node in data.get("fallback_nodes", [])}
        known = primitive_ids | fallback_ids
        assert known, path
        for primitive in data.get("primitives", []):
            for fallback_id in primitive.get("fallback_chain", []):
                assert fallback_id in known, (path, primitive["id"], fallback_id)
        for name, chain in data.get("fallback_dags", {}).items():
            for fallback_id in chain:
                assert fallback_id in known, (path, name, fallback_id)


def test_domain_surface_maps_have_minimum_process_contract():
    for path in surface_maps():
        data = load_json(path)
        assert REQUIRED_TOP_LEVEL <= set(data), path
        assert set(data["path_types"]) <= ALLOWED_PATH_TYPES, path
        assert data["forbidden"], path
        policy = data.get("execution_policy") or {}
        assert REQUIRED_POLICY <= set(policy), path
        assert REQUIRED_RECEIPTS <= set(policy["receipt_required"]), path
        assert policy["stop_on"], path
        assert policy["fallback_on"], path
        assert policy["never_fallback_to"], path
        assert isinstance(data["verification_probes"], dict), path
        for name, probes in data["verification_probes"].items():
            assert probes.get("positive"), (path, name)
            assert probes.get("negative"), (path, name)


def test_domain_surface_map_primitives_are_unique_and_typed():
    for path in surface_maps():
        data = load_json(path)
        ids = [primitive["id"] for primitive in data["primitives"]]
        assert len(ids) == len(set(ids)), path
        for primitive in data["primitives"]:
            assert REQUIRED_PRIMITIVE <= set(primitive), (path, primitive)
            assert primitive["path_type"] in data["path_types"], (path, primitive["id"])
            assert primitive["primary"], (path, primitive["id"])
            assert primitive["inputs"], (path, primitive["id"])
            assert primitive["outputs"], (path, primitive["id"])
            assert primitive["evidence"], (path, primitive["id"])


def test_domain_surface_map_declared_browser_helpers_exist():
    defined = helpers_defined()
    for path in surface_maps():
        data = load_json(path)
        for helper in data.get("browser_harness_primitives", []):
            assert helper["name"] in defined, (path, helper["name"])
            assert helper["path_type"] in data["path_types"], (path, helper["name"])
            assert helper["use"], (path, helper["name"])


def test_domain_surface_map_optional_search_filters_are_complete():
    for path in surface_maps():
        data = load_json(path)
        search = data.get("search")
        if not search:
            continue
        for group in search.get("filter_groups", []):
            assert group.get("group"), path
            assert group.get("filters"), (path, group.get("group"))
            for item in group["filters"]:
                assert item.get("label"), (path, group["group"], item)
                assert "token" in item, (path, group["group"], item)
                assert item.get("status") in FILTER_STATUSES, (path, group["group"], item)
