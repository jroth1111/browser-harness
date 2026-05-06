# API Data Source Audit — Finding and Using Structured Backends

Use this when building a domain skill for a site with unknown architecture. The core
problem: you write extractors against the first data source you find (usually HTML),
then discover a better source later — but don't fully migrate to it. Leftover code
fetches data you already have, uses wrong types, or drops fields the API actually
returns.

## The problem

Most web extraction follows a "discover, then build" pattern:

1. Load the page, look at the HTML/DOM
2. Write extraction code against what you see
3. Discover an API or JSON data source
4. Migrate to the API
5. **Stop here** — don't finish the migration

Step 5 is where silent failures accumulate. The migration is incomplete:
- Old code fetches data that the new source already provides
- Extraction schema ignores API fields that weren't in the original HTML
- Field types assumed from the HTML don't match the API's actual types
- URL construction uses patterns from the old source, not the actual site URLs

**What it looks like:** The extractor works — it returns data. But it makes redundant
API calls, drops structured fields that the API returns for free, or crashes on
unexpected types. These are silent coverage gaps, not visible errors.

## Source discovery: check for preloaded static assets

The standard discovery order in `data-source-exploration.md` checks `<script>` tags
for embedded JSON. There's another source category: **static JSON assets that the
site preloads independently of any page's HTML.**

These appear when:
- The site is a SPA (Single Page Application) that loads a shell HTML page and
  populates content client-side
- The shell HTML contains `<link rel="preload">` or `<script src="...">` pointing to
  a static JSON file
- The JSON file is served from a CDN or static asset domain (e.g., `assets.site.com`)
- The file contains the full catalog/index of categories, products, or configuration

**How to recognize it:** If the HTML is suspiciously small (< 10KB) with no content
matching what the page displays, and you see fetch/XHR requests to a separate domain
loading JSON, check if the page also preloads a static index. Look for:

```
<link rel="preload" href="https://assets.site.com/data/catalog.json" as="fetch">
<script> window.__INITIAL_DATA__ = fetch("https://cdn.site.com/index.json") </script>
```

Or just probe common static asset URLs:

```python
from helpers import http_get
import json

# Check for static catalog/category indexes
candidates = [
    "https://assets.site.com/offer/categories.json",
    "https://assets.site.com/data/catalog.json",
    "https://cdn.site.com/api/v1/index.json",
]
for url in candidates:
    try:
        raw = http_get(url, timeout=10.0)
        data = json.loads(raw)
        if isinstance(data, dict) and len(data) > 10:
            print(f"Found index: {url} ({len(data)} entries)")
    except Exception:
        pass
```

**When this matters:** Any SPA where category/navigation data is needed. The static
asset is faster, more complete, and doesn't require browser rendering. It's a
higher-tier source than HTML parsing or even API calls for discovery.

## Heterogeneous dict classification

When you find a JSON index (categories, products, navigation), don't assume all
entries have the same structure. Many sites maintain backward-compatible indexes where:

- **Rich entries** have full data (names, IDs, metadata)
- **Redirect entries** have only a pointer to the rich entry (a slug, a foreign key)
- **Legacy entries** have a subset of fields from an older API version

**The trap:** If you iterate the dict and process entries in order, redirect entries
may match your query first. You store their minimal data, then skip the rich entry
that has the same key because you've already "seen" it.

**The fix:** Two-pass classification:

```python
rich_entries = {}
redirect_entries = {}

for key, entry in index.items():
    if not isinstance(entry, dict):
        continue
    # Classify by structural signals, not by key format
    has_full_data = "service_id" in entry or "brand_id" in entry  # adapt per site
    has_redirect = "seo_term" in entry and not has_full_data

    if has_full_data:
        rich_entries[key] = entry
    elif has_redirect:
        redirect_entries[entry.get("seo_term", key)] = entry

# Process rich entries first — they have the data you need
for key, entry in rich_entries.items():
    # Extract using full field set
    ...
```

Classify by the **presence of structurally significant fields**, not by key format.
The key format (slug vs UUID vs numeric) is a convention that varies by site; the
field set is what determines whether the entry is useful.

## Data threading between crawl waves

When a crawler has multiple stages (discover categories → fetch details → paginate
offers), data discovered in early stages must be threaded forward to later stages.

**The trap:** Later stages re-fetch data that was already available. Example: Wave 1
discovers categories with `brand_id` and `service_id`. Wave 2 calls `keyword_info`
API to fetch the same `brand_id` — wasting a request and potentially getting different
or missing data.

**The fix:** After each wave, inventory what data is now available. Later waves
check this inventory before making API calls:

```python
# Wave 1 produces categories with brand_id and service_id
categories = client.search_categories(query)

# Wave 2: use what we have, fall back only if missing
for cat in categories:
    brand_id = cat.get("brand_id", "")
    service_id = cat.get("service_id", "")

    if not brand_id:
        brand_id = client.get_keyword_info(cat["seo_term"]).get("brand_id", "")

    if not service_id:
        all_services = client.get_service_types()
        # ... filter to relevant service
```

**When this matters:** Any multi-stage crawl where early stages discover metadata
IDs, tokens, or configuration that later stages need. The alternative (re-fetching)
works but wastes requests and may fail differently than the primary source.

## API schema comparison

After discovering an API endpoint, compare its response fields against your extraction
schema before writing extraction code.

**The trap:** You write extraction code for a subset of fields, and the API returns
many more. The extra fields are silently dropped. Later you discover you needed them
but they were never captured.

**The fix:** Capture one API response, dump its field names, and compare against
your schema:

```python
# After first API call, log all available fields
response = client.search_offers(...)
if isinstance(response, list) and response:
    first_offer = response[0]
    available_fields = sorted(first_offer.keys())
    print(f"API fields: {available_fields}")

    # Compare against your extraction schema
    your_fields = {"title", "price", "seller_name", ...}
    missing_from_schema = set(available_fields) - your_fields
    if missing_from_schema:
        print(f"Fields not in schema: {missing_from_schema}")
```

Add a **schema evolution check** that runs on the first response of each crawl
session and logs any unknown fields. This catches API changes that would otherwise
produce silent data loss.

## Verification checklist

After implementing extraction against an API:

1. **Field type check:** For each extracted field, print `type(value)` for the first
   response. Common mismatches: string vs int for IDs, string vs float for prices,
   list vs dict for nested objects.
2. **URL check:** Construct a URL from your code, compare it against the actual URL
   the site uses for the same page. Check all query parameters are present.
3. **Coverage check:** Compare the count of items your extractor returns against a
   count declared by the API or page. See `extraction-coverage.md` for coverage probes.
4. **Schema check:** Run the schema evolution detector on the first response. If it
   reports unknown fields, decide whether to extract them or explicitly exclude them.

## Cross-references

- `data-source-exploration.md` — source discovery order, embedded JSON extraction
- `extraction-coverage.md` — coverage probes, field triage, four-state semantics
- `domain-skills/surface-map-pattern.md` — primitive registry, verification probes
