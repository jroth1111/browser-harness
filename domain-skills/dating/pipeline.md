# Pipeline Stages

Seven stages from onboarding to date coordination. Each stage specifies what the browser does, what the AI does, what decisions are made, and what triggers the next stage.

## Stage 0: Onboarding

- **Trigger**: No `.private-data/user-model.md` exists, or user requests profile update.
- **Options** (offer in this order):
  1. **Chat audit shortcut** — `chat-audit.md` — extract voiceprint and outcomes from existing Tinder/Hinge/Feeld conversations. Richest signal source.
  2. **Deep research** — `references/research-user.md` — scan digital footprint to pre-populate user model.
  3. **Manual interview** — `onboarding.md` — structured Q&A. Use as fallback or to fill gaps after options 1-2.
- **Browser**: None for manual interview. Required for chat audit (read-only extraction).
- **AI**: Build user model and voiceprint using chosen method.
- **Output**: `.private-data/user-model.md`, `.private-data/voiceprint.md`, `.private-data/outcome-log.md` (if chat audit).
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
- **Browser**: Navigate to matches page. `js()` to extract match list.
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
- **Browser**: Navigate to chat list. `js()` to detect unread messages.
- **Per active conversation**:
  1. Navigate to conversation. `js()` to extract full message thread.
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
