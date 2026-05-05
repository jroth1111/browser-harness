"""Extract cookies from Chrome, Edge, Comet (Chromium-based) and Safari on macOS.

Chromium browsers encrypt cookie values with AES-128-CBC keyed off a Keychain
"Safe Storage" entry; Safari stores cookies unencrypted in a binary plist
(BinaryCookies format) inside a sandboxed container that requires Full Disk
Access to read.

Discovered Chromium cookie format (v10):
    'v10' (3 bytes) + 16-byte unknown prefix + 16-byte IV + AES-CBC ciphertext

Older Chrome docs claim a fixed IV of 16 spaces — this is wrong for current
Chromium forks. The IV is embedded at offset 16-32 after the v10 prefix.

Public surface:
    list_browser_profiles() -> list[BrowserProfile]
        Enumerate every Chrome/Edge/Comet profile and Safari (if accessible)
        on this machine. Use this as the entrypoint for harvesting.
    extract_cookies_from_profile(profile, domain_filter=None) -> dict
        Return decrypted cookies for one profile, optionally filtered by host
        substring. Returns {host_key: {name: {value, expires, secure, http_only, same_site}}}
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
import struct
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


PBKDF2_SALT = b"saltysalt"
PBKDF2_ITERATIONS = 1003
PBKDF2_KEY_LENGTH = 16

V10_PREFIX_LEN = 3
HEADER_LEN = 16
IV_LEN = 16


@dataclass
class BrowserProfile:
    """One concrete cookie source: a browser + profile directory."""
    browser: str          # chrome / edge / comet / arc / cursor / chromium / safari
    profile: str          # 'Default', 'Profile 1', etc; 'Default' for non-Chromium
    cookie_db: Path       # path to Cookies SQLite (Chromium) or .binarycookies (Safari)
    keychain_entry: str | None  # Safe Storage entry; None for Safari


CHROMIUM_BROWSERS = {
    "chrome":   ("Chrome Safe Storage",          "Google/Chrome"),
    "chromium": ("Chromium Safe Storage",        "Chromium"),
    "edge":     ("Microsoft Edge Safe Storage",  "Microsoft Edge"),
    "comet":    ("Comet Safe Storage",           "Comet"),
    "arc":      ("Arc Safe Storage",             "Arc/User Data"),
    "cursor":   ("Cursor Safe Storage",          "Cursor"),
    "brave":    ("Brave Safe Storage",           "BraveSoftware/Brave-Browser"),
    "vivaldi":  ("Vivaldi Safe Storage",         "Vivaldi"),
}

APPLICATION_SUPPORT = Path("~/Library/Application Support").expanduser()

# Modern sandboxed Safari path. Requires Full Disk Access in System Settings.
SAFARI_COOKIES = Path(
    "~/Library/Containers/com.apple.Safari/Data/Library/Cookies/Cookies.binarycookies"
).expanduser()
SAFARI_COOKIES_LEGACY = Path("~/Library/Cookies/Cookies.binarycookies").expanduser()


# --- Discovery -------------------------------------------------------------

def list_browser_profiles() -> list[BrowserProfile]:
    """Enumerate all browser profiles available on this machine.

    Each profile is a separate cookie jar; e.g. Chrome can have Default,
    Profile 1, Profile 2 for different Google accounts.
    """
    profiles: list[BrowserProfile] = []

    for browser, (keychain, app_subdir) in CHROMIUM_BROWSERS.items():
        base = APPLICATION_SUPPORT / app_subdir
        if not base.exists():
            continue
        for profile_dir in _chromium_profile_dirs(base):
            cookie_db = profile_dir / "Cookies"
            # Newer Chromium versions moved cookies under "Network/Cookies".
            if not cookie_db.exists():
                cookie_db = profile_dir / "Network" / "Cookies"
            if not cookie_db.exists():
                continue
            profiles.append(BrowserProfile(
                browser=browser,
                profile=profile_dir.name,
                cookie_db=cookie_db,
                keychain_entry=keychain,
            ))

    safari_path = _safari_cookie_path()
    if safari_path is not None:
        profiles.append(BrowserProfile(
            browser="safari",
            profile="Default",
            cookie_db=safari_path,
            keychain_entry=None,
        ))

    return profiles


def _chromium_profile_dirs(base: Path) -> list[Path]:
    """Find all Chrome-style profile directories under base."""
    candidates: list[Path] = []
    for entry in sorted(base.iterdir()):
        if not entry.is_dir():
            continue
        name = entry.name
        if name == "Default" or name.startswith("Profile "):
            candidates.append(entry)
    # Some Chromium forks put cookies directly in the base (no profile subdir).
    if not candidates and (base / "Cookies").exists():
        candidates.append(base)
    return candidates


def _safari_cookie_path() -> Path | None:
    for path in (SAFARI_COOKIES, SAFARI_COOKIES_LEGACY):
        if path.exists():
            return path
    return None


# --- Chromium decryption ---------------------------------------------------

_keychain_cache: dict[str, str | None] = {}


def get_keychain_password(keychain_name: str) -> str | None:
    if keychain_name in _keychain_cache:
        return _keychain_cache[keychain_name]
    result = subprocess.run(
        ["security", "find-generic-password", "-ws", keychain_name],
        capture_output=True, text=True,
    )
    pwd = result.stdout.strip() if result.returncode == 0 else None
    _keychain_cache[keychain_name] = pwd
    return pwd


def derive_aes_key(keychain_password: str) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha1",
        keychain_password.encode("utf-8"),
        PBKDF2_SALT,
        PBKDF2_ITERATIONS,
        dklen=PBKDF2_KEY_LENGTH,
    )


def decrypt_cookie_value(encrypted_value: bytes, aes_key: bytes) -> str | None:
    if not encrypted_value or not encrypted_value.startswith(b"v10"):
        return None
    payload = encrypted_value[V10_PREFIX_LEN:]
    if len(payload) < HEADER_LEN + IV_LEN + 16:
        return None
    iv = payload[HEADER_LEN:HEADER_LEN + IV_LEN]
    ciphertext = payload[HEADER_LEN + IV_LEN:]
    if len(ciphertext) == 0 or len(ciphertext) % 16 != 0:
        return None

    cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    plaintext = decryptor.update(ciphertext) + decryptor.finalize()

    pad_byte = plaintext[-1]
    if 1 <= pad_byte <= 16 and all(b == pad_byte for b in plaintext[-pad_byte:]):
        plaintext = plaintext[:-pad_byte]

    try:
        return plaintext.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _read_chromium_cookies(
    profile: BrowserProfile,
    domain_filter: str | None,
) -> dict[str, dict[str, dict]]:
    if profile.keychain_entry is None:
        raise ValueError(f"Chromium read called for non-Chromium browser: {profile.browser}")
    password = get_keychain_password(profile.keychain_entry)
    if not password:
        raise RuntimeError(f"Could not read Keychain entry: {profile.keychain_entry}")
    aes_key = derive_aes_key(password)

    if not profile.cookie_db.exists():
        raise FileNotFoundError(f"Cookie database not found: {profile.cookie_db}")

    # Open read-only via URI to avoid contention with a running browser.
    uri = f"file:{profile.cookie_db}?mode=ro&immutable=1"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row

    sql = (
        "SELECT name, host_key, path, encrypted_value, expires_utc, "
        "is_secure, is_httponly, samesite "
        "FROM cookies"
    )
    params: tuple = ()
    if domain_filter:
        sql += " WHERE host_key LIKE ?"
        params = (f"%{domain_filter}%",)
    sql += " ORDER BY host_key, name"

    rows = conn.execute(sql, params).fetchall()
    conn.close()

    out: dict[str, dict[str, dict]] = {}
    for r in rows:
        value = decrypt_cookie_value(r["encrypted_value"], aes_key)
        if value is None:
            continue
        out.setdefault(r["host_key"], {})[r["name"]] = {
            "value": value,
            "path": r["path"],
            "expires": _chromium_expires_to_epoch(r["expires_utc"]),
            "secure": bool(r["is_secure"]),
            "http_only": bool(r["is_httponly"]),
            "same_site": _samesite_label(r["samesite"]),
        }
    return out


def _chromium_expires_to_epoch(expires_utc: int) -> int | None:
    """Convert Chromium's expires_utc (microseconds since 1601-01-01) to Unix epoch."""
    if not expires_utc:
        return None
    return int(expires_utc / 1_000_000) - 11_644_473_600


