# Coverage Accounting — Completeness Metrics for Multi-Stage Crawls

Use this when building a crawler that tracks how much of the available data it has
collected. The core problem: coverage metrics have non-obvious edge cases that
produce misleading ratings. A "LOW" rating may mean the crawl is incomplete, or it
may mean the accounting is wrong.

This document covers the math. For the broader coverage problem (why fields go
missing, how to detect it), see `extraction-coverage.md`.

## The 0/0 problem

When a category or collection has 0 expected items and 0 collected items, the
coverage percentage is undefined. The naive formula:

```
pct = collected / expected * 100
```

divides by zero. Common wrong answers:

| Approach | Result | Why it's wrong |
|----------|--------|----------------|
| `0 if expected == 0` | 0% = LOW | Reports failure when nothing was expected |
| `100 if expected == 0` | 100% = HIGH | Reports success even when expected is unknown |
| Skip the category | not reported | Hides potentially problematic categories |

The correct answer depends on what "0 expected" means:

- **Confirmed empty** (the count API returned 0 for valid parameters): coverage
  is 100%. Nothing was there, nothing was missed.
- **Unknown** (the count API failed, returned an error, or wasn't called):
  coverage is indeterminate. Don't report a percentage; flag it for investigation.

**Implementation:**

```python
if expected == 0 and collected == 0:
    # Distinguish confirmed-empty from unknown
    if count_api_succeeded:
        pct = 100.0  # Confirmed empty
    else:
        pct = None   # Unknown — flag for investigation
elif expected == 0:
    pct = 0.0  # Collected items with 0 expected — count mismatch, investigate
else:
    pct = collected / expected * 100
```

When `pct is None`, the coverage report should show `"coverage_rating": "UNKNOWN"`
rather than forcing it into HIGH/MEDIUM/LOW.

## Additive vs overwrite expected counts

When a crawler processes multiple sub-collections under the same category, the
expected count must accumulate across sub-collections. The common pattern:

```python
# Wave 3-4: process multiple denominations per category
for denomination in denominations:
    expected = count_api(denomination)
    # WRONG: overwrites previous denomination's count
    accountant.record_expected(category, expected)
    # RIGHT: accumulates
    accountant.record_expected(category, expected)
```

If `record_expected` uses assignment (`=`), only the last denomination's count
survives. If it uses addition (`+=`), counts accumulate correctly.

**The fix:** Make the accumulation method explicit in the accountant's API:

```python
def record_expected(self, key: str, count: int) -> None:
    """Additive — call once per sub-collection."""
    self.expected[key] = self.expected.get(key, 0) + count
```

Then callers don't need to do manual arithmetic before calling the method.

## Dedup statistics: count disjoint events

When tracking deduplication across multiple passes (main pagination, coverage probes,
different sort modes), each dedup event should be counted exactly once.

**The trap:** Combining dedup counts from different sources that overlap:

```python
# WRONG: both terms count the same dedup events
total_deduped = (len(seen_ids) - collected) + sum(accountant.deduped.values())
```

Here, `len(seen_ids) - collected` already IS the total dedup count. Adding
`sum(accountant.deduped.values())` double-counts.

**The fix:** Pick one source of truth for the global total:

```python
# RIGHT: seen_ids is the canonical set, its excess over collected IS the dedup count
total_deduped = len(seen_ids) - collected
```

The per-category breakdowns in `accountant.deduped` are useful for reporting but
must not be summed into the global total alongside the set-based calculation.

## When "0 expected" means "wrong parameters"

A count API returning 0 is ambiguous. It could mean:
- (a) The category genuinely has no offers
- (b) The query parameters are wrong (wrong `brand_id`, `service_id`, `region_id`)
- (c) The API is erroring silently (returning 0 instead of an error)

Under the open-world assumption, you cannot distinguish these from the count alone.

**What to do:** When a count returns 0, log it as an investigation point rather
than silently skipping:

```python
if expected == 0:
    # Don't just skip — record and flag
    print(f"  Collection '{name}': 0 expected (may be empty or wrong params)", ...)
    accountant.record_collected(key, 0)
    continue
```

If the crawler has an alternative way to verify (e.g., try a bare search without
filters, or check a different API endpoint), do that before concluding the category
is empty. If no alternative exists, the coverage report should flag it:

```json
{
  "category": "google-ai-accounts",
  "expected_offers": 0,
  "collected_offers": 0,
  "coverage_pct": null,
  "coverage_rating": "UNKNOWN",
  "coverage_notes": "0 expected — could not verify if category is genuinely empty"
}
```

## Overall coverage rating

When aggregating across categories, the overall rating should be determined by the
worst category, not by the average. A crawl that achieves 100% on 10 categories but
0% on 1 category is not 91% complete — it's incomplete on that one category.

**Rating levels:**

| Rating | Threshold | Meaning |
|--------|-----------|---------|
| HIGH | >= 97% | Effectively complete |
| MEDIUM | >= 90% | Minor gaps, acceptable for analysis |
| LOW | < 90% | Significant gaps, investigation needed |
| UNKNOWN | N/A | Coverage indeterminate (0/0 with failed count) |

The overall rating is the worst rating across all categories, with UNKNOWN treated
as MEDIUM (not clearly broken, but not verifiable).

## Cross-references

- `extraction-coverage.md` — the broader coverage problem, tri-state fields, selector
  discovery, field triage
- `api-schema-audit.md` — verifying API response schemas, data threading between
  crawl waves
