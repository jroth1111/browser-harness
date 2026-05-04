"""Project-level redaction scan for public artifacts."""

from pathlib import Path
import re


SKIP_PARTS = {
    ".git",
    ".beads",
    ".private-data",
    ".session-store",
    ".venv",
    "__pycache__",
    "downloaded_files",
    "outputs",
}
MAX_FILE_BYTES = 1_000_000

_PATTERNS = [
    ("bearer_token", re.compile(r"(?i)\bauthorization\s*[:=]\s*bearer\s+[a-z0-9._~+/=-]{20,}")),
    ("set_cookie_header", re.compile(r"(?i)\bset-cookie\s*:")),
    ("cookie_header", re.compile(r"(?i)\bcookie\s*:\s*[^\\n]{8,}")),
    ("session_cookie", re.compile(r"(?i)\b(?:sessionid|session_id|_airbed_session_id|sid)\s*=\s*[^\\s;,]{8,}")),
    ("storage_token_value", re.compile(r"(?i)\"(?:token|access_token|refresh_token|id_token)\"\s*:\s*\"[^\"]{12,}\"")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
]


def _should_skip(path):
    return any(part in SKIP_PARTS for part in path.parts)


def _redact_excerpt(text):
    text = re.sub(r"(?i)(bearer\s+)[a-z0-9._~+/=-]+", r"\1REDACTED", text)
    text = re.sub(r"(?i)(=\s*)[^\\s;,]{8,}", r"\1REDACTED", text)
    text = re.sub(r'(:\s*")[^"]{8,}(")', r"\1REDACTED\2", text)
    return text[:180]


def scan_text(text, *, path="<memory>"):
    """Return redaction findings for a text blob."""
    findings = []
    for line_no, line in enumerate(text.splitlines(), 1):
        for kind, pattern in _PATTERNS:
            if pattern.search(line):
                findings.append({
                    "path": str(path),
                    "line": line_no,
                    "kind": kind,
                    "excerpt": _redact_excerpt(line.strip()),
                })
    return findings


def _iter_files(paths):
    for path in paths:
        path = Path(path)
        if _should_skip(path):
            continue
        if path.is_dir():
            for child in path.rglob("*"):
                if child.is_file() and not _should_skip(child):
                    yield child
        elif path.is_file():
            yield path


def scan_paths(paths):
    """Scan files/directories and return `{ok, findings}`."""
    findings = []
    for path in _iter_files(paths):
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        findings.extend(scan_text(text, path=path))
    return {"ok": not findings, "findings": findings}
