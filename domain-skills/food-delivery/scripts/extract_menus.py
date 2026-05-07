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
from lib.stealth_session import create_stealth_session, harvest_session_cookies, check_auth
from lib.crawl_state import CrawlState, SafetyGate
from lib import doordash, ubereats

SCROLL_PAUSE = (1.0, 3.0)
PAGE_DELAY = (2.0, 5.0)
MAX_SCROLLS_NO_NEW = 5


def extract_menu_from_next_data(s):
    """Extract menu items from DoorDash's Next.js embedded JSON.

    DoorDash embeds menu data in self.__next_f.push() script tags.
    Items appear as StorePageCarouselItem objects with name, description,
    displayPrice, imgUrl fields, grouped in carousels by category.
    """
    page_source = s.content()

    pattern = r'self\.__next_f\.push\(\[1,"(.*?)"\]\)'
    menu_items = []
    seen_ids = set()

    for match in re.finditer(pattern, page_source, re.DOTALL):
        raw = match.group(1)
        try:
            decoded = raw.encode("utf-8").decode("unicode_escape")
        except (UnicodeDecodeError, UnicodeEncodeError):
            continue

        if "StorePageCarouselItem" not in decoded:
            continue

        # Extract individual item objects using regex
        # Each item: {"__typename":"StorePageCarouselItem","id":"...","name":"...","description":"...","displayPrice":"...","imgUrl":"..."}
        item_pattern = (
            r'\{"__typename":"StorePageCarouselItem",'
            r'"id":"(\d+)",'
            r'"name":"((?:[^"\\]|\\.)*)",'
            r'"description":"((?:[^"\\]|\\.)*)",'
            r'"displayPrice":"((?:[^"\\]|\\.)*)",'
            r'"displayStrikethroughPrice":"((?:[^"\\]|\\.)*)",'
            r'"imgUrl":"((?:[^"\\]|\\.)*)"'
        )
        for im in re.finditer(item_pattern, decoded):
            item_id = im.group(1)
            if item_id in seen_ids:
                continue
            seen_ids.add(item_id)

            name = im.group(2).encode("utf-8").decode("unicode_escape") if "\\u" in im.group(2) else im.group(2)
            desc = im.group(3)
            if "\\u" in desc:
                desc = desc.encode("utf-8").decode("unicode_escape")

            menu_items.append({
                "category": None,  # filled later by DOM headings
                "item_name": name,
                "item_price": im.group(4) or None,
                "description": desc or None,
                "popular_badge": False,
                "customization_count": None,
                "image_url": im.group(6) or None,
            })

        if menu_items:
            break

    # Assign categories by matching item names to DOM headings
    if menu_items:
        try:
            _assign_categories_from_dom(s, menu_items)
        except Exception:
            pass

    return menu_items


def _assign_categories_from_dom(s, menu_items):
    """Use DOM headings (H2) to assign categories to menu items."""
    js_code = """
    (() => {
        var cats = [];
        var h2s = document.querySelectorAll('h2');
        var skipCats = ['Reviews', 'Top Pairings', 'Trending', 'Nearby', 'Get to Know', 'Let Us Help', 'Doing Business', 'Top Dishes'];
        for (var i = 0; i < h2s.length; i++) {
            var h2 = h2s[i];
            var text = h2.textContent.trim();
            if (!text || text.length > 50) continue;
            var skip = false;
            for (var j = 0; j < skipCats.length; j++) {
                if (text.indexOf(skipCats[j]) >= 0) { skip = true; break; }
            }
            if (skip) continue;
            var rect = h2.getBoundingClientRect();
            cats.push({text: text, y: Math.round(rect.top + window.scrollY)});
        }
        return JSON.stringify(cats);
    })()
    """
    raw = s.js(js_code)
    if not raw:
        return
    categories = json.loads(raw)
    if not isinstance(categories, list):
        return
    categories = [cat for cat in categories if isinstance(cat, dict)]

    # Get Y positions of H3 elements (menu item names)
    names_str = json.dumps([m["item_name"] for m in menu_items[:100]])
    js2 = f"""
    (() => {{
        var targetNames = {names_str};
        var positions = {{}};
        var h3s = document.querySelectorAll('h3');
        for (var i = 0; i < h3s.length; i++) {{
            var text = h3s[i].textContent.trim();
            for (var j = 0; j < targetNames.length; j++) {{
                if (text === targetNames[j] || targetNames[j].indexOf(text) >= 0 || text.indexOf(targetNames[j]) >= 0) {{
                    var rect = h3s[i].getBoundingClientRect();
                    positions[targetNames[j]] = Math.round(rect.top + window.scrollY);
                    break;
                }}
            }}
        }}
        return JSON.stringify(positions);
    }})()
    """
    raw2 = s.js(js2)
    if not raw2:
        return
    positions = json.loads(raw2)
    if not isinstance(positions, dict):
        return

    # Assign categories based on Y position
    for item in menu_items:
        y = positions.get(item["item_name"])
        if y is None:
            continue
        for cat in reversed(categories):
            if cat["y"] <= y:
                item["category"] = cat["text"]
                break


