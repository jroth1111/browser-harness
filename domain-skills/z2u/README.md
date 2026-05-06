# z2u.com — Exhaustive Product Search

z2u.com digital marketplace — exhaustive multi-category product search returning CSV with product names, descriptions, sellers, and prices.

## Quick Start

```bash
# Plan an exhaustive search
python3 agent-workspace/domain-skills/z2u/scripts/search.py plan "google" --filter "ultra" --output results.csv

# Plan without filter (get everything)
python3 agent-workspace/domain-skills/z2u/scripts/search.py plan "chatgpt" --output chatgpt_all.csv

# Get individual JS snippets
python3 agent-workspace/domain-skills/z2u/scripts/search.py extract-js --reset
python3 agent-workspace/domain-skills/z2u/scripts/search.py extract-js --categories
python3 agent-workspace/domain-skills/z2u/scripts/search.py extract-js --products
python3 agent-workspace/domain-skills/z2u/scripts/search.py extract-js --detail
python3 agent-workspace/domain-skills/z2u/scripts/search.py extract-js --dump

# Merge extracted JSON into filtered CSV
python3 agent-workspace/domain-skills/z2u/scripts/search.py merge products.json --filter "ultra" --output results.csv
```

## Backend

CDP (Chrome DevTools Protocol) required. z2u.com uses Cloudflare Turnstile which blocks HTTP scraping.

## How It Works

1. **Level 1**: Search for broad query → discover all category links with offer counts
2. **Level 2**: Open each category → paginate through all pages → extract product aggregations + individual seller offers
3. **Level 3** (optional): Visit product detail pages for full descriptions and seller lists
4. **Post**: Filter by relevance term → export CSV

## Files

- `overview.md` — URL patterns, DOM selectors, extraction JS, gotchas
- `scripts/search.py` — Orchestrator: JS snippets, merge/filter/CSV export
- `scripts/README.md` — Script documentation
