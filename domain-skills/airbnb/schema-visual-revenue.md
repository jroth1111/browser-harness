# Airbnb.com.au - Visual Revenue Schema

Use these tables for local visual evidence, image-improvement prompts,
portfolio photo/profit calibration, and low-cost design opportunities. These
rows are additive sidecars: they do not replace source listing records, public
market rows, or action tracking.

Visual workflows produce evidence and candidate recommendations. Accepted host
actions still move through `decisioning.md` for recommendation, action,
experiment, rollback, and outcome tracking.

## Design rules

- Every row is keyed by `run_id` and a deterministic row identifier where one is
  available.
- Listing-level rows use `listing_id` as the join key.
- Image-level rows preserve source URL, local path, and source hash whenever
  available.
- Profit and revenue correlations are directional unless the run controls for
  rent, unit size, seasonality, guest capacity, and sample-size limits.
- Insights conversion correlations are directional unless the run controls for
  reporting period, availability, price/rules changes, seasonality, comp-set
  changes, review shocks, and low-intent wishlist/view traffic.
- Prompt and design rows must preserve factual constraints. They cannot add
  fake views, amenities, room scale, finishes, parking, pool, gym, balcony,
  courtyard, furniture, whitegoods, landlord-controlled fixtures, sleep-comfort
  proof, capacity proof, stocked supplies, service quality, maintenance
  condition, theme coherence, post-clean evidence, or current-condition proof.
- Workflow outputs live under ignored `.private-data/` run stores or shareable
  `outputs/{run_id}/` reports. Do not mutate canonical scraped listing files in
  place.

## `airbnb_image_improvement_prompt`

One image-edit prompt candidate for one inferior source image, or an explicit
no-safe-prompt outcome when the image cannot be improved without materially
changing property facts.

Fields:

- `image_prompt_id`
- `run_id`
- `listing_id`
- `source_image_path`
- `source_image_hash`
- `photo_ordinal`
- `room_or_area`
- `problem_classes`
- `image_role`
- `profit_pattern_basis`
- `source_image_evidence_summary`
- `image_profit_pattern_class`
- `primary_prompt_intent`
- `guest_question_answered`
- `objection_reduced`
- `trust_signal_type`
- `proof_strength_0_100`
- `title_photo_promise_alignment`
- `source_capture_quality_flags`
- `shot_type`
- `product_photography_staging_notes`
- `eye_candy_or_statement_piece_basis`
- `hero_crop_control_notes`
- `promise_payoff_stage`
- `seasonal_relevance`
- `comp_set_pattern_basis`
- `pattern_break_basis`
- `under_serviced_amenity_basis`
- `first_five_collage_role`
- `room_hero_candidate_flag`
- `room_amenity_declaration_basis`
- `storyline_contribution`
- `guest_message_question_basis`
- `kitchen_proof_package_status`
- `guest_archetype_fit_basis`
- `experience_fit_proof_status`
- `sleep_quality_proof_status`
- `capacity_fit_proof_status`
- `theme_emotional_promise_basis`
- `maintenance_review_risk_flags`
- `service_signal_basis`
- `query_filter_alignment_basis`
- `review_relevance_basis`
- `photo_currency_status`
- `post_clean_condition_evidence_status`
- `as_pictured_risk_flags`
- `momentum_signal_caution_flags`
- `perception_of_effort_score_0_100`
- `gallery_fatigue_risk`
- `visual_tone_sequence_notes`
- `observed_hero_test_data`
- `insights_period_start`
- `insights_period_end`
- `insights_metric_basis`
- `insights_funnel_stage`
- `search_to_listing_delta_basis`
- `listing_to_booking_delta_basis`
- `wishlist_to_booking_friction_basis`
- `conversion_correlation_basis`
- `conversion_stage_priority`
- `expected_metric_to_move`
- `conversion_confounder_flags`
- `insights_confidence`
- `correlation_generalization_basis`
- `pattern_transfer_check`
- `strategic_fit_basis`
- `overfit_risk_flags`
- `strategic_override_notes`
- `fear_trigger_risk_flags`
- `post_click_trust_surface_flags`
- `qualitative_context_notes`
- `ai_skepticism_review_notes`
- `thumbnail_hook_score_0_100`
- `mobile_crop_score_0_100`
- `misleading_risk_flags`
- `prompt_priority_weights`
- `high_profit_pattern_to_strengthen`
- `low_profit_antipattern_to_reduce`
- `factual_anchors`
- `source_visible_revenue_hooks`
- `missing_or_unprovable_hooks`
- `allowed_edits`
- `forbidden_edits`
- `candidate_prompt_score_0_100`
- `recommended_gallery_action`
- `edit_vs_reshoot_decision`
- `reshoot_shot_brief`
- `improvement_prompt`
- `negative_prompt`
- `accuracy_check_prompt`
- `accuracy_retention_floor`
- `expected_conversion_leverage`
- `review_required_flag`
- `created_at`

