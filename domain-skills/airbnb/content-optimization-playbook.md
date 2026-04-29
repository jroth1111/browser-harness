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
| Gallery CRO execution board | Select exact hero/first-five actions, proof shots, captions, rollback, and test window | `scripts/decision_gates.py`, `schema-core.md` |
| Visual calibration | Correlate photos/features/copy against revenue or profit and generate prompt/design candidates | `visual-revenue-workflows.md`, `schema-visual-revenue.md` |
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
| `photo_order_gap` | First-five reorder, gallery sequence, missing early proof | Search-to-listing conversion |
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
| Listing facts | Property type, guest cap, bedrooms/baths/beds, room layout, parking, EV, workspace, laundry, balcony/alfresco, view, level/storey, building amenities |
| Guest and stay context | Target segment, stay length, seasonality, work/family/couple/group intent |
| Current public presentation | Title, photo count, hero subject, first-five subjects, proof flags, visible amenities, ratings, badges |
| A-comp presentation | Repeated winning hero subjects, proof patterns, first-five coverage, price context, trust context |
| Location proof | Walkable anchors with realistic distances or times, transport, beach/CBD/event anchors |
| Operational facts | Same-day prep window, check-in method, noise realities, building-managed amenity disclaimer, streaming limitations, fee schedule only when host-provided |
| Constraints | Do-not-mention facts, privacy, spaces to omit, facts requiring host confirmation |

## Content Principles

- Optimize for revenue per impression: CTR x post-click conversion x ADR x LOS.
- Lead with the strongest verifiable reason to book, not a generic adjective.
- Keep the title, hero, first five photos, and above-fold copy aligned.
- Use specifics over claims: numbers, bed sizes, distances, aspect, level,
  parking details, appliance brands, Wi-Fi speed, and real limitations.
- Do not fabricate property features, views, distances, fees, amenities, or
  guest rules.
- Treat compliance and policy as upstream or host-reviewed, but preserve
  risk-reducing truths in `Other things to note` when provided.
- Use Australian English and local terms: lounge, alfresco, BBQ,
  reverse-cycle, storey/level, metres, and kilometres.

## Photo Optimization

### Scoring

Score each candidate image from 0 to 100:

```text
Photo score = 0.50 x DemandDriver + 0.30 x ClarityDiagnosticity + 0.20 x CropSafety
```

| Component | What to check |
|---|---|
| DemandDriver | Strength and salience of a top USP: view, alfresco, pool/spa, grand lounge, designer kitchen, luxe primary suite, signature architecture, scarce parking, work-ready setup |
| ClarityDiagnosticity | Brightness, colour fidelity, straight verticals/horizon, readable layout/scale, low glare, subject separation |
| CropSafety | USP remains central and legible in 1:1, 16:9, 3:2, and 4:5 crops |

Apply a 10-20 point redundancy penalty to near-duplicates competing in the top
eight. Treat near-duplicates as frames from the same corner or height with
roughly the same subject and angle.

Hero candidates should usually have DemandDriver >= 80,
ClarityDiagnosticity >= 75, and CropSafety >= 80. First-five photos should
usually score >= 70. If the inventory cannot meet that bar, recommend an edit
or reshoot rather than pretending the gallery is fixed.

### Hero Selection

Choose one primary hero and two alternates.

Rules:

- The hero must prove the primary why-book and be instantly readable as a phone
  thumbnail.
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
- Explicitly state whether the hero proves the title promise. If it does not,
  recommend either a different hero or a title rewrite.

If no cover-safe USP exists, choose the brightest honest lounge wide and mark
`Need proper hero` in the reshoot list.

### First Five

Default order:

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

No two first-five images should answer the same decision question. Cover view,
space/flow, kitchen, sleep, bath, amenity, or architecture according to what the
listing sells.

### Full Gallery

Target 30-36 images when inventory supports it. Every image should add new
information.

| Sequence zone | Content |
|---|---|
| 1-5 | Search-card promise and core conversion proof |
| 6-9 | Remaining bedrooms, best bathroom, second living or workspace |
| 10-14 | Balcony, alfresco, view, pool/spa/gym/sauna, EV/parking, laundry, kids items |
| Mid-gallery | Lifestyle only when it clarifies scale or use; target 10-15%, cap 20% |
| 19-24 | Quality details: rain shower, appliances, USB-C, blackout, linen, storage |
| 25-28 | Building/access: entry, lift/lobby, parking bay, door hardware, immediate streetscape |
| End | Floor plan, or positions 6-8 when layout is complex or multi-level |

### Missing-Shot Heuristics

Flag missing evidence when any of these are true:

- Parking is listed but there is no parking bay photo.
- Building amenities are listed but pool, gym, sauna/steam, rooftop, or BBQ
  lacks photo proof.
- Balcony, view, or alfresco is in the promise but no balcony flow pair exists.
- Entry, lift/lobby, or arrival route is absent for apartments.
- Sleeping capacity is claimed but bedroom, bed size, or sofa-bed proof is
  unclear.
- Workspace, family, pet, EV, laundry, accessibility, or self-check-in is a
  thesis amenity but lacks visible proof.
- First five photos contain near-duplicates or decorative detail before core
  room/amenity proof.

### Reshoot And Edit Briefs

Use practical shot briefs, not vague requests.

Shot count defaults:

| Area | Recommended coverage |
|---|---|
| Lounge/great room | 3-5: master wide, opposite wide, seating detail, balcony transition |
| Kitchen | 2-3: wide, work triangle, appliance highlights |
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

AI edit prompts may improve legibility only. They must not invent property
features. Acceptable edit classes: straighten verticals, neutral white balance,
even brightening, glare/reflection control, realistic de-haze, noise reduction,
minor declutter of removable objects, crop variants that preserve the true USP.

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
- exact candidate photo IDs or URLs with subject labels
- demand-driver, clarity/diagnosticity, and crop-safety scores where available
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
- Missing room proof and thesis-amenity proof become a proof-shot queue, not
  vague makeover advice.
- Caption guidance must pair each selected image with the exact claim it proves.
- The board is not an implemented action. Accepted changes still need
  recommendation, action-log, experiment, rollback, and outcome attribution
  records.

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
