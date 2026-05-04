"""Phase 3: Extract menu items from restaurant pages.

For each restaurant in the input JSON, navigate to its store page and extract
all menu items with prices. Supports checkpoint/resume.

Usage:
    .venv/bin/python3 scripts/extract_menus.py --input restaurants.json --output menus.json
    .venv/bin/python3 scripts/extract_menus.py --input restaurants.json --output menus.json --resume menu_checkpoint.json
    .venv/bin/python3 scripts/extract_menus.py --input restaurants.json --output menus.json --limit 10
"""
import argparse, json, sys, time, random, re
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent))
from lib.sb_helpers import create_sb_session, harvest_session_cookies, check_auth
from lib.crawl_state import CrawlState, SafetyGate
from lib import doordash, ubereats

SCROLL_PAUSE = (1.0, 3.0)
PAGE_DELAY = (2.0, 5.0)
MAX_SCROLLS_NO_NEW = 5


def extract_menu_items(sb, platform, store_url):
    """Extract all menu items from a restaurant page via DOM scraping."""
    js = """
    () => {
        const items = [];
        const seen = new Set();
        let currentCategory = 'Unknown';

        // Find all visible text to understand page structure
        // Strategy: find category headers, then find item cards below them

        // Get all headings that could be category names
        const headings = document.querySelectorAll('h1, h2, h3, h4, [role="heading"]');
        const categoryPositions = [];

        headings.forEach(h => {
            const text = h.textContent?.trim();
            if (!text || text.length > 60 || text.length < 2) return;
            // Skip if it looks like the store name (usually h1)
            if (h.tagName === 'H1') return;
            const rect = h.getBoundingClientRect();
            if (rect.bottom > 0 && rect.top < window.innerHeight * 10) {
                categoryPositions.push({ text, y: rect.top });
            }
        });

        // Find menu item containers — look for elements with price text
        // Prices usually look like $XX.XX or $X.XX
        const allElements = document.querySelectorAll('div, section, article, li');
        const itemContainers = [];

        allElements.forEach(el => {
            const text = el.textContent || '';
            // Must contain a price pattern
            if (!/\\$\\d+\\.?\\d*/.test(text)) return;
            // Must be reasonably sized (not the whole page)
            if (text.length > 2000 || text.length < 5) return;
            // Should have a child with price-like text
            const children = el.children;
            let hasPrice = false, hasName = false;
            for (const child of children) {
                const childText = child.textContent?.trim() || '';
                if (/^\\$\\d+\\.?\\d{0,2}$/.test(childText)) hasPrice = true;
                if (childText.length > 3 && childText.length < 100 && !childText.startsWith('$')) hasName = true;
            }
            if (hasPrice && hasName) {
                itemContainers.push(el);
            }
        });

        // Extract from item containers
        itemContainers.forEach(container => {
            const containerText = container.textContent || '';
            const rect = container.getBoundingClientRect();

            // Find category for this item based on position
            let category = 'Unknown';
            for (let i = categoryPositions.length - 1; i >= 0; i--) {
                if (categoryPositions[i].y < rect.top) {
                    category = categoryPositions[i].text;
                    break;
                }
            }

            // Extract name: first significant text that isn't a price
            let name = null;
            let price = null;
            let description = null;
            const childTexts = [];

            for (const child of container.children) {
                const childText = child.textContent?.trim() || '';
                childTexts.push(childText);

                if (!price && /^\\$\\d+\\.?\\d{0,2}$/.test(childText)) {
                    price = childText;
                } else if (!name && childText.length > 2 && childText.length < 80 && !childText.startsWith('$')) {
                    name = childText;
                }
            }

            // Description: longest non-name, non-price text
            for (const ct of childTexts) {
                if (ct !== name && ct !== price && ct.length > 20) {
                    description = ct;
                    break;
                }
            }

            if (!name) return;
            const key = name + price;
            if (seen.has(key)) return;
            seen.add(key);

            items.push({
                category: category,
                item_name: name,
                item_price: price,
                description: description,
                popular_badge: /most ordered|most liked|#\\d/i.test(containerText),
                customization_count: null,
                image_url: null,
            });
        });

        // Fallback: if no items found with structured approach, try simpler extraction
        if (items.length === 0) {
            const priceElements = document.querySelectorAll('*');
            const priceTexts = new Set();
            priceElements.forEach(el => {
                const text = el.textContent?.trim() || '';
                if (/^\\$\\d+\\.?\\d{0,2}$/.test(text) && el.children.length === 0) {
                    // This is a leaf price element — find its sibling for the name
                    const parent = el.parentElement;
                    if (parent) {
                        const siblings = parent.children;
                        let name = null;
                        for (const sib of siblings) {
                            const sibText = sib.textContent?.trim() || '';
                            if (sibText !== text && sibText.length > 2 && sibText.length < 80 && !sibText.startsWith('$')) {
                                name = sibText;
                                break;
                            }
                        }
                        if (name && !seen.has(name)) {
                            seen.add(name);
                            items.push({
                                category: 'Unknown',
                                item_name: name,
                                item_price: text,
                                description: null,
                                popular_badge: false,
                                customization_count: null,
                                image_url: null,
                            });
                        }
                    }
                }
            });
        }

        return JSON.stringify(items);
    }
    """
    raw = sb.driver.execute_script(js)
    try:
        return json.loads(raw) if raw else []
    except json.JSONDecodeError:
        return []


