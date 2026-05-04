import json
from pathlib import Path


def test_external_pattern_adaptations_record_sources_adaptations_and_rejections():
    doc = Path("docs/external-pattern-adaptations.md").read_text(encoding="utf-8")

    for repo in (
        "https://github.com/cbonoz/tinderscrapy",
        "https://github.com/EatMyA/tinder-scraper",
        "https://github.com/frederikme/TinderBotz",
    ):
        assert repo in doc

    for accepted in (
        "Trace receipt",
        "Field contract",
        "Stale-pane guard",
        "Profile identity lock",
        "Halt detection",
        "Saturation and dedupe ledger",
        "Selector-drift fixture",
    ):
        assert accepted in doc

    for rejected in (
        "private API token reuse",
        "stealth browser defaults",
        "proxy rotation",
        "CAPTCHA solving",
        "raw browser profile",
        "unbounded rapid traversal",
    ):
        assert rejected in doc


def test_robustness_map_links_borrowed_patterns_to_evidence_doc():
    data = json.loads(Path("docs/robustness-surface-map.json").read_text(encoding="utf-8"))
    borrowed = data["borrowed_patterns"]

    assert borrowed
    for pattern in borrowed:
        assert pattern["evidence"] == "docs/external-pattern-adaptations.md"
        assert pattern["adapt"]
        assert pattern["reject"]
