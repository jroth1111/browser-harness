# Chat Audit — Extract Voiceprint and Outcome Patterns from Existing Conversations

Reads all existing conversations on a connected dating platform and synthesizes voiceprint, outcome patterns, compatibility signals, and user model refinements.

## Purpose

The chat audit is the richest signal source for building the user model. It reveals:
- **Voiceprint**: how the user actually writes in dating contexts
- **What worked**: messages that produced warm, engaged responses
- **What didn't**: messages that fell flat, were ignored, or killed momentum
- **Compatibility patterns**: what kinds of people the user connects with
- **Blind spots**: patterns the user may not notice (chasing, overinvesting, underinvesting, etc.)
- **Pace**: how fast the user moves from chat to meeting
- **Stage handling**: how the user handles openings, banter, escalation, exits

## Prerequisites

- User is logged into the target platform in Chrome
- Browser-harness is connected
- Platform selectors have been field-tested (see `platforms/<platform>.md`)

## Extraction process

### Step 1: Navigate to chat list
```python
new_tab("https://tinder.com/app/messages")
wait_for_content()
```

### Step 2: Extract chat list
- Get all conversation entries: match name, last message preview, timestamp
- Count total conversations for progress reporting

### Step 3: For each conversation, extract full thread
```python
# Navigate to conversation
# Scroll to load full history
# Extract: all messages, senders, timestamps
# Store as structured data
```

Per-message fields:
- `sender`: "user" or "match"
- `text`: message content
- `timestamp`: when sent (if available)
- `position_in_thread`: ordinal position

### Step 4: Classify conversations
For each thread, classify:
- **Outcome**: matched → opener sent → response → continued → date / ghosted / fizzled / unmatched
- **Length**: number of exchanges
- **User effort**: proportion of messages sent by user vs match
- **Thread health**: warm, flat, draining, one-sided

## Analysis framework

### Voiceprint extraction

From the user's messages across all threads, extract:
- **Sentence rhythm**: short/punchy, medium, or long/complex
- **Typical length**: average word count per message
- **Directness**: how directly the user states interest or asks questions
- **Warmth**: use of compliments, encouragement, personal disclosure
- **Edge**: sarcasm, teasing, challenge, flirtation intensity
- **Humour**: punny, deadpan, absurdist, self-deprecating, witty
- **Flirt style**: how the user signals romantic interest
- **Question vs statement ratio**: does the user ask a lot of questions or make statements?
- **Emoji/punctuation**: patterns in emoji use, exclamation marks, periods
- **Response time patterns**: fast/slow, consistent/variable (if timestamps available)

### Outcome pattern analysis

For each conversation, tag:
1. **Opener quality**: did the user's first message get a response? What kind?
2. **Momentum trajectory**: did energy increase, stay flat, or decrease?
3. **Turning points**: what message changed the trajectory (positive or negative)?
4. **Exit pattern**: who stopped responding? Was there a clean exit or a fade?
5. **Escalation attempts**: did the user try to move to meeting? How? What happened?

Aggregate patterns:
- **High-response openers**: what type of opener got the best responses?
- **Momentum killers**: what message patterns preceded ghosting/fading?
- **Successful escalation triggers**: what preceded date proposals that worked?
- **Recurring dynamics**: is there a pattern the user repeats? (overinvesting, chasing, going too platonic, moving too fast/slow)

### Compatibility signal extraction

From matches the user engaged with most:
- What traits did the most engaging matches share?
- What kinds of profiles produced the longest threads?
- Were there mismatches the user pursued anyway?
- Were there compatible people the user let fade?

### Blind spot identification

Flag recurring patterns the user may not notice:
- Consistently pursuing one type that doesn't work out
- Overinvesting in low-reciprocity threads
- Going platonic when romantic charge would be appropriate (or vice versa)
- Taking too long to escalate when signals are present
- Escalating too fast when the other person needs more time
- Repeating the same opener or message pattern regardless of match
- Not reviving threads that had real signal
- Not exiting threads that are clearly one-sided

## Output

Write three files:

### `.private-data/voiceprint.md`
Populate the full voiceprint template from `references/voiceprint.md` using extracted patterns. Include:
- 5+ example messages that are characteristic of the user's voice
- 5+ example messages that are NOT characteristic (for anti-pattern calibration)

### `.private-data/outcome-log.md`
Per-conversation summary:
```text
## [Match name] — [platform] — [date range]

Thread length: [N exchanges]
Outcome: [ghosted / fizzled / date / unmatched / ongoing]
User effort: [high/medium/low]
Match effort: [high/medium/low]
Best user message: [what landed]
Worst user message: [what missed or killed momentum]
Escalation: [attempted/not attempted / succeeded/failed]
Signal quality: [strong/medium/weak]
Lesson: [one-line takeaway]
```

### `.private-data/user-model.md` (research draft supplement)
Add a section:
```text
## From chat audit

Attractive-but-unsuitable patterns observed: [...]
Blind spots flagged: [...]
Communication strengths: [...]
Communication patterns to adjust: [...]
Successful compatibility signals: [...]
False chemistry patterns: [...]
```

## Privacy

- Chat content stays in `.private-data/` (gitignored)
- Outcome log entries reference matches by first name only
- Never store match photos
- The user reviews all outputs before they become part of the user model
- The user can exclude specific conversations from analysis

## Integration with onboarding

The chat audit can run before or during the onboarding interview:

1. **Before**: Audit runs first, produces draft voiceprint + outcome patterns. Interview confirms/corrects and fills remaining fields.
2. **During**: Audit runs as part of the research phase, interview continues after.
3. **After**: Interview runs first for basic fields, audit enriches with real behavioral data.

Recommended: **Before**. The audit provides the richest data, and the interview becomes a lightweight confirmation pass.
