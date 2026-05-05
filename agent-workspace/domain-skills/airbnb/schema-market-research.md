# Airbnb.com.au - Market Research Schema

Use these tables for derived market-research observations and decisions. They do
not replace the raw public-search tables in `schema-public-market.md`; they sit
above them and preserve the reasoning needed to approve, watch, or reject a
market, property, or repositioning idea.

## `airbnb_market_research_run`

One research run for opportunity discovery, property validation, or
repositioning.

Fields:

- `market_research_run_id`
- `state_run_id`
- `observed_at`
- `research_mode`
- `mode_lock_reason`
- `mode_switch_reason`
- `candidate_market`
- `candidate_suburb_or_area`
- `candidate_address_or_building`
- `candidate_address_precision`
- `candidate_boundary_type`
- `target_lat`
- `target_lng`
- `target_building_name`
- `target_block_or_micro_area`
- `business_model`
- `target_property_type`
- `bedrooms`
- `beds_possible`
- `max_guests_possible`
- `unique_features_possible`
- `features_not_possible`
- `budget_or_capex_limit`
- `rent_or_mortgage_or_owner_terms`
- `minimum_required_monthly_net`
- `acceptable_downside_monthly_net`
- `regulatory_constraints`
- `target_channels`
- `target_guest_segments`
- `target_stay_lengths`
- `market_archetype_hypothesis`
- `strict_comp_gate_required_flag`
- `counterexample_gate_required_flag`
- `slow_season_survival_required_flag`
- `operator_notes`

Allowed `research_mode` values:

- `opportunity_discovery`
- `property_validation`
- `repositioning`

## `airbnb_research_mode_gate`

Gate proving that the evidence standard matches the research mode.

Fields:

- `research_mode_gate_id`
- `market_research_run_id`
- `research_mode`
- `mode_lock_reason`
- `mode_switch_reason`
- `required_evidence_present_flag`
- `mode_specific_missing_evidence`
- `mode_gate_result`
- `decision_constraint`
- `observed_at`

Allowed `mode_gate_result` values:

- `pass`
- `fail`
- `needs_more_data`

Required evidence by mode:

| Mode | Required proof |
|---|---|
| `opportunity_discovery` | repeated winning product patterns, repeated winner examples, reproducibility assessment, counterexamples, recommended product profile |
| `property_validation` | target address/building, defensible map-boundary receipt, same-building/same-block comps or equal-or-worse profitable comps, excluded inspiration comps, map-friction assessment, listing-maturity filter |
| `repositioning` | existing listing reference, public-search appearance, current price/availability state, winner gap assessment, smallest viable change, measurement plan |

## `airbnb_map_friction_assessment`

Boundary record explaining why listings inside or outside the map area are
guest-equivalent or not equivalent.

Fields:

- `map_friction_id`
- `market_research_run_id`
- `target_address_or_boundary`
- `map_bounds`
- `anchor_type`
- `anchor_name`
- `distance_km`
- `walk_time_minutes`
- `drive_time_minutes`
- `transit_time_minutes`
- `barrier_type`
- `barrier_name`
- `same_side_requirement_flag`
- `crosses_barrier_flag`
- `guest_segment_affected`
- `impact_direction`
- `impact_notes`
- `confidence`
- `observed_at`

Suggested `anchor_type` values:

- `downtown`
- `beach`
- `hospital`
- `university`
- `airport`
- `convention_center`
- `nightlife`
- `stadium`
- `transit`
- `tourist_area`
- `event_venue`
- `other`

Suggested `barrier_type` values:

- `river`
- `highway`
- `rail_line`
- `unsafe_walk`
- `hill`
- `parking_gap`
- `transit_gap`
- `psychological_boundary`
- `none`

Allowed `impact_direction` values:

- `helps`
- `hurts`
- `neutral`
- `unknown`

## `airbnb_market_absorption_snapshot`

Visible supply versus dated available supply for a market segment.

