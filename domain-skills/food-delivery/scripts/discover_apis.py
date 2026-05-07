"""Phase 1: Discover internal JSON APIs on DoorDash and Uber Eats.

Uses the food-delivery stealth browser helper, then captures browser-observed
fetch/resource URLs while browsing search results and a restaurant menu page.
Identifies JSON API endpoints that can be replayed with plain HTTP + harvested
cookies.

Usage:
    .venv/bin/python3 scripts/discover_apis.py --platform doordash
    .venv/bin/python3 scripts/discover_apis.py --platform ubereats
    .venv/bin/python3 scripts/discover_apis.py --platform both
"""
import argparse, json, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib.stealth_session import (
    check_auth,
    create_stealth_session,
    harvest_http_headers,
    harvest_session_cookies,
    load_cookie_cache,
)


def dict_rows(rows):
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def discover_platform(s, platform):
    """Browse platform pages with network capture, discover JSON APIs."""
    from lib import doordash, ubereats
    mod = doordash if platform == "doordash" else ubereats

    print(f"\n{'='*60}")
    print(f"Discovering APIs on {platform}")
    print(f"{'='*60}")

    # Step 1: Create authenticated session
    authed = check_auth(s, platform)
    print(f"Auth check: {'logged in' if authed else 'NOT logged in'}")

    # Step 2: Navigate to search results and capture traffic
    search_queries = ["pizza", "chinese"]
    all_json_responses = []

    for query in search_queries:
        url = mod.search_url(query)
        print(f"\nNavigating to search: {url}")

        s.goto(url)

        time.sleep(4)

        # Check what loaded
        title = s.js("document.title")
        src = s.content()[:500]
        print(f"  Title: {title}")
        if "Verify you are human" in src or "access denied" in src.lower():
            print(f"  BLOCKED — waiting before continuing")
            time.sleep(5)

        # Capture page source for embedded data
        embedded = extract_embedded_json(s, platform)
        if embedded:
            all_json_responses.append({
                "source": "embedded",
                "url": url,
                "data_preview": str(embedded)[:1000],
            })
            print(f"  Found embedded JSON data ({len(str(embedded))} chars)")

        # Check network requests via performance API
        perf_urls = s.js("""
        (() => {
            return performance.getEntriesByType('resource')
                .filter(e => e.initiatorType === 'xmlhttprequest' || e.initiatorType === 'fetch')
                .map(e => e.name);
        })()
        """) or []
        print(f"  XHR/Fetch URLs observed: {len(perf_urls)}")
        for u in perf_urls:
            if "/api/" in u or "graphql" in u or "/v1/" in u or "/v2/" in u:
                print(f"    API: {u}")
                all_json_responses.append({
                    "source": "performance_api",
                    "url": u,
                    "method": "GET",
                })

        mod.random_delay(2, 4)

    # Step 3: Navigate to a restaurant menu page if we found a store
    store_urls = find_store_urls(s, platform)
    if store_urls:
        test_url = store_urls[0]
        print(f"\nNavigating to store: {test_url}")
        s.goto(test_url)
        time.sleep(5)

        title = s.js("document.title")
        print(f"  Title: {title}")

        # Check for embedded menu data
        embedded = extract_embedded_json(s, platform)
        if embedded:
            all_json_responses.append({
                "source": "embedded_store",
                "url": test_url,
                "data_preview": str(embedded)[:1000],
            })
            print(f"  Found embedded menu data ({len(str(embedded))} chars)")

        # Capture XHR/Fetch from menu page
        perf_urls = s.js("""
        (() => {
            return performance.getEntriesByType('resource')
                .filter(e => e.initiatorType === 'xmlhttprequest' || e.initiatorType === 'fetch')
                .map(e => e.name);
        })()
        """) or []
        for u in perf_urls:
            if "/api/" in u or "graphql" in u or "menu" in u.lower():
                print(f"    Menu API: {u}")
                all_json_responses.append({
                    "source": "performance_api_store",
                    "url": u,
                    "method": "GET",
                })

    # Step 4: Try to intercept fetch/XHR via JS override
    print(f"\nInjecting fetch interceptor...")
    s.js("""
    (() => {
        window.__captured_requests = [];
        const origFetch = window.fetch;
        window.fetch = function(...args) {
            window.__captured_requests.push({url: typeof args[0] === 'string' ? args[0] : args[0]?.url, method: args[1]?.method || 'GET', ts: Date.now()});
            return origFetch.apply(this, args);
        };
        const origXHR = XMLHttpRequest.prototype.open;
        XMLHttpRequest.prototype.open = function(method, url, ...rest) {
            window.__captured_requests.push({url: url, method: method, ts: Date.now()});
            return origXHR.call(this, method, url, ...rest);
        };
    })()
    """)

    # Navigate again with interceptor active
    url = mod.search_url("pizza")
    print(f"Re-navigating with interceptor: {url}")
    s.goto(url)
    time.sleep(5)

    captured = s.js("JSON.stringify(window.__captured_requests || [])")
    if captured:
        reqs = json.loads(captured)
        print(f"  Intercepted {len(reqs)} fetch/XHR requests")
        for r in dict_rows(reqs):
            u = r.get("url", "")
            if "/api/" in u or "graphql" in u or "/v1/" in u or "/v2/" in u:
                all_json_responses.append({
                    "source": "js_intercept",
                    **r,
                })
                print(f"    Intercepted API: {r.get('method')} {u}")

    # Step 5: Harvest cookies for HTTP replay
    cookie_count = harvest_session_cookies(s, platform)
    headers = harvest_http_headers(s)
    print(f"\nHarvested {cookie_count} cookies for HTTP replay")

    # Step 6: Try HTTP replay on discovered endpoints
    api_endpoints = [e for e in dict_rows(all_json_responses) if e.get("source") != "embedded"]
    http_results = try_http_replay(api_endpoints, platform, headers)
    all_json_responses.extend(http_results)

    # Step 7: Save results
    output_path = Path(__file__).parent / "lib" / f"api_discovery_{platform}.json"
    output = {
        "platform": platform,
        "authenticated": authed,
        "api_endpoints": dedup_endpoints(all_json_responses),
        "http_headers": headers,
        "cookie_file": str(Path(__file__).parent.parent / ".private-data" / f"{platform}_cookies.json"),
    }
    output_path.write_text(json.dumps(output, indent=2, default=str))
    print(f"\nSaved discovery to {output_path}")

    # Summary
    apis = [e for e in output["api_endpoints"] if e.get("http_replay_ok")]
    if apis:
        print(f"\nFOUND {len(apis)} API endpoint(s) that work via HTTP replay:")
        for a in apis:
            print(f"  {a.get('method', 'GET')} {a.get('url', '')[:100]}")
    else:
        print(f"\nNo HTTP-replayable APIs found. Will use DOM extraction path.")

    return output


