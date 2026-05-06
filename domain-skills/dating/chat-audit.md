# Chat Audit — Full Conversation Extraction

Three extraction paths, ordered by speed. All avoid private APIs and token reading.

1. **GDPR export** (fastest, zero browser interaction) — user provides Tinder's data export JSON.
2. **Browser UI crawl** (slow, resumable) — visible-DOM-only crawl with checkpointing.
3. **Manual paste** (fallback) — user pastes specific conversations into chat.

## Consent — read this before starting

The default consent rule in `safety.md:35` ("any conversation viewed → hard consent") applies to **live operations** — you opening one conversation to draft a reply. **It does not apply to chat-audit Path 2.** The audit run itself is the consented operation; once the user has approved the audit, the skill must not re-prompt per conversation inside the run. This is **session-scoped consent**, recorded in `extraction-state.json::session_consent_granted_at`.

This rule mirrors `surface-map.json` `browser_extract_all_chats.consent_gate: true`, which expresses the same "audit-run is the gate" contract in machine-readable form.

The audit run still terminates immediately on:
- block / CAPTCHA / account restriction (popup that cannot be dismissed with Escape);
- login redirect (session expired);
- the user saying *stop* or *pause*;
- unexpected popup that does not match a known dismissal pattern;
- rate-limit warnings.

Path 1 (GDPR) and Path 3 (manual paste) involve no live UI traversal and have their own implicit consent (the user provided the file or the text).

## Hard rules

- **Never call platform private APIs** (`api.gotinder.com` etc.).
- **Never read auth tokens** from `localStorage`, cookies, or browser storage.
- **Browser extraction must go through visible DOM only.**
- **Always checkpoint** after completing each conversation (Path 2).
- **Always respect pacing** — Path 2 is slow by design.

## Path selection

Ask the user:

1. **GDPR export available?** → Path 1 (fastest, richest data).
2. **No GDPR, browser available and logged in?** → Path 2 (slow, complete; explicit session-scoped consent required before starting).
3. **Neither?** → Path 3 (manual, selective).

---

## Path 1 — GDPR export (fast)

Tinder provides a full data export at *Settings → Download My Data*. The user requests it; Tinder emails a download link (typically within 24–48 hours). The JSON contains full message history, match list, usage stats, and profile data.

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

2025+ exports use `TinderPhoto[]` objects instead of `string[]` URLs. Handle both formats.

### Process

1. User provides the JSON file path.
2. Parse `Messages` — each entry is a match with its full message thread.
3. Cross-reference `User` for self-profile data.
4. Cross-reference `Usage` for activity patterns (swipe rates, match rates over time).
5. Write parsed data to `.private-data/extraction-state.json` (same shape as Path 2 output).
6. Skip directly to **Analysis**.

GDPR is richer than browser extraction (includes usage stats, purchase history, full match list with unmatched conversations). Prefer this path when available.

---

## Path 2 — Browser UI crawl (slow, resumable)

### Prerequisites

- User is logged into the target platform in Chrome.
- Browser-harness is connected.
- Platform selectors have been field-tested (see `platforms/<platform>.md`).
- **User has granted session-scoped consent for the audit run.** Record `session_consent_granted_at` in `extraction-state.json` before extracting any conversation.

### Phase 1 — Chat list discovery

Scroll through the messages sidebar to collect all conversation entries.

**Selectors (Tinder, confirmed):**

```
sidebar_link:  "nav a[href*='/app/messages/']"
```

**Process:**

1. Navigate to `https://tinder.com/app/messages`.
2. **Dismiss popups** — Tinder shows a chain of popups after navigation (cookie consent, location permission, notification prompt, upgrade nags). Dismiss each by pressing Escape or clicking dismiss/close buttons. If a popup blocks the sidebar, handle it before continuing.
3. Wait for sidebar to load.
4. Run extraction JS to collect visible sidebar links.
5. **Filter out non-chat links** — exclude URLs containing `likes-you` or `my-likes`.
6. Scroll the sidebar container via JS: `el.scrollTop = el.scrollHeight`, compare `scrollHeight` before/after. Unchanged → saturated.
7. Wait 2–4 seconds.
8. Repeat from step 4.
9. **Saturation:** 3 consecutive scrolls with 0 new entries = chat list complete.
10. Save discovered chat list to `.private-data/extraction-state.json`.