Fields:

- `absorption_snapshot_id`
- `market_research_run_id`
- `undated_search_run_id`
- `dated_search_run_id`
- `market`
- `suburb_or_area`
- `map_boundary`
- `property_type_filters`
- `room_type_filters`
- `amenity_filters`
- `instant_book_filter_state`
- `check_in_date`
- `check_out_date`
- `nights`
- `guest_count`
- `undated_inventory_count_visible`
- `undated_inventory_count_cap_hit`
- `dated_available_count_visible`
- `dated_available_count_cap_hit`
- `absorption_pct`
- `absorption_interpretation`
- `confidence`
- `observed_at`

## `airbnb_stay_length_gap_snapshot`

Availability by stay length for the same market/search context.

Fields:

- `stay_length_gap_id`
- `market_research_run_id`
- `market`
- `suburb_or_area`
- `map_boundary`
- `calendar_date_or_window`
- `guest_count`
- `property_type_filters`
- `room_type_filters`
- `one_night_available_count`
- `two_night_available_count`
- `three_night_available_count`
- `five_night_available_count`
- `seven_night_available_count`
- `fourteen_night_available_count`
- `twenty_eight_night_available_count`
- `one_night_scarcity_score`
- `minimum_stay_crowding_score`
- `weekly_gap_score`
- `monthly_gap_score`
- `recommended_stay_length_strategy`
- `confidence`
- `observed_at`

## `airbnb_guest_capacity_curve_snapshot`

Visible supply by guest count.

Fields:

- `capacity_curve_id`
- `market_research_run_id`
- `market`
- `suburb_or_area`
- `map_boundary`
- `check_in_date`
- `check_out_date`
- `nights`
- `property_type_filters`
- `room_type_filters`
- `guest_count`
- `visible_supply_count`
- `cap_hit_flag`
- `supply_drop_from_previous_guest_count_pct`
- `capacity_gap_score`
- `group_segment_hypothesis`
- `recommended_sleep_count`
- `confidence`
- `observed_at`

## `airbnb_price_distribution_snapshot`

Price histogram or price-slider distribution observed for a public search
context.

Fields:

- `price_distribution_id`
- `market_research_run_id`
- `search_run_id`
- `market`
- `suburb_or_area`
- `map_boundary`
- `check_in_date`
- `check_out_date`
- `nights`
- `guest_count`
- `price_band_low`
- `price_band_high`
- `visible_count_in_band`
- `currency`
- `distribution_source`
- `histogram_capture_quality`
- `interpretation_notes`
- `observed_at`

## `airbnb_competitor_booking_velocity_proxy`

Public proxy for whether a competitor appears to be gaining bookings. Public
calendars can show booked, blocked, or unavailable dates, so confidence must be
explicit.

Fields:

- `booking_velocity_proxy_id`
- `market_research_run_id`
- `comp_listing_id`
- `listing_url`
- `next_30_day_unavailable_pct`
- `next_60_day_unavailable_pct`
- `future_weekends_unavailable_count`
- `future_weekdays_unavailable_count`
- `latest_review_date`
- `recent_review_count_window`
- `new_listing_flag`
- `booking_velocity_interpretation`
- `booking_velocity_confidence`
- `observed_at`

## `airbnb_listing_maturity_filter`

Comp-quality gate that prevents boosted, stale, or unproven listings from
supporting base-case revenue.

Fields:

- `listing_maturity_filter_id`
- `market_research_run_id`
- `comp_listing_id`
- `listing_url`
- `first_seen_at`
- `review_count`
- `rating`
- `latest_review_date`
- `recent_review_count_30d`
- `recent_review_count_90d`
- `future_availability_signal`
- `new_listing_flag`
- `possible_airbnb_boost_flag`
- `maturity_grade`
- `can_use_for_underwriting_flag`
- `underwriting_use`
- `exclusion_reason`
- `observed_at`

Allowed `maturity_grade` values:

