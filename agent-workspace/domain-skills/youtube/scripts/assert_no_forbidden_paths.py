#!/usr/bin/env python3
"""Guard committed YouTube domain artifacts against unsafe path leakage."""
from __future__ import annotations

import argparse
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKIP_NAMES = {"assert_no_forbidden_paths.py"}
SCAN_SUFFIXES = {".md", ".json", ".py"}

FORBIDDEN_PATTERNS = [
    ("official_data_api_endpoint", re.compile(r"youtube\.googleapis\.com/youtube/v3", re.I)),
    ("api_key_env", re.compile(r"\b(?:YOUTUBE_API_KEY|GOOGLE_API_KEY)\b")),
    ("oauth_secret_material", re.compile(r"\b(?:access_token|refresh_token|client_secret|oauth_token)\b", re.I)),
    ("browser_cookie_import", re.compile(r"--cookies-from-browser")),
    ("raw_playback_url", re.compile(r"https?://[^\"'\s]+googlevideo\.com[^\"'\s]*", re.I)),
    ("raw_visitor_data", re.compile(r'"visitorData"\s*:\s*"(?!REDACTED|<redacted>|REDACTED_[^"]*")[^"]+"')),
    ("raw_innertube_api_key", re.compile(r'"INNERTUBE_API_KEY"\s*:\s*"(?!REDACTED|<redacted>|REDACTED_[^"]*")[^"]+"')),
    ("raw_caption_base_url", re.compile(r'"baseUrl"\s*:\s*"(?!REDACTED|<redacted>|REDACTED_[^"]*")[^"]+"')),
    ("raw_signature_cipher", re.compile(r'"signatureCipher"\s*:\s*"(?!REDACTED|<redacted>|REDACTED_[^"]*")[^"]+"')),
]
YTDLP_MEDIA_FLAGS = re.compile(r"\byt-dlp\b.*(?:--extract-audio|--audio-format|--recode-video|--remux-video|--download-sections|(?:^|\s)-f\s+\S+)")


def iter_files(root: Path):
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in SCAN_SUFFIXES:
            continue
        if path.name in SKIP_NAMES or ".pytest_cache" in path.parts or "tests" in path.parts:
            continue
        yield path


def scan(root: Path) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for path in iter_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line_no, line in enumerate(text.splitlines(), 1):
            for class_name, pattern in FORBIDDEN_PATTERNS:
                if pattern.search(line):
                    findings.append({
                        "file": str(path),
                        "line": line_no,
                        "class": class_name,
                        "excerpt": line.strip()[:160],
                    })
            if YTDLP_MEDIA_FLAGS.search(line) and "--skip-download" not in line:
                findings.append({
                    "file": str(path),
                    "line": line_no,
                    "class": "ytdlp_media_without_skip_download",
                    "excerpt": line.strip()[:160],
                })
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan YouTube domain artifacts for forbidden unsafe paths")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)

    findings = scan(args.root)
    if findings:
        for item in findings:
            print(f"{item['file']}:{item['line']}: {item['class']}: {item['excerpt']}")
        return 1
    print(f"ok: no forbidden YouTube paths under {args.root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
