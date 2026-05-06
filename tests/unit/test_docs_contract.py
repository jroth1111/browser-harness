from pathlib import Path


def _bullet_block(path, start_heading, stop_heading):
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == start_heading)
    stop = (
        next(i for i in range(start + 1, len(lines)) if lines[i].strip() == stop_heading)
        if stop_heading
        else len(lines)
    )
    return [
        item
        for line in lines[start:stop]
        if line.strip().startswith("- ")
        for item in [line.strip()[2:].strip("`")]
        if item.endswith(".md")
    ]


def test_skill_interaction_inventory_matches_actual_files():
    actual = sorted(p.name for p in Path("interaction-skills").glob("*.md") if p.name != "README.md")
    listed = _bullet_block("SKILL.md", "## Interaction skills", "## What actually works")

    assert listed == actual


def test_interaction_readme_complete_inventory_matches_actual_files():
    actual = sorted(p.name for p in Path("interaction-skills").glob("*.md") if p.name != "README.md")
    listed = _bullet_block("interaction-skills/README.md", "## Complete File Inventory", "")

    assert listed == actual
