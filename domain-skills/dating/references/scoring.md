# Scoring — How Rubric Scoring Works

Bridges browser automation artifacts to swipe and message decisions. Every profile and conversation passes through this scoring framework before any action is taken.

## Scoring dimensions

From `references/decision-rubric.md`. Score each LOW/MEDIUM/HIGH based on available evidence:

| Dimension | What to assess | Evidence source |
|---|---|---|
| User Model compatibility | Does this person match the user's stated preferences? | Profile text, bio, prompts |
| Attraction/chemistry potential | Is there subjective attraction potential? | Photos (visual), described interests, energy |
| Relationship/intent fit | Are their relationship goals compatible? | Bio clues, prompts, profile structure |
| Communication quality | Can this person communicate well? | Prompt answers, bio writing quality |
| Practical availability | Distance, schedule, relationship status | Location, distance, stated availability |
| Real-person/real-intent signal | Is this a real person with genuine intent? | Profile completeness, photo quality, specificity |
| False chemistry risk | Could apparent chemistry mask poor fit? | Attractive-but-unsuitable pattern matching |

## Scoring process per profile

### Step 1: Hard dealbreaker check
Scan profile for any hard dealbreakers from the user model. If any match:
- **Instant PASS**. No further scoring needed.

### Step 2: Green flag check
Scan for multiple strong green flags. If present:
- **Fast-track LIKE** with high confidence. Brief scoring only.

### Step 3: Dimension scoring
For profiles that pass dealbreaker check but lack strong green flags:

1. Browser delivers: screenshot + extracted text fields.
2. AI reads the profile artifact.
3. AI scores each dimension as LOW/MEDIUM/HIGH based on available evidence.
4. Dimensions with insufficient evidence score as UNCLEAR (neutral weight).

### Step 4: Composite decision

- **LIKE**: Dealbreaker-free AND majority of scored dimensions are MEDIUM+.
- **PASS**: Any dimension scores LOW on a strong preference, OR majority scored dimensions are LOW.
- **MAYBE**: One strong signal but one unclear dimension. Show to user.

## Evidence extraction from profiles

### What to look for in bio text
- Specific self-expression vs. generic clichés
- Values and lifestyle clues (ambition, creativity, social habits)
- Relationship-style clues (explicit mentions or implied structure)
- Humour, intelligence, emotional range signals

### What prompts reveal
- Effort level (detailed vs. one-word answers)
- Personality dimensions (playful, serious, thoughtful, adventurous)
- Compatibility signals (shared interests, complementary traits)
- Communication style preview

### What photo choices signal
- Activity diversity (active, social, creative, domestic)
- Self-presentation style (curated, casual, artistic)
- Social context (friends, solo, pets, travel)
- Confidence and authenticity indicators

### What absence reveals
- Empty bio: low effort or privacy-focused
- No prompts: may indicate lower engagement
- Sparse profile: could be new, inactive, or bot

## Confidence calibration

- **HIGH**: Multiple converging signals across dimensions. Clear match or clear mismatch.
- **MEDIUM**: Enough signal for a decision, some uncertainty. Most common.
- **LOW**: Sparse evidence. Lean toward PASS unless one very strong signal. Consider showing to user.

## Score output format

```text
Profile: [name, age, location]
Compatibility: [HIGH/MEDIUM/LOW]
Attraction: [HIGH/MEDIUM/LOW/UNCLEAR]
Intent fit: [HIGH/MEDIUM/LOW/UNCLEAR]
Communication: [HIGH/MEDIUM/LOW/UNCLEAR]
Real-person: [HIGH/MEDIUM/LOW]
Dealbreakers: [none / listed]
Decision: [LIKE/PASS/MAYBE]
Confidence: [HIGH/MEDIUM/LOW]
Read: [one-line profile read]
Watch: [what to look for if matched]
```

## Conversation scoring (Stage 5+)

For existing conversations, add these dimensions:
- **Reciprocal investment**: Is effort matching or increasing? (see `references/profile-conversation-read.md` reciprocal investment ladder)
- **Escalation readiness**: Is there enough warmth and logistical plausibility for a date proposal?
- **False chemistry risk**: Is the banter masking weak compatibility?
- **Thread health**: Is the conversation alive, flat, or draining?

Conversation scoring uses the same decision rubric but maps to message moves instead of swipe moves (see `references/decision-rubric.md` pipeline-stage mapping).

## Lead tiers

Once a thread has at least two exchanges, classify the lead into a tier and update `lead_tier` in `references/thread-state.md`. Tier drives investment level and consent gating.

| Tier | Signals | Action | Investment policy |
|---|---|---|---|
| **high** | Asks back; reveals specifics; plays back; matches or escalates flirtation; logistically plausible; structurally compatible | Invest, qualify, escalate when `escalation_readiness.ready === true` | Match her energy; slightly elevate when she increases |
| **medium** | Some warmth; inconsistent effort; one or more compatibility unknowns | Test one key unknown with a single sharper shot | Match her energy only; do not pre-invest |
| **low** | Only responds, never asks; vague; dodges clarity; hot/cold | Do not carry; let dormancy handle it | Do not over-function; one revive max if structurally viable |
| **false-positive** | High chemistry but low compatibility, low availability, or pure fantasy fuel | Do not romanticise; clarify or exit | Charge does not justify investment; check `false_chemistry_flags[]` |

**Tier rules**:
- A thread can move up tiers when she invests; downgrade after two consecutive `maintaining` or one `decreasing` (matches `references/decision-rubric.md` deprioritise triggers).
- `false-positive` is not a downgrade of `high` — it is a separate diagnosis. A thread can have high chemistry and still be false-positive.
- Lead tier informs message length: drafts to `low` and `false-positive` should be short or absent. Long replies to short replies are an over-function red flag.

**Default starting tier**: `medium` after first reply, until evidence supports `high` or `low`.
