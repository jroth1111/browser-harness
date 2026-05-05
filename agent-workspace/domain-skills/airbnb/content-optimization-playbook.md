# Airbnb.com.au - Listing Content Optimization Playbook

Use this playbook after collected evidence shows that listing presentation is a
conversion bottleneck. It turns `airbnb_conversion_diagnosis` and
`airbnb_photo_product_gap_audit` outputs into concrete photo, gallery, title,
and Airbnb-section copy changes that can be logged, tested, and reviewed.

This file is the craft layer. It does not collect Airbnb data and it does not
decide whether content is the bottleneck. Collection belongs in
`collect_own_public.py`, `collect_competitors.py`, and related source workflows.
Classification belongs in `scripts/decision_gates.py`. Recommendation tracking
belongs in `decisioning.md`.

For structured local output, use
`scripts/decision_gates.py::build_listing_content_optimization_brief()` after a
content-facing gate returns `fix`. The helper assembles the machine brief,
missing-shot guidance, rollback plan, and A/B-test scaffold from already
collected evidence; this playbook supplies the judgement rules used to refine
the host-facing copy/photo brief.
Callers may pass the source gate either as flattened fields
(`source_issue_class`, `expected_metric`, `review_window_days`, `evidence_refs`)
or as a nested `source_photo_product_gap_audit`,
`source_conversion_diagnosis`, or `source_decision_gate_output` record.

For gallery-only execution, use
`scripts/decision_gates.py::build_gallery_cro_execution_board()`. The board
turns exact photo candidates, current order, A-comp visual patterns, and the
listing promise into the hero, first-five order, proof-shot queue, captions,
rollback plan, and A/B review window needed before a photo-order change is
logged.

## Ownership

- Use this when: a content-facing gate returns `fix`, or the user explicitly
  asks for listing copy, title, caption, gallery, or photo-order optimization.
- Owns: publishable title/copy/gallery/caption/shot-brief craft, A/B plan
  structure, rollback requirements, and content safety rules.
- Does not own: raw evidence capture, deciding whether content is the
  bottleneck, visual prompt/correlation rows, durable row field lists, or
  implemented action logs.
- Next hop: `scripts/decision_gates.py` for machine brief builders,
  `schema-core.md` for row contracts, and `decisioning.md` for accepted edits,
  experiments, rollback, and outcome review.

## Architecture

| Layer | Responsibility | Primary files |
|---|---|---|
| Evidence capture | Guest-visible own listing, search-card, comp listing, title, photo subjects, proof flags, prices, trust signals | `public-market.md`, `schema-public-market.md`, collectors |
| Decision gate | Classify the bottleneck and decide whether a content action is justified | `scripts/decision_gates.py`, `schema-performance.md` |
| Photo analysis metadata | Preserve image-level captions, visible subjects, room/area, amenity proof, view type, quality scores, edit safety, and current gallery position | `visual-revenue-workflows.md`, `schema-visual-revenue.md` |
| Gallery CRO execution board | Select exact hero/first-five actions, proof shots, captions, rollback, and test window | `scripts/decision_gates.py`, `schema-core.md` |
| Visual calibration | Correlate photos/features/copy against revenue, profit, and Insights conversion stages, then generate prompt/design candidates | `visual-revenue-workflows.md`, `schema-visual-revenue.md` |
| Content optimization brief | Draft the best photo order, shot list, title, above-fold copy, section copy, and A/B plan | this file |
| Action and learning | Store accepted edits, rollback, experiment window, outcome review, and confounders | `decisioning.md` |

Do not use this playbook as an unconditional makeover prompt. Run it when a
decision gate returns a content-facing issue class or when the user explicitly
asks for a listing-content rewrite or gallery optimization.

Do not store visual observation, image prompt, or design-opportunity rows here.
Those row contracts live in `schema-visual-revenue.md`; this file only turns
approved evidence into publishable copy, gallery, caption, and shot briefs.

## Trigger Map

| Gate output | Use this playbook for | Primary metric |
|---|---|---|
| `search_card_click_problem` | Hero, title, visible promise, first-five proof | Search-to-listing conversion |
| `listing_page_conversion_problem` | Full gallery order, amenity proof, copy clarity, rules/friction | Listing-to-booking conversion |
| `photo_or_design_gap` | Gallery coverage, reshoot list, edit briefs, caption proof | Listing-to-booking conversion |
| `amenity_visibility_gap` | Amenity proof photos, captions, amenity fields, guest-access copy | Filtered visibility and conversion |
| `guest_segment_mismatch` | Persona-specific title, photo order, copy promise, rules alignment | Segment conversion |
| `hero_photo_gap` | Cover replacement, crop notes, title alignment, hero A/B test | Search-to-listing conversion |
| `photo_order_gap` | First-five reorder, gallery sequence, missing early proof | Search-to-listing or listing-to-booking by Insights stage |
| `sleeping_capacity_not_proven` | Bedroom/sleeping proof photos and copy | Listing-to-booking conversion |
| `amenity_not_visible` | Parking/view/workspace/family/pet/self-check-in photo proof and copy | Listing-to-booking conversion |
| `design_gap` | Reshoot/edit brief, room coverage, capex-vs-content boundary | Listing-to-booking conversion |

If the gate returns `price_not_content_problem`, `trust_signal_gap`, or
`no_clear_issue`, do not produce a broad content rewrite unless the user asks
for one. Record content observations as supporting evidence only.

## Required Inputs

Use the strongest available evidence. Missing fields should be listed in the
brief rather than guessed.

| Input | Why it matters |
|---|---|
| Listing facts | Property type, guest cap, bedrooms/baths/beds, dining seats, lounge seats, kitchen equipment, room layout, parking, EV, workspace, laundry, balcony/alfresco, view, level/storey, building amenities |
| Guest and stay context | Target segment, stay length, seasonality, work/family/couple/group intent |
| Current public presentation | Title, photo count, hero subject, first-five subjects, proof flags, visible amenities, ratings, badges |
| Photo analysis metadata | Per-photo caption, source, room/area, visible subjects, visible amenities, view type, quality scores, edit candidate flags, safety constraints, and current gallery position |
| Insights conversion evidence | Period-aligned impressions, search-to-listing, listing-to-booking, views, wishlists, and conversion diagnosis for the listing |
| A-comp presentation | Repeated winning hero subjects, proof patterns, first-five coverage, price context, trust context |
| Location proof | Walkable anchors with realistic distances or times, transport, beach/CBD/event anchors |
| Operational facts | Same-day prep window, check-in method, noise realities, building-managed amenity disclaimer, streaming limitations, fee schedule only when host-provided |
| Constraints | Do-not-mention facts, privacy, spaces to omit, facts requiring host confirmation |

## Content Principles

- Optimize for revenue per impression: CTR x post-click conversion x ADR x LOS.
- Let the failed funnel stage pick the content lever. Do not solve a visibility
  problem with prettier photos, a search-card click problem with deep gallery
  copy, or a high-wishlist/low-booking problem with more artificial momentum.
- Lead with the strongest verifiable reason to book, not a generic adjective.
- Keep the title, hero, first five photos, and above-fold copy aligned.
- Use specifics over claims: numbers, bed sizes, distances, aspect, level,
  parking details, appliance brands, Wi-Fi speed, and real limitations.
