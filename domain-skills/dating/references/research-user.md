# User Research — Deep Profile Builder

An alternative to the full interview. Runs before (or instead of) the onboarding interview to pre-populate the user model from observable evidence. The interview then confirms, corrects, and fills gaps rather than starting from zero.

## What this does

Scans the user's digital footprint and synthesizes findings into a draft user model and voiceprint. The output is a pre-populated `.private-data/user-model.md` and `.private-data/voiceprint.md` that the onboarding interview can refine.

## Research sources

Run these in order. Skip any the user declines to provide.

### 1. Browser history and open tabs
- What sites does the user frequent? (values, interests, lifestyle)
- Any dating-adjacent tabs open? (relationship structure signals)
- Professional/career sites? (ambition, work style signals)

### 2. Social media profiles (user provides handles or grants browser access)
- Twitter/X: posting style, humor, topics, political/values signals
- Instagram: visual aesthetic, social context, lifestyle, activities
- LinkedIn: professional identity, ambition signals, education
- Reddit: interests, communities, communication style in discussions
- GitHub: for technical users — coding style is surprisingly revealing about thinking style

### 3. Writing samples (from any source)
- Blog posts, essays, emails, social media posts
- Extract: sentence rhythm, vocabulary, humor, directness, warmth, edge
- This feeds directly into voiceprint calibration

### 4. Dating profile history (if accessible via browser)
- Existing Tinder/Hinge/Bumble profiles or drafts
- What the user chose to present reveals self-perception and intent
- Photo selection patterns reveal self-presentation style

### 5. Existing chat threads (Tinder chat audit — see `chat-audit.md`)
- Read all existing conversations on connected platforms
- Extract: what messages the user sent, what landed, what fell flat
- This is the richest signal source for voiceprint and outcome patterns

## How to run

```
1. Ask the user which sources they're willing to share
2. For each approved source, collect and analyze
3. Synthesize into draft user model + voiceprint
4. Present findings for confirmation/correction
5. Write confirmed version to .private-data/
```

## Synthesis rules

- Label inferred fields as `[inferred]` vs. user-stated facts
- Confidence-tag each field: HIGH (multiple converging signals), MEDIUM (one clear signal), LOW (thin evidence, flag for interview)
- Never assume identity, orientation, or relationship structure — these must be user-stated or very clearly evidenced
- Present inferences as questions, not declarations: "Based on your writing, you seem to value X — is that right?"

## Output format

```markdown
# User Model (Research Draft)

> Generated from: [sources used]
> Confidence: [overall assessment]
> Fields requiring interview confirmation: [list]

1. Identity and orientation fields
- Pronouns/gender: [inferred/user-stated] — [value] — confidence: [H/M/L]
- Sexuality/orientation: [inferred/user-stated] — [value] — confidence: [H/M/L]
[... continue with all user model fields ...]

6. Green / yellow / red flags
- Green signals observed: [from profile/behavior patterns]
- Potential yellow flags: [noted for user to confirm]
- Potential red flags: [noted for user to confirm]

## Voiceprint (Research Draft)
[... populated from writing samples and chat analysis ...]
```

## Interview shortcut flow

After research synthesis, the interview becomes:

1. "Here's what I found. Does this look right?" — present the research draft
2. Correct any wrong inferences
3. Fill gaps marked LOW confidence
4. Answer any remaining questions from the fast-start interview
5. Configure autonomy preferences (still required — can't be inferred)
6. Confirm and save