**Sidebar extraction JS:**

```javascript
() => {
  const links = document.querySelectorAll('nav a[href*="/app/messages/"]');
  const convos = [];
  for (const link of links) {
    const url = link.href;
    const matchId = url.split('/app/messages/')[1] || '';
    if (matchId === 'likes-you' || matchId === 'my-likes' || matchId === '') continue;
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

### Phase 2 — Thread extraction

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

1. Click the sidebar link for the next pending conversation (not URL navigation — more human-like).
2. Wait 3–6 seconds (simulating reading the opening messages).
3. **Dismiss any popups** — upgrade nags, "It's a Match!" modals, rate-limit warnings. Press Escape or click dismiss. CAPTCHA / account restriction → stop immediately (see `safety.md`).
4. Extract visible messages via JS.
5. If older messages exist, scroll up within the conversation log: `log.scrollTop = 0`, compare `scrollHeight` before/after.
6. Wait 2–4 seconds per scroll.
7. Extract newly loaded messages, deduplicate against already-extracted.
8. **Saturation:** 3 consecutive scrolls with 0 new messages = thread complete.
9. Mark conversation `complete` in checkpoint.
10. Wait 8–15 seconds before starting the next conversation.

**Thread extraction JS (with fallback selectors):**

```javascript
() => {
  const log = document.querySelector("[role='log']");
  if (!log) return { error: "no log element" };
  const articles = log.querySelectorAll("[role='article']");
  const messages = [];
  for (const art of articles) {
    const senderEl = art.querySelector("strong.Hidden");
    let sender = senderEl
      ? senderEl.textContent.replace(":", "").trim()
      : "unknown";
    let isSent = sender === "You";

    if (sender === "unknown") {
      const classStr = art.className || "";
      if (classStr.includes("Ta(e)")) { sender = "You"; isSent = true; }
      else if (classStr.includes("Ta(start)")) { sender = "match"; isSent = false; }
    }

    const textEl =
      art.querySelector("span.text") ||
      art.querySelector("span[class*='text']") ||
      art.querySelector("div.msg > span");
    const text = textEl ? textEl.textContent.trim() : "";

    const timeEl = art.querySelector("time");
    const time = timeEl ? timeEl.textContent.trim() : "";
    const datetime = timeEl ? timeEl.getAttribute("datetime") : "";

    messages.push({ sender, text, time, datetime, isSent });
  }
  return messages;
}
```

### Checkpoint format

`.private-data/extraction-state.json` (full schema in `state.md`):

```json
{
  "started": "2026-05-04T12:00:00Z",
  "last_updated": "2026-05-04T12:30:00Z",
  "session_consent_granted_at": "2026-05-04T11:58:00Z",
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

Thread statuses: `pending` (not yet visited) / `partial` (started but not saturated) / `complete` (fully extracted).

### Resumption

On session start, check `.private-data/extraction-state.json`:

- **Not present** → start fresh from Phase 1 (after re-consenting).
- **Present, `phase: "chat_list_discovery"`** → resume Phase 1 from current sidebar position.
- **Present, `phase: "thread_extraction"`** → skip Phase 1, resume Phase 2 from the next conversation with `status: "pending"` or `status: "partial"`.

If the previous run's `session_consent_granted_at` is older than 24 hours, re-confirm consent before resuming.

### Pacing rules

| Action | Delay range | Distribution |
|---|---|---|
| After navigating to a conversation | 3–6s | Uniform random |
| Between scroll-up actions within a conversation | 2–4s | Uniform random |
| Between completing one conversation and starting the next | 8–15s | Uniform random |
| After every 5 conversations | 60–120s | Break |

No hard cap on conversations per session. Pacing rules and break scheduling naturally limit throughput. If the user wants to stop, they say *stop* — the checkpoint saves and they resume in a future session.

Extraction stops automatically on:

- block / CAPTCHA / account restriction (popup that cannot be dismissed with Escape);
- user says *stop* or *pause*;
- login session expires (redirect to login page);
- unexpected popup that does not match known dismissal patterns (cookie consent, location, notification, upgrade nag, match modal).

---

## Path 3 — Manual paste (fallback)

If GDPR is unavailable and browser extraction is not feasible, the user pastes conversations directly. For each pasted conversation, extract sender, text, timestamp where present and add to the analysis pipeline. Lower fidelity (no timestamps sometimes, no metadata) but works for specific conversations the user wants analysed.

---

## Analysis (all three paths)

After extraction (or mid-extraction at user request), analyse the collected threads.

### Voiceprint extraction

From the user's messages across all extracted threads, extract per the `voiceprint.md` schema in `state.md`:

- sentence rhythm (short/punchy, medium, long/complex);
- typical length (average word count per message);
- directness (how directly the user states interest or asks questions);
- warmth (compliments, encouragement, personal disclosure);
- edge (sarcasm, teasing, challenge, flirtation intensity);
- humour (punny, deadpan, absurdist, self-deprecating, witty);
- flirt style (how the user signals romantic interest);
- question vs statement ratio;
- emoji / punctuation patterns;
- response time patterns (where timestamps available).

### Outcome pattern analysis

For each conversation, tag:

1. **Opener quality** — did the user's first message get a response? what kind?
2. **Momentum trajectory** — energy increasing, flat, or decreasing?
3. **Turning points** — what message changed the trajectory?
4. **Exit pattern** — who stopped responding? clean exit or fade?
5. **Escalation attempts** — did the user try to move to meeting? how? what happened?

Aggregate patterns:

- **High-response openers** — what type got the best responses?
- **Momentum killers** — what message patterns preceded ghosting/fading?
- **Successful escalation triggers** — what preceded date proposals that worked?
- **Recurring dynamics** — patterns the user repeats.

### Compatibility signal extraction

From matches the user engaged with most:

- traits the most engaging matches shared;
- profile types that produced the longest threads;
- mismatches the user pursued anyway;
- compatible people the user let fade.

### Blind spot identification

Flag recurring patterns the user may not notice:

- consistently pursuing one type that does not work out;
- overinvesting in low-reciprocity threads;
- going platonic when romantic charge would be appropriate;
- taking too long to escalate when signals are present;
- escalating too fast when the other person needs more time;
- repeating the same opener regardless of match;
- not reviving threads that had real signal;
- not exiting threads that are clearly one-sided.

## Output

### `.private-data/voiceprint.md`

Full voiceprint per the schema in `state.md`. Include 5+ example messages characteristic of the user's voice and 5+ that are NOT characteristic (anti-pattern calibration).

### `.private-data/outcome-log.md`

Per-conversation summary appended:

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

- All extraction data stays in `.private-data/` (gitignored).
- Outcome log entries reference matches by first name only.
- Never store match photos.
- The user reviews all analysis outputs before they become part of the user model.
- Never store auth tokens, API responses, or raw exported histories from non-DOM sources.
- `extraction-state.json` contains message content for analysis purposes only.

## Integration with onboarding

A full audit can run at any point:

1. **Before interview** — extract everything, draft voiceprint + outcome patterns, interview confirms / corrects / fills remaining fields.
2. **During interview** — audit runs as part of the research phase; interview continues after.
3. **After interview** — interview runs first for basic fields; extraction enriches with real behavioural data.

Recommended: **after** interview. Interview is the primary source; chat extraction calibrates and enriches.