- Write copy as an experience promise to the target guest, not a real-estate
  spec sheet. Use second-person, sensory language only where the listing facts
  support it, then back the promise with a plain list of real amenities and
  constraints.
- Use "message us" style calls to action only when the host can actually help
  with planning, local recommendations, access questions, or pre-arrival service.
  Otherwise, do not turn service into a claim the operation cannot deliver.
- Do not fabricate property features, views, distances, fees, amenities, or
  guest rules.
- Treat compliance and policy as upstream or host-reviewed, but preserve
  risk-reducing truths in `Other things to note` when provided.
- Use Australian English and local terms: lounge, alfresco, BBQ,
  reverse-cycle, storey/level, metres, and kilometres.

## Insights-Vs-Listing Correlation Layer

Use this layer when Insights, public listing audits, photo observations, and
economics exist for the same listing or portfolio period. The goal is to stop the
LLM from making generic "better photos" recommendations when the data says a
different stage of the funnel is broken.

Minimum source set:

```text
airbnb_insights_conversion
airbnb_conversion_diagnosis
airbnb_photo_product_gap_audit
airbnb_visual_listing_observation
airbnb_visual_image_observation
optional revenue/profit workbook
```

Join by `listing_id` and reporting period first. If the period differs, record
the mismatch as a confounder instead of treating a photo pattern from one season
as the cause of another season's conversion result.

Stage diagnosis:

| Observed pattern | Primary interpretation | Content action |
|---|---|---|
| Low impressions or no first-page search presence | Visibility, availability, rule, price, filter, or rank problem | Do not lead with gallery edits; inspect pricing, availability, filters, restrictions, search relevance, and comp position |
| High impressions with low `search_to_listing_conversion` | Search-card promise is not earning the click | Prioritize hero, title, thumbnail crop, visible differentiator, seasonal hook, and comp-set pattern break |
| Strong search-to-listing but weak `listing_to_booking_conversion` | Listing page is not converting the click into confidence | Prioritize first five, photo-tour proof, copy clarity, amenity proof, rules/fee trust, price friction, and missing objection answers |
| High views or wishlists with weak booking | Curiosity exists but commitment is blocked | Check price, fees, cancellation/min-stay rules, trust surface, proof gaps, and segment mismatch before claiming a photo win |
| Good conversion with weak revenue/profit | Demand can convert but economics lag | Inspect ADR, LOS, occupancy, rent/owner economics, orphan nights, and channel mix before rewriting the listing |

For each recommended content or image action, carry these fields into the brief:

```text
insights_period_start
insights_period_end
insights_metric_basis
insights_funnel_stage
search_to_listing_delta_basis
listing_to_booking_delta_basis
wishlist_to_booking_friction_basis
conversion_correlation_basis
conversion_stage_priority
expected_metric_to_move
conversion_confounder_flags
insights_confidence
```

Interpret correlations by funnel stage:

- A photo or title pattern correlated with `search_to_listing_conversion` is
  top-of-funnel evidence. Use it to choose hero/title/crop/pattern-break tests.
- A pattern correlated with `listing_to_booking_conversion` is post-click proof
  evidence. Use it to choose first-five order, room heroes, missing proof shots,
  trust copy, and AI edits that clarify real evidence.
- A pattern correlated with views or wishlists but not bookings is not enough to
  justify promotion. It may be curiosity, broad appeal, low-intent traffic, or
  price/rules friction.
- A visual-profit correlation should shape prompt priorities and quality bars,
  but it should not override a clear Insights-stage diagnosis. Profit tells what
  kind of visual product tends to win; Insights tells which funnel problem this
  listing currently has.

Anti-overfit rule for photo and image-edit decisions:

- Treat the prior correlation analysis as directional pattern evidence, not as a
  literal recipe. The reusable pattern was that stronger listings made the real
  product clearer, sharper, better composed, better sequenced, more intentionally
  presented, and easier to trust.
- Do not chase exact coefficients, top-quartile examples, or a prior property's
  look. Ask whether the pattern transfers to this listing's guest segment,
  season, comp set, price position, funnel stage, and source-visible facts.
- If a correlated pattern conflicts with strategic fit, arrival accuracy,
  reviews, or the active Insights-stage diagnosis, keep the strategic judgement
  and record the correlation as a weak or non-transferable hypothesis.
- The right output can be `no_safe_prompt`, `resequence`, `reshoot`, `staging`,
  `copy/rules/price review`, or `operations dependency`; image editing is only
  correct when it clarifies value already present in the source photo.

## Photo Optimization

### Operator Mental Model

Think about photos the way a high-performing STR operator thinks about the
booking funnel:

```text
search impression -> curiosity click -> first-five trust check -> photo-tour proof -> full-gallery due diligence -> booking confidence -> arrival/review payoff
```

Promise/payoff ladder:

| Stage | Promise made | Payoff required |
|---|---|---|
| Search card | Title and hero say "this is worth opening" | Listing page immediately feels like the same product |
| First five | The home has enough depth, quality, and proof to consider | Five-photo collage rewards the click with varied, high-value evidence |
| Photo tour | Each room/area is real and usable | The room hero and supporting images answer practical questions |
| Full gallery | Claimed amenities, layout, and constraints are transparent | Guest can complete due diligence without messaging |
| Stay/review | The listing accurately represented the experience | Arrival does not create a bait-and-switch feeling |

The guest is not studying the listing patiently. They are scanning against
nearby alternatives, often on mobile, with several listings open. They will not
message to resolve a confusing photo; they will usually leave. Evaluate each
image as a piece of buyer psychology:

- `search_card`: does the title/hero create a truthful pattern break that earns
  the click in this comp set?
- `first_five`: after the click, do the next images prove that the home is full,
  varied, real, and worth considering?
- `trust`: do the photos, title, copy, price, reviews, and claimed amenities feel
  like one consistent product?
- `proof`: does each important claim have a visible, high-confidence image?
- `curiosity`: are we withholding just enough to invite the listing click, while
  still paying off the promise immediately after the guest opens it?
- `editing`: can AI clarify what is already true, or is this really a reshoot,
  resequence, or product/staging problem?
- `experience_fit`: does the visible product fit the guest archetype's actual
  stay, or is it over-amenitized, under-proven, or aimed at the wrong buyer?
- `capacity_fit`: do sleep count, dining seats, lounge seating, kitchen gear,
  bathrooms, and outdoor seating tell one believable group-size story?
- `sleep_quality`: do bedroom photos and known host facts support the review
  promise of a comfortable night's sleep?
- `theme`: does color, styling, or theme create a coherent emotional promise for
  the target segment, or only add visual noise?
- `review_risk`: does the image surface a maintenance, cleanliness, stock,
  service, or expectation risk that will show up later in reviews?
- `review_relevance`: will the guest who books from this promise likely leave
  review language that reinforces the same filters, trip type, and amenities?
- `photo_currency`: is the image still current enough that a guest could not
  credibly say the home was materially different on arrival?

This means the best-looking image is not always the best conversion image.
Prefer the image that makes a guest think "I need to see more" in search and
"this is exactly what I expected" after opening the listing. Penalize stale
photos, mixed visual eras, duplicate angles, title/photo tone shifts, and images
that require the viewer to understand the whole house before the hook makes
sense.

