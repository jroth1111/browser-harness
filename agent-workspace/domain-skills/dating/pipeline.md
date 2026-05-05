# Pipeline Stages

Seven stages from onboarding to date coordination. Each stage specifies what the browser does, what the AI does, what decisions are made, and what triggers the next stage.

For the AI references that attach to each stage, see the **Stage → reference map** in `overview.md`.

## Stage 0: Onboarding

- **Trigger**: No `.private-data/user-model.md` exists, or user requests profile update.
- **Canonical option order** (offer top-down — highest signal-per-effort first):
  1. **GDPR export** — `chat-audit.md` Path 1 — user provides Tinder's data export JSON. Fastest path, richest data. Zero browser interaction.
  2. **Deep research** — `references/research-user.md` — scan user-approved digital footprint (social handles, writing samples) to pre-populate user model. No browser automation.
  3. **Full chat extraction** — `chat-audit.md` Path 2 — slow UI-only crawl of all conversations with checkpointing. Resumable across sessions. No API access or token reading.
  4. **Manual paste** — `chat-audit.md` Path 3 — user pastes specific conversations for selective analysis.
- **Always required after any prefilling path**: structured interview (`onboarding.md`) to confirm inferences, fill gaps, configure consent levels (consent levels cannot be inferred). Interview is the primary source of truth; other paths enrich and accelerate it.
- **Browser**: None for GDPR / research / manual paste / interview. Browser use for chat extraction is UI-only with checkpointing (see `chat-audit.md`).
- **AI**: Build user model and voiceprint using chosen method, then validate via interview.
- **Output**: `.private-data/user-model.md`, `.private-data/voiceprint.md`, `.private-data/outcome-log.md` (if chat extraction is used). Profile copy (filter line, green flags, not-for line) is generated as guidance only — the user pastes it into Tinder's profile editor manually. Bio editing is deliberately not automated; see `platforms/tinder.md` Out of scope.
- **Next**: User selects a platform and action.

## Stage 1: Platform Connect

- **Trigger**: User names a platform and wants to start.
- **Browser**: `new_tab(platform_url)` → `wait_for_content()` → verify logged in.
- **AI**: None (verification only).
- **Output**: Confirmed logged-in session on target platform.
- **Failure**: If not logged in, ask user to log in manually. Do not enter credentials.
- **Next**: Swiping Phase or Match Review depending on user intent.

## Stage 2: Swiping Phase

- **Trigger**: User wants to browse and swipe on profiles.
- **Loop** (per profile card):
  1. `capture_screenshot()` of current profile card.
  2. `js()` to extract profile text (name, age, bio, prompts, job, education, distance).
  3. Score profile against rubric (see `references/scoring.md`).
  4. Render decision:
     ```
     Decision: LIKE / PASS / MAYBE
     Score: [compatibility summary]
     Read: [one-line profile read]
     Watch: [what to look for if matched]
     ```
  5. If MAYBE: show to user for manual decision.
  6. If LIKE/PASS: execute swipe via `click_at_xy` on appropriate button.
  7. `wait(1.5 + random * 3.5)` — human-like timing.
  8. Check for match notification. If match: add to match queue.
  9. Repeat until: user says stop, hit rate limit, no more profiles, or session swipe limit reached.
- **Safety**: Stop when user says stop, or block/CAPTCHA detected. Vary timing. See `safety.md`.
- **Next**: Match Review.

## Stage 3: Match Review

- **Trigger**: Matches exist, user wants to review.
- **Browser**: Navigate to matches page and inspect only the visible, user-selected subset. Do not enumerate or export all matches.
- **AI**: For each match, apply `references/profile-conversation-read.md`.
- **AI**: Prioritize matches by compatibility score.
- **Output**: Ranked match list:
  ```
  1. [Name] — Fit: High — Read: [one-line] — Move: [recommended action]
  2. [Name] — Fit: Medium — ...
  ```
- **Next**: Opener Phase for selected matches.

## Stage 4: Opener Phase

- **Trigger**: User selects matches to message.
- **Per match**:
  1. Navigate to chat. Read their full profile via browser.
  2. Generate opener using `references/message-kernel.md` + `references/voiceprint.md`.
  3. Render:
     ```
     Send: [voice-matched opener]
     Read: [why this opener]
     Watch: [what response will reveal]
     ```
  4. **Hard consent gate** — openers always require explicit user approval regardless of the configured message consent level (`safety.md` Hard consent requirements). `auto-send` does not apply at this stage.
  5. Browser: `type_text(message)` → dispatch Enter or `click_at_xy(send_button)`.
  6. `wait(2 + random * 3)` — human-like timing.
  7. **Create thread state** at `.private-data/threads/<match_id>.json` per `references/thread-state.md`: `stage: "opening"`, append the opener as the first prediction with its `Watch:` line, set `last_user_message_at`.
  8. Log in `.private-data/outcome-log.md` (include `predicted_watch:` per `safety.md` audit format).
