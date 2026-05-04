# Chat Audit — Full Conversation Extraction

Three extraction paths, ordered by speed. All avoid private APIs and token reading.

1. **GDPR export** (fastest, zero browser interaction) — user provides Tinder's data export JSON
2. **Browser UI crawl** (slow, resumable) — simulates a human browsing chat history at leisurely pace
3. **Manual paste** (fallback) — user pastes specific conversations into the conversation

## Hard rules

- **Never call platform private APIs** (`api.gotinder.com` etc.)
- **Never read auth tokens** from `localStorage`, cookies, or browser storage
- **Browser extraction must go through visible DOM only**
- **Always checkpoint** after completing each conversation (browser crawl)
- **Always respect pacing** — browser crawling is slow by design

## Path 1: GDPR export (fast path)

Tinder provides a full data export at Settings → Download My Data. The user requests it, Tinder emails a download link (typically within 24-48 hours). The JSON file contains full message history, match list, usage stats, and profile data.

### GDPR export schema (confirmed from swipestats.io parser)

```
{
  "User": {
    "birth_date", "create_date", "gender", "bio",
    "city": { "name", "region" },
    "education", "jobs": [{ "company": { "name" }, "title": { "name" } }],
    "schools": [{ "name", "displayed" }],
    "interests": [{ "name" }],
    "descriptors": [{ "name", "choices", "visibility" }],
    "sexual_orientations", "email", "full_name"
  },
  "Usage": {
    "app_opens": { "date": count },
    "swipes_likes": { "date": count },
    "swipes_passes": { "date": count },
    "matches": { "date": count },
    "messages_sent": { "date": count },
    "messages_received": { "date": count }
  },
  "Messages": [
    {
      "match_id": "string",
      "messages": [
        { "to", "from", "message", "sent_date", "type": "gif|gesture|activity|contact_card|swipe_note|undefined" }
      ]
    }
  ],
  "Photos": ["url"] | [{ "id", "url", "created_at", "selfie_verified" }],
  "Purchases": { "subscription": [], "consumable": [] }
}
```

Note: 2025+ exports use `TinderPhoto[]` objects instead of `string[]` URLs. Handle both formats.

### GDPR parsing process

1. User provides the JSON file path
2. Parse `Messages` array — each entry is a match with its full message thread
3. Cross-reference `User` for self-profile data
4. Cross-reference `Usage` for activity patterns (swipe rates, match rates over time)
5. Write parsed data to `.private-data/extraction-state.json` in the same format as browser extraction
6. Skip directly to Analysis section

GDPR data is richer than browser extraction (includes usage stats, purchase history, full match list with unmatched conversations). Prefer this path when available.

## Path 2: Browser UI crawl (slow path)

Simulates a human browsing their chat history. Checkpoints after each conversation so extraction can pause and resume across sessions.

### Prerequisites

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
2. **Dismiss popups** — Tinder shows a chain of popups after navigation (cookie consent, location permission, notification prompt, upgrade nags). Dismiss each by pressing Escape or clicking dismiss/close buttons. If a popup blocks the sidebar, handle it before continuing.
3. Wait for sidebar to load
4. Run extraction JS to collect visible sidebar links
5. **Filter out non-chat links** — exclude URLs containing `likes-you` or `my-lices` (these are not conversations)
6. Scroll the sidebar container via JS: `el.scrollTop = el.scrollHeight`, then compare `scrollHeight` before and after. If unchanged, scroll is saturated.
7. Wait 2-4 seconds
8. Repeat from step 4
9. **Saturation**: 3 consecutive scrolls with 0 new entries = chat list complete
10. Save discovered chat list to `.private-data/extraction-state.json`

**Sidebar extraction JS:**
```javascript
() => {
  const links = document.querySelectorAll('nav a[href*="/app/messages/"]');
  const convos = [];
  for (const link of links) {
    const url = link.href;
    const matchId = url.split('/app/messages/')[1] || '';
    // Filter out non-chat sidebar links
    if (matchId === 'likes-you' || matchId === 'my-lices' || matchId === '') continue;
    const name = link.textContent.trim();
    convos.push({ name, matchId, url });
  }
  return convos;
}
```