Run the same analysis as a creator looking at a feed, not only as a property
manager looking at a room. Search the current comp set, identify the default
visual pattern, and ask whether the photo truthfully interrupts that pattern.
Also keep the qualitative context alive: base data such as beds, pool, and
suburb does not explain performance unless the photos, reviews, copy, design,
service, and trust cues are interpreted together.

The strongest gallery is not the biggest inventory dump. It is the smallest set
of images that makes the right guest believe the stay will work for their trip.
When the listing targets couples, a strong king room may beat extra beds. When it
targets families or groups, every capacity claim must be backed by visible
evidence: dining seats, lounge seating, kitchen equipment, bathrooms, outdoor
use, and sleeping arrangements. If the photos cannot prove that fit, record a
proof-shot or operations dependency instead of promoting the claim.

Think past the booking into the review loop. If the gallery promises pet stays,
family cooking, long-stay work, free parking, self check-in, or group trips, the
best outcome is not just a click; it is a five-star stay where the guest's review
and Airbnb-visible trip context reinforce that same job. Do not optimize toward
guest segments that the home cannot delight, because irrelevant clicks and
misfit bookings create weak reviews, refund/resolution risk, and worse future
matching.

### Metadata-First Flow

Use `photo_analysis` rows as the bridge between downloaded source photos,
photo-order decisions, AI editing prompts, exported filenames, and rollback.
Do not treat filenames as evidence; filenames are derived from metadata.

Minimum reusable flow:

```text
photo_manifest + source images
-> photo_analysis metadata
-> gallery CRO execution board
-> AI edit prompt rows for selected source photos
-> edited-photo review metadata
-> export/upload package and rollback record
```

For photo order, consume these image-level fields first:

```text
listing_id
photo_ordinal
photo_key
caption
caption_source
room_or_area
visible_subjects
visible_amenities
view_type
interior_exterior_class
confidence
current_gallery_position
source_capture_quality_flags
shot_type
product_photography_staging_notes
eye_candy_or_statement_piece_basis
hero_crop_control_notes
promise_payoff_stage
seasonal_relevance
comp_set_pattern_basis
pattern_break_basis
under_serviced_amenity_basis
first_five_collage_role
room_hero_candidate_flag
room_amenity_declaration_basis
storyline_contribution
guest_message_question_basis
kitchen_proof_package_status
guest_archetype_fit_basis
experience_fit_proof_status
sleep_quality_proof_status
capacity_fit_proof_status
theme_emotional_promise_basis
maintenance_review_risk_flags
service_signal_basis
query_filter_alignment_basis
review_relevance_basis
photo_currency_status
post_clean_condition_evidence_status
as_pictured_risk_flags
momentum_signal_caution_flags
perception_of_effort_score_0_100
gallery_fatigue_risk
visual_tone_sequence_notes
observed_hero_test_data
insights_period_start
insights_period_end
insights_metric_basis
insights_funnel_stage
search_to_listing_delta_basis
listing_to_booking_delta_basis
wishlist_to_booking_friction_basis
conversion_correlation_basis
conversion_stage_priority
expected_metric_to_move
conversion_confounder_flags
insights_confidence
correlation_generalization_basis
pattern_transfer_check
strategic_fit_basis
overfit_risk_flags
strategic_override_notes
demand_driver_score_0_100
clarity_diagnosticity_score_0_100
crop_safety_score_0_100
thumbnail_hook_score_0_100
mobile_crop_score_0_100
scroll_stop_score_0_100
guest_question_answered
objection_reduced
trust_signal_type
proof_strength_0_100
title_photo_promise_alignment
tone_shift_risk_flag
fear_trigger_risk_flags
post_click_trust_surface_flags
misleading_risk_flags
duplicate_group_id
conversion_role
recommended_gallery_action
edit_vs_reshoot_decision
reshoot_shot_brief
qualitative_context_notes
accuracy_risk_notes
```

`conversion_role` should use values such as:

```text
hero_candidate
first_five_candidate
curiosity_buffer
photo_tour_room_hero
amenity_proof
room_proof
support_photo
local_area_context
building_context
duplicate_or_filler
reshoot_needed
edit_needed
```

The ordering algorithm should be metadata-driven:

Before ranking photos, classify the active Insights stage for the listing:

- `visibility`: gather eligibility, calendar, rule, filter, and price evidence
  first; gallery work is supporting context unless a content gap is blocking
  filtered search relevance.
- `search_card_click`: rank hero candidates by thumbnail hook, comp-set pattern
  break, title alignment, seasonal relevance, and mobile crop safety.
- `listing_page_conversion`: rank first-five and room-hero candidates by proof
  strength, objection reduction, trust signal, room usability, and
  "as pictured" safety.
- `wishlist_or_view_friction`: keep the best proof images, but inspect price,
  rules, fees, cancellation, guest-segment fit, and trust gaps before editing
  more photos.
- `economics_not_content`: preserve winning content and route the decision to
  pricing, LOS, occupancy, channel, or rent economics.

1. Evaluate the search feed before choosing the hero. Record the current
   comp-set pattern and the truthful pattern break the candidate creates.
2. Check the seasonal demand driver. A hot tub, fireplace, pool, alfresco, beach
   access, work setup, or family feature can deserve hero treatment in one
   season and support placement in another.
3. Choose the hero from high-confidence, high-scoring photos that win the
   search-card click without creating a misleading promise. The hero does not
   have to reveal every feature; it does have to make the next click feel
   worthwhile and truthfully align with the title.
4. Check whether the candidate was built for the hero crop. Control the square
   search-card crop, mobile crop, and desktop five-photo crop so the hook is not
   lost at the edges.
5. Build the first five as five hero photos that work together as the desktop
   collage, not as the photographer's room-tour sequence: search hook,
   space/flow proof, sleep proof, cooking/work/outdoor use proof, and
   cleanliness/amenity proof. Swap slots when the target segment's main
   objection demands a different proof order.
6. Check right-fit before over-selling inventory. A photo sequence for a couple,
   solo work trip, family, group weekend, or pet stay should prove the experience
   that segment wants, not simply maximize visible amenities.
7. Treat bedrooms as review-risk proof, not filler. Promote bedroom images that
   show the correct bed mix, headboard or focal wall, bedside function, blackout
   or window treatment, storage, clean linens, and comfort cues; queue a reshoot
   when sleep quality is important but not visible.
8. Treat group capacity as a system. Do not promote max guests unless dining
   seats, lounge seating, kitchen equipment, bathrooms, sleeping arrangements,
   and outdoor/common areas make the group experience believable.
9. Preserve curiosity only while preserving trust. Do not hide a claimed feature
   so deeply that guests cannot verify the promise after opening the listing.
   Outdoor or exterior curiosity can work well when it creates a click without
   misrepresenting the interior product.
10. Choose a hero for each Airbnb photo-tour room or area. The first living room,
   kitchen, bedroom, bathroom, balcony, yard, pool, gym, or parking image should
   be intentional and should answer that room's strongest guest question.
