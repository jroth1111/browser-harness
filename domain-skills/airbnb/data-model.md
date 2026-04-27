# Airbnb.com.au - Host Data Model

Use this file to turn Airbnb.com.au host and public market observations into a
host intelligence system. Read `host-intelligence.md` first for workflows and
`scraping.md` for public browser extraction.

## Design rules

- Store snapshots over time. Every volatile observation needs `observed_at`.
- Preserve source context. Public price/rank without dates, guests, filters,
  currency, and geography is not comparable.
- Keep guest-facing gross, host payout, and owner net economics separate.
- Keep Airbnb-visible compliance fields separate from legal conclusions.
- Assign confidence to scraped values when the UI is ambiguous or partially
  loaded.

## Minimum keys

| Key | Use |
|---|---|
| `listing_id` | Listing join key |
| `reservation_id` | Reservation join key |
| `confirmation_code` | Human support/reconciliation key |
| `calendar_date` | Date-level calendar grain |
| `observed_at` | Snapshot history |
| `period_start` / `period_end` | Reporting windows |
| `search_run_id` | Public search context |
| `comp_listing_id` | Competitor listing key |

## Core objects

### `airbnb_listing_master`

Canonical listing record.

Fields:

- `listing_id`
- `listing_name`
- `listing_url`
- `market`
- `suburb_or_area`
- `property_type`
- `room_type`
- `max_guests`
- `bedrooms`
- `beds`
- `bathrooms`
- `amenities_list`
- `instant_book_enabled`
- `cancellation_policy`
- `house_rules_summary`
- `check_in_method`
- `check_in_window`
- `checkout_time`
- `registration_or_permit_id`
- `listing_status`
- `last_verified_at`

Refresh: setup, monthly, and after listing edits.

### `airbnb_listing_content_audit`

How the listing presents to guests.

Fields:

- `listing_id`
- `title_text`
- `title_length`
- `description_sections_present`
- `photo_count`
- `hero_photo_subject`
- `photo_coverage_bedroom`
- `photo_coverage_bathroom`
- `photo_coverage_kitchen`
- `photo_coverage_living_area`
- `photo_coverage_exterior`
- `photo_coverage_view_or_unique_feature`
- `amenity_accuracy_flags`
- `guest_favourite_visible`
- `top_percent_badge_visible`
- `content_change_date`
- `observed_at`

Refresh: monthly, after edits, and during conversion investigations.

### `airbnb_calendar_snapshot`

Daily date-level booking and availability state.

Fields:

- `listing_id`
- `calendar_date`
- `status`
- `status_reason`
- `reservation_id`
- `nightly_price`
- `custom_price_flag`
- `smart_pricing_flag`
- `rule_set_id`
- `minimum_stay`
- `maximum_stay`
- `check_in_allowed`
- `checkout_allowed`
- `observed_at`

Refresh: daily for forward dates; weekly backfill is enough for historical
audits.

### `airbnb_reservation`

Operational booking record.

Fields:

- `reservation_id`
- `confirmation_code`
- `listing_id`
- `reservation_status`
- `booking_created_at`
- `check_in_date`
- `check_out_date`
- `nights`
- `guest_count_total`
- `guest_count_adults`
- `guest_count_children`
- `guest_count_infants`
- `guest_count_pets`
- `guest_country_or_region`
- `guest_language`
- `special_requests_tags`
- `arrival_guide_sent_at`
- `cleaning_task_created_at`
- `review_due_date`
- `guest_review_received`
- `host_review_submitted`

Refresh: on booking, alteration, cancellation, and checkout.

### `airbnb_reservation_economics`

Booking-level financial record.

Fields:

- `reservation_id`
- `listing_id`
- `booking_subtotal`
- `nightly_revenue_total`
- `average_nightly_revenue`
- `cleaning_fee`
- `pet_fee`
- `extra_guest_fee`
- `other_host_fees`
- `airbnb_host_service_fee`
- `taxes_withheld`
- `adjustments`
- `cancellation_fee`
- `net_payout`
- `payout_date`
- `payout_method`
- `guest_total_price`
- `currency`

Refresh: on booking where visible, on payout, and after earnings report changes.

