# Airbnb.com.au Host Intelligence Skill

Start with `overview.md`. It is the canonical entry point and intent router:
user intent, desired outcome, control-flow stage, evidence/source guardrails,
executable lookup, schema index, and source anchors. This file holds only what
is unique to the directory landing page (photo philosophy, output-artifact
contracts, default flow, and source-state defaults).

Use this directory when the user is an Airbnb host or co-host and wants to
improve pricing, calendar control, conversion, operations, listing quality,
market selection, comp positioning, portfolio reporting, or Australian
compliance awareness from Airbnb.com.au data.

For routing, file map, schema lookup, executable entry points, and the cold
reader map, read `overview.md`. For the runnable-vs-helper script index, read
`scripts/README.md`.

## Photo Thinking Model

When the task touches photos, gallery order, AI editing, captions, or filenames,
read the photo workflow as conversion psychology, not as generic image cleanup.
The working philosophy is:

- Airbnb photos are a sales funnel. The search card earns curiosity; the first
  five photos pay off the click; the full gallery answers due-diligence questions.
- The promise/payoff chain keeps going after the click: hero/title create the
  promise, listing dwell time shows interest, booking shows confidence, arrival
  proves the product, and reviews or rebooking prove deep satisfaction.
- Think like a creator as much as a real-estate operator. Airbnb controls
  impressions; the host controls whether the search result earns attention.
- Evaluate images against the live comp-set feed. Sameness is a conversion
  problem; a useful pattern break interrupts the scroll without lying.
- The hero is not permanent. Rotate hero, first-five emphasis, and captions when
  seasonality changes the guest's demand driver.
- A guest is moving fast, comparing multiple tabs, and looking for reasons to
  trust or reject the listing. One mismatch, stale image, weak proof shot, or
  too-good-to-be-true cue can break the decision.
- The hero/title pair is a promise. It may create curiosity, but the opened
  listing must immediately feel like the same product the guest clicked.
- A good photo is not just pretty. It either stops the scroll, proves a claim,
  answers an objection, makes the space easier to understand, or increases trust.
- Treat Airbnb photos as product photography, not real-estate photography. Empty,
  wide, neutral rooms help buyers imagine their own furniture; Airbnb guests need
  staged proof that the stay is already easy, stocked, expressive, and memorable.
- A photo also signals perceived host effort. Guests look for small clues that
  the host cares, the home is maintained, and they will not be finessed.
- Experience proof beats inventory proof. Do not merely show beds, appliances,
  and rooms; prove that the target guest can sleep, cook, sit, work, arrive, and
  make the memory they are buying.
- Right-fit matters. More beds, amenities, or theatrical styling are not always
  better if the segment does not need them, the price signal becomes wasteful, or
  the photos attract a guest the home cannot satisfy.
- Sleep is a review engine. Bedroom photos should make bed mix, blackout,
  linens, bedside function, storage, and comfort cues visible where possible,
  while non-visible mattress and pillow claims must come from host facts or
  reviews rather than AI imagination.
- Group-capacity promises need proof. Do not sell a sleeps-10 story unless
  dining seats, lounge seating, kitchen equipment, bathrooms, and bedroom
  comfort make that group feel plausible.
- Theme, lead color, and statement pieces are emotional promises to a specific
  segment. Use them to create a memorable, comp-set-aware identity, not random
  decoration or generic "nice interior" noise.
- Maintenance, cleanliness, service, and review-risk cues are part of the visual
  product. Visible wear, cheap degrading supplies, missing kitchen proof, or a
  low-effort room should become operations, staging, copy, or reshoot work before
  they become AI-edit prompts.
- Treat search relevance as a loop, not a one-off listing edit. The title,
  hero, filters, photos, stay, and review language should all reinforce the same
  target guest job: pets, kids, work trips, long stays, parking, cooking, or
  whatever the listing is actually trying to win.
- Durable trust beats temporary momentum. Views, dwell time, wishlists, friend
  clicks, and artificial saves can create short-term signal, but reviews,
  response quality, resolution history, and "as pictured" accuracy compound.
- Let Insights choose the battleground. Low impressions are usually a
  visibility, availability, rule, price, or filter problem; high impressions with
  weak search-to-listing conversion point to hero/title/search-card work; high
  views with weak listing-to-booking conversion point to first-five, trust,
  proof, price, rules, or copy friction; high views or wishlists without bookings
  should be treated as curiosity or friction, not as proof the photos are
  working.
- Do not overfit the correlation analysis. Use prior high-performance patterns
  as directional clues, then apply strategic judgement: target guest, season,
  comp set, funnel stage, source-visible truth, review risk, and whether the
  better answer is edit, resequence, reshoot, staging, copy, pricing, rules, or
  operations.
- Keep photos current enough to defend. If a guest says "not as pictured," the
  operator should know whether the gallery changed, whether prior guests
  validated accuracy, and whether post-clean photos/videos or recent condition
  evidence support the listing.
- Hero photos are made, not merely selected. Design, lighting, color, props,
  statement pieces, and crop control should be planned around one image that can
  earn the search-card click.
- Treat the first five as five hero photos that look good together as a desktop
  collage. The normal room tour can start after the first-five payoff.
- Treat each Airbnb photo-tour room or area as having its own hero. The first
  photo for living, kitchen, bedroom, balcony, yard, pool, gym, or parking should
  be chosen intentionally, not inherited from photographer order.
- Do not foreground fear-trigger attributes in the title, hero, or first five
  unless they are the target segment's positive reason to book. Pet-friendly,
  smoker-friendly, worn finishes, tight spaces, or shared amenities may need
  truthful disclosure without becoming the top-of-funnel promise.
