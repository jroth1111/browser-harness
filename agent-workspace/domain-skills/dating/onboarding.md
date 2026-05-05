# Onboarding — Structured Interview Flow

Builds user model and voiceprint through a structured interview. Use as the fallback when GDPR export (`chat-audit.md` Path 1) and browser chat extraction (`chat-audit.md` Path 2) are unavailable or insufficient.

## When to use

- No `.private-data/user-model.md` exists
- User wants to update preferences
- Chat extraction or deep research left gaps that need filling

## Interview flow

Run questions conversationally, not as a form. Follow up naturally. Skip questions the user has already answered. Target 6-10 core questions; use follow-ups only when needed for clarity.

### Phase 1: Identity and context

**1. What are you looking for right now?**
- Casual dating, relationship, something in between, exploring
- Timeline: actively looking vs open to something

**2. Tell me about yourself in dating context.**
- Age, location, occupation (as much as they want to share)
- What stage of life they're in
- How they'd describe themselves to a match

### Phase 2: Desired traits and attraction patterns

**3. What draws you to someone? What makes you swipe right?**
- Physical types or traits (if they want to specify)
- Personality traits that attract them
- Dealbreakers (what makes them swipe left instantly)
- Green flags (what signals "this person gets me")

**4. What kinds of people have you had the best connections with?**
- Past relationships or dates that worked well
- What made those connections work
- Patterns they've noticed (or haven't)

### Phase 3: Communication style and blind spots

**5. How do you usually text someone you're interested in?**
- Fast responder or takes time?
- Long messages or short?
- Emoji-heavy or text-only?
- Serious or playful?
- Ask them to paste 2-3 recent messages they sent (for voiceprint calibration)

**6. What's your dating blind spot? What do friends tell you?**
- Common feedback from friends
- Self-identified patterns they want to change
- What they know doesn't work but do anyway

**6b. How do you carry attraction in writing?**
- Highest level of `references/message-kernel.md` Charge ladder the user is comfortable sending (1 warm recognition / 2 playful tension / 3 flirtatious frame / 4 personal reveal / 5 romantic subtext / 6 embodied implication / 7 direct escalation). Most users top out at 5–6 in early threads.
- Comfort with embodied implication ("dangerous over a drink and eye contact") vs preference for staying at romantic-subtext level.
- Comfort with vulnerability-as-charge (small, owned reveals like "warmth and good questions undo me pretty quickly").
- Sexual vocabulary the user uses (and avoids). Some users say "want", others find it too direct; capture their actual comfort.
- Charge moves the user does *not* want to use even if they sometimes work for others (e.g. fake dominance, explicit physical descriptions, eye-contact lines if too theatrical for them).

These answers shape draft selection across every charged message — the copilot will not generate above the user's stated ceiling.

### Phase 4: Flags and boundaries

**7. What are your hard no's? What ends things immediately?**
- Behavioral red flags
- Communication patterns they can't tolerate
- Values mismatches

**8. What are your yellow flags — things that give you pause but aren't automatic passes?**
- Uncertainties they want help evaluating
- Patterns they tend to rationalize

### Phase 5: Pace and logistics

**9. What pace feels right for you?**
- How quickly do you want to move from chat to meeting?
- How many messages before proposing a date?
- Do you prefer to meet quickly or build rapport first?

**10. What does a good first date look like for you?**
- Settings they prefer (coffee, drinks, activity, walk)
- Duration expectations
- How they decide if there's chemistry

### Phase 6: Profile copy (polarising filter)

The user's bio and prompt answers should filter, not appeal universally. Most profiles try to be liked; high-signal profiles make the right person think "that's me" and the wrong person move on. The objective here is to draft 2–3 lines that do that work.

**11. What do you actually want to filter for?**
- Two or three traits that reliably predict good fit (not "nice", "fun", or "kind" — those filter no one).
- Two or three traits that reliably predict mismatch (passive communication, "let's see where it goes", chaos dressed as freedom, etc.).

**Draft three profile components from the answers:**

1. **Filter line** — names a quality the user is drawn to, in concrete terms. Example: *"Drawn to women who can do playful and emotionally honest in the same conversation."* Avoid generic adjectives; use verbs and contrasts.
2. **Green flags** — short, specific list. Example: *"Green flags: emotional directness, ambition, weird little obsessions, the ability to flirt without turning into a motivational podcast."*
3. **Not-for line** — what the user is honestly not interested in. Example: *"Not for: chaos dressed as freedom, passive communication, or people who think 'let's see where it goes' means 'I will make no choices.'"*

These three pieces are stored in the user model as profile copy and used both as bio guidance and as voice/frame anchors for messages.

**Profile copy review checklist** before saving:
- Does the wrong match read this and self-deselect? If yes, the filter is working.
- Does the right match read this and feel recognised? If yes, the invitation is working.
- Is anything in there written to be liked by everyone? Cut it.

### Saving the profile copy

The skill outputs the three lines as guidance only. The user pastes them into Tinder's profile editor manually. The copilot does **not** automate bio editing — see `platforms/tinder.md` Out of scope for the rationale (bot-detection risk, atomicity risk, low frequency, human-in-the-loop is the right consent posture for public profile changes).

