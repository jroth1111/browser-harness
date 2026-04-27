# Airbnb.com.au - Public Market Schema

Use these tables for public search visibility, comp-set listing intelligence,
and date-specific competitor price/availability.

## `airbnb_public_search_run`

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

## `airbnb_public_search_result_snapshot`

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

## `airbnb_public_comp_listing_snapshot`

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

## `airbnb_public_price_availability_matrix`

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

## Public data quality rules

- A price observation is invalid without dates, nights, guests, currency, and
  search context.
- Use total guest price for comps when visible. Do not use crossed-out anchor
  prices as realized gross.
- Keep taxes, fees, and nightly components separate when Airbnb exposes them.
- Capture a sampled screenshot reference for QA when ranking, price, or badge
  observations drive recommendations.
