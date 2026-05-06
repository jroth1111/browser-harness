"""Uber Eats platform specifics: URLs, helpers.

IMPORTANT: The working extraction code lives in the scripts themselves:
- Restaurant extraction JS: enumerate_restaurants.py (extract_restaurants_generic)
- Menu extraction: extract_menus.py (extract_menu_from_dom)

Uber Eats menu extraction is not yet field-tested — only restaurant
enumeration has been confirmed working (82 restaurants in Melbourne AU).
"""
import json, time, random
from pathlib import Path

BASE = "https://www.ubereats.com"

URLS = {
    "home": f"{BASE}/",
    "search": f"{BASE}/search?q={{query}}",
    "store": f"{BASE}/store/{{slug}}/{{store_id}}",
    "checkout": f"{BASE}/checkout",
    "orders": f"{BASE}/orders",
    "account": f"{BASE}/account",
}

API_DISCOVERY_PATH = Path(__file__).parent / "api_discovery_ubereats.json"


def load_api_discovery():
    if API_DISCOVERY_PATH.exists():
        return json.loads(API_DISCOVERY_PATH.read_text())
    return None


def search_url(query):
    return f"{BASE}/search?q={query}"


def browse_url():
    """Browse-all URL. "food" query covers all options for the delivery area."""
    return f"{BASE}/search?q=food"


def store_url(slug, store_id):
    return f"{BASE}/store/{slug}/{store_id}"


# Extraction JS is in enumerate_restaurants.py and extract_menus.py.
# Store ID is base64-like: "F5sh58oFUZq6l-ps6Ejzww"
# Strip query params (?sc=SEARCH_SUGGESTION) before extracting IDs.


def random_delay(min_s=2.0, max_s=5.0):
    time.sleep(random.uniform(min_s, max_s))
