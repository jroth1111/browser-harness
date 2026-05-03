# Scripts

## search.py

z2u.com exhaustive search orchestrator.

**Commands:**

| Command | Role | Reads | Produces |
|---------|------|-------|----------|
| `plan` | Generate phased search plan with JS snippets | query string | Text plan + JS snippets |
| `extract-js` | Print JS extraction snippets for CDP | flags | JavaScript (stdout) |
| `merge` | Filter and export to CSV | JSON dump | CSV file |

**Invocation:**

```bash
# Full search plan
python3 search.py plan "google" --filter "ultra" --output results.csv

# JS snippet (execute via js())
python3 search.py extract-js --categories    # search page
python3 search.py extract-js --products      # category page (pass category name as arg)
python3 search.py extract-js --detail        # product detail page (pass category name as arg)
python3 search.py extract-js --dump          # dump accumulated localStorage
python3 search.py extract-js --reset         # clear localStorage

# Post-processing
python3 search.py merge dump.json --filter "ultra" --output results.csv
```

**CSV columns:** `product_name, category, description, seller, price, url, region, platform, delivery_time, stock, sold_out, type`

**Refusal conditions:** Browser not connected, Cloudflare challenge unsolvable.
