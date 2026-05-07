import importlib.util
from pathlib import Path


def load_module():
    path = Path("domain-skills/localmaxxing/hardware-scorer.py")
    spec = importlib.util.spec_from_file_location("localmaxxing_hardware_scorer", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_hardware_scorer_tolerates_malformed_nested_rows():
    module = load_module()
    rows = [
        {
            "hardware": "not-an-object",
            "model": "not-an-object",
            "engine": "not-an-object",
            "tokSOut": 12.5,
            "ttftMs": 100,
            "peakVramGb": 6,
        },
        {
            "hardware": {"hwClass": "DISCRETE_GPU", "gpuName": "RTX 3060", "gpuCount": 1, "vramGb": 12},
            "model": {"family": "qwen3", "hfId": "Qwen/Qwen3-8B", "params": 8},
            "engine": "not-an-object",
            "tokSOut": 30,
            "ttftMs": 80,
            "peakVramGb": 8,
        },
    ]

    ranked = module.score_hardware(rows)
    assert len(ranked) == 2
    assert "qwen3" in module.list_models(rows)
    model_ranked, matched = module.score_model_fit(rows, "qwen3")
    assert len(model_ranked) == 1
    assert matched == [rows[1]]