Refresh: when inferior images are supplied, after a photo/profit calibration
run changes prompt priorities, or before a new listing photo edit batch.

Rules:

- `accuracy_retention_floor` is normally `70`.
- Use `no_safe_prompt` or `reshoot_or_resequence_needed` instead of prompting a
  material property change.
- Link the prompt to the source-visible high-profit signal it strengthens and
  the low-profit anti-pattern it reduces.
- Link the prompt to the guest question, objection, title/photo promise
  alignment, and misleading-risk flags carried by `photo_analysis`.
- Preserve the promise/payoff stage, comp-set pattern basis, pattern-break
  basis, seasonal relevance, under-serviced amenity basis, first-five collage
  role, room-hero flag, room-amenity declaration basis, storyline contribution,
  guest-message question basis, kitchen proof package status,
  guest-archetype fit, experience-fit proof, sleep-quality proof, capacity-fit
  proof, theme/emotional-promise basis, maintenance/review risk, service-signal
  basis, query/filter alignment, review relevance, photo-currency status,
  post-clean condition evidence, as-pictured risk, momentum-signal caution,
	  perception of effort, source capture quality, shot type,
	  product-photography staging, eye-candy basis, hero crop-control notes,
	  gallery fatigue, visual tone sequencing, observed hero-test data, Insights
	  period/metric basis, funnel-stage priority, conversion-correlation basis,
	  expected metric, conversion confounders, correlation generalization basis,
	  pattern transfer check, strategic fit, overfit risks, strategic overrides,
	  fear-trigger flags, post-click trust surface flags, qualitative context, and
	  skeptical review notes when they affected prompt or no-safe-prompt selection.

## `airbnb_visual_listing_observation`

One portfolio-calibration observation for one listing in one visual review run.

Fields:

- `run_id`
- `listing_id`
- `observed_at`
- `public_listing_url`
- `listing_name`
- `nickname`
- `address`
- `contact_sheet_path`
- `downloaded_photo_count`
- `expected_photo_count`
- `public_photo_count_coverage`
- `overall_photo_score_0_100`
- `hero_strength_0_100`
- `first_five_strength_0_100`
- `hero_title_alignment_0_100`
- `first_five_diversity_score_0_100`
- `trust_gap_flags`
- `photo_tone_shift_flags`
- `promise_payoff_gaps`
- `comp_set_visual_pattern_basis`
- `seasonal_rotation_opportunities`
- `under_serviced_amenity_proof_gaps`
- `photo_tour_room_hero_gaps`
- `kitchen_proof_package_gaps`
- `guest_message_question_gaps`
- `perception_of_effort_0_100`
- `guest_archetype_fit_gaps`
- `experience_fit_proof_gaps`
- `sleep_quality_proof_gaps`
- `capacity_fit_proof_gaps`
- `theme_emotional_promise_gaps`
- `maintenance_review_risk_flags`
- `service_signal_gaps`
- `query_filter_alignment_gaps`
- `review_relevance_gaps`
- `photo_currency_gaps`
- `post_clean_condition_evidence_gaps`
- `as_pictured_risk_flags`
- `momentum_signal_caution_flags`
- `product_photography_staging_gaps`
- `eye_candy_or_statement_piece_gaps`
- `source_capture_quality_gaps`
- `gallery_fatigue_flags`
- `visual_tone_sequence_flags`
- `observed_hero_test_summary`
- `insights_period_start`
- `insights_period_end`
- `insights_funnel_stage`
- `search_to_listing_conversion_delta`
- `listing_to_booking_conversion_delta`
- `wishlist_to_booking_friction_flag`
- `bookings_per_impression`
- `conversion_correlation_summary`
- `conversion_confounder_flags`
- `recommended_conversion_stage_action`
- `post_click_trust_surface_flags`
- `qualitative_context_notes`
- `view_quality_0_100`
- `amenity_visual_proof_0_100`
- `interior_design_0_100`
- `brightness_visual_0_100`
- `composition_0_100`
- `room_coverage_0_100`
- `avg_image_brightness_0_255`
- `avg_image_sharpness_proxy`
- `visual_strengths`
- `visual_issues`
- `high_profit_patterns_present`
- `low_profit_antipatterns_present`
- `visual_revenue_hypotheses`
- `workflow_1_prompt_calibration_notes`
- `workflow_3_design_calibration_notes`
- `correlation_confidence`
- `residual_confounders`
- `source_manifest_path`

