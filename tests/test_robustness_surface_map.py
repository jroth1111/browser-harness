import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MAP_PATH = ROOT / "docs" / "robustness-surface-map.json"

REQUIRED_SURFACES = {
    "cli_entrypoint",
    "daemon_socket_lifecycle",
    "cdp_transport",
    "navigation_readiness",
    "block_and_auth_detection",
    "session_continuity",
    "fetch_source_selection",
    "network_capture",
    "crawl_safety",
    "extraction_contracts",
    "domain_skill_loading",
    "report_rendering",
    "packaging_release",
    "quality_gates",
}

REQUIRED_REACHABILITY = {
    "entry",
    "validation",
    "routing",
    "execution",
    "state_effect",
    "output",
    "lifecycle",
    "observability",
    "regression",
}


def load_map():
    return json.loads(MAP_PATH.read_text(encoding="utf-8"))


def test_robustness_surface_map_exists_and_lists_required_surfaces():
    data = load_map()

    assert data["schema_version"] == 1
    assert data["project"] == "browser-harness"
    assert set(data["surface_ids"]) == REQUIRED_SURFACES

    surfaces = data["surfaces"]
    assert {surface["id"] for surface in surfaces} == REQUIRED_SURFACES
    assert len(surfaces) == len(REQUIRED_SURFACES)


def test_robustness_surface_map_preserves_thin_harness_non_goals():
    data = load_map()
    non_goals = set(data["non_goals"])

    assert "no manager layer" in non_goals
    assert "no retries framework" in non_goals
    assert "no session manager" in non_goals
    assert "no daemon supervisor" in non_goals
    assert "no bot-detection circumvention" in non_goals
    assert "no committed private browser state" in non_goals


def test_robustness_surface_map_file_references_exist():
    for surface in load_map()["surfaces"]:
        assert surface["files"], surface["id"]
        for relpath in surface["files"]:
            assert (ROOT / relpath).exists(), (surface["id"], relpath)


def test_robustness_surface_map_has_positive_and_negative_probes():
    for surface in load_map()["surfaces"]:
        assert surface["contracts"], surface["id"]
        assert surface["risks"], surface["id"]
        assert surface["positive_probe"].strip(), surface["id"]
        assert surface["negative_probe"].strip(), surface["id"]


def test_robustness_surface_map_covers_reachability_ladder():
    data = load_map()
    assert set(data["required_reachability_links"]) == REQUIRED_REACHABILITY

    for surface in data["surfaces"]:
        reachability = surface["reachability"]
        assert set(reachability) == REQUIRED_REACHABILITY, surface["id"]
        for link, evidence in reachability.items():
            assert evidence.strip(), (surface["id"], link)


def test_borrowed_patterns_record_adapt_and_reject_boundaries():
    patterns = load_map()["borrowed_patterns"]
    assert patterns
    for pattern in patterns:
        assert pattern["source_family"].strip()
        assert pattern["adapt"].strip()
        assert pattern["reject"].strip()