11. Treat under-serviced amenity combinations as demand drivers only when the
   comp set shows scarcity and the listing can prove the amenity visually.
12. Treat lead color, theme, and statement pieces as emotional positioning. Use
   them when they clearly signal the right segment's desired memory and create a
   truthful comp-set pattern break; demote them when they are only decoration.
13. Check query and review relevance. The hero, first five, captions, amenities,
   and copy should attract guests whose likely filters and review language match
   the listing's real strengths.
14. Check photo currency and "as pictured" risk. Stale photos, changed decor,
   missing amenities, seasonal pool/gym status, or untracked condition changes
   should become update, disclosure, or post-clean evidence work.
15. Edit the full gallery like a storyline. Each image should add excitement,
   proof, or clarity. If it repeats the same scene without adding information,
   demote or remove it.
16. Avoid gallery fatigue. If the guest is ready to book after a tight 12-25
   image sequence, do not force them through redundant room angles, dark support
   shots, or low-value details before the booking controls.
17. Sequence mood and brightness deliberately. Do not whip the guest from bright
   bathroom to dark arcade to bright bedroom unless the contrast has a clear
   story reason.
18. Include amenity proof early only when the amenity is a real booking driver
   for the segment; otherwise place it after core room proof.
19. Demote duplicate angles, decorative details, building exteriors, local-area
   photos, and weak support images unless they prove the primary promise.
20. Do not make fear-trigger attributes the title/hero/first-five promise unless
   they are positive demand drivers for the intended guest. Truthful disclosure
   can sit later in copy, amenities, or support photos.
21. Use old guest messages and reviews as a source of real decision questions.
   If guests repeatedly ask how to use, find, access, cook, park, sleep, work, or
   check in, answer that with photo proof, captions, copy, or house-manual text.
22. Record visible maintenance, cleanliness, supply, cookware, linen, or service
   risks as dependencies. These are review risks and expectation risks, not
   image-polish problems.
23. Treat artificial momentum signals carefully. Wishlist campaigns, friend
   clicks, and non-consumer traffic can confound hero/photo tests; they are not
   the same as qualified searchers opening, booking, staying, and reviewing well.
24. If a claimed amenity has no high-confidence proof image, add it to the
   proof-shot queue instead of using copy as a substitute.
25. Preserve the old order and the proposed order with photo keys, captions, and
   rationale so rollback is possible.

For AI photo editing, consume the same `photo_analysis` row plus edit-safety
fields before generating a prompt:

```text
insights_metric_basis
insights_funnel_stage
conversion_correlation_basis
conversion_stage_priority
expected_metric_to_move
conversion_confounder_flags
correlation_generalization_basis
pattern_transfer_check
strategic_fit_basis
overfit_risk_flags
strategic_override_notes
edit_candidate_flag
edit_reason
allowed_edit_types
forbidden_edit_types
factual_anchors
accuracy_constraints
qualitative_context_notes
ai_skepticism_review_notes
source_photo_path
edited_photo_path
edit_review_status
```

Allowed edit types are limited to truthful presentation improvements: straighten
verticals, neutral white balance, realistic brightening, crop variants, glare
control, denoise/deblur, and minor removable-object declutter. Forbidden edits
include adding or changing furniture, layout, windows, views, amenities, beds,
parking, pool, gym, balcony, flooring, fixtures, or apparent room size.

Use the Insights stage to decide whether an AI edit is the right lever:

- For `search_card_click`, edit only hero or alternate-hero candidates where the
  source-visible hook can be made clearer in thumbnail crops.
- For `listing_page_conversion`, edit proof images that remove a real objection:
  sleep, cooking, workspace, parking, view, access, cleanliness, capacity, or
  room usability.
- For `wishlist_or_view_friction`, prefer resequence, copy/rules/price review,
  or proof-shot collection unless the image has a specific trust defect.
- For `visibility` or `economics_not_content`, do not emit image prompts as the
  primary action unless image evidence directly supports the diagnosed issue.

Use the transfer check to decide whether a correlated visual pattern belongs in
the prompt. For example, the prior workbook made clarity, composition, believable
interior polish, and first-five proof look valuable; that should make the agent
look for those opportunities first. It should not make the agent invent luxury,
over-brighten every room, demote a strategically important but lower-correlation
proof shot, or edit a support photo into a fake hero.

### Transcript-Derived Photo Levers

The `/tmp/airbnbautomated` transcript corpus reinforces these high-leverage
patterns:

- Treat the hero and title as the top-of-funnel promise. A strong hero earns the
  click in search, but a hero/title mismatch creates distrust after the click.
  The payoff chain continues through listing dwell time, booking, arrival,
  review, and rebooking.
- Think like a creator in an attention marketplace. Airbnb decides impressions;
  the host decides whether the hero/title/photo sequence earns clicks.
- Treat pattern break as market-specific. Search the comp set and identify the
  default look before calling a photo scroll-stopping.
- Treat hero selection as seasonal. Keep the best current demand driver forward,
  and rotate away from amenities whose season has passed.
- Treat hero selection as an experiment when data exists. Save the old hero,
  proposed hero, test window, impressions, views, click-through, bookings, and
  review outcome so the next agent can learn from the market instead of guessing.
- Treat the first five as the middle-of-funnel vibe and proof check. They are
  five hero photos in a collage, not five attractive duplicates or the first
  five files from the photographer.
- Treat each photo-tour room/area as having its own hero. The full gallery is a
  movie edit: every image should continue the storyline and increase interest.
- Treat room-level amenity declaration as visual work. If Airbnb asks for room
  amenities, each room hero and support image should prove the room's useful
  features instead of only decorating the gallery.
- Treat Airbnb photography as product photography. Stage the stay so the photo
  proves ease and use: coffee station ready, TV showing the family streaming
  promise when true, pool/alfresco props in place, bed linens crisp, and kitchen
  ready to cook.
- Treat eye candy as a conversion asset. Color, expressive props, statement
  pieces, dramatic lighting, murals, art, plants, towels, floaties, and other
  memorable details should create a truthful click hook instead of a generic
  real-estate listing.
- Treat source capture quality separately from edit quality. Low-resolution,
  screenshot-derived, grainy, underexposed, crooked, overcompressed, or unevenly
  lit photos are reshoot/crop/level problems before they are AI-edit problems.
- Treat kitchens as a proof package, not a single wide shot. For listings where
  cooking matters, show the kitchen wide, ready-to-cook work surface, clean
  fridge/water proof, coffee/tea station, and quality cookware or knives when
  those are real.
- Treat trust as a conversion asset. Old photos mixed with new photos, title
  tone that does not match the gallery, or a too-good-to-be-true visual promise
  should be flagged before testing.
- Treat perceived effort as a trust signal. Clean, maintained, specific, and
  cared-for photos reduce the feeling that the guest will be taken advantage of.
- Treat fees, rules, and messages as part of the same trust surface as photos.
  A beautiful gallery can be undercut by excessive cleaning-fee optics,
  overbearing rules, threatening automated messages, or copy that oversells.
- Treat fear triggers carefully. Pet/smoker status, tight layouts, worn
  finishes, or shared/limited amenities can be true but still poor top-of-funnel
  promises if they create avoidable cleanliness, comfort, or confidence fears.