def _samesite_label(value: int) -> str:
    return {-1: "unspecified", 0: "no_restriction", 1: "lax", 2: "strict"}.get(value, "unspecified")


# --- Safari binarycookies parser -------------------------------------------

def _read_safari_cookies(
    profile: BrowserProfile,
    domain_filter: str | None,
) -> dict[str, dict[str, dict]]:
    """Parse Apple BinaryCookies. Reading the file requires Full Disk Access."""
    try:
        data = profile.cookie_db.read_bytes()
    except PermissionError as e:
        raise PermissionError(
            f"Cannot read Safari cookies at {profile.cookie_db}. "
            "Grant Full Disk Access to your terminal in "
            "System Settings → Privacy & Security → Full Disk Access."
        ) from e

    if data[:4] != b"cook":
        raise ValueError(f"Not a binarycookies file: {profile.cookie_db}")

    out: dict[str, dict[str, dict]] = {}
    num_pages = struct.unpack(">I", data[4:8])[0]
    page_sizes = struct.unpack(f">{num_pages}I", data[8:8 + 4 * num_pages])

    cursor = 8 + 4 * num_pages
    for page_size in page_sizes:
        page = data[cursor:cursor + page_size]
        cursor += page_size
        if page[:4] != b"\x00\x00\x01\x00":
            continue
        num_cookies = struct.unpack("<I", page[4:8])[0]
        cookie_offsets = struct.unpack(f"<{num_cookies}I", page[8:8 + 4 * num_cookies])
        for offset in cookie_offsets:
            cookie = _parse_safari_cookie(page, offset)
            if cookie is None:
                continue
            host = cookie["host_key"]
            if domain_filter and domain_filter not in host:
                continue
            out.setdefault(host, {})[cookie["name"]] = {
                "value": cookie["value"],
                "path": cookie["path"],
                "expires": cookie["expires"],
                "secure": cookie["secure"],
                "http_only": cookie["http_only"],
                "same_site": "unspecified",
            }
    return out


