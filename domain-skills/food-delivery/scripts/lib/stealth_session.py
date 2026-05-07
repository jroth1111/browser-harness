"""Stealth browser session management for food delivery platforms.

Replaces sb_helpers.py (SeleniumBase) with Patchright stealth sessions.
Same cookie JSON format in .private-data/ for backward compatibility.
"""
import json
import time
from pathlib import Path

from browser_harness.stealth_helpers import stealth_session

PRIVATE_DATA = Path(__file__).parent.parent.parent / ".private-data"

PLATFORM_URLS = {
    "doordash": "https://www.doordash.com/",
    "ubereats": "https://www.ubereats.com/",
}


def cookie_path(platform):
    return PRIVATE_DATA / f"{platform}_cookies.json"


def create_stealth_session(platform, headless=False):
    """Create a stealth session, restore cookies, navigate to platform.

    Returns a StealthPage. Caller must call s.close() when done
    (or use try/finally).
    """
    s = stealth_session(headless=headless)

    cp = cookie_path(platform)
    if cp.exists():
        cookies = json.loads(cp.read_text())
        if isinstance(cookies, list):
            s.add_cookies([cookie for cookie in cookies if isinstance(cookie, dict)])

    s.goto(PLATFORM_URLS[platform])
    time.sleep(2)
    return s


def harvest_session_cookies(s, platform):
    """Save cookies from stealth session to .private-data/."""
    cookies = s.cookies()
    cp = cookie_path(platform)
    cp.parent.mkdir(parents=True, exist_ok=True)
    cp.write_text(json.dumps(cookies))
    return len(cookies)


def check_auth(s, platform):
    """Check if the current session is authenticated."""
    html = s.content()
    title = s.js("document.title")

    if platform == "doordash":
        return "Sign In" not in html[:2000] and "DoorDash" in title
    if platform == "ubereats":
        return "Sign in" not in html[:3000] and "Order food" in title
    return False
