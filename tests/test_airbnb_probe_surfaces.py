import importlib.util
from pathlib import Path


def load_module():
    path = Path("domain-skills/airbnb/scripts/probe_surfaces.py")
    spec = importlib.util.spec_from_file_location("airbnb_probe_surfaces", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_discover_hashes_for_page_tolerates_malformed_browser_context(monkeypatch):
    module = load_module()
    monkeypatch.setattr(module, "js", lambda script: "not-a-context", raising=False)
    monkeypatch.setattr(module, "http_get", lambda url: "", raising=False)
    monkeypatch.setattr(module._surfaces, "get_surface_spec", lambda surface_id: {"operations": ["ChartQuery"]})
    captured = {}

    def fake_discover(fetcher, operations, seed_texts, seed_urls, max_fetches):
        captured["operations"] = operations
        captured["seed_texts"] = seed_texts
        captured["seed_urls"] = seed_urls
        return {"hashes": {}, "sources": {}, "visited_count": 0, "remaining_queue_count": 0}

    monkeypatch.setattr(module._operation_hashes, "discover_operation_hashes", fake_discover)

    result = module.discover_hashes_for_page("host_reviews")

    assert result["hashes"] == {}
    assert captured == {
        "operations": ("ChartQuery",),
        "seed_texts": [""],
        "seed_urls": [],
    }
