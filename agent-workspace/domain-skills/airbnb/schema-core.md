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

## `airbnb_gallery_cro_execution_board`

Action-ready gallery plan for a listing where public evidence shows a
photo/order/proof bottleneck or the user explicitly requests gallery work. The
board selects exact photo candidates and defines the proof-shot queue, captions,
rollback, and review window before a photo-order change is logged.

Fields:

- `gallery_cro_execution_board_id`
- `listing_id`
- `created_at`
- `source_issue_class`
- `target_date_or_window`
- `target_guest_segment`
- `stay_length`
- `seasonality`
- `channel_goal`
- `why_book`
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
- `conversion_stage_context`
- `hero_primary_photo_id_or_subject`
- `hero_alternate_photo_ids_or_subjects`
- `hero_crop_safety_score`
- `hero_score_components`
- `first_five_order`
- `first_five_scorecard`
- `room_coverage_plan`
- `amenity_proof_plan`
- `missing_proof_shots`
- `reshoot_shotlist`
- `edit_briefs`
- `caption_copy_pairings`
- `design_gap_flags`
- `comp_visual_patterns`
- `ab_test_plan`
- `rollback_plan`
- `action_checklist`
- `expected_metric`
- `review_window_days`
- `decision`
- `confidence`
- `evidence_refs`
- `missing_required_evidence`
- `do_not_use_reason`
- `recommended_next_action`

Refresh: after a content-facing decision gate, before implementing gallery
edits, after new photos are uploaded, and after material A-comp visual evidence
changes.

Rules:

- Use exact photo IDs, image IDs, filenames, or URLs for ship-ready boards.
  Subject-only boards remain `needs_more_data`.
- Preserve current photo order and caption state in `rollback_plan`.
- Do not create a gallery action from price, trust, or visibility-only issues
  unless the user explicitly requests gallery work.
- Treat missing room proof and missing thesis-amenity proof as proof-shot work,
  not as a reason to lower price.

## `airbnb_listing_content_optimization_brief`

Generated photo, gallery, title, and section-copy brief for a content change.
Create this only after a user request or a decision gate shows that presentation
is a likely bottleneck. The brief is not an implemented action; accepted edits
must be tracked through `airbnb_recommendation`, `airbnb_action_log`, and
`airbnb_experiment` when tested.

Fields:

- `content_optimization_brief_id`
- `listing_id`
- `brief_status`
- `source_decision_gate`
- `source_conversion_diagnosis_id`
- `source_photo_product_gap_audit_id`
- `source_issue_class`
- `target_date_or_window`
- `target_guest_segment`
- `stay_length`
- `seasonality`
- `why_book`
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
- `conversion_stage_context`
- `optimization_scope`
- `current_title_text`
- `recommended_primary_title`
- `recommended_challenger_title`
- `above_fold_primary`
- `above_fold_challenger`
- `title_ctr_score`
- `above_fold_score`
- `hero_primary_photo_id_or_subject`
- `hero_alternate_photo_ids_or_subjects`
- `hero_title_alignment`
- `first_five_order`
- `gallery_sequence_notes`
- `caption_updates`
- `missing_shots`
- `reshoot_shotlist`
- `edit_briefs`
- `copy_sections`
- `ab_test_plan`
- `rollback_plan`
- `missing_required_facts`
- `content_risk_flags`
- `expected_metric`
- `review_window_days`
- `evidence_refs`
- `decision`
- `confidence`
- `missing_required_evidence`
- `do_not_use_reason`
- `recommended_next_action`
- `created_at`

Refresh: after a content-facing decision gate, before implementing listing
content edits, and after material new photo/copy evidence appears.

Rules:

- Do not store invented amenities, fees, distances, view claims, bed sizes, or
  rules. Put unconfirmed facts in `missing_required_facts`.
- Preserve the current title, above-fold copy, photo order, and captions needed
  to roll back accepted changes.
- Record whether the hero proves the title promise. If it does not, the brief
  must recommend either a hero change or a title change.

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
