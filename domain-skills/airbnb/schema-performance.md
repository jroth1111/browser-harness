# Airbnb.com.au - Pricing and Performance Schema

Use these tables for rate governance, rule-set auditing, conversion diagnosis,
occupancy, and quality monitoring.

## `airbnb_pricing_settings`

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
- `custom_promotion_discount_pct`
- `custom_promotion_eligibility_status`
- `custom_promotion_ineligible_reason`
- `median_price_basis`
- `price_tip_visible`
- `similar_listing_price_context`
- `cleaning_fee`
- `pet_fee`
- `extra_guest_fee`
- `additional_fees`
- `observed_at`

Refresh: weekly and after pricing edits.

## `airbnb_rule_set`

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

## `airbnb_insights_conversion`

Fields:

- `listing_id`
- `period_start`
- `period_end`
- `relative_ds_start`
- `relative_ds_end`
- `source_query`
- `source_route`
- `first_page_search_impressions`
- `search_to_listing_conversion`
- `listing_to_booking_conversion`
- `overall_conversion_rate`
- `bookings_per_impression`
- `views`
- `wishlist_additions`
- `wishlist_to_booking_friction`
- `booking_lead_time`
- `returning_guest_pct`
- `comparison_to_similar_listings`
- `observed_at`

Refresh: daily/weekly.

## `airbnb_insights_occupancy_rates`

Fields:

- `listing_id`
- `period_start`
- `period_end`
- `relative_ds_start`
- `relative_ds_end`
- `source_query`
- `source_route`
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

## `airbnb_insights_quality`

Fields:

- `listing_id`
- `period_start`
- `period_end`
- `relative_ds_start`
- `relative_ds_end`
- `source_query`
- `source_route`
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

## `airbnb_insights_metric_snapshot`

Generic per-listing Performance metric row from Airbnb's authenticated
Performance API.

Fields:

- `listing_id`
- `listing_name`
- `metric_family`
- `metric_subroute`
- `metric_name`
- `metric_label`
- `period_label`
- `relative_ds_start`
- `relative_ds_end`
- `value`
- `value_type`
- `value_string`
- `value_change`
- `value_change_type`
- `value_change_string`
- `currency`
- `source_query`
- `source_url`
- `observed_at`

Refresh: daily for tactical metrics; weekly/monthly for broader reporting.

## `airbnb_insights_chart_point`

Atomic chart/history point from Airbnb `ChartQuery`.

Use this table for both tactical daily history and lower-call-volume trend
history. When `series_granularity == DAY`, the row is a daily primitive. When
Airbnb returns `WEEK` or `MONTH` for broader chart windows, preserve that
granularity and do not compose it as daily data.

Fields:

- `listing_id`
- `listing_name`
- `metric_family`
- `metric_subroute`
- `primary_metric_name`
- `primary_metric_label`
- `ds`
- `series_index`
- `series_label`
- `series_granularity`
- `is_comparison_series`
- `value`
- `value_type`
- `value_string`
- `relative_ds_start`
- `relative_ds_end`
- `source_query`
- `source_url`
- `observed_at`

Design rule: store the chart point with its native `series_granularity`. For
recent tactical control, prefer `DAY` rows from rolling 7-day windows and then
compose 7-day, 30-day, monthly, quarterly, and yearly views where the metric is
additive or otherwise composable. Preserve Airbnb summary rows separately for
metrics whose aggregation semantics are ratios or averages.

## `airbnb_conversion_diagnosis`

Decision-gate output that classifies whether a listing's problem is visibility,
search-card click appeal, listing-page conversion, price friction, trust, photos,
amenity visibility, guest-segment mismatch, or no clear issue.

Fields:

- `conversion_diagnosis_id`
- `listing_id`
- `target_date_or_window`
- `guest_segment`
- `search_rank`
- `impressions`
- `search_to_listing_rate`
- `listing_to_booking_rate`
- `insights_funnel_stage`
- `search_to_listing_delta_basis`
- `listing_to_booking_delta_basis`
- `wishlist_to_booking_friction_basis`
- `expected_metric_to_move`
- `conversion_confounder_flags`
- `comp_price_index`
- `hero_photo_subject`
- `photo_count`
- `review_count`
- `rating`
- `badge_signals`
- `missing_amenity_filters`
- `conversion_issue_type`
- `top_3_fix_candidates`
- `decision`
- `confidence`
- `evidence_refs`
- `missing_required_evidence`
- `do_not_use_reason`
- `recommended_next_action`
- `observed_at`

Suggested `conversion_issue_type` values:

- `visibility_problem`
- `search_card_click_problem`
- `listing_page_conversion_problem`
- `price_friction`
- `trust_signal_gap`
- `photo_or_design_gap`
- `amenity_visibility_gap`
- `guest_segment_mismatch`
- `no_clear_issue`

## `airbnb_photo_product_gap_audit`

Decision-gate output that compares the host's own public search card/listing
presentation against A-comps before recommending broad price cuts.

Fields:

- `photo_product_gap_audit_id`
- `listing_id`
- `target_date_or_window`
- `guest_segment`
- `stay_length`
- `own_hero_photo_subject`
- `comp_hero_subject_mode`
- `first_five_photo_subjects`
- `room_proof_flags`
- `amenity_proof_flags`
- `amenity_claims_proven_in_photos`
- `missing_photo_proof`
- `missing_visible_amenities`
- `design_gap_flags`
- `photo_product_score`
- `review_count`
- `rating`
- `comp_price_index`
- `primary_gap`
- `issue_class`
- `top_3_fix_candidates`
- `expected_metric`
- `review_window_days`
- `decision`
- `confidence`
- `evidence_refs`
- `missing_required_evidence`
- `do_not_use_reason`
- `recommended_next_action`
- `observed_at`

