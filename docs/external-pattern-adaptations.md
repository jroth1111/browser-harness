# External Pattern Adaptations

This records method-level ideas borrowed from public browser automation and
extraction projects. It is intentionally not a recipe for copying target-site
logic. Full extraction can be a coverage objective, but the constraint is the
method: use authorized browser-visible surfaces, bounded crawls, consent gates,
and receipts.

## Sources Reviewed

| Source | Evidence used | Adapt | Reject |
|---|---|---|---|
| [cbonoz/tinderscrapy](https://github.com/cbonoz/tinderscrapy) | Scrapy spider with page limits, next-page traversal, item fields, and image URL filtering. | Saturation and dedupe ledgers, field contracts, explicit pagination/next-link accounting. | Treating a tiny page limit as proof of full extraction, and silent skip paths without coverage receipts. |
| [EatMyA/tinder-scraper](https://github.com/EatMyA/tinder-scraper) | Puppeteer flow that waits for selectors, observes network responses, tracks match processing state, and records storage. | Trace receipts for source choice, bounded waits, request status checks, stale-pane recovery, and per-record source provenance. | Private API promotion for dating platforms, request interception that masks page behavior, and mutating DOM to mark progress. |
| [frederikme/TinderBotz](https://github.com/frederikme/TinderBotz) | Selenium flow with profile reuse, popup handling, scroll-to-bottom loops, dedupe of chat IDs, session counters, and retry after missing tabs. | Popup/halt detection, profile identity lock, scroll saturation, action counters, and stop-on-block policy. | `undetected_chromedriver`, proxy defaults, credential automation, account setting mutations, and raw browser profile/session artifacts. |

## Project Adaptation

| Pattern | Browser-harness home | Robustness rule |
|---|---|---|
| Trace receipt | `source_receipts.py`, `interaction-skills/source-selection-receipts.md` | Every promoted source decision records origin, auth state, method, status, confidence, safety flags, and blocked state. |
| Field contract | `extraction_contracts.py`, `interaction-skills/extraction-coverage.md` | Extracted rows distinguish `present`, `missing`, `unobservable`, and `error` rather than collapsing gaps into blanks. |
| Stale-pane guard | `helpers.fetch(..., source="browser")`, `Response.reason`, `Response.block` | Browser-visible extraction must return an explicit blocked/timeout/error reason instead of empty success. |
| Profile identity lock | `interaction-skills/session-continuity.md`, `redaction_scan.py` | Reuse logged-in browser state only through redacted manifests and same-profile verification; never export raw cookies or auth tokens. |
| Halt detection | `SafetyGate`, `CrawlState.receipt(...)`, domain safety docs | CAPTCHA, auth redirects, account warnings, repeated blocks, and repeated selector failures are terminal states for automation. |
| Saturation and dedupe ledger | `CrawlState` | Full extraction attempts track new/deduped/blocked/missing-key records and stop only on coverage, saturation, or safety limits. |
| Selector-drift fixture | `domain_skill_maturity.py`, domain surface maps | Domain skills that claim live readiness need field-tested selectors, fixtures, receipts, or explicit lower maturity tiers. |

## Dating Skill Comparison

The local dating skill already has the correct safety posture:

- `domain-skills/dating/safety.md` forbids direct Tinder API calls, token reads,
  CAPTCHA bypass, and unconfirmed message sends.
- `domain-skills/dating/surface-map.json` allows full chat extraction only as a
  slow UI-only crawl with checkpointing and saturation evidence.
- `domain-skills/dating/overview.md` keeps the primary mechanism in the
  browser-harness conversation loop, with screenshots and DOM reads as evidence.

This robustness pass keeps those constraints and generalizes the machinery into
shared helpers: source receipts, four-state extraction contracts, crawl receipts,
redacted session scans, and package/release proof. It does not import unsafe
dating-bot practices into the shared harness.

## Ban-Safe Rejection List

Do not adapt these patterns from external projects:

- automated account creation, credential entry, OTP handling, or profile setup;
- private API token reuse or localStorage/cookie extraction;
- stealth browser defaults, proxy rotation, CAPTCHA solving, or block bypass;
- deleting lock files or profiles to force a session open;
- raw browser profile, cookie, HAR, or generated-output publication;
- unbounded rapid traversal without saturation, pacing, halt detection, and
  checkpoint receipts.
