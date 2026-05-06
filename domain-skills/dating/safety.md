# Safety — Consent Gates, Rate Limits, Anti-Detection

This file is the consent and rate-limit authority for every action in this skill. Action files (`onboard.md`, `swipe.md`, `reply.md`, `escalate.md`, `chat-audit.md`) read consent levels from `.private-data/user-model.md` and gate execution against the rules below.

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

- First message to a new match (opener) — `reply.md` Stage 4 / opener path.
- Date proposal or escalation message — `escalate.md`.
- Any message the AI flags as **high risk** (could be misread, boundary-crossing, or tone-mismatched).
- Messages to a match where the most recent exchange is older than **7 days** (treat as a re-engagement, not a continuation; see `reply.md` dormancy bands).
- Any action where AI confidence (per `swipe.md` and `reply.md`) is **LOW**.
- **Opening or reviewing any existing conversation, *outside an active audit run*** — see *Audit-run clause* below.

These actions are **never** allowed:

- Direct platform API calls, including `api.gotinder.com` — all data comes through browser UI.
- Reading auth tokens from `localStorage`, cookies, or browser storage.
- Bulk export of matches or conversations via any non-UI surface.
- Storing match photos.

### Audit-run clause (session-scoped consent)

`chat-audit.md` Path 2 (UI crawl) explicitly enumerates and reads the user's existing conversations. That is the operation the user is consenting to when they begin an audit run.

- The audit run **itself** is the consented operation. Once the user has approved a Path 2 run and `extraction-state.json` records `session_consent_granted_at`, the per-conversation hard-consent rule above does **not** re-apply for the duration of that run.
- The audit run is **read-only**. It must not draft, send, or otherwise act on any conversation it touches. Any send-side action originating from material discovered in an audit run re-enters live-ops territory and is gated normally (opener / re-engagement / dormancy rules apply).
- Session-scoped consent **expires** after 24h or when the audit run is marked `completed`, whichever comes first. Resumption past expiry requires fresh confirmation.
- Live-ops paths (`reply.md`, `escalate.md`, `swipe.md` opening a match thread) are **not** audit runs. The per-conversation hard-consent rule applies to them in full.

This is the only carve-out from the per-conversation rule. Everywhere else — including any send-side use of audit findings — the standard hard-consent gate runs.

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
| Chat extraction (Path 2) | See `chat-audit.md` pacing | Slow UI-only crawl |
| GDPR export (Path 1) | No limits — no browser interaction | Instant, zero risk |

## Anti-detection countermeasures

### Behavioral patterns

1. **Variable timing** — never use fixed intervals. Randomize all delays.
2. **Profile engagement** — occasionally scroll through full profile (3–8s) before swiping rather than always swiping instantly.
3. **Navigation variety** — occasionally navigate away from the swipe stack and back. Visit matches page, then return.
4. **Session breaks** — never run for extended periods without breaks. Follow pacing guidelines above.
5. **Message uniqueness** — never send identical messages to multiple matches. Each message must be unique and context-specific.
6. **No direct APIs** — never call platform private APIs or read auth tokens from browser storage.
7. **Read-before-send** — review the relevant visible conversation before drafting a reply, but only for the user-selected conversation being handled (or the audit run's current target).
8. **Extraction pacing** — full chat extraction via UI crawl must follow pacing rules in `chat-audit.md`: 3–6s between navigation, 2–4s between scrolls, 8–15s between conversations, checkpoint after each.
9. **Popup chain handling** — Tinder shows 7+ popup types in sequence after login/navigation. Dismiss each with Escape. If a popup cannot be dismissed, stop and notify the user.
10. **Photo cycling** — use SPACE key to cycle through profile photos (0.4s pause between) — this is how the keen-slider carousel works. More natural than clicking navigation arrows.

### Fingerprint reduction

1. Use keyboard shortcuts for swiping when available (more human-like than button clicks).
2. Vary the entry point (sometimes start from matches, sometimes from recs).
3. Don't always open the first match first. Vary traversal order.
4. Occasionally re-read a profile already seen.
5. Do not enumerate the whole account via API. Slow UI-only chat extraction with checkpointing is permitted under the audit-run clause — it looks like a human browsing their history.

## Block / CAPTCHA handling

### Detection

Stop immediately on any of:

- CAPTCHA challenge (reCAPTCHA, hCaptcha, puzzle).
- "Something went wrong" or error pages.
- Redirect to login page when already logged in.
- "Your account is under review" or similar restriction notice.
- Any 24-hour restriction, temporary ban, or account activity warning.
- Unusually fast rate limit (signals detection).
- Page content does not match expected structure.
- Element selectors fail repeatedly (may indicate DOM changes or block).
- Unexpected popup that does not match a known dismissal pattern (known popups: cookie consent, location permission, notification prompt, upgrade nags, match modal — all dismissible with Escape).

### Response protocol

1. **Stop all automation immediately.** Do not retry the action.
2. **Screenshot the block state.** Save to `.private-data/` for diagnosis.
3. **Notify the user** with: what triggered the stop, what the page shows, recommended next steps (usually: wait 24h, use platform manually).
4. **Log the incident** in `.private-data/outcome-log.md` with timestamp, platform, action attempted, and block type.
5. **Do not attempt to bypass** CAPTCHA or blocks. This is a hard stop.

### After a block

Three-tier escalation. Tier is set by the block type detected, not by count.

- **Tier 1 — soft signal** (CAPTCHA, "Something went wrong", unexpected popup, repeated selector failure): wait at least 24h, then resume only with manual, UI-only, one-action-at-a-time operation. If a second Tier-1 signal appears in the next session, escalate to Tier 2.
- **Tier 2 — explicit restriction** ("Your account is under review", 24-hour temporary ban, rate-limit lockout, account activity warning): do not automate that platform again unless the user explicitly re-enables it in a later session. Resumption starts with manual, UI-only operation.
- **Tier 3 — repeat or hard block** (any block after a Tier-2 reset, or permanent restriction): stop all automation on that platform and discuss with the user before any further action.

## Audit trail

### Required logging

Every automated action logs to `.private-data/outcome-log.md` per the action-log format in `state.md`:

```text
At: <iso8601>
Action: <swipe | message | navigate | read | extract>
Target: <match_id or selector>
Platform: <tinder | hinge | feeld>
Result: <success | blocked | captcha | auth>
Consent: <auto | approved | manual | session-audit>
Confidence: <HIGH | MEDIUM | LOW>
Predicted_watch: <Watch line if message; per state.md predictions>
Verdict: <confirmed | falsified | inconclusive — when a prior prediction was resolved this cycle>
Thread_stage: <from threads/<match_id>.json — for messages>
Note:
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

The funnel rates and verdicts are computed by reading `.private-data/threads/*.json` per `state.md` cross-thread queries. They are the primary feedback signal for whether rubric/voice changes are working; review them at the end of every session.

## Emergency stop

The user can say "stop" or "pause" at any time. The skill must:

1. Halt the current action immediately.
2. Not send any queued messages.
3. Log where it stopped.
4. Ask the user what they want to do next.

If the skill detects anything that could compromise the user's account or safety, it stops autonomously and notifies the user. This includes:

- Unexpected API responses.
- Account warning messages.
- Changes in account permissions or features.
- Messages from the platform about terms of service.