- Treat qualitative context as first-class data. Photos, reviews, descriptions,
  design quality, service signals, and trust cues explain performance in ways
  beds/pool/suburb fields cannot.
- Treat old guest questions as conversion research. Message history and reviews
  reveal proof gaps that raw listing facts miss.
- Treat gallery length and mood sequencing as conversion risks. A long reel can
  make interested guests apathetic; abrupt brightness or color shifts can make
  the shopping experience feel incoherent.
- Treat AI editing as a production accelerator, not a substitute for missing
  product proof. AI can make source-visible value more legible; it should not
  invent a hero hook, amenity, layout, view, or design finish.
- Treat AI output skeptically. Use a war-room style pass to surface arguments,
  blind spots, and objections, but do not trust AI as the final authority on
  accuracy, guest promise, or listing strategy. Do not ask AI to invent revenue
  strategy from generic priors; give it operator rules, real listing data,
  review/message evidence, and hard constraints.

For every photo considered for hero, first-five, or AI editing, record:

```text
what click or decision question this photo answers
which guest objection it reduces
which trust signal it creates or risks
whether the title/hero/gallery promise stays consistent
what current comp-set pattern this photo breaks or follows
where it sits in the promise/payoff ladder
whether the photo's hook is seasonally relevant now
which under-serviced amenity, if any, it proves
which guest archetype the image fits and why that fit is believable
whether the image proves the actual stay experience: sleep, cook, sit, work,
  arrive, gather, or make the promised memory
whether sleep quality is visible or supported by trustworthy non-image facts
whether group capacity is proven by dining, lounge, kitchen, bathroom, outdoor,
  and sleeping evidence rather than bed count alone
whether theme, lead color, or statement piece supports an emotional promise to a
  specific segment
whether visible wear, low-quality supplies, missing stock, cleaning risk, or weak
  service cues should become an operations dependency
whether the photo aligns with the filters, trip type, and review language the
  listing wants to accumulate
whether the photo is current enough to survive an "as pictured" challenge
whether post-clean photos/videos, recent walkthroughs, or prior review language
  support the condition shown
whether any observed views, wishlists, friend clicks, or dwell-time signals are
  qualified guest intent or only temporary momentum/noise
whether old messages or reviews show this question matters
whether it advances the gallery storyline or repeats a scene
whether it introduces a fear trigger or trust objection
whether it increases perceived host effort and care
source capture quality defects such as grain, low resolution, screenshot
  reupload, crooked verticals, uneven light, overcompression, or bad crop
shot type: establishing, medium, feature/detail, product-staged, lifestyle, or
  support/disclosure
staging and eye-candy evidence: what visible prop, color, statement piece,
  lighting move, or product setup makes the stay easier or more memorable
crop-control notes for search card, mobile, and desktop first-five display
whether the gallery is already long enough that this image creates fatigue
whether the image creates a jarring mood/brightness transition from neighbours
any observed hero-test data tied to the photo: test dates, impressions, views,
  click-through, bookings, and notes about confounding season/price changes
whether the source photo should be edited, reshot, resequenced, or discarded
```

Use this as the working heuristic: a photo can be beautiful and still be a bad
conversion photo if it does not earn a click, answer a guest question, prove a
claim, or preserve trust.

### Scoring

Score each candidate image from 0 to 100:

```text
Photo score =
  0.35 x DemandDriver
+ 0.25 x ClarityDiagnosticity
+ 0.20 x ThumbnailHook
+ 0.10 x CropSafety
+ 0.10 x TrustProof
```

| Component | What to check |
|---|---|
| DemandDriver | Strength and salience of a top USP: view, alfresco, pool/spa, grand lounge, designer kitchen, luxe primary suite, signature architecture, scarce parking, work-ready setup |
| ClarityDiagnosticity | Brightness, colour fidelity, straight verticals/horizon, readable layout/scale, low glare, subject separation |
| ThumbnailHook | Whether the image stops the scroll and creates a truthful reason to open the listing in the current comp set |
| CropSafety | USP remains central and legible in 1:1, 16:9, 3:2, and 4:5 crops |
| TrustProof | Whether the photo supports the title/listing promise, reduces an objection, and avoids stale, misleading, or too-good-to-be-true cues |

Separately tag `source_capture_quality_flags` and
`product_photography_staging_notes`. A technically flawed source can score well
for demand driver but still require original-file recovery or reshoot; a clean
real-estate image can be technically strong but commercially weak because it
does not show the stay ready to use.

Apply a 10-20 point redundancy penalty to near-duplicates competing in the top
eight. Treat near-duplicates as frames from the same corner or height with
roughly the same subject and angle.

Apply a hard review gate before any hero or first-five recommendation when:

- the photo only works if the viewer already understands the whole home
- the mobile crop removes the booking hook
- the title promise and image promise attract different guest intents
- the title, hero, or first-five image foregrounds a fear trigger that is not
  the target guest's positive reason to book
- the photo appears stale against other gallery photos
- the photo leads with an off-season hook while a stronger current demand driver
  exists
- the image proves an amenity or view weakly but the copy claims it strongly
- the image attracts a guest archetype the home is not set up to satisfy
- a capacity claim is visible or implied but dining, lounge, kitchen, bathroom,
  outdoor, or sleep proof is missing
- sleep quality is a main promise but the bedroom image is plain, under-staged,
  missing comfort cues, or unsupported by host facts/reviews
- visible wear, cheap supplies, missing kitchen stock, cleaning risk, or service
  gaps would likely become a review issue
- the image is stale, the amenity is seasonal/closed, the furnishings have
  changed, or no current condition evidence supports the photo
- the photo attracts a filter/trip type that the listing does not want to earn
  future reviews for
- an AI edit would be needed to add, not merely clarify, the conversion hook

Hero candidates should usually have DemandDriver >= 80,
ClarityDiagnosticity >= 75, ThumbnailHook >= 75, CropSafety >= 80, and no
unresolved title/photo trust risk. First-five photos should usually score >= 70.
If the inventory cannot meet that bar, recommend an edit, resequence, or reshoot
rather than pretending the gallery is fixed.

### Hero Selection

Choose one primary hero and two alternates.

Rules:

- The hero must create a truthful reason to open the listing, align with the
  title promise, and be instantly readable as a phone thumbnail.
- The hero should be evaluated against the current comp set, not in isolation.
  Record whether it creates a truthful pattern break or merely repeats the
  market default.
- The hero should be re-evaluated when seasonality, events, weather, school
  holidays, or guest mix change. Record `seasonal_relevance` for any hero or
  first-five candidate.
- Coastal listings usually lead with ocean, balcony, alfresco, pool, or
  waterfront proof over a generic interior.
- Urban listings usually lead with lounge plus skyline/outlook, balcony flow,
  work-ready outlook, building identity, or scarce parking when those are the
  real differentiators.
- Architecture-led listings may lead with exterior, rooftop, stair void,
  warehouse shell, or glass facade only when that identity is the why-book.
- Avoid night shots unless night lights or sunset view are the actual demand
  driver.
- Avoid edge-critical USPs that fail common Airbnb crops. Do not bake level,
  floor, or text claims into the image; keep those in captions/copy.
