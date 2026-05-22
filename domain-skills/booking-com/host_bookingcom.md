# Booking.com Extranet — Host Bookings And Invoices

Use this subskill when the user is a Booking.com host or co-host and wants to
log in at `https://admin.booking.com/` and download missing booking,
reservation, invoice, finance, payout, or statement data for all properties.

## Operating Posture

- Use a visible browser session. Booking.com Extranet is authenticated,
  tenant-scoped, and may require MFA or property/account selection.
- Do not type credentials, paste one-time codes, or store session cookies in
  this shared skill. If redirected to login, stop and ask the user to complete
  login in the browser.
- Treat exports and first-party downloadable documents as the authoritative
  source when they contain the needed fields. Use table scraping or API replay
  only to fill documented export gaps.
- Every run starts with a property inventory. "All missing data" means every
  visible property has been checked, including properties with no current
  reservations or no available invoice documents.

## Goal State

Create a private run directory containing:

- one property inventory for every visible Extranet property
- booking/reservation source exports or captures per property
- invoice/finance document exports or captures per property
- a source-hashed reconciliation ledger linking bookings to finance lines and
  payout-transfer evidence where the captured sources prove the relationship
- a coverage receipt that marks each property and data family as `complete`,
  `empty`, `partial`, or `blocked`

Suggested local layout:

```text
domain-skills/booking-com/.private-data/host-bookingcom/<run-id>/
  properties.json
  bookings/
  invoices/
  reconciliation_ledger/
  receipts/<run-id>-coverage.json
```

Keep `.private-data/` and `.session-store/` ignored and out of reusable docs.

## Browser Entry

Start from a fresh tab so the user can see and complete login:

```python
new_tab("https://admin.booking.com/")
wait_for_load()
print(page_info())
```

If the page is a login, MFA, passkey, consent, or account-selection step, pause
for the user. Continue only after `page_info()["url"]` is on
`https://admin.booking.com/` and the Extranet navigation is visible.

### Observed Entry Flow

Codex in-app Browser trace, 2026-05-22 Australia/Melbourne session:

- `https://admin.booking.com/` redirected to
  `https://account.booking.com/sign-in?...`.
- The page title was `Sign in to manage your property | Booking.com`.
- The sign-in page carried an `op_token` return parameter. Treat this as a
  transient auth artifact: record only `has_op_token: true`, never the token.
- The visible username field used `id="loginname"`, `name="loginname"`,
  `autocomplete="username"`, and placeholder text
  `Also known as "Login name" and "Login ID"`.
- A hidden password input with `id="hidden-password"`,
  `name="password"`, and `autocomplete="current-password"` was present before
  the password step. Do not use it to infer that password entry is ready.
- Stable unauthenticated links included `Having trouble signing in?`,
  `Partner Help`, `Create your partner account`, `Terms & Conditions`, and
  `Privacy Statement`.
- The `More` header button opened a menu with language selection only in this
  trace.

Stop at this boundary unless the user takes over and completes login/MFA. After
the browser returns to `admin.booking.com`, take a fresh screenshot and DOM
snapshot before looking for property switchers or finance/reservations routes.

### Authenticated Group Homepage Trace

Read-only authenticated curl and in-app Browser traces, 2026-05-22
Australia/Melbourne session:

- A valid host session returned HTTP 200 and title
  `Group homepage · Booking.com` for:
  `/hotel/hoteladmin/groups/home/index.html?lang=xu&ses=<redacted>`.
- The page was not a sign-in page (`contains_sign_in: false`).
- The group homepage is a multi-property surface. Stable labels included
  `All properties`, `Filter by status`, `Customize data`, `Customize view`, and
  `Download`.
- The property inventory filter field used
  `id="properties-free-text-search"` and placeholder
  `Filter by property ID, name, or location`.
- A global search input used `name="query"`, `autocomplete="off"`, and
  placeholder `Search`.
- Stable group-level navigation links were observed for:
  - `/hotel/hoteladmin/groups/home/index.html`
  - `/hotel/hoteladmin/groups/reservations/index.html`
  - `/hotel/hoteladmin/groups/reviews/index.html`
  - `/hotel/hoteladmin/groups/bulk/index.html`
  - `/hotel/hoteladmin/groups/opportunities/index.html`
  - `/hotel/hoteladmin/groups/analytics/market_insights.html`
- The group `bulk/index.html` page also returned authenticated HTTP 200 and
  title `Bulk Editing · Booking.com`.
