# Escalate — Conversion Move and Date Coordination

Use when a thread has earned a date proposal, or when the other person has agreed to meet and logistics need to be handled. Replaces Stage 6 (Escalation Phase) and Stage 7 (Date Coordination) of the old pipeline.

Reads: this file + `.private-data/threads/<match_id>.json` (thread state, schema in `state.md`) + `.private-data/voiceprint.md` + `.private-data/positioning.md`.
Writes: thread state (`stage`, `date_proposed_at`, `date_confirmed_at`, `date_outcome`, `predictions[]`), `.private-data/outcome-log.md`.

If the thread state file does not yet exist or `escalation_readiness.ready` is not present, the conversation has not been driven through `reply.md` long enough to escalate — run `reply.md` for at least one cycle first to populate the gate counters.

## Output contract

```text
Readiness: [which escalation_readiness clauses are met — one line each]
Invite: [voice-matched date proposal]
Why now: [specific evidence from trajectory + revelations]
Fallback: [backup move if response is hesitant]
```

## Hard consent

Any date proposal is a hard-consent action per `safety.md` — overrides any configured `auto-send` level. The user explicitly confirms the exact invite text before it is sent.

## Readiness gate

Restate from `reply.md` so escalate.md can be read alone. Set `escalation_readiness.ready === true` only when **all** of:

- `consecutive_increasing_or_matching ≥ 3` across the most recent 4 trajectory entries;
- `logistical_signal_seen === true` — at least one location/availability/schedule reference from her;
- `real_revelation_user === true` AND `real_revelation_them === true`;
- `charge_attempted === true` AND `charge_landed === true`;
- `charge_level_reciprocated_max ≥ 4` — she has reciprocated at the personal-reveal level or higher;
- confidence on the conversation read is at least MEDIUM.

If any clause is false → do **not** escalate. Return to `reply.md`: continue, add charge, or clarify per the move rules. Qualitative "feels warm enough" is not sufficient — the gate is mechanical.

## The conversion move

Direct, low-pressure, brief. Names what is being proposed (drink, walk, coffee, specific time window), references what makes the move earned (rhythm, signal, the specific thing you are continuing), invites a yes/no choice without auditioning.

### Working invite forms (register, not boilerplate)

- *"I like the rhythm here. Want to test the chemistry over a drink this week?"*
- *"This has enough signal that I'd rather not leave it trapped in app limbo. Want to continue it over a drink?"*
- *"I'm enjoying this enough that the app is starting to feel like the least interesting place for it. Drink this week?"*
- *"You're more interesting than this format allows. Walk and a coffee on the weekend?"*

Calibrate the verb — drink, walk, coffee, dinner — to her stated availability and to the platform/region tone.

### Anti-forms — rewrite before sending

| Anti-form | Failure mode |
|---|---|
| *"if you'd maybe possibly be interested at some point"* | Hedged. Reads as low investment in own move. |
| *"I would love to take you out if you'd be willing"* | Auditioning. Performs investment instead of inviting. |
| *"we should hang out sometime"* | Vague. No yes/no surface; no commitment to choose. |
| *"would you ever want to grab a drink?"* | Hypothetical. Removes the actual ask. |
| *"sorry to be forward but..."* | Apology frames the move as transgression. The thread earned the move; do not undo it. |
| *"so when am I taking you out?"* | Presumption without invitation. Skips the choice. |

### Why-now line (internal only — not sent)

Before drafting, write a one-line `Why now:` capturing the specific evidence from the trajectory: which revelation, which logistical signal, which reciprocated charge level. If you cannot name two specific moments, the thread is not yet ready — re-check the readiness gate.

## Per-message protocol — proposal

1. Read `threads/<match_id>.json`. Confirm `escalation_readiness.ready === true`. If not, exit to `reply.md`.
2. Read the most recent 4 trajectory entries and the last reciprocated charge level. The invite tone should match (or sit one level below) the working register the thread is already in.
3. Draft the invite. Single message. No preamble. No multi-message setup.
4. Render the output contract (Readiness / Invite / Why now / Fallback).
5. **Hard consent gate** — show the user the exact text. Wait for explicit approval.
6. On approval, send via the platform (per `platforms/<platform>.md` selectors). Use natural pacing per `safety.md` (2–5s typing, then send).
7. Update thread state:
   - `stage: "date_proposed"`;
   - `date_proposed_at: <iso8601>`;
   - append the proposal to `predictions[]` with the `Watch:` line (e.g., *"Whether she names a day, deflects with a question, hedges, or goes quiet."*);
   - update `last_user_message_at`.
8. Append to `outcome-log.md` per the action-log format (`predicted_watch:` populated).

## Reading her response

Classify the reply on the trajectory ladder. Five labels:

- **increasing** — she added length, a new question, a logistical specific, or a charge step beyond your invite. She is investing more than the invite required.
- **matching** — she met the invite at its register: agreed, gave a day or place, asked one calibrated question.
- **maintaining** — polite but flat. Agreed without specifics, low-token reply, no question, no logistics.
- **decreasing** — shorter, hedged, vague-without-specificity, deflective, or topic-changing.
- **draining** — dismissive, contemptuous, or disrespectful.

Branch on the dominant signal.