- Avoid leading with fear-trigger attributes unless the target segment actively
  wants that attribute and the image/copy makes the cleanliness, comfort, or
  access promise feel safe.
- Explicitly state whether the hero proves the title promise. If it does not,
  recommend either a different hero or a title rewrite.

If no cover-safe USP exists, choose the brightest honest lounge wide and mark
`Need proper hero` in the reshoot list.

### First Five

Default order. Treat these as five hero photos that reward the click and look
strong together as the desktop collage:

| Rank | Purpose |
|---:|---|
| 1 | Hero: primary why-book |
| 2 | Trust-build: alternate angle proving the same promise without duplication |
| 3 | Space and flow: lounge/dining wide with seating vs guest count readable |
| 4 | Kitchen or outdoor/alfresco, whichever is the stronger booking driver |
| 5 | Primary bedroom or signature bathroom, whichever sells harder |

Overrides:

- View-led listing: use a balcony flow pair across the first three where
  possible, with one inside-to-out frame and one outside-to-in frame.
- Remote work or executive listing: show desk/work zone by positions 4-6.
- Families: surface bunk/kids room or family amenity by positions 4-5 when it
  is a booking driver.
- Romance or spa: move an exceptional bath/spa frame to positions 3-4.
- Parking-scarce market: show the actual bay by positions 5-7 when parking is a
  differentiator.
- Summer: elevate pool, alfresco, balcony, BBQ, and outdoor flow.
- Winter: elevate fireplace, cosy lounge, bath, and weather-proof comfort.
- Cooking-led family, group, or long-stay listing: use a kitchen proof photo by
  positions 4-6, and ensure the full kitchen proof package exists later.

No two first-five images should answer the same decision question. Cover view,
space/flow, kitchen, sleep, bath, amenity, or architecture according to what the
listing sells.

The normal room tour can start after the first five or six. Do not spend the
first five on three living-room angles simply because that is the order a
photographer delivered.

After selecting the first five, write one line per image in this form:

```text
{photo_key}: answers {guest_question_answered}; reduces {objection_reduced}; proves {claim_or_hook}; trust risk {none|risk}
```

If two rows have the same `guest_question_answered`, resequence or demote one
unless the duplication is deliberately proving a high-value feature from two
different perspectives.

### Full Gallery

Target the shortest gallery that proves the stay. Compact listings may only
need 12-25 images; larger homes, complex layouts, and amenity-heavy listings can
justify 30-36 only when every image adds new information.

| Sequence zone | Content |
|---|---|
| 1-5 | Search-card promise and core conversion proof |
| 6-9 | Photo-tour room heroes for remaining bedrooms, best bathroom, second living or workspace |
| 10-14 | Balcony, alfresco, view, pool/spa/gym/sauna, EV/parking, laundry, kids items |
| Mid-gallery | Lifestyle only when it clarifies scale or use; target 10-15%, cap 20% |
| 19-24 | Quality details: rain shower, appliances, USB-C, blackout, linen, storage |
| 25-28 | Building/access: entry, lift/lobby, parking bay, door hardware, immediate streetscape |
| End | Floor plan, or positions 6-8 when layout is complex or multi-level |

For Airbnb's photo tour, also choose the first image inside each room/area
bucket intentionally. Record `room_hero_candidate_flag` and the room-specific
question it answers. Room-tour order should not silently inherit upload order.

When the kitchen is a real booking driver, treat it as a proof sequence:

1. wide establishing shot showing layout, island/fridge/appliance context
2. ready-to-cook medium shot with real pots, pans, board, knives, utensils, or
   prep surface visible
3. clean fridge or water-filter proof when offered
4. coffee/tea station close-up when supplied
5. quality cookware, knife, blender, rice cooker, or specialty tool proof only
   when those items will actually be present

### Missing-Shot Heuristics

Flag missing evidence when any of these are true:

- Parking is listed but there is no parking bay photo.
- Building amenities are listed but pool, gym, sauna/steam, rooftop, or BBQ
  lacks photo proof.
- Balcony, view, or alfresco is in the promise but no balcony flow pair exists.
- Entry, lift/lobby, or arrival route is absent for apartments.
- Sleeping capacity is claimed but bedroom, bed size, or sofa-bed proof is
  unclear.
- Kitchen is a stay-length or family/group driver but the gallery lacks a
  ready-to-cook proof package.
- Workspace, family, pet, EV, laundry, accessibility, or self-check-in is a
  thesis amenity but lacks visible proof.
- Reviews or old messages repeatedly ask about an amenity, access path, appliance,
  parking, bedding, or house rule that is not visually or textually answered.
- First five photos contain near-duplicates or decorative detail before core
  room/amenity proof.
- The listing lacks at least one deliberately staged product photo for a core
  use case: cooking, coffee, family streaming, work, pool/alfresco, sleep, or
  arrival.
- The hero candidate depends on a crop that cuts off the actual hook in Airbnb's
  square/mobile/desktop display.
- The gallery includes more photos than needed to prove the stay and contains
  low-information images after the point where a guest could reasonably book.
- Similar rooms jump between dark, bright, heavily saturated, and flat images
  without an intentional sequence.

### Reshoot And Edit Briefs

Use practical shot briefs, not vague requests.

Shot count defaults:

| Area | Recommended coverage |
|---|---|
| Lounge/great room | 3-5: master wide, opposite wide, seating detail, balcony transition |
| Kitchen | 4-6 when cooking matters: wide establishing shot, ready-to-cook medium shot, clean fridge/water proof, coffee/tea station, quality cookware/knives if real, appliance highlight |
| Primary bedroom | 2-3: entry wide, alternate wide, storage/charging |
| Secondary bedrooms | 1-2 each: wide plus storage/desk when relevant |
| Bathrooms | 1-2 each: honest wide plus selling detail if real |
| Outdoor/alfresco/view | 2-4: context wide, seating, view, BBQ |
| Building amenities | 1 each unless exceptional |
| Parking bay | 2: context wide plus bay number/signage close crop |
| Neighbourhood anchors | 1-3 authentic guest-relevant anchors with realistic distances |

Technique defaults: daylight, camera height about 1.2 m, straight verticals,
16-20 mm full-frame equivalent for rooms, 35-50 mm for details, natural white
balance, no HDR halos, sRGB export, long edge around 3000-4000 px, JPEG quality
85-90%.

Capture and staging defaults:

- Overshoot before selecting. For a full refresh, capture many angles per room
  and choose the best 12-25 listing images rather than trying to save one weak
  upload.
- Use an establishing/medium/feature mix. Wide shots show layout, medium shots
  prove use, and feature shots prove quality details like linens, coffee, art,
  cookware, or craftsmanship.
- Stage before the shoot. Set the table, prep the coffee station, place pots,
  pans, spices, cutting board, and knife for kitchen proof, turn on true
  streaming services when they are an offered family amenity, and add outdoor
  props where they make pool, alfresco, or lawn use easier to imagine.
- Build bedroom proof deliberately. Show the bed mix the target segment values,
  make the headboard or feature wall readable, include bedside lamps/charging
  where real, show storage when it matters, and make blackout curtains or window
  treatment visible when they are a sleep-quality advantage.