- In the authenticated browser, the group homepage showed a location selector
  such as `<count> properties in <location>`, control tabs `Operations`,
  `Performance`, and `Settings`, and "Happening today" links to group
  reservations filtered by `dateType=BOOKING`, `dateType=ARRIVAL`, and
  `dateType=DEPARTURE`.
- The `Operations` table columns were `ID`, `Property`,
  `Status on Booking.com`, `Arrivals in next 48 hours`,
  `Departures in next 48 hours`, `Guest messages`, and
  `Booking.com messages`.
- Property rows linked to
  `/hotel/hoteladmin/extranet_ng/manage/index.html?...&hotel_id=<hotel_id>&hotel_account_id=<hotel_account_id>`.
  Some arrival/departure counters linked directly to
  `/hotel/hoteladmin/extranet_ng/manage/search_reservations.html?...&hotel_id=<hotel_id>&hotel_account_id=<hotel_account_id>`.
  Message counters linked to either `manage/inbox.html` or
  `manage/messaging/inbox.html`.
- A direct curl fetch of `groups/reservations/index.html` with the same captured
  cookie set did not prove an authenticated reservations body in this trace
  (`contains_sign_in: true`). Treat reservations as browser-verified only until
  a live authenticated browser trace or export response proves otherwise.
- A live browser navigation from the group homepage to
  `groups/reservations/index.html` redirected to
  `https://account.booking.com/auth-assurance...` with heading
  `Verify your identity` and text `Select a verification method to continue`.
  This is a hard user-action gate; do not bypass it or continue reservations
  tracing until the user completes verification in the visible browser.
- After the user completed the identity check, the same group reservations route
  rendered title `Reservations · Booking.com` at
  `/hotel/hoteladmin/groups/reservations/index.html?...&tlc=1`.
- The group reservations page had:
  - `Date of` select with `Reservation`, `Check-in`, and `Check-out`.
  - date-range input `id="peg-reservations-ranged"`.
  - `More filters`, `Show reservations`, `Print reservation list`, and
    `Download` buttons.
  - pagination select `id="peg-reservations-table-pagination"` with
    `Show 10 reservations`, `Show 30 reservations`, and
    `Show 50 reservations`.
  - table columns `Property ID`, `Property Name`, `Location`, `Guest name`,
    `Check-in`, `Check-out`, `Status`, `Total Payment`,
    `Commission and charges`, `Reservation Number`, and `Booked on`.
- Reservation detail links used
  `/hotel/hoteladmin/extranet_ng/manage/booking.html?...&hotel_id=<hotel_id>&res_id=<reservation_id>`.
- Selecting a property row opened a per-property dashboard at
  `/hotel/hoteladmin/extranet_ng/manage/home.html?...&hotel_id=<hotel_id>`.
  Its top navigation included `Home`, `Rates & availability`, `Promotions`,
  `Reservations`, `Property`, `Boost performance`, `Inbox`, `Guest Reviews`,
  `Finance`, and `Analytics`.
- The per-property dashboard `Reservations` link went to
  `/hotel/hoteladmin/extranet_ng/manage/search_reservations.html?...&hotel_id=<hotel_id>&source=nav&upcoming_reservations=1`.
- The per-property `Finance` menu can hydrate after the property dashboard
  loads. In this trace it exposed `Payout info`, `Documents and invoices`,
  `Reservations statement`, `Financial Overview`, `Finance Help`, and
  `Finance settings`.
- `Documents and invoices` opened
  `/hotel/hoteladmin/extranet_ng/manage/finance_invoices.html?...&hotel_id=<hotel_id>`
  with title `Invoices · Booking.com`.
- The invoices page showed a `Download all 2026 PDFs` action plus a document
  table with columns `Document name`, `Number`, `Date`, `Period`,
  `Payment date`, `Actions`, `Status`, and `Amount`.
- Per-document PDF links used
  `/fresa/extranet/finance/invoices/get_document?ses=<redacted>&hotel_id=<hotel_id>&lang=xu&invoice_name=<invoice_name>`.
- Commission rows linked `View statement` to
  `/hotel/hoteladmin/extranet_ng/manage/finance_reservations.html?...&period=<yyyy-mm>`.
  SSL/payment overview rows linked to
  `/hotel/hoteladmin/extranet_ng/manage/finance_document_details.html?...&document_id=<document_id>`.
- The Codex in-app Browser may report that file downloads are unsupported or
  block direct document-endpoint navigation. When that happens, do not bypass
  the browser policy with raw CDP or alternate browser surfaces. Mark document
  downloads `blocked` for that run, preserve the visible document inventory,
  and ask the user to perform the download manually in their browser profile or
  provide a first-party export artifact.

