"""Phase 2: Enumerate all restaurants on DoorDash or Uber Eats.

Uses SeleniumBase UC Mode with DOM extraction. Scrolls through search results
to discover restaurants, extracting metadata from each card.

Usage:
    .venv/bin/python3 scripts/enumerate_restaurants.py --platform doordash --query "pizza" --output restaurants.json
    .venv/bin/python3 scripts/enumerate_restaurants.py --platform ubereats --query "chinese" --output restaurants.json
    .venv/bin/python3 scripts/enumerate_restaurants.py --platform doordash --query "pizza" --output restaurants.json --resume checkpoint.json
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
MAX_SCROLLS_TOTAL = 80


def extract_restaurants_generic(sb, platform):
    """Extract restaurant data from whatever cards are visible on the page."""
    base_url = "https://www.doordash.com" if platform == "doordash" else "https://www.ubereats.com"

    # Build JS with platform/base_url baked in. Use bare return (no arrow func).
    js = """
    var results = [];
    var seen = {};
    var baseUrl = BASEURL;
    var platform = PLAT;

    var storeLinks = document.querySelectorAll('a[href*="/store/"]');
    var storeData = {};

    for (var i = 0; i < storeLinks.length; i++) {
        var link = storeLinks[i];
        var href = link.getAttribute('href') || '';
        var text = link.textContent.trim();
        var storeId = null, slug = null;

        var m = href.match(/\\/store\\/(\\d+)/);
        if (m) storeId = m[1];

        if (!storeId) {
            m = href.match(/\\/store\\/([\\w-]+?)-(\\d+)/);
            if (m) { slug = m[1]; storeId = m[2]; }
        }

        if (!storeId) {
            m = href.match(/\\/store\\/([^\\/]+)\\/([^\\/]+)/);
            if (m) { slug = m[1]; storeId = m[2]; }
        }

        if (!storeId) continue;

        if (!storeData[storeId] || text.length > (storeData[storeId].text || '').length) {
            storeData[storeId] = {href: href, text: text, slug: slug};
        }
    }

    var ids = Object.keys(storeData);
    for (var j = 0; j < ids.length; j++) {
        var storeId = ids[j];
        var data = storeData[storeId];
        var text = data.text;

        var name = text.split(/[•]/)[0].trim();
        name = name.replace(/\\d\\.\\d\\s*\\(\\d+\\+\\).*$/, '').trim();
        if (!name) name = null;

        var ratingMatch = text.match(/(\\d\\.\\d)/);
        var rating = ratingMatch ? parseFloat(ratingMatch[1]) : null;

        var timeRange = text.match(/(\\d+)\\s*-\\s*(\\d+)\\s*min/i);
        var timeSingle = text.match(/(\\d+)\\s*min/i);
        var dtMin = timeRange ? parseInt(timeRange[1]) : (timeSingle ? parseInt(timeSingle[1]) : null);
        var dtMax = timeRange ? parseInt(timeRange[2]) : dtMin;

        var feeMatch = text.match(/\\$(\\d+\\.\\d{2})/);
        var freeDelivery = /\\$0 delivery|free delivery/i.test(text);
        var deliveryFee = feeMatch ? parseFloat(feeMatch[1]) : (freeDelivery ? 0.0 : null);

        var promoMatch = text.match(/(\\d+%\\s*off|buy \\d+ get \\d+|\\$\\d+ off)/i);
        var promoBadge = promoMatch ? promoMatch[0] : null;

        results.push({
            platform: platform,
            store_id: storeId,
            slug: data.slug || null,
            url: baseUrl + data.href,
            name: name,
            rating: rating,
            delivery_time_min: dtMin,
            delivery_time_max: dtMax,
            delivery_fee: deliveryFee,
            promo_badge: promoBadge,
            discovered_at: new Date().toISOString(),
        });
    }

    return JSON.stringify(results);
    """.replace("BASEURL", json.dumps(base_url)).replace("PLAT", json.dumps(platform))

    raw = sb.execute_script(js)
    try:
        return json.loads(raw) if raw else []
    except json.JSONDecodeError:
        return []


def scroll_down(sb):
    """Scroll down to trigger lazy loading."""
    sb.driver.execute_script("window.scrollBy(0, window.innerHeight * 1.5);")
    time.sleep(random.uniform(*SCROLL_PAUSE))


def enumerate_platform(sb, platform, queries, checkpoint_path=None):
    """Enumerate restaurants for a platform by searching and scrolling."""
    mod = doordash if platform == "doordash" else ubereats
    state = CrawlState(key_field="store_id")

    if checkpoint_path and Path(checkpoint_path).exists():
        state = CrawlState.load(checkpoint_path)
        print(f"Resumed from checkpoint: {state.summary()}")

    gate = SafetyGate(max_requests=200, max_seconds=1800)

    for query in queries:
        if not gate.ok():
            print(f"Safety gate limit reached: {gate.summary()}")
            break

        url = mod.search_url(query)
        print(f"\nSearching: {query} -> {url}")

        try:
            sb.driver.get(url)
        except Exception:
            sb.uc_open_with_reconnect(url, 4)

        time.sleep(random.uniform(*PAGE_DELAY))

        # Check for blocks
        title = sb.get_title()
        src = sb.driver.page_source[:1000]
        if "Verify you are human" in src or "access denied" in src.lower():
            print(f"  BLOCKED. Trying captcha click...")
            sb.uc_gui_click_captcha()
            time.sleep(5)
            title = sb.get_title()
            if "Verify you are human" in sb.driver.page_source[:1000]:
                print(f"  Still blocked. Skipping query.")
                gate.record(403, blocked=True)
                state.record_blocked(url, "captcha")
                continue

        print(f"  Page loaded: {title}")
        gate.record(200)

        # Scroll and extract
        scrolls_no_new = 0
        for scroll_num in range(MAX_SCROLLS_TOTAL):
            restaurants = extract_restaurants_generic(sb, platform)
            new = 0
            for r in restaurants:
                if state.add(r):
                    new += 1
            state.page_done(new)

            if new > 0:
                scrolls_no_new = 0
                if scroll_num % 5 == 0:
                    print(f"  Scroll {scroll_num}: {new} new, {len(state._records)} total")
            else:
                scrolls_no_new += 1

            if scrolls_no_new >= MAX_SCROLLS_NO_NEW:
                print(f"  Saturation: {MAX_SCROLLS_NO_NEW} scrolls with 0 new items")
                break

            scroll_down(sb)

        # Checkpoint after each query
        if checkpoint_path:
            state.save(checkpoint_path)

        print(f"  Query '{query}' done: {state.summary()}")
        mod.random_delay(*PAGE_DELAY)

    return state


def main():
    parser = argparse.ArgumentParser(description="Enumerate restaurants from food delivery platforms")
    parser.add_argument("--platform", choices=["doordash", "ubereats"], required=True)
    parser.add_argument("--query", nargs="+", default=["pizza", "chinese", "thai", "indian", "burgers", "sushi", "mexican", "italian", "healthy", "breakfast"],
                        help="Search queries to enumerate (default: 10 popular cuisines)")
    parser.add_argument("--output", required=True, help="Output JSON file path")
    parser.add_argument("--resume", help="Checkpoint file to resume from")
    args = parser.parse_args()

    from seleniumbase import SB

    with SB(uc=True, test=True) as sb:
        authed = create_sb_session(sb, args.platform)
        if not authed:
            print(f"WARNING: Not authenticated. Results may be limited.")

        state = enumerate_platform(sb, args.platform, args.query, args.resume)

        # Save final results
        output = {
            "platform": args.platform,
            "extracted_at": datetime.now(timezone.utc).isoformat(),
            "summary": state.summary(),
            "restaurants": state._records,
        }
        Path(args.output).write_text(json.dumps(output, indent=2, default=str))
        print(f"\nSaved {len(state._records)} restaurants to {args.output}")
        print(f"Summary: {json.dumps(state.summary(), indent=2)}")

        # Harvest fresh cookies for next phase
        harvest_session_cookies(sb, args.platform)


if __name__ == "__main__":
    main()