Refresh: portfolio visual calibration runs, after major photo changes, or when a
new economics workbook changes the target revenue/profit period.

Rules:

- `photo_count` and downloaded coverage are coverage signals, not quality
  scores.
- `correlation_confidence` must flag small-sample and confounded results.
- Treat views, amenities, balcony/courtyard, parking, pool, and gym as valuable
  hooks only when source evidence proves them.

## `airbnb_visual_image_observation`

One reviewed source image inside a portfolio visual calibration run.
This row is also the reusable image-level metadata layer for photo order
optimization, AI edit prompts, and filename/export generation.

Fields:

- `run_id`
- `listing_id`
- `image_id`
- `unit_or_nickname`
- `suburb`
- `listing_name`
- `address`
- `public_listing_url`
- `photo_ordinal`
- `photo_key`
- `source_url`
- `local_path`
- `source_hash`
- `width`
- `height`
- `caption`
- `caption_source`
- `room_or_area`
- `visible_subjects`
- `visible_amenities`
- `view_type`
- `interior_exterior_class`
- `confidence`
- `current_gallery_position`
- `source_capture_quality_flags`
- `shot_type`
- `product_photography_staging_notes`
- `eye_candy_or_statement_piece_basis`
- `hero_crop_control_notes`
- `promise_payoff_stage`
- `seasonal_relevance`
- `comp_set_pattern_basis`
- `pattern_break_basis`
- `under_serviced_amenity_basis`
- `first_five_collage_role`
- `room_hero_candidate_flag`
- `room_amenity_declaration_basis`
- `storyline_contribution`
- `guest_message_question_basis`
- `kitchen_proof_package_status`
- `guest_archetype_fit_basis`
- `experience_fit_proof_status`
- `sleep_quality_proof_status`
- `capacity_fit_proof_status`
- `theme_emotional_promise_basis`
- `maintenance_review_risk_flags`
- `service_signal_basis`
- `query_filter_alignment_basis`
- `review_relevance_basis`
- `photo_currency_status`
- `post_clean_condition_evidence_status`
- `as_pictured_risk_flags`
- `momentum_signal_caution_flags`
- `perception_of_effort_score_0_100`
- `gallery_fatigue_risk`
- `visual_tone_sequence_notes`
- `observed_hero_test_data`
- `insights_period_start`
- `insights_period_end`
- `insights_metric_basis`
- `insights_funnel_stage`
- `search_to_listing_delta_basis`
- `listing_to_booking_delta_basis`
- `wishlist_to_booking_friction_basis`
- `conversion_correlation_basis`
- `conversion_stage_priority`
- `expected_metric_to_move`
- `conversion_confounder_flags`
- `insights_confidence`
- `correlation_generalization_basis`
- `pattern_transfer_check`
- `strategic_fit_basis`
- `overfit_risk_flags`
- `strategic_override_notes`
- `demand_driver_score_0_100`
- `clarity_diagnosticity_score_0_100`
- `crop_safety_score_0_100`
- `thumbnail_hook_score_0_100`
- `mobile_crop_score_0_100`
- `scroll_stop_score_0_100`
- `guest_question_answered`
- `objection_reduced`
- `trust_signal_type`
- `proof_strength_0_100`
- `title_photo_promise_alignment`
- `tone_shift_risk_flag`
- `fear_trigger_risk_flags`
- `post_click_trust_surface_flags`
- `misleading_risk_flags`
- `duplicate_group_id`
- `conversion_role`
- `source_image_evidence_summary`
- `image_profit_pattern_class`
- `primary_prompt_intent_candidate`
- `source_visible_revenue_hooks`
- `missing_or_unprovable_hooks`
- `high_profit_pattern_to_strengthen`
- `low_profit_antipattern_to_reduce`
- `recommended_gallery_action`
- `edit_vs_reshoot_decision`
- `reshoot_shot_brief`
- `edit_candidate_flag`
- `edit_reason`
- `allowed_edit_types`
- `forbidden_edit_types`
- `factual_anchors`
- `accuracy_constraints`
- `ai_edit_prompt`
- `edited_photo_path`
- `edit_review_status`
- `qualitative_context_notes`
- `ai_skepticism_review_notes`
- `accuracy_risk_notes`
- `review_notes`
- `review_status`