def _parse_safari_cookie(page: bytes, offset: int) -> dict | None:
    if offset + 56 > len(page):
        return None
    cookie_size = struct.unpack("<I", page[offset:offset + 4])[0]
    if offset + cookie_size > len(page):
        return None
    blob = page[offset:offset + cookie_size]

    flags = struct.unpack("<I", blob[8:12])[0]
    secure = bool(flags & 0x1)
    http_only = bool(flags & 0x4)

    url_offset, name_offset, path_offset, value_offset = struct.unpack("<IIII", blob[16:32])
    # Safari stores expiration as Cocoa epoch (seconds since 2001-01-01).
    expires_cocoa, _creation = struct.unpack("<dd", blob[40:56])
    expires = int(expires_cocoa + 978_307_200) if expires_cocoa else None

    host = _read_cstr(blob, url_offset)
    name = _read_cstr(blob, name_offset)
    path = _read_cstr(blob, path_offset)
    value = _read_cstr(blob, value_offset)
    if not host or not name:
        return None
    return {
        "host_key": host,
        "name": name,
        "path": path,
        "value": value,
        "expires": expires,
        "secure": secure,
        "http_only": http_only,
    }


def _read_cstr(blob: bytes, offset: int) -> str:
    end = blob.find(b"\x00", offset)
    if end == -1:
        end = len(blob)
    try:
        return blob[offset:end].decode("utf-8")
    except UnicodeDecodeError:
        return blob[offset:end].decode("latin-1", errors="replace")


# --- Public API ------------------------------------------------------------

def extract_cookies_from_profile(
    profile: BrowserProfile,
    domain_filter: str | None = None,
) -> dict[str, dict[str, dict]]:
    """Extract cookies from one browser profile.

    Returns {host_key: {cookie_name: {value, path, expires, secure, http_only, same_site}}}.
    Empty dict on read failure (e.g. Safari without FDA) — never raises for that case
    when the caller passed a domain_filter, so a sweep across many browsers can continue.
    """
    if profile.browser == "safari":
        return _read_safari_cookies(profile, domain_filter)
    return _read_chromium_cookies(profile, domain_filter)


def harvest_for_domain(
    domain_filter: str,
    *,
    skip_browsers: tuple[str, ...] = (),
    on_error: callable = None,
) -> list[tuple[BrowserProfile, dict[str, dict[str, dict]]]]:
    """Sweep every available browser profile and return any cookies matching domain_filter.

    Skips browsers in skip_browsers. Errors are routed to on_error(profile, exc) when
    provided, otherwise printed to stderr. The caller decides whether each non-empty
    jar authenticates.
    """
    results: list[tuple[BrowserProfile, dict[str, dict[str, dict]]]] = []
    for profile in list_browser_profiles():
        if profile.browser in skip_browsers:
            continue
        try:
            cookies = extract_cookies_from_profile(profile, domain_filter)
        except Exception as exc:
            if on_error is not None:
                on_error(profile, exc)
            else:
                import sys
                print(
                    f"  [skip] {profile.browser}/{profile.profile}: {exc}",
                    file=sys.stderr,
                )
            continue
        if cookies:
            results.append((profile, cookies))
    return results


# --- Backwards compatibility -----------------------------------------------

# Old single-browser helper used by chatgpt_http_sync.py. Prefer harvest_for_domain
# in new code.
def extract_cookies(
    browser: str,
    domain_filter: str | None = None,
) -> dict[str, dict[str, str]]:
    """Legacy: extract cookies as flat {host: {name: value}} for one browser."""
    profiles = [p for p in list_browser_profiles() if p.browser == browser]
    if not profiles:
        raise ValueError(f"No profile found for browser: {browser}")
    cookies = extract_cookies_from_profile(profiles[0], domain_filter)
    return {host: {name: c["value"] for name, c in jar.items()} for host, jar in cookies.items()}


# Backwards-compat constant for callers that imported BROWSER_PROFILES.
BROWSER_PROFILES = {
    name: {"keychain": kc, "cookie_db": str(APPLICATION_SUPPORT / f"{sub}/Default/Cookies")}
    for name, (kc, sub) in CHROMIUM_BROWSERS.items()
}
