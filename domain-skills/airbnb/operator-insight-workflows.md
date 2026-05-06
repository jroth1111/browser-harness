# Airbnb.com.au - Operator Insight Workflows

Use this file when operator patterns need to become repeatable Airbnb
host-intelligence workflows. These workflows are final-state
processes: they consume already-collected Airbnb, public-market, finance,
demand, and operations primitives, then produce auditable decisions.

The workflows do not replace `workflows-current-state.md`,
`market-research-playbook.md`, or `analytics-alerts.md`. They sit above those
sources and turn recurring operator themes into bounded decision processes.

## Ownership

- Use this when: already-collected evidence needs a repeatable operator decision
  process for photo/product gaps, gallery CRO, content briefs, or case-study
  replay.
- Owns: content/product diagnosis gates, required evidence packs, bounded
  experiment framing, and decision-helper handoffs.
- Does not own: source collection, visual prompt generation, publishable copy
  craft, durable row contracts, or action/outcome tracking.
- Next hop: `content-optimization-playbook.md` for publishable copy/gallery
  craft, `visual-revenue-workflows.md` for prompt/correlation/design workflows,
  schema files for row contracts, and `decisioning.md` for accepted actions.

## Photo/Product Gap Audit

Question:

```text
Is the listing losing because the product presentation is weaker than A-comps,
or because price, rules, demand, or trust are the real bottleneck?
```

Run this before recommending broad price cuts when conversion is weak.

Required inputs:

- `listing_id`
- guest segment and stay length
- own public search card or own public listing audit
- A-comp search cards or A-comp public listing snapshots
- Insights conversion metrics when available
- comp price index when available
- review maturity and rating signals
- recent action history when available
- evidence refs

Capture layer:

- Public search-card collection should capture image labels from the card DOM
  when Airbnb exposes them, then store `hero_photo_subject_tag`,
  `first_five_photo_subjects`, and `obvious_differentiator_tags`.
- Public listing-page collection should capture image labels from the listing
  page when Airbnb exposes them, then store `hero_photo_subject`,
  `first_five_photo_subjects`, room proof flags, amenity proof flags,
  `amenity_claims_visible`, `amenity_claims_proven_in_photos`,
  `missing_photo_proof`, `design_gap_flags`, `photo_product_score`, and
  `photo_product_evidence_source`.
- Own public listing audits and public comp listing snapshots must use the same
  normalized field names so the audit compares like with like.
- When image labels are unavailable, keep the evidence source explicit and use
  the fields only as low-confidence content hints, not as proof that the photo
  itself shows the claimed feature.

Use only A-comps for visual/product comparison. A-comps must match the target
guest segment, stay length, room type, capacity, core amenities, season, and map
boundary. Premium or unreproducible winners can inspire a design brief, but they
do not prove the host has a content gap that can be fixed cheaply.

Audit dimensions:

| Dimension | Evidence |
|---|---|
| Hero photo | Own hero subject vs repeated A-comp hero subject |
| First five photos | Whether the main promise is proven before decorative shots |
| Sleeping capacity | Bedroom, bed, and layout proof for the target guest count |
| Amenity proof | Parking, pool, view, workspace, family, pet, self-check-in, or other thesis amenities |
| Trust | Rating, review count, badges, Guest Favourite, review maturity |
| Design/product | Whether room presentation is materially below A-comps |
| Guest segment fit | Whether content, rules, and layout match the intended guest |
| Price separation | Whether content/trust blockers are absent and price is the bottleneck |

Allowed issue classes:

- `hero_photo_gap`
- `photo_order_gap`
- `sleeping_capacity_not_proven`
- `amenity_not_visible`
- `trust_signal_gap`
- `design_gap`
- `guest_segment_mismatch`
- `price_not_content_problem`
- `no_clear_issue`

Decision rules:

- Weak search-to-listing conversion plus a repeated A-comp hero subject that the
  listing does not show returns `hero_photo_gap`.
