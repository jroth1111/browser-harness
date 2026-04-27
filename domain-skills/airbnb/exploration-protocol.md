# Airbnb.com.au - Exploration Protocol

Use this before building an Airbnb host report or adding new schema. Airbnb data
should be explored as primitives first, then composed into host decisions.

General source-exploration rules live in
`interaction-skills/data-source-exploration.md`. This file keeps the
Airbnb-specific source families, examples, and acceptance notes.

For market, competitor, or own-listing current-state capture, use
`workflows-current-state.md` after this discovery protocol identifies which
sources and backends are available.

## Goal

Build a complete inventory of public, authenticated, exportable, and manual data
available for the specific host account, market, and listings. Do not assume that
all hosts have the same tools enabled.

## Airbnb backend strategy

| Source type | Preferred backend | Why |
|---|---|---|
| Public listing pages | Lightpanda if `diagnose_url_capability()` returns useful content | Fast DOM/text extraction |
| Public search pages | Lightpanda if price/rank/card text renders correctly; otherwise headful Chrome | Search cards can be dynamic and layout-dependent |
| Airbnb Help/Resource Centre pages | Lightpanda or direct HTTP when content is static | Fast documentation refresh |
| Authenticated host UI | Persistent headful Chrome profile | Preserves login, device trust, MFA, and full browser surface |
| Authenticated exports/downloads | Persistent headful Chrome profile for download; parser after download | Reliable source files |
| Same-domain authenticated fetches | `fetch_with_browser_session()` after headful seed | Faster than rendering each private page, but only after session is valid |

Do not type Airbnb credentials. If login, MFA, or account selection is required,
stop and ask the user to complete it in the browser.

## Airbnb auth-state policy

Use the least-privileged Airbnb state that can answer the question.

- Guest-visible public sources must be collected logged out by default. This
  includes public search results, public listing pages, public reviews, public
  host responses, public badges, amenities, rules, visible prices, and Help or
  Resource Centre pages.
- Do not restore or reuse the host auth bundle for public comp data just because
  it is available. Logged-in pages can personalize ranking, prices, language,
  currency, wishlists, account prompts, and host-specific surfaces, which makes
  guest-market observations less comparable.
- Use logged-in state only for sources that cannot be accessed logged out:
  host dashboard, Insights, earnings, reservations, calendar controls, pricing
  settings, rule-sets, messages, tasks, listing editor, tax/levy/account fields,
  exports, and Airbnb-selected similar-listing context inside host tools.
- If comparing guest-visible behavior for logged-out vs logged-in users is the
  explicit question, run two separate observations and store them as separate
  search contexts. Never merge logged-out and logged-in public observations into
  one comp set.
- Every observation receipt must record `logged_in_flag`; public comp receipts
  should normally have `logged_in_flag: false`.

## Exploration phases

### 1. Public capability pass

For each public URL family, test the cheapest backend first:

```python
diag = diagnose_url_capability(
    "https://www.airbnb.com.au/rooms/ROOM_ID",
    min_text=500,
    timeout=20,
)
print(diag["backend"]["kind"], diag["ok"], diag["reason"], diag["block"])
```

Record:

- backend kind
- URL tested
- useful text length
- block/challenge state
- fields visible
- extraction confidence
- whether Lightpanda is sufficient

Public URL families to test:

- listing page with no dates
- listing page with dates and guests
- search results by destination
- search results with map bounds
- search results with filters
- Help Centre pages
- Resource Centre pages

### 2. Public primitive inventory

For each public source, record the primitives before deriving metrics:

- listing ID / room ID
- title and location label
- capacity, bedrooms, beds, bathrooms
- rating, review count, badges/highlights
- visible total price and nightly component
- amenities and differentiator tags
- house rules and cancellation policy where visible
- availability and minimum-stay messages
- review text and public host responses
- photo count, hero subject, room/photo-tour signals where visible

### 3. Private capability pass

Use the user's persistent browser profile. Start with pages that expose exports:

- Earnings reports and CSV
- Calendar and iCal export
- Reservation details
- Listing editor/settings
- Insights
- Pricing and rule-sets
- Messages and scheduled quick replies
- Tasks and teams
- Reviews
- Regulations/tax fields
- Personal data export request/download when the user explicitly wants it

For each surface, record:

- URL or navigation path
- listing/account scope
- date filters
- export/download availability
- UI fields visible
- whether a structured file is available
- required user interaction
- session/cookie names only, never values

### 4. Network/API observation pass

Only after UI/export behavior is understood, inspect network requests for
structured payloads. Use `interaction-skills/network-requests.md` if needed.

Record request shape, endpoint path, response field names, auth requirements, and
whether the data is more reliable than UI text. Do not commit tokens, cookies,
headers, guest data, downloaded reports, or raw responses.

### 5. Data primitive registry

Every discovered primitive should map to:

- source family
- public/private scope
- backend suitability
- refresh cadence
- schema target
- confidence rules
- privacy class
- example host decision it supports

Use `data-inventory.md` as the canonical registry.

## Airbnb Lightpanda acceptance criteria

Lightpanda is acceptable for a source only when:

- `diagnose_url_capability()` returns `ok == True`.
- expected fields appear in `document.body.innerText` or DOM queries.
- price/rank/card ordering is stable enough for the task.
- no login, MFA, file download, or visual confirmation is required.
- sampled output matches a headful Chrome capture for the same URL context.

If any criterion fails, use persistent headful Chrome for exploration and record
the Lightpanda limitation.

## Airbnb private-session continuity

Before private exploration, read both `interaction-skills/session-continuity.md`
and `domain-skills/airbnb/session-continuity.md`. Store only session metadata and
capability receipts in the local ignored session store. The normal auth
continuity mechanism is the user's persistent browser profile, not checked-in
cookie files.
