# Onboard — Build the Portable Assets

Use when:
- `.private-data/user-model.md` does not exist;
- the user wants to update preferences;
- chat-audit or research left gaps that need filling.

Onboarding produces three files in `.private-data/`: `user-model.md`, `voiceprint.md`, `positioning.md`. See `state.md` for the schemas. Without all three, no swipe / reply / escalate action runs.

## Two paths in

**Path A — Interview from zero** (default).
Run the structured interview below. Fast: 6–10 core questions plus voice-sample collection.

**Path B — Research-pre-populated interview.**
If the user wants to skip ahead, scan available digital footprint first, draft the user-model + voiceprint, then run the interview as confirmation rather than discovery. Sources, in order of value, where the user grants access:

1. Writing samples (blog, essays, social, emails) → directly feeds voiceprint cadence/vocabulary/edge.
2. Existing dating profile copy / drafts → self-perception and intent.
3. Social handles (Twitter/X, Instagram, LinkedIn, Reddit, GitHub) → values, humour, lifestyle, communication style.
4. Existing chat threads → run `chat-audit.md` (Path 1 GDPR > Path 2 UI crawl > Path 3 manual paste).
5. Browser history / open tabs → values, interests, lifestyle context.

**Synthesis rules for Path B:**
- Label every inferred field `[inferred]` vs user-stated.
- Confidence-tag each field: HIGH (multiple converging signals) / MEDIUM (one clear signal) / LOW (thin evidence — flag for interview).
- Never assume identity, orientation, or relationship structure — these must be user-stated or very clearly evidenced.
- Present inferences as questions, not declarations: *"Based on your writing, you seem to value X — is that right?"*

The interview then becomes: *"Here's what I found. Does this look right?"* → correct wrong inferences → fill LOW-confidence gaps → ask anything still missing → configure consent → save.

## Interview flow (Path A; also confirmation pass for Path B)

Run conversationally, not as a form. Follow up naturally. Skip questions the user has already answered. Target 6–10 core questions; use follow-ups only when needed.

### Phase 1 — Identity and context

1. **What are you looking for right now?** Casual, relationship, in-between, exploring. Timeline: actively looking vs open.
2. **Tell me about yourself in dating context.** Age, location, occupation (as much as the user wants to share). What stage of life. How they would describe themselves to a match.

### Phase 2 — Desired traits and attraction patterns

3. **What draws you to someone? What makes you swipe right?** Physical traits if they want to specify. Personality. Dealbreakers. Green flags ("this person gets me").
4. **What kinds of people have you had the best connections with?** Past dates / relationships that worked. What made them work. Patterns they have noticed (or have not).

### Phase 3 — Communication style and blind spots

5. **How do you usually text someone you're interested in?** Fast vs slow responder. Long vs short. Emoji-heavy vs text-only. Serious vs playful. **Ask the user to paste 2–3 recent messages they sent** — voiceprint calibration.
6. **What's your dating blind spot? What do friends tell you?** Common feedback. Self-identified patterns they want to change. What they know does not work but do anyway.

**6b. How do you carry attraction in writing?** (Charge ceiling — required for `voiceprint.md`.)
- Highest charge level the user is comfortable sending. Charge ladder (see `reply.md`):
  - 1 warm recognition
  - 2 playful tension
  - 3 flirtatious frame
  - 4 personal reveal
  - 5 romantic subtext
  - 6 embodied implication
  - 7 direct escalation

  Most users top out at 5–6 in early threads.
- Comfort with embodied implication ("dangerous over a drink and eye contact") vs preference for staying at romantic-subtext level.
- Comfort with vulnerability-as-charge (small, owned reveals like *"warmth and good questions undo me pretty quickly"*).
- Sexual vocabulary the user uses (and avoids). Some users say "want", others find it too direct; capture their actual comfort.
- Charge moves the user does *not* want to use even if they sometimes work for others (fake dominance, explicit physical descriptions, eye-contact lines if too theatrical for them).

These answers shape draft selection across every charged message — the copilot will not generate above the user's stated ceiling.

### Phase 4 — Flags and boundaries

7. **What are your hard no's? What ends things immediately?** Behavioral red flags, communication patterns, values mismatches.
8. **Yellow flags — pause but not automatic pass?** Uncertainties they want help evaluating. Patterns they tend to rationalise.

### Phase 5 — Pace and logistics

9. **What pace feels right for you?** How quickly from chat to meeting. How many messages before proposing a date. Meet quickly vs build rapport first.
10. **What does a good first date look like?** Settings (coffee, drinks, activity, walk). Duration. How they decide if there is chemistry.

### Phase 6 — Profile copy (polarising filter)

The user's bio and prompt answers should filter, not appeal universally. Most profiles try to be liked; high-signal profiles make the right person think *"that's me"* and the wrong person move on. Draft 2–3 lines that do that work.

11. **What do you actually want to filter for?**
- Two or three traits that reliably predict good fit (not "nice", "fun", or "kind" — those filter no one).
- Two or three traits that reliably predict mismatch (passive communication, "let's see where it goes", chaos dressed as freedom, etc.).

Draft three components:

