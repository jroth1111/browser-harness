import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent


def load_script_module(name, relative_path):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class Args:
    query = "RTX 4090"
    sort = "volume"
    synonyms = None
    modifiers = None
    specs = None
    products = None
    spec_terms = None
    urls_only = False
    layers = 3


def test_generate_exits_when_child_generator_fails(monkeypatch):
    search = load_script_module("aliexpress_search", "domain-skills/aliexpress/scripts/search.py")

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 7, stdout="", stderr="generator exploded")

    monkeypatch.setattr(search.subprocess, "run", fake_run)

    with pytest.raises(SystemExit) as exc:
        search.cmd_generate(Args())

    assert "exit 7" in str(exc.value)
    assert "generator exploded" in str(exc.value)


def test_plan_exits_when_child_generator_fails(monkeypatch):
    search = load_script_module("aliexpress_search", "domain-skills/aliexpress/scripts/search.py")

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 9, stdout="", stderr="bad plan input")

    monkeypatch.setattr(search.subprocess, "run", fake_run)

    with pytest.raises(SystemExit) as exc:
        search.cmd_plan(Args())

    assert "exit 9" in str(exc.value)
    assert "bad plan input" in str(exc.value)


def test_aliexpress_merge_payload_requires_product_object_array():
    search = load_script_module("aliexpress_search_payloads", "domain-skills/aliexpress/scripts/search.py")

    rows = [{"product_id": "1", "title": "Mini PC"}]
    assert search.normalize_merge_payload(rows) == rows

    with pytest.raises(ValueError, match="must be a JSON array"):
        search.normalize_merge_payload({"products": rows})
    with pytest.raises(ValueError, match="item 1 must be an object"):
        search.normalize_merge_payload([{"product_id": "1"}, "bad-row"])


def test_ebay_urls_exits_when_child_generator_fails(monkeypatch):
    search = load_script_module("ebay_search", "domain-skills/ebay/scripts/search.py")

    class EbayArgs:
        chip = "RTX 4090"
        pages = 1
        base_terms = None
        products = None
        form_factors = None
        spec_terms = None
        location = None

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 11, stdout="", stderr="ebay generator exploded")

    monkeypatch.setattr(search.subprocess, "run", fake_run)

    with pytest.raises(SystemExit) as exc:
        search.cmd_urls(EbayArgs())

    assert "exit 11" in str(exc.value)
    assert "ebay generator exploded" in str(exc.value)


def test_aliexpress_classifier_accepts_json_title_strings():
    script = ROOT / "domain-skills/aliexpress/scripts/classify_product_line.py"

    result = subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(["GMKtec EVO-X2 AI Mini PC AMD Ryzen AI Max+ 395 128GB"]),
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload[0]["title"].startswith("GMKtec EVO-X2")
    assert payload[0]["product_line"] == "GMKtec EVO-X2"


def test_aliexpress_classifier_tolerates_non_string_json_titles():
    script = ROOT / "domain-skills/aliexpress/scripts/classify_product_line.py"

    result = subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps([{"title": 12345}]),
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload == [
        {
            "title": "12345",
            "product_line": "Unknown",
            "form_factor": "unknown",
        }
    ]


def test_ebay_classifier_accepts_json_title_strings():
    script = ROOT / "domain-skills/ebay/scripts/classify_product_line.py"

    result = subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(["ASUS ROG Flow Z13 GZ302EA 64GB"]),
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload[0]["title"].startswith("ASUS ROG Flow Z13")
    assert payload[0]["product_line"] == "ASUS ROG Flow Z13"


def test_ebay_classifier_tolerates_non_string_json_titles():
    script = ROOT / "domain-skills/ebay/scripts/classify_product_line.py"

    result = subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps([{"title": 12345}]),
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload == [
        {
            "title": "12345",
            "product_line": "Unknown",
            "form_factor": "unknown",
            "ram_gb": None,
            "storage_tb": None,
            "condition": None,
        }
    ]
