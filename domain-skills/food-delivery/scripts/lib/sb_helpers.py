"""SeleniumBase session management for food delivery platforms.

Handles SB UC Mode launch, cookie injection, auth verification, and
cookie harvesting. Run via: .venv/bin/python3 from repo root."""
import json, time
from pathlib import Path

PRIVATE_DATA = Path(__file__).parent.parent.parent / ".private-data"


def cookie_path(platform):
    return PRIVATE_DATA / f"{platform}_cookies.json"


def create_sb_session(sb, platform):
    """Launch SB UC Mode, navigate to platform, inject saved cookies, verify auth.

    This is the standard entry point for all scripts — opens the platform,
    restores the session from .private-data/, and checks if auth succeeded.
    """
    urls = {
        "doordash": "https://www.doordash.com/",
        "ubereats": "https://www.ubereats.com/",
    }
    url = urls[platform]
    sb.uc_open_with_reconnect(url, 4)
    time.sleep(2)

    cp = cookie_path(platform)
    if cp.exists():
        inject_cookies(sb, platform)
        sb.driver.refresh()
        time.sleep(3)

    return check_auth(sb, platform)


def inject_cookies(sb, platform):
    """Load saved cookies and inject into the current SB session.

    Some cookies will fail (domain mismatch) — this is expected and harmless.
    """
    cp = cookie_path(platform)
    if not cp.exists():
        return 0
    cookies = json.loads(cp.read_text())
    injected = 0
    for c in cookies:
        try:
            sb.driver.add_cookie(c)
            injected += 1
        except Exception:
            pass
    return injected


def check_auth(sb, platform):
    """Check if the current session is authenticated. Returns True/False."""
    src = sb.driver.page_source
    title = sb.get_title()

    if platform == "doordash":
        if "Sign In" not in src[:2000] and "DoorDash" in title:
            return True
        return False

    if platform == "ubereats":
        if "Sign in" not in src[:3000] and "Order food" in title:
            return True
        return False

    return False


def harvest_session_cookies(sb, platform):
    """Save current session cookies to .private-data/ for next run.

    Call this at the end of every script to keep cookies fresh.
    DoorDash cf_clearance expires ~30min, so harvesting after each run
    extends the session for the next script invocation.
    """
    cookies = sb.driver.get_cookies()
    cp = cookie_path(platform)
    cp.parent.mkdir(parents=True, exist_ok=True)
    cp.write_text(json.dumps(cookies))
    return len(cookies)


def harvest_http_headers(sb):
    """Extract User-Agent for HTTP replay (not currently used — no public APIs)."""
    ua = sb.driver.execute_script("return navigator.userAgent")
    return {
        "User-Agent": ua,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
    }