### `airbnb_payout_tax_levy`

Airbnb-visible tax, levy, and payout reporting layer.

Fields:

- `listing_id`
- `period_start`
- `period_end`
- `gross_revenue_period`
- `net_payout_period`
- `taxes_withheld`
- `levy_or_tax_collected_flag`
- `levy_jurisdiction`
- `declaration_status`
- `tax_report_downloaded_at`
- `owner_statement_included_flag`
- `observed_at`

Refresh: monthly and annually.

## Pricing and restrictions

### `airbnb_pricing_settings`

Standing pricing configuration.

Fields:

- `listing_id`
- `base_price`
- `weekend_price`
- `smart_pricing_enabled`
- `smart_pricing_min`
- `smart_pricing_max`
- `weekly_discount_pct`
- `monthly_discount_pct`
- `early_bird_discount_rules`
- `last_minute_discount_rules`
- `custom_promotion_active`
- `cleaning_fee`
- `pet_fee`
- `extra_guest_fee`
- `additional_fees`
- `observed_at`

Refresh: weekly and after pricing edits.

### `airbnb_rule_set`

Custom pricing and availability rule-set table.

Fields:

- `rule_set_id`
- `rule_set_name`
- `listing_ids_applied`
- `date_range_start`
- `date_range_end`
- `nightly_price_adjustment`
- `length_of_stay_discount`
- `last_minute_discount`
- `early_bird_discount`
- `minimum_nights`
- `maximum_nights`
- `check_in_day_rules`
- `checkout_day_rules`
- `smart_pricing_active_for_listing`
- `observed_at`

Refresh: on creation/edit and weekly for applied date ranges.

## Insights

### `airbnb_insights_conversion`

Fields:

- `listing_id`
- `period_start`
- `period_end`
- `first_page_search_impressions`
- `search_to_listing_conversion`
- `listing_to_booking_conversion`
- `overall_conversion_rate`
- `views`
- `wishlist_additions`
- `booking_lead_time`
- `returning_guest_pct`
- `comparison_to_similar_listings`
- `observed_at`

Refresh: daily/weekly.

### `airbnb_insights_occupancy_rates`

Fields:

- `listing_id`
- `period_start`
- `period_end`
- `occupancy_rate`
- `nights_blocked`
- `nights_booked`
- `unbooked_nights`
- `check_ins`
- `cancellation_rate`
- `average_length_of_stay`
- `average_nightly_rate`
- `similar_listing_comparison`
- `future_period_flag`
- `observed_at`

Refresh: weekly.

### `airbnb_insights_quality`

Fields:

- `listing_id`
- `period_start`
- `period_end`
- `overall_rating`
- `five_star_pct_total`
- `accuracy_5star_pct`
- `checkin_5star_pct`
- `cleanliness_5star_pct`
- `communication_5star_pct`
- `location_5star_pct`
- `value_5star_pct`
- `comparison_to_similar_listings`
- `quality_alert_flag`
- `observed_at`

Refresh: weekly/monthly.

## Reviews and guest context

### `airbnb_review`

Fields:

- `review_id`
- `listing_id`
- `reservation_id`
- `review_date`
- `stay_month`
- `length_of_stay_band`
- `trip_type`
- `overall_rating`
- `category_ratings`
- `review_text`
- `theme_cleanliness`
- `theme_accuracy`
- `theme_checkin`
- `theme_noise`
- `theme_beds_sleep`
- `theme_wifi_work`
- `theme_value`
- `host_response_present`
- `host_response_date`

Refresh: after reviews post.

### `airbnb_guest_profile_minimal`

Fields:

- `reservation_id`
- `guest_first_name`
- `guest_review_count`
- `guest_rating_or_review_signal`
- `guest_language`
- `guest_country_or_region`
- `identity_status_visible`
- `guest_is_host_flag`
- `special_access_needs_flag`
- `arrival_reason_tag`
- `guest_notes_internal`

Refresh: on booking/request and when guest messages add context.

## Messaging and operations

### `airbnb_message_workflow`

Fields:

