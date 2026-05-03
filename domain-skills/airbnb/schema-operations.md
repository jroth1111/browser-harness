# Airbnb.com.au - Guest and Operations Schema

Use these tables for review intelligence, guest context, communication
consistency, cleaning, check-in, checkout, and maintenance tracking.

## `airbnb_review`

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
- `host_response_text`

Refresh: after reviews post.

## `airbnb_guest_profile_minimal`

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

## `airbnb_message_workflow`

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

## `airbnb_operations_task`

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

## `airbnb_operations_risk_snapshot`

Derived operations-risk output from reviews, messages, tasks, maintenance,
cleaning, and turnover-load primitives.

Fields:

- `operations_risk_snapshot_id`
- `listing_id`
- `risk_class`
- `severity`
- `recent_examples`
- `recommended_intervention`
- `next_review_window`
- `decision`
- `confidence`
- `evidence_refs`
- `missing_required_evidence`
- `do_not_use_reason`
- `recommended_next_action`
- `observed_at`

Allowed `risk_class` values:

- `cleaning_quality_risk`
- `checkin_risk`
- `message_gap_risk`
- `maintenance_recurrence`
- `fee_complaint_risk`
- `turnover_overload`
- `review_theme_regression`

Allowed `severity` values:

- `low`
- `medium`
- `high`

## Operations joins

- Join reviews to reservations by `reservation_id` when visible; otherwise use
  listing, guest, and stay-date matching with confidence.
- Join messages and operations tasks to reservations by `reservation_id`.
- Join cleaning/check-in defects to calendar turnover load by listing and date.
- Keep internal guest notes separate from public review text and exported Airbnb
  fields.