Redaction rules for authenticated traces:

- Never persist or quote raw `Cookie`, `Set-Cookie`, `op_token`, `ses`, SSO, WAF,
  `bkng`, or `esadm` values in reusable guidance.
- Record route skeletons with `ses=<redacted>` and account/property IDs replaced
  with placeholders.
- A captured curl is useful only if the response title and markers prove an
  authenticated surface. If the title or body shows sign-in, mark the probe
  `blocked` or `unauthenticated` and do not infer data coverage.

## Collection Plan

### 1. Inventory All Properties

Open the group homepage, property switcher, or account/property list and capture
every visible property before downloading data. Record at least:

- Booking.com property ID when visible in URLs, links, data attributes, or export
  filenames
- property display name
- status label if visible
- currently selected property marker
- URL or navigation hint used to reselect that property

If there is no direct all-properties export, iterate the switcher. Use
screenshot-driven clicks for menus and `js()` only after the menu is open.
For a group account, first try the `All properties` table on
`groups/home/index.html`; use its `Filter by property ID, name, or location`
field only for narrowing a known target, not as a replacement for full inventory.
If a `Download` action is available on this table, prefer it for the inventory
source and record the downloaded filename in the receipt.
If the full table is visible, the table itself is enough to seed a property
inventory; normalize property links by redacting `ses`, `hotel_id`, and
`hotel_account_id` in reusable receipts and keeping the actual IDs only in
private run output when the user needs them for joins.

Useful DOM probe after opening the switcher:

```python
properties = js("""
(() => Array.from(document.querySelectorAll('a[href], button, [role="option"], [role="menuitem"]'))
  .map((el) => ({
    text: (el.innerText || el.textContent || '').trim(),
    href: el.href || el.getAttribute('href') || '',
    aria: el.getAttribute('aria-label') || '',
    selected: el.getAttribute('aria-selected') === 'true'
      || el.getAttribute('aria-current') === 'true'
      || /selected|current/i.test(el.className || '')
  }))
  .filter((row) => row.text && /property|hotel|apartment|selected|switch|id/i.test(
    `${row.text} ${row.href} ${row.aria}`
  )))()
""")
```

Save the inventory before moving to booking or invoice downloads. If the
inventory is partial, mark the whole run `partial` and do not claim all-property
coverage.

### 2. Determine Missing Data

Build a per-property gap matrix before downloading:

| Data family | Required evidence | Missing when |
|---|---|---|
| bookings / reservations | export file, first-party API capture, or table capture with reservation IDs and date range | property has no current local source for the requested period or prior source lacks reservation IDs/status/date/guest/price fields |
| invoices / finance documents | downloaded invoice PDFs/CSVs or first-party finance export with document IDs and periods | local invoice source is absent, period is stale, or document IDs do not match the Extranet list |
| empty state | screenshot or structured capture of the Extranet "no results/no documents" state | a property has no rows but no proof of emptiness |

Do not scrape everything blindly if a local source is already complete and fresh.
Download only the missing or stale family for each property, then record why it
was needed.

### 3. Download Bookings / Reservations Per Property

For all properties, prefer the group reservations page first:

1. Open `/hotel/hoteladmin/groups/reservations/index.html`.
2. Complete any `auth-assurance` identity verification manually in the browser.
3. Choose `Date of` (`Reservation`, `Check-in`, or `Check-out`) according to the
   business question.
4. Set the date range, open `More filters` only when the default filters are
   insufficient, then use `Show reservations`.
5. Prefer the `Download` button over scraping the table. If downloading is not
   possible, capture table rows and pagination state.

The group reservations table is the best all-property booking source observed
so far. It carries property, guest, stay dates, status, payment, commission, and
reservation-number columns in one surface.

Observed group export API, browser-harness trace, 2026-05-22:

- Start capture immediately before clicking `Download` on the group
  reservations page. Use `NetworkCapture(capture_bodies=True)` and keep raw
  captures private.
- The export creation request is a POST to
  `/dml/graphql.json?lang=xu&ses=<redacted>` with
  `operationName: createDownloadableReservations`.
- Despite the operation name, the GraphQL operation is a `query`, not a
  `mutation`:
  `query createDownloadableReservations($input: CreateDownloadableReservationsInput!)`.