- **Filter line** — names a quality the user is drawn to, in concrete terms. Example: *"Drawn to women who can do playful and emotionally honest in the same conversation."* Avoid generic adjectives; use verbs and contrasts.
- **Green flags** — short, specific list. Example: *"Green flags: emotional directness, ambition, weird little obsessions, the ability to flirt without turning into a motivational podcast."*
- **Not-for line** — what the user is honestly not interested in. Example: *"Not for: chaos dressed as freedom, passive communication, or people who think 'let's see where it goes' means 'I will make no choices.'"*

**Profile copy review checklist** before saving:
- Does the wrong match read this and self-deselect? If yes, the filter is working.
- Does the right match read this and feel recognised? If yes, the invitation is working.
- Is anything in there written to be liked by everyone? Cut it.

The skill outputs the three lines as guidance only. The user pastes them into Tinder's profile editor manually. The copilot does **not** automate bio editing — see `platforms/tinder.md` for the rationale (bot-detection risk, atomicity risk, low frequency, human-in-the-loop is the right consent posture for public profile changes).

### Phase 7 — Positioning derivation

After Phases 1–6 are complete, derive the user's market positioning and write to `.private-data/positioning.md` per the schema in `state.md`.

**Inputs to the derivation:**
- Phase 2 attraction patterns and Phase 3 communication style → which scarcity-stack levers come naturally vs need reinforcement.
- Phase 4 hard no's and Phase 6 filter copy → core positioning statement and anti-positioning.
- Phase 5 pace + relationship structure (mono / poly / ENM / RA) → low-chaos directness register.
- Voiceprint frame stance and charge ceiling → felt-experience target.

**Five positioning sections to populate:**

1. **Core statement** — one sentence in the user's voice. Usually a sharper version of the default — *"Erotic charge without chaos. Depth without heaviness. Directness without pressure. Standards without bitterness."* — in the user's actual words.
2. **Scarcity stack** — which of the five levers (erotic intelligence, selective warmth, low-chaos directness, felt life, good logistics) are native vs need deliberate reinforcement.
3. **Profile copy alignment** — which filter / green-flag / not-for line carries which scarcity element.
4. **Felt-experience target** — what the right woman should feel after three exchanges.
5. **Anti-positioning** — moves the user must not lean on even if they sometimes work for others (fake dominance, founder pitch-deck energy, performed unavailability, etc.).

**Validation.** Read the core statement back to the user: *"Does this sound like an offer you'd actually make, in a register you'd actually use?"* If the user pauses or qualifies it, rewrite — positioning that does not sound like the user is dead on arrival.

## Voiceprint sample collection

After the interview, ask the user to write 3–5 messages they might send. Each surfaces a different register:

1. An opener to someone they're excited about.
2. A reply to *"hey, how's your week going?"*
3. A message turning down a second date politely.
4. A flirty follow-up after a good date.
5. A message to someone they're losing interest in.

From these samples + interview answers, extract:
- sentence length and rhythm;
- directness level;
- warmth and humour style;
- emoji / punctuation patterns;
- question vs statement ratio;
- how the user signals interest;
- how the user exits or sets limits.

Map directly to the `voiceprint.md` template fields in `state.md`.

## Consent configuration

Ask the user to set their consent level for each action type. Use the canonical tokens from `safety.md` so other action files can match on them.

### Message consent levels

| Token | Behaviour |
|---|---|
| `draft-only` | Show message; user sends manually |
| `approve` | Show message; send on user approval (default) |
| `auto-send` | Send automatically; log what was sent |
| `auto-threshold` | Auto-send below confidence threshold; approve above |

### Swipe consent levels

| Token | Behaviour |
|---|---|
| `manual` | Show each profile; user decides |
| `approve-non-obvious` | Auto-swipe obvious PASS; show LIKE and MAYBE (default) |
| `full-auto` | Auto-swipe all; log decisions |
| `auto-threshold` | Auto-swipe below score threshold; show above |

Hard consent requirements in `safety.md` override the configured level for first-message openers, date proposals, high-risk drafts, dormant matches (7+ days), low-confidence actions (<50%), and opening any existing conversation outside an active audit run.

### Pacing preferences (defaults)

| Setting | Default |
|---|---|
| Swipe pace | Comfortable (1.5–5s between) |
| Message pace | Comfortable (2–5s between) |
| Break frequency | Every 10 swipes / 5 messages |

Record consent configuration inside `.private-data/user-model.md`.

## Output

Three files written to `.private-data/`. Schemas in `state.md`.

- `user-model.md` — populated from Phases 1–5 and Phase 4. Includes consent configuration and pacing preferences.
- `voiceprint.md` — populated from Phase 3, 6b, voice samples. Charge ceiling required.
- `positioning.md` — populated from Phase 7.

## Validation

After writing all three:

1. Read back key preferences from `user-model.md` to verify accuracy.
2. Show extracted voiceprint with the example messages that feel like the user.
3. Confirm consent levels.
4. Read back the positioning core statement — does it sound like the user?
5. Ask: *"Does this feel like an accurate picture of you? What would you change?"*

Incorporate corrections before any platform automation runs.