- Weak search-to-listing conversion plus missing early-photo proof returns
  `photo_order_gap`.
- Weak listing-to-booking conversion plus missing sleeping layout proof returns
  `sleeping_capacity_not_proven`.
- Missing visible proof for a thesis amenity returns `amenity_not_visible`.
- Low review maturity or weak rating returns `trust_signal_gap`.
- Material room/design weakness or too little photo coverage returns
  `design_gap`.
- Mismatched actual and target guest segments returns `guest_segment_mismatch`.
- If content and trust blockers are not present but the comp price index is
  high, return `price_not_content_problem`.
- Do not recommend a price cut until photo, product, amenity, trust, and segment
  blockers have been ruled out.

Output:

```text
airbnb_photo_product_gap_audit
decision: fix | monitor | needs_more_data
primary_gap
issue_class
top_3_fix_candidates
expected_metric
review_window_days
confidence
evidence_refs
missing_required_evidence
do_not_use_reason
recommended_next_action
```

Use `scripts/decision_gates.py::audit_photo_product_gap()` for the pure local
evaluator.

When the result is `fix` with `hero_photo_gap`, `photo_order_gap`,
`sleeping_capacity_not_proven`, `amenity_not_visible`, `design_gap`, or
`guest_segment_mismatch`, create an
`airbnb_gallery_cro_execution_board` when the action is primarily gallery
selection/order/proof, then create an
`airbnb_listing_content_optimization_brief` using
`content-optimization-playbook.md` before editing the listing. The audit says
what is wrong; the gallery board says exactly which photo order and proof
actions can ship; the content optimization brief says what title, caption, and
copy changes should be made and how they will be tested.

## Gallery CRO Execution Board

Question:

```text
Which exact hero, first-five order, proof shots, captions, and test window
should ship for this listing?
```

Run this after a content-facing gate when the proposed action touches the
gallery. The board is narrower than a full content brief: it converts photo
evidence into an action-ready order, shot queue, and review window.

Required inputs:

- source issue class or explicit gallery request
- listing ID, target guest segment, stay length, seasonality, and channel goal
- current title or search-card promise
- primary why-book
- exact candidate photo IDs, image IDs, filenames, or URLs
- candidate photo subject, demand-driver score, clarity/diagnosticity score,
  and crop-safety score where available
- current photo order or current first-five state for rollback
- own public listing audit and A-comp visual patterns where available
- evidence refs

Decision rules:

- Price-only, trust-only, visibility-only, and no-clear-issue outputs return
  `monitor` unless the user explicitly requests gallery work.
- Missing exact candidate photos, current order, why-book, title promise, or
  evidence refs returns `needs_more_data`.
- A ship-ready board requires a cover-safe hero candidate and exact first-five
  photo identifiers.
- Missing room proof or thesis-amenity proof becomes a proof-shot queue.
- Captions must state what each selected image proves; they must not add facts
  that are not visible or host-provided.

Output:

```text
airbnb_gallery_cro_execution_board
decision: fix | monitor | needs_more_data
board_status: ready_to_ship | needs_photo_selection | not_applicable
hero_primary_photo_id_or_subject
hero_alternate_photo_ids_or_subjects
hero_crop_safety_score
first_five_order
room_coverage_plan
amenity_proof_plan
missing_proof_shots
reshoot_shotlist
edit_briefs
caption_copy_pairings
ab_test_plan
rollback_plan
action_checklist
expected_metric
review_window_days
confidence
evidence_refs
missing_required_evidence
do_not_use_reason
recommended_next_action
```

Use `scripts/decision_gates.py::build_gallery_cro_execution_board()` for the
pure local evaluator.

## Listing Content Optimization Brief

Question:

```text
Given a proven content bottleneck, what is the strongest concrete photo,
gallery, title, caption, and Airbnb-section copy change to test?
```

