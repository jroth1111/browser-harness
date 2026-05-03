# Onboarding — Structured Interview Flow

Builds user model and voiceprint through a structured interview. Use as the fallback option after chat audit (`chat-audit.md`) and deep research (`references/research-user.md`).

## When to use

- No `.private-data/user-model.md` exists
- User wants to update preferences
- Chat audit or deep research left gaps that need filling

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

### Message consent levels
| Level | Behavior |
|---|---|
| **Draft only** | Show message, user sends manually |
| **Approve** | Show message, send on user approval |
| **Auto-send** | Send automatically, log what was sent |
| **Auto-send with threshold** | Auto-send below confidence threshold, approve above |

### Swipe consent levels
| Level | Behavior |
|---|---|
| **Manual only** | Show each profile, user decides |
| **Approve non-obvious** | Auto-swipe obvious PASS, show LIKE and MAYBE |
| **Full auto** | Auto-swipe all, log decisions |
| **Full auto with threshold** | Auto-swipe below score threshold, show above |

### Session limits
| Setting | Default | Range |
|---|---|---|
| Max swipes per session | 80 | 20-200 |
| Max messages per session | 40 | 10-100 |
| Session duration limit | 30 min | 10-120 min |

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

## Validation

After writing both files, confirm with the user:
1. Read back key preferences to verify accuracy
2. Show extracted voiceprint with example messages
3. Confirm consent levels are correct
4. Ask: "Does this feel like an accurate picture of you? What would you change?"

Incorporate corrections before proceeding to any platform automation.
