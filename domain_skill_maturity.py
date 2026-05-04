"""Domain skill maturity classification."""

from pathlib import Path


TIERS = ["documented", "scripted", "fixture-tested", "live-smoked", "packaged-safe"]
PRIVATE_DIRS = {".private-data", ".session-store", "outputs", "auth-state", "session-state", "browser-profile", "chrome-profile"}


def evaluate_domain_skill(path):
    """Return maturity tiers and missing evidence for a domain skill folder."""
    root = Path(path)
    evidence = {}
    missing = []

    docs = [p for p in (root / "overview.md", root / "README.md") if p.exists()]
    evidence["documented"] = bool(docs)
    if not evidence["documented"]:
        missing.append("documented: overview.md or README.md")

    scripts = root / "scripts"
    evidence["scripted"] = scripts.is_dir() and any(scripts.glob("*.py")) and (scripts / "README.md").exists()
    if not evidence["scripted"]:
        missing.append("scripted: scripts/*.py plus scripts/README.md")

    fixtures = root / "fixtures"
    tests = root / "tests"
    evidence["fixture-tested"] = fixtures.is_dir() and any(fixtures.rglob("*")) and (
        tests.is_dir() and any(tests.glob("test*.py"))
    )
    if not evidence["fixture-tested"]:
        missing.append("fixture-tested: fixtures plus domain tests/test*.py")

    receipts = root / "receipts"
    smoke_scripts = list(scripts.glob("*smoke*.py")) if scripts.is_dir() else []
    evidence["live-smoked"] = bool(smoke_scripts) and receipts.is_dir() and any(receipts.glob("*.json"))
    if not evidence["live-smoked"]:
        missing.append("live-smoked: smoke script plus redacted receipts/*.json")

    private_present = [d.name for d in root.iterdir() if d.is_dir() and d.name in PRIVATE_DIRS] if root.exists() else []
    surface_map = root / "surface-map.json"
    evidence["packaged-safe"] = surface_map.exists() and not private_present
    if not evidence["packaged-safe"]:
        missing.append("packaged-safe: surface-map.json and no private/generated dirs in package path")

    achieved = [tier for tier in TIERS if evidence[tier]]
    return {
        "domain": root.name,
        "tiers": achieved,
        "highest": achieved[-1] if achieved else None,
        "evidence": evidence,
        "missing": missing,
    }