def extract_embedded_json(s, platform):
    """Extract __NEXT_DATA__ or similar embedded JSON from page source."""
    return s.js("""
    (() => {
        try {
            if (document.getElementById('__NEXT_DATA__')) {
                return JSON.parse(document.getElementById('__NEXT_DATA__').textContent);
            }
        } catch(e) {}
        try {
            // Look for large script tags with JSON data
            const scripts = document.querySelectorAll('script[type="application/json"], script#__NEXT_DATA__');
            for (const s of scripts) {
                try {
                    const data = JSON.parse(s.textContent);
                    if (data && typeof data === 'object') return data;
                } catch(e) {}
            }
        } catch(e) {}
        return null;
    })()
    """)


def find_store_urls(s, platform):
    """Find restaurant URLs from current search results page."""
    links = s.js("""
    (() => {
        const links = document.querySelectorAll('a[href*="/store/"]');
        return [...new Set([...links].map(a => a.href))];
    })()
    """) or []
    print(f"  Found {len(links)} store links on page")
    return links[:3]


def try_http_replay(endpoints, platform, headers):
    """Try to fetch discovered API endpoints via plain HTTP with harvested cookies."""
    import urllib.request

    results = []
    cookies = dict_rows(load_cookie_cache(platform))
    if not cookies:
        return results

    cookie_str = "; ".join(
        f"{c['name']}={c['value']}"
        for c in cookies
        if c.get("name") and c.get("value") is not None
    )
    headers["Cookie"] = cookie_str

    seen_urls = set()
    for ep in dict_rows(endpoints):
        url = ep.get("url", "")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        if not url.startswith("http"):
            continue

        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                ct = resp.headers.get("Content-Type", "")
                body = resp.read(5000).decode("utf-8", errors="replace")
                is_json = "json" in ct or body.strip().startswith("{") or body.strip().startswith("[")
                results.append({
                    "source": "http_replay",
                    "url": url,
                    "method": "GET",
                    "status": resp.status,
                    "content_type": ct,
                    "http_replay_ok": is_json,
                    "body_preview": body[:500] if is_json else None,
                })
                print(f"  HTTP replay: {resp.status} {ct[:50]} -> {url[:80]}")
        except Exception as e:
            results.append({
                "source": "http_replay",
                "url": url,
                "http_replay_ok": False,
                "error": str(e)[:200],
            })

    return results


def dedup_endpoints(endpoints):
    """Deduplicate endpoints by URL."""
    seen = set()
    deduped = []
    for ep in dict_rows(endpoints):
        url = ep.get("url", "")
        if url and url not in seen:
            seen.add(url)
            deduped.append(ep)
    return deduped


def main():
    parser = argparse.ArgumentParser(description="Discover JSON APIs on food delivery platforms")
    parser.add_argument("--platform", choices=["doordash", "ubereats", "both"], required=True)
    args = parser.parse_args()

    platforms = ["doordash", "ubereats"] if args.platform == "both" else [args.platform]

    for platform in platforms:
        s = create_stealth_session(platform)
        try:
            discover_platform(s, platform)
        finally:
            try:
                s.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
