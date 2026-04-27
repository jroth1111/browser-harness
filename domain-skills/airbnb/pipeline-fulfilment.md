# Airbnb.com.au - Pipeline Fulfilment Review

Use this file as the current evidence ledger for the host intelligence data
pipeline. Status is field-level: a source can be high coverage for fields Airbnb
exposes publicly while still carrying explicit nulls for fields Airbnb does not
show for a listing.

## Current status

| Pipeline stage | Status | Evidence |
|---|---:|---|
| Live host listing inventory | High | 27 active listings, 70 total seen, required fields present: address, beds, bedrooms, bathrooms, max guests. |
| Per-listing Insights | High | 27 listings x 16 routes; 2,025 summary rows; 26,784 daily DAY chart rows; 11,232 monthly trend rows; 0 failures. |
| Public competitor collection | High | 27 target listings, 108 search contexts, 1,296 price rows, 864 target-comp links, 120 comp snapshots; 0 failures. Follow-up scroll smoke verified bounded rank-window metadata and logged-out guard. |
| Own listing guest-visible audit | High | Dedicated `scripts/collect_own_public.py`; 27 logged-out public listing-page content audits; 27 logged-out search/rank contexts; 0 failures. Follow-up scroll smoke verified logged-out guard, result limit, and search scroll metadata. |
| Reviews / rating distribution | High for public-visible fields | 27 own-listing review rows; listing-level review count captured for all 27; overall rating captured where Airbnb exposes listing average; star distribution/category fields captured where Airbnb exposes them or visible individual review stars support the estimate. `rating_display_state`, `star_distribution_source`, `star_distribution_confidence`, `visible_individual_review_star_count`, and `rating_category_source` distinguish absent or partial Airbnb widgets from parser failure. Host aggregate reviews are explicitly excluded from listing-level review count/rating. |
| Session continuity | Medium-high | Fresh-profile Airbnb auth restore verified; Lightpanda auth restore documented, but headful Chrome remains canonical for private host extraction. |
| API-vs-browser source classification | High | Listings and Insights use backend APIs first; browser UI used only for missing/private rendered fields. |

## Review outcomes

- Own public rank/content is no longer partial. It has an executable logged-out
  collector, schema tables, receipts, and private JSON/CSV artifacts.
- Review/rating distribution is no longer partial for public-visible data. The
  collector distinguishes listing-level review signals from host-level aggregate
  signals and records why ratings, star distributions, or category widgets are
  absent or incomplete.
- Multi-page/lazy search ranking must never use an owner session. The public
  rank collectors refuse to run when known Airbnb authenticated-session cookies
  are present.
- Rank observations are bounded-window observations. Store result limit,
  scroll depth, and logged-in state with every row; do not treat a missing row in
  the collected window as proof of global invisibility.

## Remaining evidence gaps

- Public rank is still a sampled, date-specific observation, not a permanent
  platform ranking. Repeat it across dates, guests, stay lengths, devices, and
  time to build a stable trend.
- Airbnb does not expose listing-level overall rating or category distribution
  for every listing, especially no-review and low-review listings. Preserve nulls
  with `rating_display_state` instead of filling from host aggregate reviews.
- Lightpanda remains a capability candidate only after it proves field-level
  parity for the exact public search/listing fields.
