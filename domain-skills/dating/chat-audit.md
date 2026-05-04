# Chat Audit — Slow Resumable Browser UI Extraction

Extracts all conversations through the browser UI — no private APIs, no token reading, no direct `api.gotinder.com` calls. Simulates a human browsing their chat history at a leisurely pace. Checkpoints after each conversation so extraction can pause and resume across sessions.

## Hard rules

- **Never call platform private APIs** (`api.gotinder.com` etc.)
- **Never read auth tokens** from `localStorage`, cookies, or browser storage
- **Never extract data via any path other than visible browser DOM**
- **Always checkpoint** after completing each conversation
- **Always respect pacing** — this is slow by design

## Prerequisites

- User is logged into the target platform in Chrome
- Browser-harness is connected
- Platform selectors have been field-tested (see `platforms/<platform>.md`)

## Extraction protocol

### Phase 1: Chat list discovery

Scroll through the messages sidebar to collect all conversation entries.

**Selectors (Tinder, confirmed):**
```
sidebar_link:  "nav a[href*='/app/messages/']"
```

**Process:**
1. Navigate to `https://tinder.com/app/messages`
2. Wait for sidebar to load
3. Run extraction JS to collect visible sidebar links
4. Scroll the sidebar down
5. Wait 2-4 seconds
6. Repeat from step 3
7. **Saturation**: 3 consecutive scrolls with 0 new entries = chat list complete
8. Save discovered chat list to `.private-data/extraction-state.json`

**Extraction JS:**
```javascript
() => {
  const links = document.querySelectorAll('nav a[href*="/app/messages/"]');
  const convos = [];
  for (const link of links) {
    const url = link.href;
    const matchId = url.split('/app/messages/')[1] || '';
    const name = link.textContent.trim();
    convos.push({ name, matchId, url });
  }
  return convos;
}
```

### Phase 2: Thread extraction

Iterate through the discovered chat list. One conversation per step.

**Selectors (Tinder, confirmed):**
```
conversation_log:  "[role='log']"
message_article:   "[role='log'] [role='article']"
sender:            "strong.Hidden"  →  textContent minus ":"
message_text:      "span.text"
timestamp:         "time"  →  textContent + datetime attribute
is_user_sent:      sender === "You"
```

**Per-conversation process:**
1. Click the sidebar link for the next pending conversation (not URL navigation — more human-like)
2. Wait 3-6 seconds (simulating reading the opening messages)
3. Extract visible messages via JS
4. If the conversation has older messages (scroll-up arrow or "load more" present), scroll up within the conversation log
5. Wait 2-4 seconds per scroll
6. Extract newly loaded messages, deduplicate against already-extracted
7. **Saturation**: 3 consecutive scrolls with 0 new messages = thread complete
8. Mark conversation as `complete` in checkpoint
9. Wait 8-15 seconds before starting the next conversation

**Thread extraction JS:**
```javascript
() => {
  const log = document.querySelector("[role='log']");
  if (!log) return { error: "no log element" };
  const articles = log.querySelectorAll("[role='article']");
  const messages = [];
  for (const art of articles) {
    const senderEl = art.querySelector("strong.Hidden");
    const sender = senderEl
      ? senderEl.textContent.replace(":", "").trim()
      : "unknown";
    const textEl =
      art.querySelector("span.text") ||
      art.querySelector("span[class*='text']");
    const text = textEl ? textEl.textContent.trim() : "";
    const timeEl = art.querySelector("time");
    const time = timeEl ? timeEl.textContent.trim() : "";
    const datetime = timeEl ? timeEl.getAttribute("datetime") : "";
    const isSent = sender === "You";
    messages.push({ sender, text, time, datetime, isSent });
  }
  return messages;
}
```

### Checkpoint format

`.private-data/extraction-state.json`:
```json
{
  "started": "2026-05-04T12:00:00Z",
  "last_updated": "2026-05-04T12:30:00Z",
  "phase": "thread_extraction",
  "chat_list": [
    { "name": "Ale", "match_id": "abc123", "url": "https://tinder.com/app/messages/abc123" }
  ],
  "threads": {
    "abc123": {
      "name": "Ale",
      "status": "complete",
      "message_count": 14,
      "messages": [
        { "sender": "You", "text": "Hey!", "time": "10:30 AM", "datetime": "2026-04-28T03:30:00Z", "isSent": true }
      ]
    }
  },
  "completed_count": 15,
  "total_count": 60
}
```

Thread statuses: `pending` (not yet visited), `partial` (started but not saturated), `complete` (fully extracted).

### Resumption

On session start, check if `.private-data/extraction-state.json` exists:
- **If not present**: start fresh from Phase 1
- **If present with `phase: "chat_list_discovery"`**: resume Phase 1 from current sidebar position
- **If present with `phase: "thread_extraction"`**: skip Phase 1, resume Phase 2 from the next conversation with `status: "pending"` or `status: "partial"`

### Pacing rules

| Action | Delay range | Distribution |
|---|---|---|
| After navigating to a conversation | 3-6s | Uniform random |
| Between scroll-up actions within a conversation | 2-4s | Uniform random |
| Between completing one conversation and starting the next | 8-15s | Uniform random |
| After every 5 conversations | 60-120s | Break |

### Session limits

No hard cap on conversations per session. The pacing rules and break scheduling naturally limit throughput. If the user wants to stop, they say "stop" — the checkpoint saves progress and they can resume in a future session.

The extraction stops automatically on:
- Block/CAPTCHA/account restriction detected
- User says "stop" or "pause"
- Login session expires (redirect to login page)

## Analysis

After extraction (or mid-extraction at user request), analyze the collected threads:

### Voiceprint extraction

From the user's messages across all extracted threads, extract:
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
- **Recurring dynamics**: is there a pattern the user repeats?

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
- Going platonic when romantic charge would be appropriate
- Taking too long to escalate when signals are present
- Escalating too fast when the other person needs more time
- Repeating the same opener regardless of match
- Not reviving threads that had real signal
- Not exiting threads that are clearly one-sided

## Output

### `.private-data/voiceprint.md`
Full voiceprint from `references/voiceprint.md` template. Include:
- 5+ example messages characteristic of the user's voice
- 5+ example messages NOT characteristic (anti-pattern calibration)

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

### `.private-data/user-model.md` (supplement)
```text
## From full chat extraction

Attractive-but-unsuitable patterns observed: [...]
Blind spots flagged: [...]
Communication strengths: [...]
Communication patterns to adjust: [...]
Successful compatibility signals: [...]
False chemistry patterns: [...]
```

## Privacy

- All extraction data stays in `.private-data/` (gitignored)
- Outcome log entries reference matches by first name only
- Never store match photos
- The user reviews all analysis outputs before they become part of the user model
- Never store auth tokens, API responses, or raw exported histories from non-DOM sources
- `extraction-state.json` contains message content for analysis purposes only

## Integration with onboarding

The full extraction can run at any point in the onboarding flow:

1. **Before interview**: Extract everything, produce draft voiceprint + outcome patterns. Interview confirms/corrects and fills remaining fields.
2. **During interview**: Extraction runs as part of the research phase, interview continues after.
3. **After interview**: Interview runs first for basic fields, extraction enriches with real behavioral data.

Recommended: **After**. Manual interview is the primary source; chat extraction calibrates and enriches.