- For group stays, shoot capacity as a connected experience: dining seats,
  lounge seats, cooking gear, servingware, outdoor seating, bathrooms, and bed
  setup should all make the advertised guest count feel comfortable.
- Build at least one hero-moment frame when the listing lacks a memorable image:
  color wall, statement piece, mural, lighting feature, pool setup, view frame,
  or other truthful one-photo concept.
- Use theme and color as positioning, not decoration. The shot brief should name
  the guest segment and emotional promise the theme supports before asking for
  more props or styling.
- Do not use AI to repair missing pixels. Grainy underexposed smartphone photos,
  screenshots, excessive crops, and low-resolution downloads normally need a
  reshoot or original file recovery.

AI edit prompts may improve legibility only. They must not invent property
features. Acceptable edit classes: straighten verticals, neutral white balance,
even brightening, glare/reflection control, realistic de-haze, noise reduction,
minor declutter of removable objects, crop variants that preserve the true USP.

Use this edit-versus-reshoot gate:

| Decision | Use when |
|---|---|
| `edit` | The source already proves the room, amenity, view, layout, or hook, but presentation defects reduce clarity, crop safety, or trust. |
| `reshoot` | The source lacks the hook, has unreadable layout, cannot survive mobile crop, is stale/inconsistent, or would require AI to invent a material fact. |
| `resequence` | The image is truthful but belongs later because it is support proof, a duplicate, local context, or a low-value detail. |
| `discard` | The image is misleading, redundant, low quality, or creates more doubt than proof. |

Movable props are acceptable only when they do not imply a functional amenity or
fixture that guests expect on arrival. Beds, workspaces, parking, pool/gym
access, laundry, views, room count, and sleeping capacity must be real and
delivered, not staged or generated for the photo.

AI edits must not invent comfort, capacity, service, or maintenance facts. Do
not add blackout curtains, better bedding, extra seats, a larger dining table,
more kitchen equipment, stocked supplies, service labels, cleaner finishes, or a
coherent theme unless those facts are source-visible and will be present for
guests. If the needed improvement is operational, staging, purchasing, or
cleaning work, emit a dependency or reshoot brief instead of a prompt.

## Gallery CRO Execution Board

Use this board when the needed action is primarily photo selection, gallery
order, visual proof, captions, or a reshoot queue. Use the broader content
optimization brief when the action also changes the title, above-fold copy, or
Airbnb section copy.

Required inputs:

- source issue class or explicit gallery request
- listing ID, target guest segment, stay length, seasonality, and channel goal
- current title or search-card promise
- primary why-book
- exact candidate photo IDs or URLs from `photo_analysis`, with caption,
  room/area, visible-subject, visible-amenity, view-type, and confidence fields
- comp-set pattern basis, pattern-break basis, promise/payoff stage, first-five
  collage role, room-hero candidate flag, storyline contribution, and
  fear-trigger risk flags where available
- seasonal relevance, under-serviced amenity basis, room-level amenity proof,
  guest-message/review question basis, kitchen proof package status, and
  perceived-effort score where available
- guest-archetype fit, experience-fit proof, sleep-quality proof, capacity-fit
  proof, theme/emotional-promise basis, maintenance/review-risk flags, and
  service-signal basis where available
- demand-driver, clarity/diagnosticity, thumbnail-hook, crop-safety, trust-proof,
  and mobile-crop scores where available
- guest question answered, objection reduced, trust signal type, proof strength,
  title/photo promise alignment, tone-shift risk, misleading-risk flags, and
  edit-versus-reshoot decision where available
- current gallery or first-five order for rollback
- own public listing audit and A-comp visual patterns where available
- evidence refs

Board rules:

- Do not create a gallery action from price, trust, or visibility-only issues
  unless the user explicitly asks for gallery work.
- The hero must be both high-scoring and cover-safe. If no candidate passes the
  hero bar, require a proper hero reshoot or edit rather than treating the board
  as ship-ready.
- The first five must answer different guest decision questions. Repeated angles
  or decorative detail should not displace the core proof sequence.
- The first five must also work as a five-image desktop collage. If the collage
  feels like a photographer's room tour rather than five distinct reasons to
  keep evaluating, resequence it.
- Seasonal hero and first-five candidates must match the current booking window,
  not only the listing's all-time best feature.
- If hero-test data exists, use it. Separate algorithm exposure, click-through,
  booking conversion, and review outcome instead of treating one number as the
  whole funnel.
- Hero candidates must include crop-control notes for search-card, mobile, and
  desktop first-five display.
- Photo-tour room heroes must be selected for every important room or amenity
  bucket, especially where Airbnb exposes room-level photo ordering.
- Under-serviced amenity claims must be backed by comp-set scarcity evidence and
  clear visual proof before they become hero or title material.
- Kitchen-led listings must have the ready-to-cook proof package or an explicit
  reshoot queue item.
- Bedroom-led or long-stay listings must have a sleep-quality proof package or
  an explicit reshoot/operations dependency. Useful proof includes bed mix,
  bedside function, blackout or window treatment, storage, clean linens, pillows,
  and review-backed comfort facts where available.
- Group and family listings must show capacity fit before capacity is promoted:
  dining seats, lounge seats, cooking gear, servingware, bathrooms, outdoor/common
  use, and sleeping arrangements should all support the advertised guest count.
- Theme, lead color, and statement pieces must be tied to a target guest segment
  and comp-set pattern break before they become hero material.
- Filter-led claims such as pet-friendly, kids, self check-in, free parking,
  workspace, washer/dryer, pool, gym, or long-stay kitchen use should be checked
  against the review loop: the listing should be able to earn five-star reviews
  from guests who actually used those filters and stayed for that purpose.
- Stale or disputed images should trigger a photo-currency check: when the image
  was taken, what changed since, whether the amenity is seasonal, whether recent
  reviews support "as pictured", and whether post-clean condition evidence exists.
- Photos with technical capture defects should be reshot, recovered from the
  original file, cropped/levelled, or demoted before AI editing is considered.
- Product-staging gaps should become shot briefs, not prompt requests.
- Gallery recommendations should flag fatigue risk when the sequence is longer
  than the proof burden requires or when several support photos add no new
  buying temperature.
- Mood and brightness jumps should be resequenced unless the contrast is part of
  a deliberate room-to-room story.
- Missing room proof and thesis-amenity proof become a proof-shot queue, not
  vague makeover advice.
- Trust-surface issues outside photos, such as cleaning-fee optics, overbearing
  rules, threatening automated messages, or old guest questions that remain
  unanswered, should be recorded as copy/operations dependencies rather than
  hidden inside a gallery recommendation.
- Caption guidance must pair each selected image with the exact claim it proves.
- The board is not an implemented action. Accepted changes still need
  recommendation, action-log, experiment, rollback, and outcome attribution
  records.
- If an AI-edited image is proposed for hero or first-five placement, include
  the source photo key, edited photo path, allowed edit types, forbidden edit
  types, and edit review status. Do not place edited images into a ship-ready
  order until the edit review confirms the room, layout, view, amenities, and
  material constraints remain truthful.

Machine board row: emit an `airbnb_gallery_cro_execution_board` record. The
durable field list lives in `schema-core.md`; this playbook owns only the craft
and judgement rules above. The row must preserve source issue, photo
identifiers, first-five order, proof-shot queue, captions, rollback, review
window, confidence, evidence refs, and any missing required evidence.

