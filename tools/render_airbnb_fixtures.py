#!/usr/bin/env python3
"""Render canonical Airbnb fixtures and refresh existing local HTML reports."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from browser_harness.data_display import render_dataset

AIRBNB_PRIVATE = ROOT / "domain-skills" / "airbnb" / ".private-data"
LISTING_DIR = AIRBNB_PRIVATE / "listing-collections"
INSIGHTS_DIR = AIRBNB_PRIVATE / "insights-collections"

CANONICAL_SOURCES = [
    LISTING_DIR / "airbnb-live-listings-20260427T080658Z.json",
    INSIGHTS_DIR / "airbnb-insights-20260427T084255Z.json",
    INSIGHTS_DIR / "airbnb-insights-20260427T094855Z-daily-chart-raw.jsonl",
]


def _source_for_html(html_path: Path) -> Path | None:
    stem = html_path.name[:-5] if html_path.name.endswith(".html") else html_path.name
    base = html_path.with_name(stem)
    for ext in (".json", ".jsonl", ".csv"):
        candidate = base.with_suffix(ext)
        if candidate.exists():
            return candidate
    if base.exists():
        return base
    return None


def _render_source(src: Path, out: Path | None = None) -> Path:
    rendered = render_dataset(str(src), out=str(out) if out else None)
    return Path(rendered).resolve()


def main() -> int:
    rendered_paths: list[Path] = []
    seen: set[Path] = set()
    combined_specs: list[tuple[str, Path]] = []

    for src in CANONICAL_SOURCES:
        if not src.exists():
            print(f"[warn] missing canonical source: {src}")
            continue
        out = _render_source(src)
        if out not in seen:
            rendered_paths.append(out)
            seen.add(out)
        combined_specs.append((src.stem, src))

    for directory in (LISTING_DIR, INSIGHTS_DIR):
        if not directory.exists():
            continue
        for html_path in sorted(directory.glob("*.html")):
            src = _source_for_html(html_path)
            if src is None:
                print(f"[warn] skipped (no sibling source): {html_path}")
                continue
            out = _render_source(src, out=html_path)
            if out not in seen:
                rendered_paths.append(out)
                seen.add(out)

    if len(combined_specs) > 1:
        combined_out = AIRBNB_PRIVATE / "data-explorer.html"
        combined = render_dataset(
            [(label, str(path)) for label, path in combined_specs],
            out=str(combined_out),
            title=f"Airbnb canonical artifacts · {len(combined_specs)} sources",
        )
        rendered_paths.append(Path(combined).resolve())

    print("\nRendered HTML reports:")
    for path in rendered_paths:
        print(f"- {path}")

    print("\nManual QA checklist:")
    print("- DevTools console clean (no Tailwind Play-CDN warning expected).")
    print("- At least one chart-eligible field surfaced; line/bar charts render.")
    print("- Table sort + search work; sort and page round-trip in URL hash.")
    print("- Row drawer opens; shows row N of M; JSON tree expands.")
    print("- Keyboard 1-5, /, j/k, [/], Esc.")
    print("- Light + dark mode both render legibly; toggle persists on reload.")
    print("- Combined explorer: sidebar Sources list switches active dataset; per-source view + search persist across switches.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
