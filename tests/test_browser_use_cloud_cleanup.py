import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "domain-skills" / "browser-use-cloud" / "cleanup-zombies.py"


def load_cleanup_module():
    spec = importlib.util.spec_from_file_location("browser_use_cleanup_zombies", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_list_active_browsers_skips_malformed_rows(monkeypatch):
    module = load_cleanup_module()
    pages = iter([
        {
            "items": [
                ["not", "an", "object"],
                {"id": "missing-start"},
                {"startedAt": "2026-05-07T00:00:00Z"},
                {"id": "finished", "startedAt": "2026-05-07T00:00:00Z", "finishedAt": "2026-05-07T00:10:00Z"},
                {"id": "active", "startedAt": "2026-05-07T00:00:00Z"},
            ],
            "totalItems": 5,
        },
        {"items": [], "totalItems": 5},
    ])
    monkeypatch.setattr(module, "_call", lambda method, path: next(pages))

    assert module.list_active_browsers() == [{"id": "active", "startedAt": "2026-05-07T00:00:00Z"}]


@pytest.mark.parametrize("listing, message", [
    (["not", "an", "object"], "expected object, got list"),
    ({"items": "not-a-list"}, "items.*must be a list"),
])
def test_list_active_browsers_rejects_malformed_listing_envelope(monkeypatch, listing, message):
    module = load_cleanup_module()
    monkeypatch.setattr(module, "_call", lambda method, path: listing)

    with pytest.raises(RuntimeError, match=message):
        module.list_active_browsers()
