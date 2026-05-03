# Airbnb.com.au - Data Quality and Provenance

Use this file to keep host intelligence auditable. A recommendation should be
traceable back to source observations, timestamps, confidence, and evidence.

## Quality principles

- Every capture has a run ID.
- Every derived field can be traced to source fields.
- Every alert has enough evidence to review or suppress it.
- Missing data is explicit; never silently treat missing as zero.
- Apply the general backend-invariant and field-level acceptance rules from
  `../../interaction-skills/backend-capability.md` to Airbnb source observations.
- Sensitive guest data is minimized, purpose-limited, and not copied into public
  skill files, logs, or screenshots.
- Exports are preferred when they contain the required primitive; UI/API
  scraping is justified when the website exposes materially richer fields. Keep
  both as separate source observations and reconcile conflicts explicitly.
- Every row family should carry `source_family`, `surface_class`, and
  `auth_context` so public, host-private, export, and third-party/open-data
  observations cannot be merged accidentally.
- Network-resource sniffing is discovery/probe evidence only. Runtime
  collectors may use the discovered route or hash after validation, but should
  not depend on raw performance-log sniffing as their normal collection path.

## `airbnb_data_capture_run`

One collection job.

Fields:

- `capture_run_id`
- `run_type`
- `started_at`
- `finished_at`
- `actor`
- `browser_backend`
- `logged_in_flag`
- `account_or_profile_label`
- `target_listing_ids`
- `target_date_start`
- `target_date_end`
- `source_files_downloaded`
- `screenshot_refs`
- `status`
- `error_summary`
- `parser_version`
- `session_manifest_id`

## `airbnb_source_observation`

Evidence record for a source page, export, screenshot, or API-like response.

Fields:

- `source_observation_id`
- `capture_run_id`
- `source_type`
- `source_name`
- `source_url_or_file_ref`
- `listing_id`
- `reservation_id`
- `period_start`
- `period_end`
- `observed_at`
- `http_status_or_ui_status`
- `content_hash`
- `screenshot_ref`
- `download_ref`
- `extraction_method`
- `confidence`

## `airbnb_field_quality`

Field-level confidence and freshness.

Fields:

- `field_quality_id`
- `source_observation_id`
- `table_name`
- `record_key`
- `field_name`
- `field_value_hash`
- `field_value_redacted`
- `extraction_confidence`
- `freshness_status`
- `validation_status`
- `validation_rule`
- `conflict_group_id`
- `notes`

## Freshness SLAs

| Data family | Freshness target |
|---|---:|
| Calendar forward availability | Daily |
| Reservation changes | On booking/change |
| Pricing settings and rule-sets | Weekly and after edits |
| Insights conversion/occupancy | Weekly |
| Earnings and payouts | Monthly and after payout changes |
| Reviews | After review posts |
| Public comp prices | Weekly and before major pricing decisions |
| Demand context next 90 days | Daily/weekly depending on source |
| Internal costs | Monthly and after supplier changes |

## Confidence scale

| Confidence | Meaning |
|---|---|
| `high` | Exported or structured source with matching keys and date scope |
| `medium` | Visible UI text or public listing text with clear labels |
| `low` | Inferred from partial text, screenshots, or ambiguous card ordering |
| `blocked` | Source unavailable, login required, challenge page, or incomplete load |
| `backend_capability_failed` | Backend loaded a page but did not expose required fields that another supported backend exposes |

## Validation rules

- Guest-facing total price must have dates, nights, guest count, currency, and
  source context.
- Public search/card observations must contain result-card evidence. For comp
  price runs, require room/listing identity plus total-price evidence; do not
  use page text length alone.
- Public search ranking observations must be logged out. If known Airbnb
  authenticated-session cookies are present, rank and visibility fields are
  invalid for market analysis because owner-account state can personalize
  ordering.
- Public rank observations must preserve the bounded result window: requested
  result limit, scroll depth/page, search context, and whether the row was from
  the initial viewport or lazy-loaded search results.
- Own-listing rank confidence must use bounded-window labels such as
  `matched_in_bounded_result_window` or `not_seen_in_bounded_result_window`;
  avoid older top-window labels after lazy scrolling is enabled.
- Public review/category fields must carry source/status fields such as
  `rating_display_state`, `star_distribution_source`, and
  `rating_category_source`; do not backfill listing-level nulls from host
  aggregate review widgets.
