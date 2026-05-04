# Pipeline Stages

Seven stages from onboarding to date coordination. Each stage specifies what the browser does, what the AI does, what decisions are made, and what triggers the next stage.

## Stage 0: Onboarding

- **Trigger**: No `.private-data/user-model.md` exists, or user requests profile update.
- **Options** (offer in this order):
  1. **Manual interview** — `onboarding.md` — structured Q&A. Safest primary source.
  2. **GDPR export** — `chat-audit.md` Path 1 — user provides Tinder's data export JSON. Fastest path, richest data. Zero browser interaction.
  3. **Full chat extraction** — `chat-audit.md` Path 2 — slow UI-only crawl of all conversations with checkpointing. Resumable across sessions. No API access or token reading.
  4. **Deep research** — `references/research-user.md` — scan user-approved digital footprint to pre-populate user model.
- **Browser**: None for manual interview or GDPR export. Browser use for chat extraction is UI-only with checkpointing (see `chat-audit.md`).
- **AI**: Build user model and voiceprint using chosen method.
- **Output**: `.private-data/user-model.md`, `.private-data/voiceprint.md`, `.private-data/outcome-log.md` (if chat extraction is used).
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
- **Safety**: Stop after session swipe limit (default 80). Vary timing. See `safety.md`.
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
  4. Pass consent gate (show to user, or auto-send if configured).
  5. Browser: `type_text(message)` → dispatch Enter or `click_at_xy(send_button)`.
  6. `wait(2 + random * 3)` — human-like timing.
  7. Log in `.private-data/outcome-log.md`.
- **Next**: Conversation Phase.

## Stage 5: Conversation Phase

- **Trigger**: User wants to check conversations or monitor for new messages.
- **Browser**: Navigate to chat list. Inspect only user-selected or visibly unread conversations.
- **Per active conversation** (maximum 3 per session unless user explicitly raises to 5):
  1. Navigate to conversation through the normal UI. Do not call platform APIs, read auth tokens, or download full history.
  2. Apply `references/profile-conversation-read.md` to read the conversation.
  3. Classify stage (opening, early rally, banter, compatibility discovery, etc.).
  4. Apply `references/decision-rubric.md` to choose move.
  5. Generate reply using `references/message-kernel.md` + `references/voiceprint.md`.
  6. Render:
     ```
     Send: [voice-matched reply]
     Read: [conversation read and stage]
     Watch: [what response will reveal]
     ```
  7. Pass consent gate.
  8. Browser: Send message.
  9. Update outcome log.
- **Next**: Escalation Phase when conditions met.

## Stage 6: Escalation Phase

- **Trigger**: AI detects sufficient warmth, reciprocity, and logistical plausibility.
- **AI**: Uses date transition template from `references/templates.md`.
- **Output**:
  ```
  Readiness: [assessment]
  Invite: [date proposal message]
  Why now: [evidence]
  Fallback if hesitant: [backup plan]
  ```
- **Consent**: User must explicitly confirm any date proposal before sending.
- **Browser**: Send date proposal message.
- **Next**: Date Coordination.

## Stage 7: Date Coordination

- **Trigger**: Other person agreed to meet.
- **AI**: Handle logistics conversation (when, where).
- **Browser**: Send logistics messages.
- **Output**: Confirmed date details logged in outcome log.

## State transitions

```
Onboarding → Platform Connect → [Swiping | Match Review]
Swiping → Match Review → Opener → Conversation → Escalation → Date Coordination
```

Any stage can return to Onboarding if the user requests preference changes.
Any stage can stop if safety protocols trigger (see `safety.md`).