Before saving in Tinder:
- Review the live preview (Tinder shows what the profile will look like to other users).
- Check the bio character count fits Tinder's limit.
- Confirm the green flags / not-for line read as intended in context.

### Phase 7: Positioning derivation

After Phases 1–6 are complete, derive the user's market positioning and save to `.private-data/positioning.md` per the template in `references/positioning.md`. Positioning is a portable asset alongside `user-model.md` and `voiceprint.md`; it sits above the kernel/voiceprint/charge layers and informs every draft.

Inputs to the derivation:
- Phase 2 attraction patterns and Phase 3 communication style → which scarcity-stack levers come naturally vs need reinforcement.
- Phase 4 hard no's and Phase 6 filter copy → core positioning statement and anti-positioning.
- Phase 5 pace + relationship structure (mono / poly / ENM / RA) → low-chaos directness register.
- Voiceprint frame stance and charge ceiling → felt-experience target.

Output the five sections of the positioning template:
1. Core statement (one sentence in the user's voice — usually a sharper version of *"Erotic charge without chaos. Depth without heaviness. Directness without pressure. Standards without bitterness."* in the user's actual words).
2. Scarcity stack — which of the five (erotic intelligence, selective warmth, low-chaos directness, felt life, good logistics) are native vs need deliberate reinforcement.
3. Profile copy alignment — which filter / green-flag / not-for line carries which scarcity element.
4. Felt-experience target — what the right woman should feel after three exchanges.
5. Anti-positioning — moves the user must not lean on even if they sometimes work for others (fake dominance, founder pitch-deck energy, performed unavailability, etc.).

### Validation of positioning

Read the core statement back to the user and ask: "Does this sound like an offer you'd actually make, in a register you'd actually use?" If the user pauses or qualifies it, rewrite — positioning that does not sound like the user is dead on arrival.

## Voiceprint calibration

After the interview, collect voice samples:

1. Ask the user to write 3-5 messages they might send:
   - An opener to someone they're excited about
   - A reply to "hey, how's your week going?"
   - A message turning down a second date politely
   - A flirty follow-up after a good date
   - A message to someone they're losing interest in

2. From these samples + interview answers, extract:
   - Sentence length and rhythm
   - Directness level
   - Warmth and humor style
   - Emoji/punctuation patterns
   - Question vs statement ratio

3. Compare against `references/voiceprint.md` template fields.

## Rubric construction

From the interview answers, construct the scoring rubric (see `references/scoring.md`):

1. **Dealbreakers** (Phase 4 answers) → auto-PASS triggers
2. **Green flags** (Phase 2 answers) → auto-LIKE boosters
3. **Trait weights** (Phase 2-3 answers) → dimension scoring weights
4. **Pace preferences** (Phase 5 answers) → escalation timing
5. **Communication style** (Phase 3-4 answers) → message matching

## Consent configuration

Ask the user to set their consent level for each action type:

Canonical level names live in `safety.md`. Use those tokens verbatim when writing to `.private-data/user-model.md` so other files can match on them.

### Message consent levels (`safety.md` canonical)
| Token | Behavior |
|---|---|
| `draft-only` | Show message, user sends manually |
| `approve` | Show message, send on user approval (default) |
| `auto-send` | Send automatically, log what was sent |
| `auto-threshold` | Auto-send below confidence threshold, approve above |

### Swipe consent levels (`safety.md` canonical)
| Token | Behavior |
|---|---|
| `manual` | Show each profile, user decides |
| `approve-non-obvious` | Auto-swipe obvious PASS, show LIKE and MAYBE (default) |
| `full-auto` | Auto-swipe all, log decisions |
| `auto-threshold` | Auto-swipe below score threshold, show above |

Hard consent requirements in `safety.md` override the configured level for first-message openers, date proposals, high-risk drafts, dormant matches (7+ days), low-confidence actions (<50%), and opening any existing conversation.

### Pacing preferences
| Setting | Default |
|---|---|
| Swipe pace | Comfortable (1.5-5s between) |
| Message pace | Comfortable (2-5s between) |
| Break frequency | Every 10 swipes / 5 messages |

Record consent configuration in `.private-data/user-model.md`.

## Output

Write two files:

### `.private-data/user-model.md`
Populate all fields from `references/user-model.md` template:
- Demographics and context
- Dating goals and intent
- Desired traits and dealbreakers
- Attraction patterns (stated and inferred)
- Communication style
- Pacing preferences
- Blind spots (self-reported)
- Consent configuration

### `.private-data/voiceprint.md`
Populate all fields from `references/voiceprint.md` template:
- Voice characteristics extracted from interview answers and samples
- Example messages (characteristic and anti-pattern)
- Tone calibration notes

### `.private-data/positioning.md`
Populate all fields from `references/positioning.md` Positioning template:
- Core statement
- Scarcity stack notes (erotic intelligence, selective warmth, low-chaos directness, felt life, good logistics)
- Profile copy alignment (filter line, green flags, not-for line)
- Felt-experience target
- Anti-positioning

## Validation

After writing both files, confirm with the user:
1. Read back key preferences to verify accuracy
2. Show extracted voiceprint with example messages
3. Confirm consent levels are correct
4. Ask: "Does this feel like an accurate picture of you? What would you change?"

Incorporate corrections before proceeding to any platform automation.
