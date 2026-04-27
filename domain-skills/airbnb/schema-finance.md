# Airbnb.com.au - Internal Finance Schema

Airbnb earnings and payouts are not the same as owner profit. Use these tables to
turn Airbnb-visible economics into margin, owner statements, and cash-flow.

## Design rules

- Keep Airbnb-exported amounts immutable after import; corrections should be
  adjustment rows.
- Keep internal costs separate from Airbnb payout fields.
- Allocate costs at the narrowest defensible grain: reservation, night, month, or
  listing.
- Mark estimates separately from actual invoices.

## `airbnb_internal_cost_model`

Standing cost assumptions by listing.

Fields:

- `cost_model_id`
- `listing_id`
- `effective_start_date`
- `effective_end_date`
- `cleaning_base_cost`
- `short_stay_cleaning_surcharge`
- `linen_cost_per_stay`
- `consumables_cost_per_guest_night`
- `utilities_cost_per_night`
- `internet_cost_per_month`
- `management_fee_type`
- `management_fee_value`
- `maintenance_reserve_pct`
- `insurance_cost_per_month`
- `strata_or_body_corporate_cost_per_month`
- `owner_use_opportunity_cost_policy`
- `currency`
- `observed_at`

Refresh: monthly and whenever supplier, owner, or fee arrangements change.

## `airbnb_reservation_actual_cost`

Actual or estimated cost for a reservation.

Fields:

- `reservation_id`
- `listing_id`
- `cost_model_id`
- `cleaning_actual_cost`
- `linen_actual_cost`
- `consumables_actual_cost`
- `utilities_allocated_cost`
- `maintenance_allocated_cost`
- `management_fee_amount`
- `payment_processing_or_bank_fee`
- `damage_or_resolution_cost`
- `cost_estimate_flag`
- `invoice_refs`
- `observed_at`

Refresh: after checkout and after invoices arrive.

## `airbnb_owner_contract`

Owner or portfolio commercial arrangement.

Fields:

- `owner_contract_id`
- `owner_id`
- `listing_id`
- `effective_start_date`
- `effective_end_date`
- `owner_split_type`
- `owner_split_value`
- `minimum_guarantee_amount`
- `management_fee_type`
- `management_fee_value`
- `cleaning_pass_through_flag`
- `maintenance_approval_threshold`
- `statement_frequency`
- `currency`
- `observed_at`

Refresh: on contract change and quarterly audit.

## `airbnb_owner_statement`

Statement-level owner reporting.

Fields:

- `owner_statement_id`
- `owner_id`
- `listing_id`
- `period_start`
- `period_end`
- `gross_revenue`
- `airbnb_host_service_fee`
- `cleaning_fees_collected`
- `taxes_withheld_or_remitted`
- `adjustments`
- `internal_costs_total`
- `management_fee_amount`
- `maintenance_reserve_amount`
- `owner_net_amount`
- `statement_status`
- `sent_at`
- `observed_at`

Refresh: monthly or owner contract period.

## `airbnb_capex_maintenance_plan`

Longer-term property investment and maintenance planning.

Fields:

- `plan_item_id`
- `listing_id`
- `item_type`
- `issue_theme`
- `source_refs`
- `estimated_cost`
- `expected_revenue_or_quality_impact`
- `priority`
- `approval_status`
- `target_completion_date`
- `completed_at`
- `observed_at`

Refresh: monthly and after repeated maintenance/review themes.

## Finance metrics

| Metric | Formula |
|---|---|
| Contribution margin per stay | Net payout - actual stay costs |
| Contribution margin per night | Contribution margin / nights |
| Owner net RevPAN | Owner net amount / available nights |
| Cleaning margin | Cleaning fee collected - cleaning and linen actual cost |
| Break-even nightly rate | Allocated fixed/variable costs divided by sellable nights |
| Promotion margin safety | Discounted expected payout - variable stay cost |
| Maintenance drag | Maintenance costs / net payout |

## Finance alerts

| Alert | Trigger |
|---|---|
| Negative contribution stay | Expected or actual stay margin below zero |
| Cleaning fee under-recovery | Cleaning fee fails to cover cleaning + linen cost |
| Discount margin breach | Promotion or discount pushes expected stay below target margin |
| Owner statement incomplete | Airbnb payout exists but owner statement has missing costs or unresolved adjustments |
| Maintenance reserve shortfall | Maintenance reserve below recurring issue cost trend |
