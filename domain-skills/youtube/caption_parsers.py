"""Local caption normalization helpers for already-captured YouTube payloads."""
from __future__ import annotations

import html
import json
import re
import xml.etree.ElementTree as ET
from urllib.parse import urlencode


TIMESTAMP_RE = re.compile(
    r"^\s*(?:\d{1,2}:)?\d{1,2}:\d{2}[.,]\d{3}\s+-->\s+(?:\d{1,2}:)?\d{1,2}:\d{2}[.,]\d{3}"
)
TAG_RE = re.compile(r"<[^>]+>")


def normalize_caption_line(line: str) -> str:
    text = TAG_RE.sub("", line)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _is_vtt_cue_identifier(raw_lines: list[str], index: int) -> bool:
    line = raw_lines[index].strip("\ufeff").strip()
    if not line or "-->" in line:
        return False
    if index + 1 >= len(raw_lines):
        return False
    next_line = raw_lines[index + 1].strip("\ufeff").strip()
    return bool(TIMESTAMP_RE.match(next_line))


def vtt_to_text(text: str, keep_timestamps: bool = False) -> str:
    lines: list[str] = []
    last = None
    pending_time = None
    raw_lines = text.splitlines()
    for index, raw in enumerate(raw_lines):
        line = raw.strip("\ufeff").strip()
        if not line or line.upper().startswith(("WEBVTT", "NOTE", "STYLE", "REGION")):
            continue
        if TIMESTAMP_RE.match(line):
            pending_time = line if keep_timestamps else None
            continue
        if _is_vtt_cue_identifier(raw_lines, index):
            continue
        cleaned = normalize_caption_line(line)
        if not cleaned or cleaned == last:
            continue
        if keep_timestamps and pending_time:
            lines.append(f"[{pending_time}] {cleaned}")
            pending_time = None
        else:
            lines.append(cleaned)
        last = cleaned
    return "\n".join(lines)


def json3_to_text(raw: str) -> str:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return ""
    if not isinstance(data, dict):
        return ""
    lines: list[str] = []
    for event in data.get("events", []):
        if not isinstance(event, dict):
            continue
        segs = event.get("segs") or []
        if not isinstance(segs, list):
            continue
        text = "".join(str(seg.get("utf8", "")) for seg in segs if isinstance(seg, dict))
        cleaned = normalize_caption_line(text)
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines)


def _element_text(element: ET.Element) -> str:
    return normalize_caption_line(" ".join(text for text in element.itertext()))


def xml_to_text(raw: str) -> str:
    """Normalize timedtext, SRV3, or TTML XML captions to plain text."""
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        cleaned = normalize_caption_line(raw)
        return cleaned if cleaned else ""

    lines: list[str] = []
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1].lower()
        if tag not in {"text", "p"}:
            continue
        cleaned = _element_text(element)
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines)


def build_timedtext_url(video_id: str, language: str = "en", fmt: str = "srv3") -> str:
    query = urlencode({"v": video_id, "lang": language, "fmt": fmt})
    return f"https://www.youtube.com/api/timedtext?{query}"