Run this after the content-facing decision gates, or when the user explicitly
asks for a photo/gallery/copy rewrite.

Required inputs:

- source decision gate and issue class
- listing facts, target guest segment, stay length, and seasonality
- own public listing audit and own search-card presentation
- A-comp visual and title/copy patterns where available
- current title, photo count, hero subject, first-five subjects, proof flags,
  missing photo proof, visible amenity claims, and content confidence
- host-provided facts for parking bay, building amenities, fees, house rules,
  same-day prep window, streaming limits, walkable anchors, and constraints
- prior content action history when available
- evidence refs

Use `content-optimization-playbook.md` for the craft rules. Keep this workflow
as the evidence and routing wrapper.

Output:

```text
airbnb_listing_content_optimization_brief
source_decision_gate
source_issue_class
optimization_scope
why_book
target_guest_segment
recommended_primary_title
recommended_challenger_title
above_fold_primary
above_fold_challenger
hero_primary_photo_id_or_subject
hero_alternate_photo_ids_or_subjects
hero_title_alignment
first_five_order
gallery_sequence_notes
caption_updates
missing_shots
reshoot_shotlist
edit_briefs
copy_sections
ab_test_plan
rollback_plan
missing_required_facts
content_risk_flags
evidence_refs
confidence
```

Decision rules:

- Do not create a content brief from `price_not_content_problem`,
  `trust_signal_gap`, or `no_clear_issue` unless the user asks for content work.
- Do not invent unavailable facts. Missing bed sizes, fees, parking clearance,
  amenity disclaimers, distances, or rules stay in `missing_required_facts`.
- If the proposed hero does not prove the proposed title, either change the
  hero or change the title before the brief is accepted.
- If exact photo IDs are unavailable, produce a subject-level brief and mark the
  exact image selection as missing evidence.
- Accepted briefs become `airbnb_recommendation` records. Implemented edits
  become `airbnb_action_log` records with rollback details. Controlled tests
  become `airbnb_experiment` records.

## Case Study Replay Workflow

Question:

```text
Can a walkthrough or coaching pattern be replayed as a controlled,
evidence-backed recommendation for this listing?
```

Use this for case studies, live coaching patterns, and rescue stories. The
workflow prevents vague advice from becoming a recommendation without
before-state evidence, counterexamples, and a measurable outcome.

Required evidence pack:

- case type
- starting symptom
- before-state evidence
- hypothesis
- counterexample matrix
- one smallest viable intervention
- expected metric
- pre-window and post-window
- rollback criteria
- review window
- evidence refs

Starting symptoms may include:

- high impressions with low search-to-listing conversion
- strong clicks with weak booking conversion
- slow-season empty calendar
- minimum-stay choke
- stale pricing or rule-set drift
- cleaning or check-in review recurrence
- strong design but weak location or anchor fit
- beautiful listing using unreproducible comps

Counterexample requirements:

- same market with the feature
- same market without the feature
- better design but weaker location
- worse design but stronger location
- same building, same block, or same friction boundary when available
- equal-or-worse comp still succeeding when property validation is involved

Decision rules:

- Missing before-state evidence returns `needs_more_data`.
- Missing counterexample matrix returns `needs_more_data`.
- Bundled interventions return `needs_more_data`; split them into one
  measurable change.
- A contradicted counterexample matrix returns `reject`.
- A supported or still-plausible pattern with one intervention returns `fix` and
  an experiment template.

Output:

```text
airbnb_case_study_replay
decision: fix | reject | needs_more_data
validated_pattern
case_type
starting_symptom
expected_metric
experiment_template
confidence
evidence_refs
missing_required_evidence
do_not_use_reason
recommended_next_action
```

Accepted case-study replays should become `airbnb_recommendation`,
`airbnb_action_log`, and `airbnb_experiment` records in `decisioning.md`. Do not
claim causal lift until the outcome window has been reviewed against demand
context and confounders.