- `mature`
- `promising`
- `boosted_or_unproven`
- `stale`
- `unknown`

Allowed `underwriting_use` values:

- `base_case`
- `sensitivity`
- `inspiration`
- `exclude`

Rules:

- `base_case` requires a mature comp with meaningful review count and recent
  review activity.
- `promising` comps may support sensitivity only.
- `boosted_or_unproven` comps are inspiration only unless corroborated by mature
  equal-or-worse comps.
- `stale` and `unknown` comps do not support base-case revenue.

## `airbnb_comp_thesis`

Hypothesis for why a comp or comp set wins.

Fields:

- `comp_thesis_id`
- `market_research_run_id`
- `thesis_statement`
- `winning_variable`
- `alternative_variable_rejected`
- `replicable_by_candidate_flag`
- `replication_requirements`
- `unreproducible_feature_flag`
- `confidence`
- `created_at`

## `airbnb_comp_selection_gate`

Eligibility record that determines whether a comp can be used for underwriting,
sensitivity, inspiration, or exclusion.

Fields:

- `comp_selection_gate_id`
- `market_research_run_id`
- `comp_listing_id`
- `listing_url`
- `candidate_property_ref`
- `comp_grade`
- `evidence_use`
- `same_map_boundary_flag`
- `same_room_type_flag`
- `same_property_class_flag`
- `same_bedroom_band_flag`
- `same_bathroom_band_flag`
- `same_bed_sleep_capacity_band_flag`
- `same_target_guest_count_flag`
- `same_stay_length_flag`
- `same_date_or_season_flag`
- `same_core_amenity_filters_flag`
- `same_currency_observer_device_login_flag`
- `same_visible_price_context_flag`
- `same_channel_flag`
- `matched_fields`
- `mismatched_fields`
- `winning_variable`
- `can_host_reproduce`
- `cost_to_reproduce`
- `time_to_reproduce`
- `operational_requirement`
- `exclusion_reason`
- `observed_at`

Allowed `comp_grade` values:

- `A`
- `B`
- `C`
- `reject`

Allowed `evidence_use` values:

- `underwriting`
- `sensitivity`
- `inspiration`
- `exclude`

Allowed `can_host_reproduce` values:

- `yes`
- `no`
- `partial`
- `unknown`

## `airbnb_comp_thesis_evidence`

Supporting and counterexample evidence for a comp thesis.

Fields:

- `comp_thesis_evidence_id`
- `comp_thesis_id`
- `comp_listing_id`
- `listing_url`
- `evidence_role`
- `property_type`
- `bedrooms`
- `beds`
- `max_guests`
- `location_similarity`
- `feature_present_flags`
- `feature_absent_flags`
- `design_quality_assessment`
- `future_booking_proxy_ref`
- `price_position`
- `review_signal`
- `supports_or_weakens_thesis`
- `notes`
- `observed_at`

Allowed `evidence_role` values:

- `winner`
- `supporting_comp`
- `winner_with_feature`
- `loser_with_feature`
- `winner_without_feature`
- `loser_without_feature`
- `counterexample_with_feature`
- `counterexample_without_feature`
- `same_building_or_block`
- `better_design_weaker_location`
- `worse_design_better_location`
- `same_capacity_different_anchor`
- `same_anchor_different_capacity`
- `hotel_or_channel_substitute`
- `candidate_equivalent`

## `airbnb_counterexample_matrix`

Summary of whether a comp thesis survives the required counterexample checks.

Fields:

- `counterexample_matrix_id`
- `market_research_run_id`
- `comp_thesis_id`
- `thesis_statement`
- `winner_with_feature_ref`
- `loser_with_feature_ref`
- `winner_without_feature_ref`
- `loser_without_feature_ref`
- `same_building_or_same_block_ref`
- `better_design_weaker_location_ref`
- `worse_design_better_location_ref`
- `same_capacity_different_anchor_ref`
- `same_anchor_different_capacity_ref`
- `hotel_or_channel_substitute_ref`
- `thesis_result`
- `causal_feature`
- `contradictions`
- `missing_counterexamples`
- `counterexample_that_could_kill_this`
- `confidence`
- `observed_at`