def extract_menu_from_dom(s):
    """Extract menu items via DOM scraping.

    Uber Eats: li elements with A$ prices. Text pattern:
      [#N most liked][Plus small/medium]ItemNameA$XX.XX [• rating% (count)]
    """
    js = """
    (() => {
        var items = [];
        var seen = {};
        var categoryPositions = [];

        var headings = document.querySelectorAll('h2, h3');
        for (var i = 0; i < headings.length; i++) {
            var h = headings[i];
            var text = (h.textContent || '').trim();
            if (!text || text.length > 60 || text.length < 2) continue;
            var rect = h.getBoundingClientRect();
            if (rect.bottom > 0 && rect.top < window.innerHeight * 20) {
                categoryPositions.push({text: text, y: rect.top});
            }
        }

        var lis = document.querySelectorAll('li');
        for (var j = 0; j < lis.length; j++) {
            var li = lis[j];
            var text = (li.textContent || '').trim();
            if (text.indexOf('A$') === -1 || text.length > 500 || text.length < 10) continue;

            var priceMatch = text.match(/A\\$\\d+\\.?\\d{0,2}/);
            if (!priceMatch) continue;
            var price = priceMatch[0];

            var name = text;
            name = name.replace(/#\\d+\\s*most liked/g, '');
            name = name.replace(/Plus (?:small|medium|large)\\s*/g, '');
            var cutIdx = name.indexOf('A$');
            if (cutIdx > 0) name = name.substring(0, cutIdx);
            name = name.replace(/\\s*[•·].*$/, '');
            name = name.replace(/\\s*\\d+%\\s*\\(\\d+\\)\\s*$/g, '');
            name = name.trim();

            if (!name || name.length < 2 || name.length > 120) continue;
            if (/^(Savings|Enjoy|Use by|Save \\d|Uber One|\\d+% off)/.test(name)) continue;
            if (/^\\d+%/.test(name) && name.length < 15) continue;

            var key = name + price;
            if (seen[key]) continue;
            seen[key] = true;

            var rect = li.getBoundingClientRect();
            var category = 'Unknown';
            for (var k = categoryPositions.length - 1; k >= 0; k--) {
                if (categoryPositions[k].y < rect.top) {
                    category = categoryPositions[k].text;
                    break;
                }
            }

            items.push({
                category: category,
                item_name: name,
                item_price: price,
                description: null,
                popular_badge: /most liked/i.test(text),
                customization_count: null,
                image_url: null,
            });
        }

        return JSON.stringify(items);
    })()
    """
    raw = s.js(js)
    try:
        return json.loads(raw) if raw else []
    except json.JSONDecodeError:
        return []


def extract_menu_items(s, platform, store_url):
    """Extract all menu items from a restaurant page.

    Primary: Parse Next.js embedded JSON (DoorDash).
    Fallback: DOM scraping via aria-labels and headings.
    """
    items = []

    # Primary: Next.js embedded data (DoorDash)
    if platform == "doordash":
        items = extract_menu_from_next_data(s)

    # Fallback: DOM scraping for any platform
    if not items:
        items = extract_menu_from_dom(s)

    return items


def scroll_down(s):
    s.js("window.scrollBy(0, window.innerHeight * 1.2)")
    time.sleep(random.uniform(*SCROLL_PAUSE))


def extract_menus_for_restaurants(s, platform, restaurants, checkpoint_path=None):
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

        s.goto(store_url)
        time.sleep(random.uniform(3.0, 5.0))

        # Check for blocks
        html = s.content()[:1000]
        if "Verify you are human" in html or "access denied" in html.lower():
            print(f"  BLOCKED. Waiting for Turnstile...")
            time.sleep(8)
            html = s.content()[:1000]
            if "Verify you are human" in html or "access denied" in html.lower():
                print(f"  Still blocked. Skipping store.")
                gate.record(403, blocked=True)
                continue

        gate.record(200)
        title = s.js("document.title")
        print(f"  Loaded: {title}")

        # Extract menu items — try multiple scrolls for lazy-loaded content
        scrolls_no_new = 0
        total_new = 0
        for scroll_num in range(30):
            items = extract_menu_items(s, platform, store_url)
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

            # DoorDash Next.js: first pass gets everything, skip scrolling
            if platform == "doordash" and scroll_num == 0 and total_new > 0:
                break

            if scrolls_no_new >= MAX_SCROLLS_NO_NEW:
                break

            scroll_down(s)

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


def load_restaurant_input(path):
    data = json.loads(Path(path).read_text())
    if isinstance(data, list):
        return data, "doordash"
    if not isinstance(data, dict):
        raise ValueError("restaurant input must be a JSON object or array")
    restaurants = data.get("restaurants")
    if restaurants is None:
        restaurants = []
    if not isinstance(restaurants, list):
        raise ValueError("restaurant input field 'restaurants' must be an array")
    for row in restaurants:
        if not isinstance(row, dict):
            raise ValueError("restaurant input records must be objects")
    return restaurants, data.get("platform", "doordash")


def main():
    parser = argparse.ArgumentParser(description="Extract menus from restaurant pages")
    parser.add_argument("--input", required=True, help="Restaurant list JSON from enumerate_restaurants.py")
    parser.add_argument("--output", required=True, help="Output JSON file path")
    parser.add_argument("--resume", help="Checkpoint file to resume from")
    parser.add_argument("--limit", type=int, help="Limit number of restaurants to process")
    args = parser.parse_args()

    # Load restaurant list
    restaurants, platform = load_restaurant_input(args.input)

    if args.limit:
        restaurants = restaurants[:args.limit]
        print(f"Limited to {args.limit} restaurants")

    print(f"Processing {len(restaurants)} restaurants from {platform}")

    s = create_stealth_session(platform)
    try:
        authed = check_auth(s, platform)
        if not authed:
            print("WARNING: Not authenticated.")

        state = extract_menus_for_restaurants(s, platform, restaurants, args.resume)

        output = {
            "platform": platform,
            "extracted_at": datetime.now(timezone.utc).isoformat(),
            "summary": state.summary(),
            "menu_items": state._records,
        }
        Path(args.output).write_text(json.dumps(output, indent=2, default=str))
        print(f"\nSaved {len(state._records)} menu items to {args.output}")

        harvest_session_cookies(s, platform)
    finally:
        s.close()


if __name__ == "__main__":
    main()
