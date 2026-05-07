import importlib.util
import subprocess
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