## Copy Optimization

### Title And Above-Fold Scoring

```text
TitleCTR = 0.60 x USP_Priority + 0.20 x MobileLegibility + 0.20 x Differentiation
AboveFoldScore = 0.40 x CTRPotential + 0.30 x Diagnosticity + 0.20 x Differentiation + 0.10 x Readability
```

Soft gates: title score >= 80 and above-fold score >= 75. If a draft misses
the gate, revise once before emitting it.

Title rules:

- Maximum 50 characters, target 46-50 when natural.
- Put the primary why-book in the first 3-5 words.
- Prefer `Suburb/Building | USP + USP` only when the location/building is a
  real demand signal.
- Include level, view, parking, balcony, or architecture only when true and
  proven by photos or host facts.
- Do not lead with fear-trigger attributes such as pet-friendly, smoker-friendly,
  tight stairs, worn finishes, or shared amenity access unless they are the
  intended guest's positive demand driver and the above-fold proof reduces the
  obvious trust concern.
- Avoid cliches and low-information adjectives.

Above-fold rules:

- 240-280 characters, maximum two sentences.
- Include the primary USP, one proof point, and the sleeping headline.
- End with a practical micro-benefit such as work-ready setup, alfresco flow,
  parking, easy arrival, or long-stay comfort.

### Verbalized Sampling

Generate five distinct title plus above-fold pairs before choosing a primary
and challenger. Vary the promise axis and tone:

| Axis | Options |
|---|---|
| Promise | view, space, alfresco, sleep, location, work, family, luxe, architecture |
| Tone | premium, warm, cheeky, minimalist |
| Directness | polite, neutral, direct |

Give each pair a subjective probability of winning and a one-line rationale.
Choose a primary and challenger that test a meaningful hypothesis, not minor
wording differences.

### Humaniser

Avoid: nestled, boasts, amenities galore, look no further, perfectly located,
perfectly situated, charming, cozy/spacious when used alone, curated,
thoughtfully designed without proof, indulge, elevate your stay, unforgettable,
ideal base, heart of the city, oasis unless literal, sanctuary.

Replace generic phrasing with concrete facts: king bed, hotel-grade topper,
65 inch TV and soundbar, cafe 150 m, NE sunrise aspect, Level 53, 2.1 m parking
clearance, 500 Mbps Wi-Fi.

Keep most sentences under 20 words. If a line could fit ten random listings,
add a real specific or delete it.

### Airbnb Section Architecture

Use Airbnb's native section order:

| Section | Guidance |
|---|---|
| About this space - above fold | USP, proof, sleeping headline, micro-benefit |
| The space | 2-4 short paragraphs plus optional quick-scan bullets for bedrooms, apartment features, security/parking, extras |
| Guest access | Bullets only: entire place, balcony/alfresco, building amenities, parking bay, lift/level, step-free notes, check-in, storage |
| Other things to note | Bullet truths that reduce churn: noise windows, water pressure, strata/building rules, seasonal notes, same-day prep if provided, ID/agreement if required, streaming limits |
| House rules | Friendly-firm bullets: quiet hours, smoking/vaping, pets, guest count, no parties, rubbish/recycling, fees only when host-provided |

ADR levers: view orientation, brand appliances, premium bedding, renovation
year, designer finishes, secure parking/EV, privacy, quiet, building amenities.

LOS levers: workspace, fast Wi-Fi, laundry, pantry basics, storage, blackout,
weekly clean, routines nearby, monthly or relocation suitability.

Never invent a fee schedule. Include fees only from host-supplied values and
mark missing values as `missing_items`.

## Output Contract

Emit a host-readable summary and a machine-readable brief.

Host summary:

- Insights funnel-stage diagnosis and target metric.
- Primary title and challenger with reasons.
- Above-fold copy.
- Hero and two alternates with crop notes and title-alignment note.
- First-five order with one-line rationale per image.
- Full gallery order or order principles when exact photo IDs are unavailable.
- Caption updates.
- Section copy for `The space`, `Guest access`, `Other things to note`, and
  `House rules` when copy optimization is in scope.
- Top gaps to fix this week: missing shots, quick edits, host facts needed.
- A/B plan with KPI, guardrails, cadence, stop rule, and rollback.

Machine brief row: emit an `airbnb_listing_content_optimization_brief` record.
The durable field list lives in `schema-core.md`; this playbook owns the output
structure, copy/gallery judgement, A/B plan, and safety rules. The row must keep
the source decision gate, issue class, title/copy recommendations, gallery and
caption changes, missing facts, content risk flags, rollback plan, confidence,
and evidence refs tied to the collected source records.

## A/B Testing

Default content test:

- Primary hypothesis: hero/title/above-fold variant A will improve bookings per
  impression or search-to-listing conversion against variant B.
- KPI: bookings per impression when observable, otherwise grid-to-listing CTR
  or search-to-listing conversion.
- Guardrails: save rate, message rate, listing-to-booking conversion,
  bounce/time on photos, complaint/review accuracy signals.
- Cadence: read weekly.
- Stop rule: stop early only if one variant sustains at least 10% relative lift
  across two consecutive reads and guardrails are neutral or improving.
- Sizing note: 25k-40k impressions per arm is order-of-magnitude guidance for a
  10% relative CTR lift; small listings may need quasi-experimental before/after
  review instead.

For hero-photo tests, separate the funnel before judging:

- Exposure: first-page/search-card impressions or representation.
- Click: views or grid-to-listing CTR for the hero/title pair.
- Consideration: dwell, photo depth, message rate, and save rate.
- Booking: listing-to-booking conversion and revenue per impression.
- Trust: complaints, review accuracy, guest-favorite movement, and post-stay
  sentiment.

Use the stage diagnosis to choose the KPI. A `search_card_click` test should
lead with search-to-listing conversion and treat listing-to-booking as a
guardrail. A `listing_page_conversion` test should lead with listing-to-booking
or bookings per impression and treat views/wishlists as consideration only. A
`wishlist_or_view_friction` review should require price, rules, fees,
cancellation, and trust-surface notes before attributing the issue to photos.

Do not use artificial wishlist campaigns or clicks from people outside the
consumer archetype as positive evidence. They can send the wrong audience signal
and make a hero look better than it is.

Keep pricing, availability, discounts, and rules stable during the test when
possible. If simultaneous changes happen, record them as confounders in
`airbnb_outcome_attribution`.

## Evidence And Safety Rules

- A content brief is not an implemented action. Accepted edits must become
  `airbnb_recommendation`, `airbnb_action_log`, and optionally
  `airbnb_experiment` records.
- Every accepted content change needs a rollback plan: prior title, prior
  above-fold copy, prior photo order, prior captions, and date changed.
- Do not recommend a price cut until content, trust, amenity, and segment
  blockers have been ruled out by the relevant gate.
- Separate what was visually proven from what was inferred from listing text.
- Mark image-label-only evidence as lower confidence when Airbnb does not expose
  reliable photo labels.
- Premium or unreproducible comps can inspire a brief, but they do not prove a
  cheap content fix.
