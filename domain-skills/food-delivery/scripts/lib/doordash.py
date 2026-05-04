"""DoorDash platform specifics: URLs, API patterns, extraction JS."""
import json, time, re, random
from pathlib import Path

BASE = "https://www.doordash.com"

URLS = {
    "home": f"{BASE}/",
    "search": f"{BASE}/search/store/{{query}}",
    "store": f"{BASE}/store/{{slug}}-{{store_id}}",
    "checkout": f"{BASE}/checkout",
    "orders": f"{BASE}/orders/",
    "account": f"{BASE}/account",
}

# Populated by discover_apis.py after Phase 1
API_DISCOVERY_PATH = Path(__file__).parent / "api_discovery_doordash.json"


def load_api_discovery():
    if API_DISCOVERY_PATH.exists():
        return json.loads(API_DISCOVERY_PATH.read_text())
    return None


def search_url(query):
    return f"{BASE}/search/store/{query}"


def browse_url():
    """URL for browsing all available restaurants/stores.
    Uses generic 'food' search to return all restaurants.
    """
    return f"{BASE}/search/store/food"


def store_url(slug, store_id):
    return f"{BASE}/store/{slug}-{store_id}"


EXTRACT_RESTAURANTS_JS = """
() => {
    const cards = document.querySelectorAll('[data-testid="storeCard"], a[href*="/store/"]');
    const results = [];
    cards.forEach(card => {
        const link = card.closest('a') || card.querySelector('a');
        const href = link ? link.getAttribute('href') : '';
        const slugMatch = href.match(/\\/store\\/([^\\/]+)-(\\d+)/);
        results.push({
            store_id: slugMatch ? slugMatch[2] : null,
            slug: slugMatch ? slugMatch[1] : null,
            url: href ? 'https://www.doordash.com' + href : null,
            name: (card.querySelector('h3, h2, [class*="StoreCard"] span, p') || {}).textContent?.trim() || null,
            rating: null,
            delivery_time: null,
            delivery_fee: null,
            cuisine: null,
            promo_badge: null,
        });
    });
    return JSON.stringify(results);
}
"""

EXTRACT_MENU_JS = """
() => {
    const sections = document.querySelectorAll('h2, h3, [role="heading"]');
    const items = [];
    let currentCategory = 'Unknown';

    sections.forEach(heading => {
        const text = heading.textContent?.trim();
        if (!text) return;

        // Check if this is a category header
        const parent = heading.closest('section, [class*="menu"], [class*="category"]') || heading.parentElement;
        if (!parent) return;

        currentCategory = text;

        // Find item containers near this heading
        const siblings = parent.querySelectorAll('[class*="MenuItem"], [data-testid*="item"]');
        if (siblings.length === 0) return;

        siblings.forEach(item => {
            const nameEl = item.querySelector('[class*="itemName"], h3, h4, p:first-of-type');
            const priceEl = item.querySelector('[class*="price"], [class*="Price"]');
            const descEl = item.querySelector('[class*="description"], [class*="Description"]');
            items.push({
                category: currentCategory,
                item_name: nameEl?.textContent?.trim() || null,
                item_price: priceEl?.textContent?.trim() || null,
                description: descEl?.textContent?.trim() || null,
                popular_badge: item.textContent?.includes('Most Ordered') || false,
                customization_count: null,
                image_url: null,
            });
        });
    });
    return JSON.stringify(items);
}
"""


def random_delay(min_s=2.0, max_s=5.0):
    time.sleep(random.uniform(min_s, max_s))
