# Safety — Consent Gates, Rate Limits, Anti-Detection

## Consent gates

### Message consent levels

| Level | Behavior | When to use |
|---|---|---|
| **draft-only** | Show message, user sends manually | New users, calibration period |
| **approve** | Show message, send on user approval | Default. User stays in the loop |
| **auto-send** | Send automatically, log what was sent | Trusted patterns, low-stakes replies |
| **auto-threshold** | Auto-send below confidence threshold, approve above | Experienced users who want oversight on edge cases |

The user's configured level is stored in `.private-data/user-model.md`. Default is **approve** for messages.

### Swipe consent levels

| Level | Behavior | When to use |
|---|---|---|
| **manual** | Show each profile, user decides | Full control, learning rubric |
| **approve-non-obvious** | Auto-swipe obvious PASS, show LIKE and MAYBE | Reduce noise while keeping agency on matches |
| **full-auto** | Auto-swipe all, log decisions | Trusted rubric, high-volume sessions |
| **auto-threshold** | Auto-swipe below score threshold, show above | Balanced automation |

Default is **approve-non-obvious** for swipes.

### Hard consent requirements

Regardless of configured level, these always require explicit user confirmation:
- First message to a new match (opener)
- Date proposal or escalation message
- Any message the AI flags as "high risk" (could be misread, boundary-crossing, or tone-mismatched)
- Messages to matches the user hasn't interacted with in 7+ days
- Any action when the AI confidence is below 50%
- Opening or reviewing any existing conversation
- Any review of more than 3 conversations in a session (does not apply to slow UI-only chat extraction with checkpointing — see `chat-audit.md`)

These actions are never allowed:
- Direct platform API calls, including `api.gotinder.com` — all data comes through browser UI
- Reading auth tokens from localStorage, cookies, or browser storage

## Rate limiting

### Inter-action timing

| Action | Minimum delay | Maximum delay | Distribution |
|---|---|---|---|
| Between swipes | 1.5s | 5.0s | Uniform random |
| Between reading profiles | 0.5s | 2.0s | Uniform random |
| Between sending messages | 2.0s | 5.0s | Uniform random |
| Between opening chats | 15.0s | 45.0s | User-paced, not bulk |
| After navigation | 1.0s | — | Wait for content |

### Session limits

| Limit | Default | Maximum | Rationale |
|---|---|---|---|
| Swipes per session | 20 | 40 | Conservative account-safety cap |
| Messages per session | 10 | 20 | Avoid spam detection |
| Existing conversations reviewed | 3 | 5 | User-selected sample for live review |
| Chat extraction per session | No hard cap | No hard cap | Slow UI-only crawl with checkpointing (see `chat-audit.md`). Pacing rules self-limit. |
| Session duration | 20 min | 45 min | Avoid prolonged bot-like sessions |
| Concurrent conversations | 3 | 5 | Quality over quantity |

### Break scheduling

- After every 10 swipes: pause 60-120 seconds
- After every 5 messages: pause 120-240 seconds
- After each reviewed existing conversation: pause and ask whether to continue
- After session limit: stop completely, report summary

## Anti-detection countermeasures

### Behavioral patterns

1. **Variable timing**: Never use fixed intervals. Randomize all delays.
2. **Profile engagement**: Occasionally scroll through full profile (3-8 seconds) before swiping, rather than always swiping instantly.
3. **Navigation variety**: Occasionally navigate away from the swipe stack and back. Visit matches page, then return.
4. **Session breaks**: Never run for extended periods without breaks. Respect session duration limits.
5. **Message uniqueness**: Never send identical messages to multiple matches. Each message must be unique and context-specific.
6. **No direct APIs**: Never call platform private APIs or read auth tokens from browser storage.
7. **Read-before-send**: Review the relevant visible conversation before drafting a reply, but only for the user-selected conversation being handled.
8. **Extraction pacing**: Full chat extraction via UI crawl must follow pacing rules in `chat-audit.md` — 3-6s between navigation, 2-4s between scrolls, 8-15s between conversations, checkpoint after each.

### Fingerprint reduction

1. Use keyboard shortcuts for swiping when available (more human-like than button clicks).
2. Vary the entry point (sometimes start from matches, sometimes from recs).
3. Don't always open the first match first. Vary traversal order.
4. Occasionally re-read a profile you've already seen.
5. Do not enumerate the whole account via API. Slow UI-only chat extraction with checkpointing is allowed — it looks like a human browsing their history.

## Block / CAPTCHA handling

### Detection

Stop immediately if any of these appear:
- CAPTCHA challenge (reCAPTCHA, hCaptcha, puzzle)
- "Something went wrong" or error pages
- Redirect to login page when already logged in
- "Your account is under review" or similar restriction notice
- Any 24-hour restriction, temporary ban, or account activity warning
- Unusually fast rate limit (signals detection)
- Page content doesn't match expected structure
- Element selectors fail repeatedly (may indicate DOM changes or block)

### Response protocol

1. **Stop all automation immediately.** Do not retry the action.
2. **Screenshot the block state.** Save to `.private-data/` for diagnosis.
3. **Notify the user** with:
   - What triggered the stop
   - What the page shows
   - Recommended next steps (usually: wait 24h, use platform manually)
4. **Log the incident** in `.private-data/outcome-log.md` with timestamp, platform, action attempted, and block type.
5. **Do not attempt to bypass** CAPTCHA or blocks. This is a hard stop.

### After a block

- Wait at least 24 hours before attempting automation on that platform again.
- After a platform restriction, do not automate that platform again unless the user explicitly re-enables it in a later session.
- On any later session, start with manual, UI-only, one-action-at-a-time operation.
- If blocked a second time, stop all automation on that platform and discuss with user.

## Audit trail

### Required logging

Every automated action logs to `.private-data/outcome-log.md`:

```text
## [Timestamp] — [Platform] — [Action]

Type: [swipe | message | navigate | read]
Target: [match name or profile identifier]
Decision: [LIKE/PASS | message text | URL]
AI confidence: [0-100]
Consent: [auto/approved/manual]
Rubric score: [if applicable]
Result: [success/fail/block]
Notes: [any observations]
```

### Session summary

At the end of each session, append:

```text
## Session Summary — [Date]

Duration: [minutes]
Swipes: [N] (LIKE: N, PASS: N, MAYBE: N)
Messages sent: [N]
Messages drafted: [N]
New matches: [N]
Conversations checked: [N]
Blocks/incidents: [N]
```

## Emergency stop

The user can say "stop" or "pause" at any time. The AI must:
1. Halt the current action immediately.
2. Not send any queued messages.
3. Log where it stopped.
4. Ask the user what they want to do next.

If the AI detects anything that could compromise the user's account or safety, it stops autonomously and notifies the user. This includes:
- Unexpected API responses
- Account warning messages
- Changes in account permissions or features
- Messages from the platform about terms of service
