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
- `views`
- `wishlist_additions`
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

## Performance joins

- Join pricing settings and rule-sets to `airbnb_calendar_snapshot` by
  `listing_id`, date range, and `observed_at` window.
- Join Insights to calendar/reservation economics by `listing_id` and reporting
  period.
- Use public comp tables from `schema-public-market.md` to calculate guest-facing
  price competitiveness.
- Join promotion eligibility to calendar snapshots so hosts can see when blocked
  dates or recent price history prevent promotion use.