**Sidebar scroll JS:**
```javascript
(el) => {
  const before = el.scrollHeight;
  el.scrollTop = el.scrollHeight;
  return { before, after: el.scrollHeight, changed: el.scrollHeight !== before };
}
```

### Phase 2: Thread extraction

Iterate through the discovered chat list. One conversation per step.

**Selectors (Tinder, confirmed — with fallback chain):**
```
conversation_log:  "[role='log']"
message_article:   "[role='log'] [role='article']"
sender:            "strong.Hidden"  →  textContent minus ":"
sender_fallback:   Yahoo-style class — "Ta(e)" = sent by user, "Ta(start)" = received (less stable)
message_text:      "span.text"  →  fallback: "span[class*='text']"  →  fallback: "div.msg > span"
timestamp:         "time"  →  textContent + datetime attribute
is_user_sent:      sender === "You"  →  fallback: class contains "Ta(e)"
```

Selector priority: a11y attributes (`strong.Hidden`, `role`, `aria-label`) over Yahoo-style CSS classes (`Ta(e)`, `Px(16px)`) which change across builds.

**Per-conversation process:**
1. Click the sidebar link for the next pending conversation (not URL navigation — more human-like)
2. Wait 3-6 seconds (simulating reading the opening messages)
3. **Dismiss any popups** — upgrade nags, "It's a Match!" modals, rate-limit warnings. Press Escape or click dismiss. If a CAPTCHA or account restriction appears, stop immediately (see safety.md).
4. Extract visible messages via JS
5. If the conversation has older messages, scroll up within the conversation log: `log.scrollTop = 0`, then compare `scrollHeight` before/after
6. Wait 2-4 seconds per scroll
7. Extract newly loaded messages, deduplicate against already-extracted
8. **Saturation**: 3 consecutive scrolls with 0 new messages = thread complete
9. Mark conversation as `complete` in checkpoint
10. Wait 8-15 seconds before starting the next conversation

**Thread extraction JS (with fallback selectors):**
```javascript
() => {
  const log = document.querySelector("[role='log']");
  if (!log) return { error: "no log element" };
  const articles = log.querySelectorAll("[role='article']");
  const messages = [];
  for (const art of articles) {
    // Sender: primary selector → fallback to Yahoo-style class detection
    const senderEl = art.querySelector("strong.Hidden");
    let sender = senderEl
      ? senderEl.textContent.replace(":", "").trim()
      : "unknown";
    let isSent = sender === "You";

    // Fallback: Ta(e) = sent by user, Ta(start) = received
    if (sender === "unknown") {
      const classStr = art.className || "";
      if (classStr.includes("Ta(e)")) { sender = "You"; isSent = true; }
      else if (classStr.includes("Ta(start)")) { sender = "match"; isSent = false; }
    }

    // Message text: primary → class partial match → div.msg > span
    const textEl =
      art.querySelector("span.text") ||
      art.querySelector("span[class*='text']") ||
      art.querySelector("div.msg > span");
    const text = textEl ? textEl.textContent.trim() : "";

    // Timestamp
    const timeEl = art.querySelector("time");
    const time = timeEl ? timeEl.textContent.trim() : "";
    const datetime = timeEl ? timeEl.getAttribute("datetime") : "";

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
- Block/CAPTCHA/account restriction detected (popup that cannot be dismissed with Escape)
- User says "stop" or "pause"
- Login session expires (redirect to login page)
- Unexpected popup that doesn't match known dismissal patterns (cookie consent, location, notification, upgrade nag, match modal)

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

## Path 3: Manual paste (fallback)

If GDPR export is unavailable and browser extraction isn't feasible, the user can paste conversations directly. For each pasted conversation, extract the same fields (sender, text, timestamp) and add to the analysis pipeline. This is lower fidelity (no timestamps sometimes, no metadata) but works for specific conversations the user wants analyzed.

## Path selection

Ask the user which path to use:
1. **GDPR export available?** → Use Path 1 (fastest, richest data)
2. **No GDPR, browser available and logged in?** → Use Path 2 (slow but complete)
3. **Neither?** → Use Path 3 (manual, selective)
