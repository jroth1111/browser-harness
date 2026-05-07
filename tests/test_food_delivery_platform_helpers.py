import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "domain-skills" / "food-delivery" / "scripts" / "lib"


def load_module(name):
    spec = importlib.util.spec_from_file_location(f"food_delivery_{name}", LIB / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_load_api_discovery_rejects_malformed_json_shapes(tmp_path, monkeypatch):
    for name in ("doordash", "ubereats"):
        module = load_module(name)
        discovery = tmp_path / f"{name}.json"
        discovery.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")
        monkeypatch.setattr(module, "API_DISCOVERY_PATH", discovery)

        assert module.load_api_discovery() is None
