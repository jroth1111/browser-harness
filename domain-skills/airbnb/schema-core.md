# Airbnb.com.au - Core Schema

Core tables join listings, content, calendar dates, reservations, economics, and
Airbnb-visible payout/tax fields.

## Design rules

- Every volatile table includes `observed_at` or an equivalent verification
  timestamp.
- `listing_id` is the listing join key.
- `reservation_id` and `confirmation_code` are both useful; keep both when
  visible.
- `calendar_date` is the date-level grain for occupancy and bookability.

## `airbnb_listing_master`

Canonical listing record.

Fields:

- `listing_id`
- `listing_name`
- `listing_url`
- `host_editor_path`
- `address`
- `address_source`
- `market`
- `suburb_or_area`
- `location_label`
- `property_type`
- `property_type_summary`
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
- `api_state`
- `source_overview`
- `source_detail_url`
- `last_verified_at`

Refresh: setup, monthly, and after listing edits.

## `airbnb_listing_content_audit`

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
- `photo_tour_rooms_present`
- `photo_tour_missing_room_flags`
- `room_level_amenity_flags`
- `photo_caption_coverage_pct`
- `accessibility_feature_photo_flags`
- `content_confidence`
- `content_change_date`
- `observed_at`

Refresh: monthly, after edits, and during conversion investigations.

## `airbnb_calendar_snapshot`

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

## `airbnb_reservation`

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

## `airbnb_reservation_economics`

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

## `airbnb_payout_tax_levy`

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