- For an all-property canonical booking ledger, use input fields:
  `accountId: <account_id>`, `propertyIds: []`, `typeOfDate: BOOKING`,
  `dateFrom`, `dateTo`, and
  `statusCriteria: {showCancelled:false, showOk:false, showNoShow:false, showPaidOnline:false}`.
  Empty `propertyIds` means all properties in the group account.
- Poll
  `operationName: checkReservationsDownloadableFilesStatus` with
  `query checkReservationsDownloadableFilesStatus($input: AccountIdInput!)`.
  The status list is nested at
  `partnerExportFile.checkDownloadableFilesStatus.requests.reservation[]`; do
  not treat `requests` itself as a list.
- Download completed files from
  `/fresa/extranet/partner/exports/download?lang=xu&ses=<redacted>&request_id=<request_id>&hotel_account_id=<account_id>`
  only after `requestStatus` is `REQUEST_IS_DONE`.
- Avoid one giant all-history request. In the observed account, broad
  all-history and one-year jobs could remain `REQUEST_IS_NEW` or return server
  errors at download time, while monthly `BOOKING` chunks completed reliably.
  A month-by-month sweep from the oldest needed booking date to today is the
  current preferred exhaustive strategy.
- `ARRIVAL` and `DEPARTURE` are alternate date filters. Download them only when
  the user specifically needs arrival/departure ledgers; `BOOKING` monthly
  chunks enumerate each booking once for reconciliation.

For a per-property fallback:

1. Select the property from the inventory.
2. Navigate to the per-property `Reservations` link or
   `search_reservations.html?...&hotel_id=<hotel_id>`.
3. Set the requested or default full-history date range if the UI supports it.
4. Prefer an export/download action over paginated table scraping.
5. If there is no export, capture the network calls while applying filters and
   page through until no more rows remain.

Minimum normalized fields to preserve when observable:

- `property_id`, `property_name`
- `reservation_id` or confirmation number
- booking status
- guest name or redacted guest key
- check-in and check-out dates
- booked date or created date
- gross amount, commission, fees, taxes, payout amount when visible
- source filename, URL, or capture ID

### 4. Download Invoices / Finance Documents Per Property

For each property:

1. Select the property.
2. Navigate to finance, invoices, documents, payouts, or statements.
3. Capture the visible document list first.
4. Download each missing invoice/document for the requested or available period.
5. If the UI offers CSV/XLS export, download that alongside PDFs because it is
   easier to reconcile.

Observed finance routes:

- `Documents and invoices`:
  `/hotel/hoteladmin/extranet_ng/manage/finance_invoices.html?...&hotel_id=<hotel_id>`
- PDF document endpoint:
  `/fresa/extranet/finance/invoices/get_document?ses=<redacted>&hotel_id=<hotel_id>&lang=xu&invoice_name=<invoice_name>`
- `Reservations statement`:
  `/hotel/hoteladmin/extranet_ng/manage/finance_reservations.html?...&hotel_id=<hotel_id>`
- `Payout info`:
  `/hotel/hoteladmin/extranet_ng/manage/payouts.html?...&hotel_id=<hotel_id>`
- `Financial Overview`:
  `/hotel/hoteladmin/extranet_ng/manage/finance_overview.html?...&hotel_id=<hotel_id>`

Do not mark invoice coverage `complete` from the presence of the `Finance`
button alone. Require one of:

- a visible finance/invoice/document page title or heading
- a table/list of invoice or payout documents
- a successful downloaded invoice/export file
- a redacted network capture proving a first-party invoice/document response

If the Finance menu stays on `Loading...` or the `#finance` hash returns to the
home DOM without invoice links, mark invoices `blocked` for that property with
`reason: finance_route_unresolved`.
If the page lists documents but the in-app browser cannot save the PDF/export
files, mark invoices `blocked` or `partial` with
`reason: download_blocked_by_browser_surface` and include the visible document
inventory as evidence.

Observed payout APIs, browser-harness trace, 2026-05-22:

- Use the browser-harness-attached Chrome profile for payout downloads when the
  in-app browser cannot save files. First confirm the page is authenticated with
  `page_info_js()` and keep `ses` private.
- The visible payout page may only expose `THIS_YEAR`, `LAST_YEAR`, and a
  constrained custom date range, but the frontend also ships GraphQL operations
  for older operating years.
- Query yearly payout transfer summaries with:
  `operationName: PayoutHistory`,
  `query PayoutHistory($input: PayoutsInYear!)`, and variables
  `input: {propertyId: <hotel_id>, year: <yyyy>}`.