Allowed `thesis_result` values:

- `supported`
- `contradicted`
- `inconclusive`

Suggested `causal_feature` values:

- `location`
- `capacity`
- `parking`
- `view`
- `pool`
- `design`
- `price`
- `rules`
- `channel`
- `operations`
- `unknown`

## `airbnb_market_archetype_assessment`

Assessment of which repeatable market archetype applies.

Fields:

- `archetype_assessment_id`
- `market_research_run_id`
- `archetype`
- `evidence_for`
- `evidence_against`
- `required_product_features`
- `common_failure_signs_checked`
- `archetype_fit_score`
- `confidence`
- `observed_at`

Suggested `archetype` values:

- `walkable_water`
- `supply_dry`
- `nostalgic_family_stay`
- `historic_story_property`
- `hotel_hollow`
- `category_anchor`
- `business_medical_monthly`
- `event_venue_proximity`
- `hotel_substitute_consistency`

## `airbnb_channel_demand_snapshot`

Market observations by distribution channel.

Fields:

- `channel_demand_snapshot_id`
- `market_research_run_id`
- `channel`
- `market`
- `suburb_or_area`
- `target_guest_segment`
- `channel_supply_count`
- `channel_comp_quality_summary`
- `channel_price_position_summary`
- `channel_booking_proxy`
- `content_adjustment_required`
- `pricing_adjustment_required`
- `channel_opportunity_score`
- `channel_concentration_risk`
- `confidence`
- `observed_at`

Suggested `channel` values:

- `airbnb`
- `vrbo`
- `booking_com`
- `priceline`
- `whimstay`
- `furnished_finder`
- `google_hotels`
- `direct`
- `pet_channel`
- `marriott_homes_villas`
- `other`

## `airbnb_channel_strategy_snapshot`

Decision-gate output for whether the product should remain Airbnb-native only
or test additional channels after market evidence exists.

Fields:

- `channel_strategy_snapshot_id`
- `market_research_run_id`
- `listing_id`
- `market_research_decision`
- `product_channel_fit`
- `operations_can_support_channels`
- `channel_recommendations`
- `default_source_for_airbnb_native_decisions`
- `decision`
- `confidence`
- `evidence_refs`
- `missing_required_evidence`
- `do_not_use_reason`
- `recommended_next_action`
- `observed_at`

Suggested channel keys:

- `airbnb`
- `vrbo`
- `booking_com`
- `google_hotels`
- `marriott_homes_villas`
- `direct`
- `monthly_midterm`

Rules:

- Do not recommend channel expansion before market evidence supports the
  product.
- Keep Airbnb as the default evidence source for Airbnb-native pricing, rank,
  and conversion decisions.
- Channel recommendations should become `airbnb_recommendation` and
  `airbnb_action_log` rows when accepted.

## `airbnb_midterm_viability_snapshot`

Monthly or midterm stay viability as a stay-length segment.

Fields:

- `midterm_viability_id`
- `market_research_run_id`
- `market`
- `suburb_or_area`
- `regulation_forces_30_day_flag`
- `slow_season_midterm_flag`
- `twenty_eight_night_search_count`
- `monthly_comp_price_low`
- `monthly_comp_price_median`
- `monthly_comp_price_high`
- `monthly_discount_required`
- `monthly_net_after_utilities_cleaning`
- `short_stay_peak_opportunity_cost`
- `long_stay_amenity_gaps`
- `recommended_monthly_role`
- `confidence`
- `observed_at`

Suggested `recommended_monthly_role` values:

- `primary_due_to_regulation`
- `slow_season_fill`
- `operations_smoothing`
- `not_recommended`
- `needs_more_data`

## `airbnb_slow_season_survival_model`