| Response shape | Read | Move |
|---|---|---|
| Yes + names a day or asks for one | matching/increasing | Proceed to logistics. Stage → `date_coordinating`. |
| Yes + warm follow-up question | increasing | Proceed to logistics; carry the warmth into the day pick. |
| Yes but vague ("sounds good", "maybe sometime") | maintaining-flat | One concrete day pick from the user. If she still flattens → treat as soft no; deprioritise. |
| Hedged ("busy this week, maybe later") with specificity ("but next Thursday could work") | matching | Take the specificity; agree the time. |
| Hedged with no specificity | decreasing | Drop the ask. Return to `reply.md` for one calibrated reply. If next exchange is not increasing → deprioritise. |
| Counter-proposal (different activity, different time) | matching/increasing | Accept gracefully if it fits; otherwise propose one alternative. |
| No / clean decline | exit signal | Acknowledge briefly and stop. No re-pitch. Mark thread `deprioritized` with reason. |
| Disrespect or contempt | exit signal | Use the clean-exit template from `reply.md`. Mark `dead`. |
| No response 48h+ | dormancy | Apply dormancy band per `reply.md`. One revive permitted only if budget remains. |

**Do not re-pitch a date proposal in the same week.** A second ask after a soft no inside the same thread reads as pressure and confirms the no.

## Date coordination

Triggered when she agrees to meet. Set `stage: "date_coordinating"` in thread state.

### What the AI handles

- **Day pick** — propose two day options, not three+. Two reads as decisive; three+ reads as availability anxiety.
- **Time pick** — name a time window ("around 7" / "7–8") rather than asking what works for her.
- **Place pick** — name one specific venue you actually like, with a one-line reason ("[Bar] on [Street] — quiet enough to talk, walkable to other places after"). If she has a preferred area, default to it.
- **Contact exchange** — number swap once date and place are set. Single line: *"What's your number? Easier than the app for the day-of."* Do not move to a different chat platform mid-coordination unless she initiates.
- **Fallback** — if the picked day breaks (her side or yours), have one alternative day ready. Do not let logistics drift into a multi-day negotiation.

### Send shape during coordination

Each logistics message follows the message consent level (`approve` by default). The hard-consent gate is for the *initial* date proposal; once she has agreed, day/time/place/contact-exchange messages run on the configured level.

```text
Send: [next logistics message]
Read: [where coordination stands]
Watch: [what her response will reveal — confirmation / preference / drift]
```

### When she goes quiet during coordination

24–48h silence after a logistics message before the date is locked is a soft drift signal. One short, warm nudge that names the day:

- *"You good for Thursday? Want to lock the spot or pick a different day?"*

If silent another 48h after the nudge → treat as cancelled-by-drift. Do not chase. Mark `deprioritized` with reason `coordination_drift`. The date does not happen.

### Confirmation

When day/time/place/contact are settled:

- Set `date_confirmed_at: <iso8601>` in thread state;
- Append a confirmation prediction with `Watch:` capturing what the date itself will reveal (chemistry hypothesis, single specific thing to look for);
- Optional: send one short pre-date confirmation 4–8h before the time ("still good for 7?"). Reads as competent, not anxious. Skip if she has already confirmed in the prior 24h.

## Fallback if hesitant

When the readiness gate is borderline (5 of 6 clauses; or `charge_level_reciprocated_max === 3`) and the user wants to push anyway, the move is not the date proposal — it is **one more charge step + a logistical surface**. The conversion move stays held until the gate closes.

Working forms for the surface step (Level 3–4 charge with availability bait):

- *"There's a [specific thing] this Saturday I'm half tempted to drag the right person to."*
- *"I'm at [neighbourhood] most weekends — when you're around there, you'd like [specific spot]."*

Then read her response on the same trajectory ladder. If she names her availability or counter-bids the spot → the gate has closed; move to the proposal. If she stays general → hold; do not force the date.

## After the date

User reports `date_outcome` per `state.md`:

| Outcome | Meaning | Next |
|---|---|---|
| `good_meet` | Chemistry confirmed; both want a second | Continue thread; stage → next round of `reply.md` toward second-date escalation. |
| `mismatch` | Met, no chemistry / no second date | Mark `dead`. Brief outcome-log entry on what the chat predicted vs the meet. |
| `no_show` | She did not show or cancelled at the door | Mark `dead`. Audit the predictions on the proposal — what was missed. |
| `cancelled` | Cancelled before the date with notice | If reschedules → return to `date_coordinating`. If does not reschedule within 7d → mark `dead`. |
| `pending_second` | Meet went well; second-date proposal in flight | Same thread continues; do not re-run the readiness gate from zero — escalation is now warm-restart. |

Always feed the meet vs the chat-prediction back into `outcome-log.md` per the closed-loop format. The chat read either confirmed or falsified — that is the strongest signal the rubric ever gets.

## Cold-start checklist

1. Confirm thread state file exists at `.private-data/threads/<match_id>.json`. If not (first session resuming an existing thread), reconstruct from outcome log + visible chat per `reply.md`.
2. Re-evaluate the readiness gate. Do not trust a stale `ready: true` from a previous session if her last reply has not been classified this cycle.
3. If ready: draft the invite, render the output contract, hard-consent gate, send, update state.
4. If not ready: do not escalate. Return to `reply.md`.