- Query booking membership and costs for each payout with:
  `operationName: Payout`,
  `query Payout($input: SinglePayout!)`, and variables
  `input: {propertyId: <hotel_id>, payoutUuid: <uuid>}`.
- Download the matching CSV for each payout UUID from:
  `/fresa/payment/payout/migrated/payoutCSV?hotel_id=<hotel_id>&lang=xu&ses=<redacted>&payout_uuid=<uuid>`.
- The `Payout` response's `reservations[]` rows are direct booking-to-bank
  transfer membership evidence. Preserve reservation amount, commission,
  cost-of-payments, VAT, city/short-stay levy, withheld taxes, net amount,
  check-in/out, guest name, payout UUID, and transfer reference.
- If a UI-expanded payout table exposes a nonzero short-stay levy that the
  GraphQL row reports as zero/missing, merge that levy field into the same
  booking+payout membership row rather than duplicating the whole row.

Minimum normalized fields to preserve when observable:

- `property_id`, `property_name`
- invoice/document ID
- document type
- issue date and covered period
- currency and amount
- payment or payout status
- downloaded filename and source URL/capture ID

### 5. Receipt And Completion Check

Before claiming the run is complete, write a coverage receipt with one row per
property and data family:

```json
{
  "run_id": "bookingcom-host-YYYYMMDDTHHMMSSZ",
  "entry_url": "https://admin.booking.com/",
  "properties_total": 0,
  "families": ["bookings", "invoices"],
  "coverage": [
    {
      "property_id": "",
      "property_name": "",
      "bookings_status": "complete|empty|partial|blocked",
      "bookings_sources": [],
      "invoices_status": "complete|empty|partial|blocked",
      "invoices_sources": [],
      "residual_gap": ""
    }
  ]
}
```

Use `complete` only when the property has a source file/capture for that family
or the gap matrix proved the existing local source was already fresh. Use
`empty` only with an Extranet empty-state proof. Use `blocked` for permissions,
MFA, missing role access, unavailable export buttons, or document-download
errors that cannot be resolved locally. Use `blocked` rather than `partial`
when an auth-assurance step or unresolved Finance route prevents reaching the
source surface at all.

## Reconciliation Ledger

After exports are captured, build the audit ledger from the run directory:

```bash
uv run --with xlrd python domain-skills/booking-com/scripts/build_reconciliation_ledger.py \
  /path/to/bookingcom-finance-export-run
```

The builder creates `reconciliation_ledger/` with:

- `booking_ledger.sqlite` for structured joins
- `booking_reconciliation.csv` for one row per reservation export booking
- `finance_statement_items.csv` for captured statement/document line items
- `payout_transfers.csv` for payout transfer summaries
- `payout_booking_details.csv` for direct payout-to-booking membership and cost
  rows when GraphQL or the expanded payout table exposes them
- `payout_booking_links.csv` for legacy Vuex payout-to-booking membership rows,
  when the static page source exposes them
- `source_manifest.csv`, `output_manifest.csv`, and `ledger_chain.jsonl` for
  source hashes, output hashes, and chained row evidence
- `reconciliation_summary.json` with counts and the claim boundary

Ledger claims must be conservative:

- Booking revenue and commission/cost lines are direct only when reservation
  numbers match captured Booking.com finance statement data.
- Bank transfer membership is direct only when a payout source exposes booking
  membership rows. If only payout summary periods are captured, record transfer
  candidates as property/date-period overlaps and mark them as candidate-only,
  not immutable proof.
- GST, VAT, tax, short-stay levy, or similar costs are reported only when an
  explicit amount-like field exists in the captured source. Do not infer those
  costs from display flags, labels, or the existence of payment charges.

## Network Capture Pattern

When exports are unavailable or insufficient, use bounded network capture around
the exact UI action:

```python
cap = NetworkCapture(capture_bodies=True)
cap.start()
# click the filter/search/export/page-next control in the visible browser
wait_for_load()
events = cap.poll()
matches = cap.redacted_entries()
print(url_cluster([e["url"] for e in matches if "admin.booking.com" in e.get("url", "")]))
```

Store only redacted receipts in reusable notes. Raw captures and downloaded
files stay under `.private-data/`.

## Refusal And Stop Conditions

Stop and report the exact blocker when:

- the user is not logged in or must complete MFA/account selection
- the account has no visible property list
- a property cannot be selected with the current role
- invoice or finance pages are permission-blocked
- an export/download action would change account settings or send external
  messages instead of only reading/downloading data
- the run cannot prove all-property coverage
