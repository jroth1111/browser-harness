"""SeleniumBase session management for food delivery platforms.

Handles SB UC Mode launch, cookie injection, auth verification, and
cookie harvesting for HTTP replay."""
import json, time, os
from pathlib import Path

PRIVATE_DATA = Path(__file__).parent.parent.parent / ".private-data"


def cookie_path(platform):
    return PRIVATE_DATA / f"{platform}_cookies.json"


def create_sb_session(sb, platform):
    """Launch SB UC Mode, navigate to platform, inject saved cookies, verify auth."""
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
    """Load saved cookies and inject into the current SB session."""
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
        # Logged in: no "Sign In" in the first 2000 chars of source
        if "Sign In" not in src[:2000] and "DoorDash" in title:
            return True
        return False

    if platform == "ubereats":
        if "Sign in" not in src[:3000] and "Order food" in title:
            return True
        return False

    return False


def harvest_session_cookies(sb, platform):
    """Save current session cookies to .private-data/ for HTTP replay."""
    cookies = sb.driver.get_cookies()
    cp = cookie_path(platform)
    cp.parent.mkdir(parents=True, exist_ok=True)
    cp.write_text(json.dumps(cookies))
    return len(cookies)


def harvest_http_headers(sb):
    """Extract User-Agent and other headers for HTTP replay."""
    ua = sb.driver.execute_script("return navigator.userAgent")
    return {
        "User-Agent": ua,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
    }
