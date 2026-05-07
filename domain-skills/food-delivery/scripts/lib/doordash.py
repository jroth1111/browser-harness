"""DoorDash platform specifics: URLs, helpers.

IMPORTANT: The working extraction code lives in the scripts themselves:
- Restaurant extraction JS: enumerate_restaurants.py (extract_restaurants_generic)
- Menu extraction: extract_menus.py (extract_menu_from_next_data)

Do NOT use class-based selectors or arrow functions — DoorDash uses
styled-components with hashed class names that rotate per build.
SeleniumBase execute_script returns None for arrow functions.
"""
import json, time, random
from pathlib import Path

BASE = "https://www.doordash.com"

URLS = {
    "home": f"{BASE}/",
    "search": f"{BASE}/search/store/{{query}}",
    "store": f"{BASE}/store/{{store_id}}",
    "checkout": f"{BASE}/checkout",
    "orders": f"{BASE}/orders/",
    "account": f"{BASE}/account",
}

API_DISCOVERY_PATH = Path(__file__).parent / "api_discovery_doordash.json"


def load_api_discovery():
    if API_DISCOVERY_PATH.exists():
        data = json.loads(API_DISCOVERY_PATH.read_text())
        return data if isinstance(data, dict) else None
    return None


def search_url(query):
    return f"{BASE}/search/store/{query}"


def browse_url():
    """Browse-all URL. "food" query covers restaurants, groceries, convenience, retail."""
    return f"{BASE}/search/store/food"


def store_url(slug=None, store_id=None):
    """Store page URL. DoorDash uses just numeric ID, slug is optional."""
    if slug:
        return f"{BASE}/store/{slug}-{store_id}"
    return f"{BASE}/store/{store_id}"


# Extraction JS is in enumerate_restaurants.py and extract_menus.py, not here.
# Those scripts bake variables into the JS string via .replace() and use
# bare return statements (not arrow functions) because SB returns None
# for arrow functions and IIFEs.


def random_delay(min_s=2.0, max_s=5.0):
    time.sleep(random.uniform(min_s, max_s))
