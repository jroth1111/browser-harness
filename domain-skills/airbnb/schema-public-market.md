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
- `results_limit_requested`
- `max_search_scrolls_requested`
- `search_scrolls_attempted`
- `rank_collection_scope`
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
- `top_home_highlight_visible`
- `top_percent_label`
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
- `five_star_pct`
- `five_star_count_estimate`
- `four_star_pct`
- `four_star_count_estimate`
- `three_star_pct`
- `three_star_count_estimate`
- `two_star_pct`
- `two_star_count_estimate`
- `one_star_pct`
- `one_star_count_estimate`
- `star_distribution_source`
- `rating_display_state`
- `review_scope_confidence`
- `public_badges`
- `top_home_highlight_visible`
- `bottom_percent_warning_visible`
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

## `airbnb_public_target_competitor_snapshot`

Links each live host listing to the closest public competitors observed for a
specific search context.

Fields:

- `target_listing_id`
- `comp_listing_id`
- `search_run_id`
- `check_in_date`
- `nights`
- `comp_rank_for_target`
- `search_result_position`
- `page_number_or_scroll_depth`
- `competitor_score`
- `reason_codes`

## `airbnb_own_public_listing_audit`

Guest-visible public listing-page audit for the host's own live listings. This
is collected logged out and should not use host-authenticated state.

Fields:

- `listing_id`
- `observed_at`
- `logged_in_flag`
- `source_url`
- `public_listing_url`
- `title_text`
- `title_length`
- `property_type`
- `max_guests`
- `bedrooms`
- `beds`
- `bathrooms`
- `photo_count`
- `visible_amenities_core`
- `parking_flag`
- `pool_spa_flag`
- `pet_friendly_flag`
- `workspace_wifi_flag`
- `family_amenities_flag`
- `accessible_features_flag`
- `house_rules_summary_flags`
- `cancellation_policy_visible`
- `guest_favourite_visible`
- `top_percent_badge_visible`
- `content_confidence`

## `airbnb_own_public_review_summary`

Guest-visible own-listing review and rating summary. Airbnb may expose review
star percentages instead of exact counts; store percentages and derived count
estimates separately.

Fields:

- `listing_id`
- `observed_at`
- `logged_in_flag`
- `source_url`
- `overall_rating`
- `review_count`
- `rating_display_state`
- `review_scope_confidence`
- `rating_category_source`
- `accuracy_rating`
- `checkin_rating`
- `cleanliness_rating`
- `communication_rating`
- `location_rating`
- `value_rating`
- `five_star_pct`
- `five_star_count_estimate`
- `four_star_pct`
- `four_star_count_estimate`
- `three_star_pct`
- `three_star_count_estimate`
- `two_star_pct`
- `two_star_count_estimate`
- `one_star_pct`
- `one_star_count_estimate`
- `star_distribution_source`
- `review_theme_tags`

## `airbnb_own_public_search_appearance`

Own-listing guest-visible search/rank appearance for the same search contexts
used by competitor collection.

Fields:

- `search_run_id`
- `listing_id`
- `observed_at`
- `observer_location_country`
- `device_type`
- `logged_in_flag`
- `currency`
- `destination`
- `check_in_date`
- `check_out_date`
- `nights`
- `guest_count_adults`
- `guest_count_children`
- `guest_count_pets`
- `filters_applied`
- `source_url`
- `results_limit_requested`
- `max_search_scrolls_requested`
- `search_scrolls_attempted`
- `rank_collection_scope`
- `search_appears_flag`
- `search_result_position`
- `page_number_or_scroll_depth`
- `listing_url`
- `visible_title_short`
- `visible_location_label`
- `visible_price_total`
- `visible_price_per_night`
- `visible_rating`
- `visible_review_count`
- `visible_badge`
- `top_home_highlight_visible`
- `available_flag`
- `rank_observation_confidence`

## Public data quality rules

- A price observation is invalid without dates, nights, guests, currency, and
  search context.
- Use total guest price for comps when visible. Do not use crossed-out anchor
  prices as realized gross.
- Keep taxes, fees, and nightly components separate when Airbnb exposes them.
- Capture a sampled screenshot reference for QA when ranking, price, or badge
  observations drive recommendations.
- Public guest-market observations should normally have `logged_in_flag == false`.
  Logged-in public observations are valid only for an explicit personalization
  comparison and must be stored as a separate run/segment, not mixed with normal
  logged-out comp data.
- Closest-competitor links are date-specific. Do not treat a competitor observed
  for one check-in date, stay length, or guest count as generally available or
  directly price-comparable for another context without a matching matrix row.