Seasonal downside model proving whether the candidate survives ordinary weak
periods without relying on peak-season prices.

Fields:

- `slow_season_survival_model_id`
- `market_research_run_id`
- `candidate_property_ref`
- `season_segment`
- `date_sample`
- `map_boundary`
- `room_type_filters`
- `property_class`
- `bedroom_bath_bed_capacity_filters`
- `core_amenity_filters`
- `guest_count`
- `nights`
- `weekday_or_weekend`
- `available_A_comp_count`
- `available_B_comp_count`
- `available_C_comp_count`
- `price_floor_A_comps`
- `price_median_A_comps`
- `price_floor_B_comps`
- `occupancy_or_absorption_proxy`
- `candidate_required_total_price`
- `candidate_required_occupancy`
- `slow_season_adr_floor`
- `slow_season_occupancy_floor`
- `slow_season_weekday_gap`
- `slow_season_weekend_gap`
- `slow_season_14_day_or_monthly_option`
- `slow_season_break_even_occupancy`
- `five_day_discount_needed`
- `fourteen_day_discount_needed`
- `temporary_minimum_stay_change`
- `seasonal_photo_or_copy_needed`
- `holiday_fit_upgrade_needed`
- `amenity_filter_gap_to_fix`
- `temporary_rule_flexibility_needed`
- `channel_support_needed`
- `net_after_tactics`
- `slow_season_low_case_net`
- `cash_buffer_required`
- `survival_pass_flag`
- `failure_reason`
- `confidence`
- `observed_at`

Allowed `season_segment` values:

- `peak`
- `shoulder`
- `slow`
- `slow_holiday_or_event`
- `ordinary_slow_weekday`
- `ordinary_slow_weekend`

## `airbnb_deal_underwriting_summary`

Financial model summary tied to the market research evidence.

Fields:

- `underwriting_summary_id`
- `market_research_run_id`
- `candidate_property_ref`
- `expected_monthly_gross_low`
- `expected_monthly_gross_base`
- `expected_monthly_gross_high`
- `seasonal_shape`
- `rent_or_mortgage`
- `utilities`
- `cleaning_cost_net_of_cleaning_fee`
- `linen_consumables`
- `platform_or_channel_fees`
- `management_or_labor`
- `insurance`
- `maintenance_reserve`
- `capex_or_furnishing_amortization`
- `owner_split_or_cohost_fee`
- `expected_monthly_net_low`
- `expected_monthly_net_base`
- `break_even_occupancy_or_revenue`
- `cash_buffer_required`
- `strict_comp_gate_pass_flag`
- `counterexample_gate_pass_flag`
- `slow_season_survival_ref`
- `slow_season_low_case_net`
- `slow_season_survival_pass_flag`
- `downside_case_pass_flag`
- `underwriting_confidence`
- `observed_at`

## `airbnb_market_research_decision`

Final decision output for a market research run.

Fields:

- `market_research_decision_id`
- `market_research_run_id`
- `decision`
- `confidence`
- `candidate_product_summary`
- `market_boundary_summary`
- `winning_thesis_ref`
- `replicable_feature_summary`
- `primary_disqualifier_checked`
- `top_supporting_comp_refs`
- `top_counterexample_refs`
- `strict_comp_selection_result`
- `counterexample_matrix_ref`
- `counterexample_matrix_result`
- `listing_maturity_filter_result`
- `absorption_signal_summary`
- `stay_length_gap_summary`
- `capacity_gap_summary`
- `slow_season_survival_ref`
- `slow_season_survival_summary`
- `channel_opportunity_summary`
- `midterm_role_summary`
- `underwriting_summary_ref`
- `evidence_refs`
- `missing_required_evidence`
- `do_not_use_reason`
- `required_next_action`
- `recommended_next_action`
- `what_would_change_the_decision`
- `created_at`

Allowed `decision` values:

- `pursue`
- `watch`
- `reject`
- `needs_more_data`
