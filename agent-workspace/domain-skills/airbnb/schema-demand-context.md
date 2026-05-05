# Airbnb.com.au - Demand Context Schema

Airbnb data shows what happened on the platform. Demand context helps explain
why it happened and what may happen next.

## Data scope

These enrichments may come from public calendars, official event pages,
government holiday sources, weather services, transport data, manual host notes,
or other verified local sources. Keep them separate from Airbnb-native tables.

## `airbnb_market_event`

Local event or market driver.

Fields:

- `event_id`
- `market`
- `suburb_or_area`
- `event_name`
- `event_category`
- `venue_or_area`
- `start_date`
- `end_date`
- `expected_attendance_band`
- `demand_segment_tags`
- `distance_to_listing_km`
- `source_url`
- `source_confidence`
- `observed_at`

Refresh: weekly for the next 180 days and monthly beyond that.

## `airbnb_holiday_calendar`

Public, school, and seasonal holiday context.

Fields:

- `holiday_id`
- `jurisdiction`
- `market`
- `holiday_name`
- `holiday_type`
- `date_start`
- `date_end`
- `school_term_flag`
- `long_weekend_flag`
- `source_url`
- `observed_at`

Refresh: quarterly and annually after official calendars update.

## `airbnb_weather_context`

Weather and disruption context by date and market.

Fields:

- `weather_context_id`
- `market`
- `calendar_date`
- `forecast_or_actual`
- `temperature_min`
- `temperature_max`
- `rain_probability`
- `severe_weather_flag`
- `air_quality_flag`
- `beach_or_outdoor_suitability_score`
- `source`
- `observed_at`

Refresh: daily for the next 14 days, weekly for historical actuals.

## `airbnb_transport_access_signal`

Transport and access demand or disruption signal.

Fields:

- `transport_signal_id`
- `market`
- `signal_type`
- `start_date`
- `end_date`
- `affected_area`
- `expected_demand_effect`
- `source_url`
- `source_confidence`
- `observed_at`

Examples: airport disruption, major road closure, rail shutdown, major cruise
arrival, conference shuttle access, or event transport restriction.

## `airbnb_regulatory_market_signal`

Regulation or supply-change signal.

Fields:

- `regulatory_signal_id`
- `jurisdiction`
- `market`
- `signal_type`
- `effective_date`
- `description`
- `expected_supply_or_demand_effect`
- `official_source_url`
- `review_required_by`
- `observed_at`

Use as compliance and market-awareness context, not legal advice.

## `airbnb_demand_calendar`

Date-level demand features for pricing and calendar decisions.

Fields:

- `market`
- `calendar_date`
- `event_ids`
- `holiday_ids`
- `weather_context_id`
- `transport_signal_ids`
- `regulatory_signal_ids`
- `demand_window`
- `expected_demand_level`
- `expected_guest_segments`
- `confidence`
- `observed_at`

Refresh: daily for the next 90 days and weekly for 91-365 days.

## Demand-context joins

- Join `airbnb_demand_calendar` to `airbnb_calendar_snapshot` by market and
  date.
- Join events to listings by market, suburb, distance, and guest segment.
- Use demand context to explain booking pace and comp price changes before
  recommending price changes.
- Do not overwrite Airbnb performance data with external assumptions; store
  context as explanatory features.