- Mine reviews and old guest messages for real unanswered questions. Those
  questions should become photo proof, captions, copy, or house-manual updates.
- Quality defects have different remedies. Grainy, underexposed, low-resolution,
  screenshot-derived, crooked, or unevenly lit photos usually need reshoot or
  careful crop/level work; AI editing should not be used to pretend missing image
  information exists.
- Measure hero tests when the data exists. Views, impressions, click-through,
  wishlist noise, bookings, and review outcomes answer different funnel questions;
  do not infer product-market fit from a single vanity metric.
- AI editing is production leverage, not product invention. Use it to clarify
  source-visible value; use reshoot, resequence, or discard when the source photo
  cannot honestly prove the needed hook.
- Use AI recommendations in a skeptical, war-room style. Let AI surface options,
  blind spots, and disagreements, but keep human/operator judgement responsible
  for accuracy, trust, and whether the photo actually sells the stay.

Before generating a gallery recommendation or image-edit prompt, ask: what
promise does this image create, what guest question does it answer, what trust
risk does it introduce, how does it compare to the current market feed, and
would the guest still feel accurately informed on arrival?

## Output artifacts

Private run data goes under ignored `domain-skills/airbnb/.private-data/`. Each
subdirectory holds collected raw data from a specific source family:

| Directory | Contents |
|---|---|
| `auth-state/` | Restorable CDP auth bundle (`host-main-cdp-state.json`) |
| `capability-probes/` | Surface availability probes (which pages/fields load) |
| `insights-collections/` | Host Insights exports (metric rows, daily rows, HTML/CSV/JSON) |
| `listing-collections/` | Live host listing snapshots |
| `own-public-collections/` | Own listing content audits, review summaries, search appearance |
| `photo-observations/` | Per-listing photo observation batches |
| `public-market-collections/` | Public comp search results and price matrices |
| `review-collections/` | Host review raw data and summaries |
| `calendar-export-collections/` | Host calendar exports (if any) |
| `realestate-rental-collections/` | REA building rental observations (if any) |
| `network-discovery/` | Public network/API surface discovery results |

These are ephemeral local working data. Delete after the user no longer needs
them. Do not commit to git.

Shareable generated workbooks, cross-domain reports, and team handoff packages
go under `outputs/{run_id}/` at the skill root (e.g.
`outputs/msa-property-performance-mapping-20260429/`). For listing photo
handoffs, keep source downloads in `.private-data/photo-observations/`, then
persist image-level `photo_analysis.json`/CSV metadata before generating a flat
`outputs/{run_id}/photos/` directory with image-level captions in filenames and
a `photo_filename_manifest.csv`. Filenames are a derived export view of photo
analysis metadata. Do not use listing titles as per-photo captions; only use
`pool`, `gym`, `bedroom`, `balcony_view`, and similar labels when that content
is visible in the individual photo or exposed by an official per-photo source
field. For listing optimization, the same `photo_analysis` layer should also
carry thumbnail hook, mobile crop, guest question, objection, trust-signal,
title/photo alignment, Insights funnel stage, conversion-correlation basis,
expected metric to move, edit-versus-reshoot, and misleading-risk fields so
photo order, AI editing, and filename exports all reuse the same evidence
instead of recaptioning independently.

Committed docs should describe shapes and workflows, not private addresses,
cookies, raw guest details, or portfolio-specific secrets.

The root markdown files are intentionally flat and organized logically by
`overview.md`. Treat physical moves as a broad path migration: update every
cross-reference, script constant, package-data expectation, and test path in the
same change.

When reviewing or searching the reusable skill surface, exclude private run
stores unless the task explicitly asks for local evidence records:

```bash
rg "pattern" domain-skills/airbnb \
  --glob '!domain-skills/airbnb/.private-data/**' \
  --glob '!domain-skills/airbnb/.session-store/**' \
  --glob '!outputs/**'

find domain-skills/airbnb \
  -path '*/.private-data' -prune -o \
  -path '*/.session-store' -prune -o \
  -path '*/outputs' -prune -o \
  -type f -print
```

## Default Flow

1. Identify the host decision.
2. Read the matching row in `overview.md` under **Intent Router**, then use
   **Expanded Routing Matrix** only if the task spans multiple artifacts.
3. Collect the smallest source primitives needed for the decision.
4. Evaluate collected rows with `scripts/decision_gates.py` when a decision is
   needed.
5. Store source observations in the relevant schema family.
6. Turn accepted recommendations into `decisioning.md` action, experiment, and
   outcome records.

## Source State Defaults

- Public market, public comps, own public rank, and guest-visible listing pages
  are logged-out observations by default.
- Host calendar, pricing settings, Insights, reviews, messages, tasks, exports,
  and listing editor fields are logged-in observations only when needed.
- Public Airbnb comp searches default to `Entire home` unless the task
  explicitly studies private-room or shared-room competition.
- Do not mix logged-out market observations and logged-in personalized
  observations in the same comp set.

## Implementation Pointers

- Browser-backed collectors live in `scripts/` and are run through
  `browser-harness`, not as plain standalone Python files.
- Pure decision helpers live in `scripts/decision_gates.py`; they do not browse,
  mutate Airbnb, or read private artifacts.
- Photo/product normalization lives in `scripts/photo_product_evidence.py`.
- Public scan planning and default comp filters live in
  `scripts/public_scan_planner.py`.
- Data quality, freshness, confidence, receipts, and redaction rules live in
  `data-quality.md`.