def scroll_down(sb):
    sb.driver.execute_script("window.scrollBy(0, window.innerHeight * 1.2);")
    time.sleep(random.uniform(*SCROLL_PAUSE))


def extract_menus_for_restaurants(sb, platform, restaurants, checkpoint_path=None):
    """Extract menus from a list of restaurants."""
    mod = doordash if platform == "doordash" else ubereats
    state = CrawlState(key_field="item_key")  # composite: store_id + item_name

    if checkpoint_path and Path(checkpoint_path).exists():
        state = CrawlState.load(checkpoint_path)
        print(f"Resumed from checkpoint: {len(state._records)} items already extracted")

    gate = SafetyGate(max_requests=100, max_seconds=3600, consecutive_block_threshold=3)
    processed_stores = set()
    for r in state._records:
        processed_stores.add(r.get("store_id"))

    for i, rest in enumerate(restaurants):
        store_id = rest.get("store_id")
        store_url = rest.get("url")
        store_name = rest.get("name", "Unknown")

        if not store_url or store_id in processed_stores:
            continue

        if not gate.ok():
            print(f"Safety gate: {gate.summary()}")
            break

        print(f"\n[{i+1}/{len(restaurants)}] {store_name} ({store_id})")
        print(f"  URL: {store_url}")

        try:
            sb.driver.get(store_url)
        except Exception:
            sb.uc_open_with_reconnect(store_url, 4)

        time.sleep(random.uniform(3.0, 5.0))

        # Check for blocks
        src = sb.driver.page_source[:1000]
        if "Verify you are human" in src or "access denied" in src.lower():
            print(f"  BLOCKED. Trying captcha click...")
            sb.uc_gui_click_captcha()
            time.sleep(5)
            src = sb.driver.page_source[:1000]
            if "Verify you are human" in src or "access denied" in src.lower():
                print(f"  Still blocked. Skipping store.")
                gate.record(403, blocked=True)
                continue

        gate.record(200)
        title = sb.get_title()
        print(f"  Loaded: {title}")

        # Scroll and extract menu items
        scrolls_no_new = 0
        total_new = 0
        for scroll_num in range(30):
            items = extract_menu_items(sb, platform, store_url)
            new = 0
            for item in items:
                item["store_id"] = store_id
                item["store_name"] = store_name
                item["platform"] = platform
                item["item_key"] = f"{store_id}::{item.get('item_name', '')}"
                item["extracted_at"] = datetime.now(timezone.utc).isoformat()
                if state.add(item):
                    new += 1

            state.page_done(new)
            total_new += new

            if new == 0:
                scrolls_no_new += 1
            else:
                scrolls_no_new = 0

            if scrolls_no_new >= MAX_SCROLLS_NO_NEW:
                break

            scroll_down(sb)

        processed_stores.add(store_id)
        print(f"  Extracted {total_new} items")

        # Checkpoint every 5 restaurants
        if checkpoint_path and (i + 1) % 5 == 0:
            state.save(checkpoint_path)
            print(f"  Checkpoint saved: {len(state._records)} total items")

        # Take a break every 15 restaurants
        if (i + 1) % 15 == 0:
            print("  Taking a break (15 stores done)...")
            time.sleep(random.uniform(10, 30))

        mod.random_delay(*PAGE_DELAY)

    return state


def main():
    parser = argparse.ArgumentParser(description="Extract menus from restaurant pages")
    parser.add_argument("--input", required=True, help="Restaurant list JSON from enumerate_restaurants.py")
    parser.add_argument("--output", required=True, help="Output JSON file path")
    parser.add_argument("--resume", help="Checkpoint file to resume from")
    parser.add_argument("--limit", type=int, help="Limit number of restaurants to process")
    args = parser.parse_args()

    # Load restaurant list
    data = json.loads(Path(args.input).read_text())
    restaurants = data.get("restaurants", data if isinstance(data, list) else [])
    platform = data.get("platform", "doordash")

    if args.limit:
        restaurants = restaurants[:args.limit]
        print(f"Limited to {args.limit} restaurants")

    print(f"Processing {len(restaurants)} restaurants from {platform}")

    from seleniumbase import SB

    with SB(uc=True, test=True) as sb:
        authed = create_sb_session(sb, platform)
        if not authed:
            print("WARNING: Not authenticated.")

        state = extract_menus_for_restaurants(sb, platform, restaurants, args.resume)

        output = {
            "platform": platform,
            "extracted_at": datetime.now(timezone.utc).isoformat(),
            "summary": state.summary(),
            "menu_items": state._records,
        }
        Path(args.output).write_text(json.dumps(output, indent=2, default=str))
        print(f"\nSaved {len(state._records)} menu items to {args.output}")

        harvest_session_cookies(sb, platform)


if __name__ == "__main__":
    main()
