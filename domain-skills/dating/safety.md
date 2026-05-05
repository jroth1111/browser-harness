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
- Messages to a match where the most recent exchange in `.private-data/outcome-log.md` is older than 7 days (treat as a re-engagement, not a continuation)
- Any action where AI confidence (per `references/scoring.md` and `references/decision-rubric.md`) is LOW
- Opening or reviewing any existing conversation

These actions are never allowed:
- Direct platform API calls, including `api.gotinder.com` — all data comes through browser UI
- Reading auth tokens from localStorage, cookies, or browser storage

## Rate limiting

No hard caps. Pacing rules and break scheduling keep behavior human-like; the user controls when to stop. All inter-action delays use uniform random within the stated range.

| Action | Delay | Purpose |
|---|---|---|
| Between swipes | 1.5–5.0s | Human-like rhythm |
| Between reading profiles | 0.5–2.0s | Human-like rhythm |
| Between sending messages | 2.0–5.0s | Human-like rhythm |
| Between opening chats | 15–45s | User-paced, not bulk |
| After navigation | wait for content (≥1.0s) | DOM ready |
| After every 10 swipes | Pause 60–120s | Break cadence |
| After every 5 messages | Pause 120–240s | Break cadence |
| After each conversation | Pause and ask whether to continue | User control |
| Chat extraction | See `chat-audit.md` pacing | Slow UI-only crawl |
| GDPR export | No limits — no browser interaction | Instant, zero risk |

## Anti-detection countermeasures

### Behavioral patterns

1. **Variable timing**: Never use fixed intervals. Randomize all delays.
2. **Profile engagement**: Occasionally scroll through full profile (3-8 seconds) before swiping, rather than always swiping instantly.
3. **Navigation variety**: Occasionally navigate away from the swipe stack and back. Visit matches page, then return.
4. **Session breaks**: Never run for extended periods without breaks. Follow pacing guidelines above.
5. **Message uniqueness**: Never send identical messages to multiple matches. Each message must be unique and context-specific.
6. **No direct APIs**: Never call platform private APIs or read auth tokens from browser storage.
7. **Read-before-send**: Review the relevant visible conversation before drafting a reply, but only for the user-selected conversation being handled.
8. **Extraction pacing**: Full chat extraction via UI crawl must follow pacing rules in `chat-audit.md` — 3-6s between navigation, 2-4s between scrolls, 8-15s between conversations, checkpoint after each.
9. **Popup chain handling**: Tinder shows 7+ popup types in sequence after login/navigation. Dismiss each with Escape. If a popup can't be dismissed, stop and notify the user.
10. **Photo cycling**: Use SPACE key to cycle through profile photos (0.4s pause between) — this is how the keen-slider carousel works. More natural than clicking navigation arrows.

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
- Unexpected popup that doesn't match known dismissal patterns (known popups: cookie consent, location permission, notification prompt, upgrade nags, match modal — all dismissible with Escape)

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

Three-tier escalation. Tier is set by the block type detected, not by count.

- **Tier 1 — soft signal** (CAPTCHA, "Something went wrong", unexpected popup, repeated selector failure): wait at least 24 hours, then resume only with manual, UI-only, one-action-at-a-time operation. If a second Tier-1 signal appears in the next session, escalate to Tier 2.
- **Tier 2 — explicit restriction** ("Your account is under review", 24-hour temporary ban, rate-limit lockout, account activity warning): do not automate that platform again unless the user explicitly re-enables it in a later session. Resumption starts with manual, UI-only operation.
- **Tier 3 — repeat or hard block** (any block after a Tier-2 reset, or permanent restriction): stop all automation on that platform and discuss with the user before any further action.

## Audit trail

### Required logging

Every automated action logs to `.private-data/outcome-log.md`:

```text
## [Timestamp] — [Platform] — [Action]

Type: [swipe | message | navigate | read]
Target: [match name or profile identifier]
Decision: [LIKE/PASS | message text | URL]
AI confidence: [HIGH/MEDIUM/LOW]
Consent: [auto/approved/manual]
Rubric score: [if applicable]
Result: [success/fail/block]
Predicted_watch: [Watch line if message; per references/thread-state.md predictions]
Verdict: [confirmed/falsified/inconclusive — when a prior prediction was resolved this cycle]
Thread_stage: [from .private-data/threads/<match_id>.json — for messages]
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

Funnel (this session):
- Openers sent: [N]
- Opener replies received: [N] ([rate%])
- Conversations active: [N]
- Date proposals sent: [N] ([rate% of active conversations])
- Date proposals accepted: [N] ([rate%])

Funnel (rolling 30 days, computed from .private-data/threads/*.json):
- Opener → reply: [rate%] over [N openers]
- Conversation → escalation: [rate%] over [N conversations]
- Escalation → date confirmed: [rate%] over [N proposals]
- Date confirmed → meet: [rate%] over [N confirmed]

Closed-loop verdicts (this session):
- Predictions resolved: [N]
- Confirmed / Falsified / Inconclusive: [N / N / N]
- Cross-thread patterns surfaced: [N — list briefly]
```

The funnel rates and verdicts are computed by reading `.private-data/threads/*.json` per `references/thread-state.md` cross-thread queries. They are the primary feedback signal for whether rubric/voice changes are working; review them at the end of every session.

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