Refresh: with the parent `airbnb_visual_listing_observation` run.

Rules:

- `caption` is analysis metadata. Filenames, contact sheets, and upload
  packages are derived artifacts.
- `caption_source` must identify whether the caption came from Airbnb
  room/photo-tour data, Airbnb image captions, manual contact-sheet review, or
  manual full-image review.
- `room_or_area`, `visible_amenities`, and `view_type` must be visible in the
  image or exposed by an official per-photo source field. Do not inherit these
  from listing titles.
- Use image evidence, not listing copy alone, for `source_visible_revenue_hooks`.
- If an image cannot truthfully support a hook, record it under
  `missing_or_unprovable_hooks`.
- `allowed_edit_types`, `forbidden_edit_types`, `factual_anchors`, and
  `accuracy_constraints` are required before an AI edit prompt can be treated
  as safe to run.
- `guest_question_answered`, `objection_reduced`, `trust_signal_type`,
  `proof_strength_0_100`, `title_photo_promise_alignment`,
  `tone_shift_risk_flag`, `fear_trigger_risk_flags`, `misleading_risk_flags`,
  `promise_payoff_stage`, `seasonal_relevance`, `comp_set_pattern_basis`,
  `pattern_break_basis`, `under_serviced_amenity_basis`,
  `first_five_collage_role`, `room_hero_candidate_flag`,
  `room_amenity_declaration_basis`, `storyline_contribution`,
  `guest_message_question_basis`, `kitchen_proof_package_status`,
  `guest_archetype_fit_basis`, `experience_fit_proof_status`,
  `sleep_quality_proof_status`, `capacity_fit_proof_status`,
  `theme_emotional_promise_basis`, `maintenance_review_risk_flags`,
  `service_signal_basis`, `query_filter_alignment_basis`,
  `review_relevance_basis`, `photo_currency_status`,
  `post_clean_condition_evidence_status`, `as_pictured_risk_flags`,
  `momentum_signal_caution_flags`, `perception_of_effort_score_0_100`,
	  `source_capture_quality_flags`,
	  `shot_type`, `product_photography_staging_notes`,
	  `eye_candy_or_statement_piece_basis`, `hero_crop_control_notes`,
	  `gallery_fatigue_risk`, `visual_tone_sequence_notes`,
	  `observed_hero_test_data`, `insights_metric_basis`,
	  `insights_funnel_stage`, `conversion_correlation_basis`,
	  `conversion_stage_priority`, `expected_metric_to_move`,
	  `conversion_confounder_flags`, `correlation_generalization_basis`,
	  `pattern_transfer_check`, `strategic_fit_basis`, `overfit_risk_flags`,
	  `strategic_override_notes`, and `post_click_trust_surface_flags` are required
	  before an image can be promoted into a hero, first-five, or photo-tour
	  room-hero recommendation when Insights or correlation evidence exists.