- `workflow_id`
- `listing_id`
- `trigger_type`
- `trigger_offset`
- `template_name`
- `template_language`
- `personalisation_fields_used`
- `house_rules_included_flag`
- `checkin_info_included_flag`
- `checkout_info_included_flag`
- `last_minute_send_enabled`
- `sent_at`
- `skipped_flag`
- `guest_response_required_flag`

Refresh: on setup/edit and per reservation timeline.

### `airbnb_operations_task`

Fields:

- `task_id`
- `reservation_id`
- `listing_id`
- `task_type`
- `task_due_at`
- `assigned_to_role`
- `guest_count`
- `pet_flag`
- `early_checkin_late_checkout_flag`
- `maintenance_keywords`
- `completion_at`
- `issue_found_flag`
- `photo_evidence_flag`

Refresh: on reservation/change and task update.

## Public market data

### `airbnb_public_search_run`

Defines the exact search context.

Fields:

- `search_run_id`
- `observed_at`
- `observer_location_country`
- `device_type`
- `logged_in_flag`
- `currency`
- `destination`
- `map_area_bounds_description`
- `check_in_date`
- `check_out_date`
- `nights`
- `guest_count_adults`
- `guest_count_children`
- `guest_count_pets`
- `filters_applied`
- `results_count_visible`
- `audit_screenshot_ref`

### `airbnb_public_search_result_snapshot`

Search-card visibility.

Fields:

- `search_run_id`
- `result_position`
- `page_number_or_scroll_depth`
- `listing_url`
- `listing_id_if_extractable`
- `visible_title_short`
- `visible_location_label`
- `visible_rating`
- `visible_review_count`
- `visible_badge`
- `visible_price_total`
- `visible_price_per_night`
- `fees_included_flag`
- `hero_photo_subject_tag`
- `available_flag`
- `instant_book_visible_flag`
- `obvious_differentiator_tags`

### `airbnb_public_comp_listing_snapshot`

Structured competitor listing snapshot.

Fields:

- `comp_listing_id`
- `observed_at`
- `listing_url`
- `market`
- `property_type`
- `room_type`
- `max_guests`
- `bedrooms`
- `beds`
- `bathrooms`
- `rating`
- `review_count`
- `public_badges`
- `visible_amenities_core`
- `parking_flag`
- `pool_spa_flag`
- `pet_friendly_flag`
- `workspace_wifi_flag`
- `family_amenities_flag`
- `accessible_features_flag`
- `house_rules_summary_flags`
- `cancellation_policy_visible`
- `photo_count`
- `hero_photo_subject`
- `review_theme_positive_tags`
- `review_theme_negative_tags`

### `airbnb_public_price_availability_matrix`

Date-specific comp-set price and availability.

Fields:

- `matrix_id`
- `comp_listing_id`
- `search_run_id`
- `check_in_date`
- `check_out_date`
- `nights`
- `guest_count`
- `available_flag`
- `visible_total_guest_price`
- `visible_nightly_component`
- `visible_fees_or_taxes_component`
- `minimum_stay_observed`
- `cancellation_policy_visible`
- `price_observation_confidence`

## Derived metrics

### Revenue and yield

| Metric | Formula |
|---|---|
| Booked nights | Count booked `calendar_date` values |
| Available nights | Sellable nights excluding defined non-sellable blocks |
| Occupancy rate | Booked nights / available nights |
| ADR | Nightly revenue / booked nights |
| Net ADR | Net payout allocated to nights / booked nights |
| RevPAN | Revenue / available nights |
| Net RevPAN | Net payout / available nights |
| Booking lead time | Check-in date - booking created date |
| Booking pace | Future booked nights as of `observed_at` |
| Cancellation-adjusted revenue | Confirmed revenue - refunds/adjustments + cancellation fees |
| Fee ratio | Fees charged / total guest price |
| Host-fee take rate | Host service fee / booking subtotal |
| Cleaning-fee recovery | Cleaning fee collected / actual cleaning cost |
| Long-stay discount impact | Discounted revenue vs standard nightly revenue |

### Conversion