Allowed `issue_class` values:

- `hero_photo_gap`
- `photo_order_gap`
- `sleeping_capacity_not_proven`
- `amenity_not_visible`
- `trust_signal_gap`
- `design_gap`
- `guest_segment_mismatch`
- `price_not_content_problem`
- `no_clear_issue`

## `airbnb_case_study_replay`

Decision-gate output that turns an operator-derived rescue, walkthrough, or
coaching pattern into a bounded recommendation experiment.

Fields:

- `case_study_replay_id`
- `case_type`
- `listing_id`
- `starting_symptom`
- `before_state_evidence`
- `hypothesis`
- `counterexample_matrix`
- `recommended_intervention`
- `expected_metric`
- `pre_window`
- `post_window`
- `rollback_criteria`
- `review_window_days`
- `validated_pattern`
- `experiment_template`
- `decision`
- `confidence`
- `evidence_refs`
- `missing_required_evidence`
- `do_not_use_reason`
- `recommended_next_action`
- `observed_at`

## `airbnb_calendar_action_candidate`

Date-level tactical action generated from calendar state, comp pressure, booking
pace, demand context, restrictions, and margin floor.

Fields:

- `calendar_action_candidate_id`
- `listing_id`
- `target_date`
- `calendar_state`
- `season_segment`
- `booking_pace`
- `comp_price_index`
- `margin_floor`
- `own_price`
- `proposed_price`
- `action_type`
- `expected_metric`
- `expected_direction`
- `rollback_criteria`
- `review_window_days`
- `decision`
- `confidence`
- `evidence_refs`
- `missing_required_evidence`
- `do_not_use_reason`
- `recommended_next_action`
- `observed_at`

Allowed `action_type` values:

- `raise_price`
- `reduce_price`
- `add_promotion`
- `remove_peak_date_promotion`
- `lower_minimum_stay`
- `fix_orphan_night`
- `add_5_day_discount`
- `add_14_day_discount`
- `protect_price_floor`
- `no_action`

Rules:

- Do not recommend a price or discount below the margin floor.
- Do not apply slow-season tactics to peak dates without explicit evidence.
- Every action needs rollback criteria and a review window.

## Performance joins

- Join pricing settings and rule-sets to `airbnb_calendar_snapshot` by
  `listing_id`, date range, and `observed_at` window.
- Join Insights to calendar/reservation economics by `listing_id` and reporting
  period.
- Use public comp tables from `schema-public-market.md` to calculate guest-facing
  price competitiveness.
- Join promotion eligibility to calendar snapshots so hosts can see when blocked
  dates or recent price history prevent promotion use.

## `airbnb_settings_drift_finding`

Pure decision-gate output for auditing whether active pricing, rule-set,
discount, promotion, Smart Pricing, and availability settings still match the
intended revenue strategy for a listing/date window.

Fields:

- `listing_id`
- `target_date`
- `target_date_or_window`
- `drift_type`
- `severity`
- `affected_dates_count`
- `affected_nights`
- `revenue_risk_direction`
- `intended_setting`
- `actual_setting`
- `active_rule_set_id`
- `active_discount_or_promotion`
- `active_discount_pct`
- `smart_pricing_state`
- `margin_floor`
- `effective_price_after_discounts`
- `demand_context`
- `comp_price_index`
- `decision`
- `confidence`
- `evidence_refs`
- `do_not_use_reason`
- `recommended_next_action`
- `rollback_criteria`
- `review_window_days`
- `observed_at`

Suggested `drift_type` values:

- `discount_leakage`
- `margin_floor_breach`
- `smart_pricing_conflict`
- `rule_set_overlap_conflict`
- `rule_set_gap`
- `stale_manual_override`
- `software_sync_drift`
- `minimum_stay_choke`
- `checkin_checkout_choke`
- `promotion_eligibility_gap`
- `stale_pricing_evidence`

Severity rules:

- `critical`: active settings can immediately damage margin or underprice
  high-demand dates.
- `high`: active settings likely block sellable demand or leave automation in
  conflict with strategy.
- `medium`: active settings are stale, incomplete, or inconsistent enough to
  require review before new recommendations.
- `low` or `monitor`: informational hygiene findings.

Required inputs:

- `airbnb_pricing_settings`
- `airbnb_rule_set`
- `airbnb_calendar_snapshot`
- demand context for the target dates
- internal margin floor or strategy price floor
- intended strategy baseline for the date class

Intended strategy baseline fields:

- `source_of_authority`
- `season_segment`
- `date_class`
- `target_guest_segment`
- `target_stay_lengths`
- `price_floor`
- `target_price_band_vs_A_comps`
- `allowed_discount_types`
- `blocked_discount_types`
- `minimum_stay_policy`
- `checkin_checkout_policy`
- `smart_pricing_policy`
- `require_rule_set_for_high_demand`
- `review_cadence_days`

Rules:

- Treat missing strategy, calendar rows, listing ID, or margin floor as
  `needs_more_data`.
- Remove or narrow discounts that leak into peak, event, holiday, or strong
  booking-pace dates unless the intended strategy explicitly allows them.
- Never accept an effective guest price below the margin floor.
- Flag Smart Pricing when it is active below the margin floor or where manual
  or custom rule-set control is the intended authority.
- Flag minimum-stay, check-in, and checkout restrictions that block otherwise
  sellable high-demand or orphan-night opportunities.
- Treat stale pricing-software sync evidence as a settings drift risk before
  trusting calendar prices.