- `edit_vs_reshoot_decision` must be one of `edit`, `reshoot`, `resequence`,
  `discard`, or `no_action`; if it is not `edit`, do not emit an AI edit prompt
  as the primary recommendation.
- `ai_skepticism_review_notes` should name the strongest argument against the
  recommendation when the image affects hero, first-five, photo-tour room hero,
  or AI editing.

## `airbnb_interior_design_opportunity`

One scored, low-cost visual or staging improvement candidate for a listing or
rental-arbitrage candidate.

Fields:

- `run_id`
- `listing_id`
- `observed_at`
- `opportunity_id`
- `operating_mode`
- `room_or_area`
- `photo_ordinals`
- `visual_issue`
- `guest_archetype_fit_basis`
- `experience_fit_gap`
- `sleep_quality_gap`
- `capacity_fit_gap`
- `theme_emotional_promise_gap`
- `maintenance_review_risk_addressed`
- `service_signal_dependency`
- `query_filter_alignment_gap`
- `review_relevance_gap`
- `photo_currency_gap`
- `post_clean_condition_evidence_gap`
- `as_pictured_risk_addressed`
- `momentum_signal_caution`
- `linked_high_profit_pattern`
- `linked_low_profit_antipattern`
- `recommendation`
- `improvement_class`
- `cost_band`
- `cost_band_index`
- `estimated_cost_aud`
- `estimated_effort`
- `operator_time_hours`
- `owner_approval_status`
- `reversibility`
- `budget_scenario`
- `revenue_hook_score_0_100`
- `first_five_impact_score_0_100`
- `gap_severity_score_0_100`
- `cost_efficiency_score_0_100`
- `speed_to_implement_score_0_100`
- `reusability_across_listings_score_0_100`
- `accuracy_safety_score_0_100`
- `leverage_score`
- `cost_penalty`
- `risk_penalty`
- `priority_score`
- `priority_tier`
- `expected_metric`
- `expected_effect_size_band`
- `expected_monthly_revenue_uplift_band_aud`
- `expected_monthly_profit_uplift_band_aud`
- `payback_weeks_low`
- `payback_weeks_high`
- `payback_confidence`
- `implementation_dependency`
- `pareto_selection_status`
- `dominates_opportunity_ids`
- `dominated_by_opportunity_id`
- `evidence_refs`
- `accuracy_or_misrepresentation_risk`
- `rollback_path`
- `operator_brief`
- `confidence`
- `operator_notes`

Refresh: when visual gaps, design constraints, or high/low pattern summaries are
updated.

Rules:

- Consider lowest-cost reversible changes before replacement or renovation.
- For `unfurnished_arbitrage_candidate`, do not score existing furniture,
  whitegoods, or removable decor as property advantages.
- Mark Pareto-dominated recommendations as `dominated`.

## `airbnb_portfolio_design_action`

One bulk design or staging action that applies a repeated pattern across
multiple listings.

Fields:

- `run_id`
- `portfolio_action_id`
- `pattern_or_antipattern`
- `affected_listing_ids`
- `affected_photo_ordinals`
- `standard_kit_or_rule`
- `estimated_total_cost_aud`
- `estimated_cost_per_listing_aud`
- `priority_tier`
- `expected_metric`
- `expected_monthly_revenue_uplift_band_aud`
- `expected_monthly_profit_uplift_band_aud`
- `payback_confidence`
- `purchase_or_shoot_list`
- `reuse_logic`
- `rollback_path`
- `owner_approval_required_count`
- `confidence`

Refresh: after a portfolio visual calibration run finds repeated high-value
gaps or anti-patterns across multiple listings.

Rules:

- Use bulk actions only for repeated, evidence-backed patterns.
- Keep rollback and owner-approval counts explicit before actioning.