| Metric | Formula or source |
|---|---|
| Search visibility index | First-page impressions vs target/similar listings |
| Search-card conversion | Search-to-listing conversion |
| Listing-page conversion | Listing-to-booking conversion |
| Wishlist friction index | High wishlists plus low bookings |
| Returning guest rate | Airbnb returning guests metric |
| Comp price index | Your total guest price / median comp-set total guest price |
| Comp quality index | Rating/review/badge profile vs comp set |
| Minimum-stay choke score | Failed or weakened bookability from LOS rules |

### Quality and operations

| Metric | Formula |
|---|---|
| Cleanliness defect rate | Cleanliness-negative tags / stays |
| Check-in friction rate | Check-in-negative tags / stays |
| Accuracy complaint rate | Accuracy-negative tags / stays |
| Maintenance recurrence | Repeated issue tags by listing |
| Message workflow success | Scheduled messages sent on time / eligible reservations |
| Review completion rate | Host reviews submitted / eligible stays |
| Low-rating early warning | Category rating decline vs prior period |
| Turnover load | Check-ins + checkouts by date |
| Pet-stay margin | Pet fees - pet-related cleaning/repair cost |

## Alerts

### `airbnb_alerts`

Alert event table.

Fields:

- `alert_id`
- `listing_id`
- `reservation_id`
- `calendar_date`
- `alert_type`
- `severity`
- `trigger_value`
- `threshold_value`
- `source_tables`
- `recommended_action`
- `status`
- `created_at`
- `resolved_at`

| Alert | Trigger |
|---|---|
| High-demand date unbooked | Future date remains available while target pace is behind |
| Underpriced peak date | Your total guest price < 85% of comparable median |
| Overpriced conversion risk | Your price > 125-130% of comp median and conversion weakens |
| Accidental block | Blocked night without defined reason |
| Orphan-night alert | 1-2 night gap between bookings |
| Minimum-stay choke | Common guest search dates blocked by min-stay rules |
| Smart Pricing conflict | Smart Pricing active where custom rule intention exists |
| Discount drift | Discount applies to peak or event period unexpectedly |
| Quality drop | Any category rating falls below threshold |
| Repeated review theme | Same negative theme appears twice within N stays |
| Message skipped | Scheduled check-in/checkout message skipped |
| Turnover overload | Same-day checkouts/check-ins exceed cleaner capacity |
| Levy/tax field mismatch | Airbnb-visible levy/tax field inconsistent with listing jurisdiction |

## Build order

### Phase 1 - Core business intelligence

1. `airbnb_listing_master`
2. `airbnb_calendar_snapshot`
3. `airbnb_reservation`
4. `airbnb_reservation_economics`
5. `airbnb_pricing_settings`
6. `airbnb_insights_conversion`
7. `airbnb_insights_occupancy_rates`
8. `airbnb_insights_quality`

Outcome: revenue, occupancy, booking pace, conversion, and quality visibility.

### Phase 2 - Revenue optimization

1. `airbnb_rule_set`
2. `airbnb_public_search_run`
3. `airbnb_public_search_result_snapshot`
4. `airbnb_public_comp_listing_snapshot`
5. `airbnb_public_price_availability_matrix`
6. Price-index and booking-pace alerts

Outcome: comp-set price intelligence and restriction optimization.

### Phase 3 - Operational scale

1. `airbnb_message_workflow`
2. `airbnb_operations_task`
3. Review-theme tagging
4. Cleaner and maintenance recurrence reports
5. Turnover load alerts

Outcome: repeatable guest operations and property quality control.

## Highest-ROI dashboard

| Tile | Source tables |
|---|---|
| Net RevPAN by listing | Reservation economics + calendar |
| Forward booking pace | Calendar snapshots + reservations |
| Comp price index | Public price matrix + pricing settings |
| Search funnel | Insights conversion |
| Occupancy and blocked-night mix | Calendar + Insights |
| Orphan nights | Calendar snapshot |
| Rule-set conflicts | Rule-set + pricing settings + calendar |
| Quality category trend | Insights quality + reviews |
| Review theme recurrence | Reviews |
| Turnover workload | Reservations + operations tasks |
| Message workflow status | Message workflow + reservations |
| High-demand unbooked dates | Calendar + comp availability + price matrix |