- **Next**: Conversation Phase.

## Stage 5: Conversation Phase

- **Trigger**: User wants to check conversations or monitor for new messages.
- **Hard consent gate**: opening any existing conversation requires explicit user confirmation per `safety.md` (overrides configured level). Never enumerate conversations on the user's behalf.
- **Browser**: Navigate to chat list. Inspect only user-selected or visibly unread conversations.
- **Per active conversation**:
  1. Navigate to conversation through the normal UI. Do not call platform APIs, read auth tokens, or download full history.
  2. **Read thread state** at `.private-data/threads/<match_id>.json` (per `references/thread-state.md`). If the file does not exist (first reply to an opener sent in a prior session), reconstruct it from outcome log + visible transcript.
  3. **Run closed loop** on the user's most recent prediction (per `references/outcome-learning.md` closed loop): classify their new reply against the prior `Watch:` line, append `verdict` to the prediction entry. If a cross-thread pattern emerges (≥3 falsified at same stage), surface for user confirmation before drafting.
  4. Apply `references/profile-conversation-read.md` to read the new exchange. Classify the latest received message on the reciprocal-investment ladder; append to `trajectory[]`. Also classify the active path (banter-first / depth-first / direct-sexual / compatibility-first / low-effort validation / fantasy trap) and the message category (invitation / test / bid / boundary / logistics window / noise) per `references/decision-rubric.md` Signal-responsive routing. Re-classify when the path shifts mid-thread.
  5. **Update `escalation_readiness`** counters in thread state per `references/decision-rubric.md` operational triggers, including `charge_level_reciprocated_max` from her latest reply per `references/message-kernel.md` Charge ladder and `references/profile-conversation-read.md` Charge mutuality. Re-evaluate `lead_tier` per `references/scoring.md` Lead tiers; record the dominant signal in `lead_tier_reason`. Tier downgrades (high → medium, medium → low) take effect immediately and feed into draft length and consent gating for the next message. After drafting the user's reply, set `charge_level_attempted_max` to the higher of its prior value and the level of the new draft.
  6. **Dormancy check**: if `last_their_message_at` falls in a dormancy band per `references/decision-rubric.md`, branch — wait, revive once (with required callback content), or mark `dead`. Skip drafting when waiting or dead.
  7. **Deprioritize check**: if any deprioritize trigger fires, set `deprioritized: true` and stop drafting on this thread; surface to user.
  8. Apply `references/decision-rubric.md` to choose move.
  9. Generate reply using `references/message-kernel.md` + `references/voiceprint.md`.
  10. Render:
      ```
      Send: [voice-matched reply]
      Read: [conversation read and stage]
      Watch: [what response will reveal]
      ```
  11. Pass consent gate.
  12. Browser: Send message.
  13. **Append the new prediction** (`message`, `watch`, `sent_at`) to thread state `predictions[]`; update `stage` and `last_user_message_at`.
  14. Update outcome log (include `predicted_watch:` and prior `verdict:` per `safety.md` audit format).
- **Next**: Escalation Phase when `escalation_readiness.ready === true`.

## Stage 6: Escalation Phase

- **Trigger**: `escalation_readiness.ready === true` in thread state per `references/decision-rubric.md` operational triggers (all five clauses satisfied). Qualitative "feels warm enough" is not sufficient — the gate is mechanical.
- **AI**: Uses date transition template from `references/templates.md`.
- **Output**:
  ```
  Readiness: [escalation_readiness summary — which clauses are met]
  Invite: [date proposal message]
  Why now: [specific evidence from trajectory + revelations]
  Fallback if hesitant: [backup plan]
  ```
- **Consent**: User must explicitly confirm any date proposal before sending (hard consent per `safety.md`).
- **Browser**: Send date proposal message.
- **Thread state**: set `stage: "date_proposed"`, `date_proposed_at` to send time, append the proposal as a prediction with its `Watch:` line.
- **Next**: Date Coordination.

## Stage 7: Date Coordination

- **Trigger**: Other person agreed to meet. Set `stage: "date_coordinating"`.
- **AI**: Handle logistics conversation (when, where, time, contact exchange, fallback).
- **Browser**: Send logistics messages (each subject to the configured message consent level).
- **On confirmation**: set `date_confirmed_at` in thread state.
- **After the date**: user reports `date_outcome` (`good_meet` / `mismatch` / `no_show` / `cancelled` / `pending_second`); update thread state and feed into `references/outcome-learning.md`.
- **Output**: Confirmed date details logged in outcome log; thread state reflects the lifecycle terminal stage until either re-engagement or `dead`.

## State transitions

```
Onboarding → Platform Connect → [Swiping | Match Review]
Swiping → Match Review → Opener → Conversation → Escalation → Date Coordination
```

Any stage can return to Onboarding if the user requests preference changes.
Any stage can stop if safety protocols trigger (see `safety.md`).
