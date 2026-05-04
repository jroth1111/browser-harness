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


def extract_menu_from_next_data(sb):
    """Extract menu items from DoorDash's Next.js embedded JSON.

    DoorDash embeds all menu data in self.__next_f.push() script tags.
    Parse the itemLists from the page source — no DOM scraping needed.
    """
    page_source = sb.driver.page_source

    # Find all self.__next_f.push calls containing itemLists
    pattern = r'self\.__next_f\.push\(\[1,"(.*?)"\]\)'
    menu_items = []

    for match in re.finditer(pattern, page_source, re.DOTALL):
        raw = match.group(1)
        try:
            decoded = raw.encode("utf-8").decode("unicode_escape")
        except (UnicodeDecodeError, UnicodeEncodeError):
            continue

        if "itemLists" not in decoded:
            continue

        # Extract itemLists array from the decoded string
        # Find "itemLists":[ and match brackets
        idx = decoded.find('"itemLists"')
        if idx == -1:
            continue

        # Find the opening [ after "itemLists":
        bracket_start = decoded.find("[", idx)
        if bracket_start == -1:
            continue

        # Count brackets to find matching ]
        depth = 0
        bracket_end = bracket_start
        for i in range(bracket_start, len(decoded)):
            if decoded[i] == "[":
                depth += 1
            elif decoded[i] == "]":
                depth -= 1
                if depth == 0:
                    bracket_end = i + 1
                    break

        json_str = decoded[bracket_start:bracket_end]
        try:
            item_lists = json.loads(json_str)
        except json.JSONDecodeError:
            continue

        for category_obj in item_lists:
            category = category_obj.get("title", "Unknown")
            # subtitle may contain item count like "10 items"
            for item in category_obj.get("items", []):
                name = item.get("name", "").strip()
                if not name:
                    continue

                price = item.get("displayPrice", "")
                if not price:
                    price = str(item.get("price", ""))

                menu_items.append({
                    "category": category,
                    "item_name": name,
                    "item_price": price,
                    "description": item.get("description", ""),
                    "popular_badge": bool(item.get("isPopular") or item.get("mostOrdered")),
                    "customization_count": None,
                    "image_url": item.get("imageUrl") or item.get("imageSrc") or None,
                })

        # Only need the first match with itemLists
        if menu_items:
            break

    return menu_items


def extract_menu_from_dom(sb):
    """Fallback: extract menu items via DOM scraping using aria-labels and headings."""
    js = """
    var items = [];
    var seen = {};
    var categoryPositions = [];

    var headings = document.querySelectorAll('h2, h3, h4, [role="heading"]');
    for (var i = 0; i < headings.length; i++) {
        var h = headings[i];
        var text = (h.textContent || '').trim();
        if (!text || text.length > 60 || text.length < 2) continue;
        if (h.tagName === 'H1') continue;
        var rect = h.getBoundingClientRect();
        if (rect.bottom > 0 && rect.top < window.innerHeight * 10) {
            categoryPositions.push({text: text, y: rect.top});
        }
    }

    var buttons = document.querySelectorAll('button[aria-label]');
    for (var j = 0; j < buttons.length; j++) {
        var btn = buttons[j];
        var name = btn.getAttribute('aria-label');
        if (!name || name.length < 2 || name.length > 120) continue;

        var text = btn.textContent || '';
        var priceMatch = text.match(/\\$\\d+\\.?\\d{0,2}/);
        var price = priceMatch ? priceMatch[0] : null;

        if (seen[name]) continue;
        seen[name] = true;

        var rect = btn.getBoundingClientRect();
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
            popular_badge: /most ordered|most liked/i.test(text),
            customization_count: null,
            image_url: null,
        });
    }

    if (items.length === 0) {
        var allEls = document.querySelectorAll('div, section, article, li');
        for (var m = 0; m < allEls.length; m++) {
            var el = allEls[m];
            var elText = el.textContent || '';
            if (!/\\$\\d+\\.?\\d{0,2}/.test(elText)) continue;
            if (elText.length > 2000 || elText.length < 5) continue;
            var children = el.children;
            var hasPrice = false, hasName = false;
            for (var n = 0; n < children.length; n++) {
                var ct = (children[n].textContent || '').trim();
                if (/^\\$\\d+\\.?\\d{0,2}$/.test(ct)) hasPrice = true;
                if (ct.length > 3 && ct.length < 100 && !ct.startsWith('$')) hasName = true;
            }
            if (!hasPrice || !hasName) continue;

            var elRect = el.getBoundingClientRect();
            var elCat = 'Unknown';
            for (var p = categoryPositions.length - 1; p >= 0; p--) {
                if (categoryPositions[p].y < elRect.top) {
                    elCat = categoryPositions[p].text;
                    break;
                }
            }

            var elName = null, elPrice = null, elDesc = null;
            var childTexts = [];
            for (var q = 0; q < children.length; q++) {
                var ct2 = (children[q].textContent || '').trim();
                childTexts.push(ct2);
                if (!elPrice && /^\\$\\d+\\.?\\d{0,2}$/.test(ct2)) elPrice = ct2;
                else if (!elName && ct2.length > 2 && ct2.length < 80 && !ct2.startsWith('$')) elName = ct2;
            }
            for (var r = 0; r < childTexts.length; r++) {
                if (childTexts[r] !== elName && childTexts[r] !== elPrice && childTexts[r].length > 20) {
                    elDesc = childTexts[r];
                    break;
                }
            }

            if (!elName) continue;
            var key = elName + elPrice;
            if (seen[key]) continue;
            seen[key] = true;
            items.push({
                category: elCat,
                item_name: elName,
                item_price: elPrice,
                description: elDesc,
                popular_badge: /most ordered|most liked/i.test(elText),
                customization_count: null,
                image_url: null,
            });
        }
    }

    return JSON.stringify(items);
    """
    raw = sb.driver.execute_script(js)
    try:
        return json.loads(raw) if raw else []
    except json.JSONDecodeError:
        return []


def extract_menu_items(sb, platform, store_url):
    """Extract all menu items from a restaurant page.

    Primary: Parse Next.js embedded JSON (DoorDash).
    Fallback: DOM scraping via aria-labels and headings.
    """
    items = []

    # Primary: Next.js embedded data (DoorDash)
    if platform == "doordash":
        items = extract_menu_from_next_data(sb)

    # Fallback: DOM scraping for any platform
    if not items:
        items = extract_menu_from_dom(sb)

    return items


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

        # Extract menu items — try multiple scrolls for lazy-loaded content
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

            # DoorDash Next.js: first pass gets everything, skip scrolling
            if platform == "doordash" and scroll_num == 0 and total_new > 0:
                break

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