- If individual public review rows are visible but fewer than the listing
  review count, record the visible row count and mark the star distribution as
  partial. Do not derive a full 1-5 star distribution from a sampled review
  page.
- Visible public review snapshots are row-level evidence only for the reviews
  rendered in the collected page text. Treat them as theme/provenance samples
  unless row count equals listing review count or an explicit complete-review
  source is available.
- Public comp price matrices with zero valid cards or zero valid prices are
  evidence gaps, not market signals.
- Backend parity must be sampled for new Airbnb public URL families. If
  Lightpanda lacks Airbnb fields that logged-out headful Chrome exposes for the
  same context, use headful Chrome for host intelligence and record the
  Lightpanda limitation.
- Host payout must reconcile to an earnings report or reservation payout view.
- Calendar date statuses must be one of available, booked, blocked, unavailable,
  or unknown.
- `net_payout` cannot be treated as owner profit without finance cost joins.
- Alerts based on public comps need at least three valid comp observations unless
  the user explicitly accepts a thinner comp set.
- Insights comparisons must preserve Airbnb's selected time window and listing
  scope.
- Suspicious empty runs after a prior non-empty run are quarantined, not treated
  as fresh zero-state evidence. This applies to calendar exports, public comps,
  own-public review summaries, host-private reviews, and Insights metrics.
- Warehouse/BI outputs should publish stable table names, row counts, grains,
  source family, surface class, auth context, and artifact paths in each receipt
  so downstream SQL/dbt imports can reject partial or quarantined collections.

## Canonical Source Taxonomy And Join Policy

Use LLM-facing labels for routing, but preserve the machine `source_family`,
`surface_class`, and `auth_context` values already written by collectors and
receipts. Do not rename persisted values without a separate migration.

| LLM-facing evidence family | Persisted value(s) | Examples | Default join posture |
|---|---|---|---|
| public Airbnb market | `public_market` | logged-out search cards, comp listing pages, price matrices | Join only to public-market analysis and explicitly reconciled decision rows. |
| own public listing | `own_public` | the host's public listing pages, own search appearance, public review samples | Join to own-public analysis after listing ID/public URL reconciliation; do not mix with owner-session rank. |
| host-private Airbnb | `host_private`, `host_private_sensitive` | listing inventory, Insights, host reviews, earnings UI/API, pricing settings | Join to host-private reporting after listing-scope, date-window, and auth-context reconciliation. |
| calendar/iCal export | `calendar_export`, `calendar` | iCal/export URL rows, host calendar capability checks | Join to calendar snapshots only after listing/date reconciliation and empty-feed quarantine checks. |
| host export | `host_export` | earnings CSV, reservation detail, personal-data export parses | Prefer as source of truth for included fields; keep UI/API augmentation as separate source observations. |
| external market / REA | `external_public_market` | REA rent observations, building price snapshots, rental lifecycle events | Join only as external market context or underwriting input with separate freshness/confidence. |
| demand context | `third_party_open_data` or demand-context schema rows | holidays, events, weather, transport, regulation | Join only as context with cited source, period, geography, and confidence. |
| local visual evidence | `local_visual_evidence` or visual schema rows | photo manifests, contact sheets, visual observations, image prompts | Join through listing/photo identifiers; preserve source image refs and confidence. |
| internal/manual facts | internal/manual source rows | costs, owner contracts, action history, host-supplied constraints | Join only with explicit provenance and privacy handling. |
| capability/quality control | `capability`, `scheduler` | capability probes, network discovery receipts, refresh schedules, redaction scans | Use to validate or schedule source work; do not treat as business evidence rows. |

Cross-source joins require an explicit reconciliation rule and should preserve
the original source family, surface class, and auth context after the join.

## Privacy and retention

- Do not store full guest names when first name or reservation ID is enough.
- Redact emails, phone numbers, message bodies, and access instructions unless
  the user specifically asks to analyze them.
- Store hashes or short excerpts for evidence where possible.
- Keep screenshots only when they are needed for QA or user-requested evidence.
- Do not commit guest data, cookies, exports, screenshots, or downloaded reports
  into this skill repository.
- For private Airbnb continuity, use `session-continuity.md` and the ignored
  `.session-store/` path. Store raw cookies only when explicitly requested and
  only outside tracked files.
