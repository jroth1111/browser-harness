"""Uber Eats platform specifics: URLs, API patterns, extraction JS."""
import json, time, re, random
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


def store_url(slug, store_id):
    return f"{BASE}/store/{slug}/{store_id}"


EXTRACT_RESTAURANTS_JS = """
() => {
    const cards = document.querySelectorAll('a[href*="/store/"]');
    const results = [];
    const seen = new Set();
    cards.forEach(card => {
        const href = card.getAttribute('href') || '';
        const slugMatch = href.match(/\\/store\\/([^\\/]+)\\/([^\\/]+)/);
        if (!slugMatch) return;
        const storeId = slugMatch[2];
        if (seen.has(storeId)) return;
        seen.add(storeId);
        results.push({
            store_id: storeId,
            slug: slugMatch[1],
            url: 'https://www.ubereats.com' + href,
            name: (card.querySelector('h3, h2, h4, p') || {}).textContent?.trim() || null,
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
    const items = [];
    let currentCategory = 'Unknown';

    // Uber Eats uses section headings for categories
    const allElements = document.querySelectorAll('h2, h3, h4, [role="heading"]');
    const categoryHeaders = new Set();

    allElements.forEach(el => {
        const text = el.textContent?.trim();
        if (!text || text.length > 50) return;
        // Category headers are typically short text that aren't inside item cards
        const parent = el.closest('a[href*="/store/"]');
        if (parent) return; // Skip if inside a link (it's an item, not a header)
        categoryHeaders.add(el);
    });

    // Try to find menu item containers
    const menuItems = document.querySelectorAll('[class*="item"], [class*="Item"], [class*="product"], [class*="Product"]');
    menuItems.forEach(item => {
        const nameEl = item.querySelector('h3, h4, p:first-of-type');
        const priceEl = item.querySelector('[class*="price"], [class*="Price"]');
        const descEl = item.querySelector('[class*="description"], [class*="Description"]');
        items.push({
            category: currentCategory,
            item_name: nameEl?.textContent?.trim() || null,
            item_price: priceEl?.textContent?.trim() || null,
            description: descEl?.textContent?.trim() || null,
            popular_badge: item.textContent?.includes('Most Liked') || false,
            customization_count: null,
            image_url: null,
        });
    });
    return JSON.stringify(items);
}
"""


def random_delay(min_s=2.0, max_s=5.0):
    time.sleep(random.uniform(min_s, max_s))
