import importlib.util
import json
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


def test_list_active_browsers_tolerates_malformed_total_items(monkeypatch):
    module = load_cleanup_module()
    calls = []
    pages = iter([
        {
            "items": [
                {"id": "active", "startedAt": "2026-05-07T00:00:00Z"},
            ],
            "totalItems": "not-a-count",
        },
        {"items": []},
    ])

    def fake_call(method, path):
        calls.append((method, path))
        return next(pages)

    monkeypatch.setattr(module, "_call", fake_call)

    assert module.list_active_browsers() == [{"id": "active", "startedAt": "2026-05-07T00:00:00Z"}]
    assert calls[-1] == ("GET", "/browsers?pageSize=100&pageNumber=2")


def test_list_active_browsers_rejects_boolean_total_items(monkeypatch):
    module = load_cleanup_module()
    calls = []
    pages = iter([
        {
            "items": [
                {"id": "active", "startedAt": "2026-05-07T00:00:00Z"},
            ],
            "totalItems": True,
        },
        {"items": []},
    ])

    def fake_call(method, path):
        calls.append((method, path))
        return next(pages)

    monkeypatch.setattr(module, "_call", fake_call)

    assert module.list_active_browsers() == [{"id": "active", "startedAt": "2026-05-07T00:00:00Z"}]
    assert calls[-1] == ("GET", "/browsers?pageSize=100&pageNumber=2")


def test_main_skips_active_rows_with_malformed_runtime_fields(monkeypatch, capsys):
    module = load_cleanup_module()
    monkeypatch.setattr(module.sys, "argv", ["cleanup-zombies.py", "--older-than", "0", "--dry-run", "--json"])
    monkeypatch.setattr(module, "stop_browser", lambda browser_id: {})
    monkeypatch.setattr(module, "list_active_browsers", lambda: [
        {"id": "bad-time", "startedAt": "not-a-date"},
        {
            "id": "bad-cost",
            "startedAt": "2026-05-07T00:00:00Z",
            "browserCost": "not-a-cost",
            "proxyCost": "also-bad",
            "proxyUsedMb": "bad-mb",
        },
    ])

    assert module.main() == 0

    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert rows[0]["id"] == "bad-time"
    assert rows[0]["action"] == "skipped_malformed"
    assert "startedAt" in rows[0]["error"]
    assert rows[1]["id"] == "bad-cost"
    assert rows[1]["browser_cost"] == 0.0
    assert rows[1]["proxy_cost"] == 0.0
    assert rows[1]["proxy_used_mb"] == 0.0
    assert rows[1]["action"] == "would_stop"


def test_main_tolerates_malformed_stop_response(monkeypatch, capsys):
    module = load_cleanup_module()
    monkeypatch.setattr(module.sys, "argv", ["cleanup-zombies.py", "--older-than", "0", "--json"])
    monkeypatch.setattr(module, "list_active_browsers", lambda: [
        {
            "id": "zombie",
            "startedAt": "2026-05-07T00:00:00Z",
        },
    ])
    monkeypatch.setattr(module, "stop_browser", lambda browser_id: ["not", "an", "object"])

    assert module.main() == 0

    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert rows == [{
        "id": "zombie",
        "started_at": "2026-05-07T00:00:00Z",
        "age_minutes": rows[0]["age_minutes"],
        "browser_cost": 0.0,
        "proxy_cost": 0.0,
        "proxy_used_mb": 0.0,
        "is_zombie": True,
        "action": "stopped",
        "final_browser_cost": 0.0,
        "final_proxy_cost": 0.0,
    }]


@pytest.mark.parametrize("listing, message", [
    (["not", "an", "object"], "expected object, got list"),
    ({"items": "not-a-list"}, "items.*must be a list"),
])
def test_list_active_browsers_rejects_malformed_listing_envelope(monkeypatch, listing, message):
    module = load_cleanup_module()
    monkeypatch.setattr(module, "_call", lambda method, path: listing)

    with pytest.raises(RuntimeError, match=message):
        module.list_active_browsers()
