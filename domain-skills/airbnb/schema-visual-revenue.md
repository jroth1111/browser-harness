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
- Prompt and design rows must preserve factual constraints. They cannot add
  fake views, amenities, room scale, finishes, parking, pool, gym, balcony,
  courtyard, furniture, whitegoods, or landlord-controlled fixtures.
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

Fields:

- `run_id`
- `listing_id`
- `image_id`
- `photo_ordinal`
- `source_url`
- `local_path`
- `source_hash`
- `room_or_area`
- `source_image_evidence_summary`
- `image_profit_pattern_class`
- `primary_prompt_intent_candidate`
- `source_visible_revenue_hooks`
- `missing_or_unprovable_hooks`
- `high_profit_pattern_to_strengthen`
- `low_profit_antipattern_to_reduce`
- `recommended_gallery_action`
- `accuracy_risk_notes`
- `review_status`

Refresh: with the parent `airbnb_visual_listing_observation` run.

Rules:

- Use image evidence, not listing copy alone, for `source_visible_revenue_hooks`.
- If an image cannot truthfully support a hook, record it under
  `missing_or_unprovable_hooks`.

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
