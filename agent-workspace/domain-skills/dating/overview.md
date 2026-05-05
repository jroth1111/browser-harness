# Dating Platform Copilot — Overview

Automated dating pipeline that operates Tinder, Hinge, and Feeld on the user's behalf via browser-harness CDP automation. Conducts a structured interview to build a user model and rubric, then runs a pipeline from swiping through conversation to first-date coordination.

## Prerequisites

- User must be logged into the target platform in their running Chrome.
- The skill does not handle login credentials. If not logged in, ask the user to log in manually.
- `.private-data/user-model.md` must exist before any platform automation. If absent, run onboarding first.

## Cold-start sequence

1. Read `references/copilot-instructions.md` for AI personality, objectives, and quality standards, and `references/operating-model.md` for the core decision loop and live output formats.
2. Check for `.private-data/user-model.md`. If absent, run Stage 0 onboarding per `pipeline.md` (canonical option order: GDPR → deep research → UI crawl → manual paste, then always confirm via `onboarding.md` interview).
3. Identify platform (Tinder / Hinge / Feeld). Read `platforms/<platform>.md`.
4. Identify pipeline stage. Read `pipeline.md`.
5. Execute.

## Intent router

| User intent | Read first | When to escalate |
|---|---|---|
| First-time setup / build my profile | `onboarding.md` | Ask for clarification on unknown fields |
| Research me / build profile from my data | `references/research-user.md` | `onboarding.md` to confirm and fill gaps |
| Audit my existing chats | `chat-audit.md` | `references/research-user.md` for synthesis |
| Update my profile or preferences | `onboarding.md` + `.private-data/user-model.md` | `references/user-model.md` |
| Swipe session on a platform | `platforms/<platform>.md` → `references/scoring.md` | `references/decision-rubric.md` for edge cases |
| Review matches | `pipeline.md` Match Review | `references/profile-conversation-read.md` |
| Draft or send a message | `references/message-kernel.md` + `references/voiceprint.md` | `references/decision-rubric.md` for move selection |
| Check conversations / new messages | `pipeline.md` Conversation phase | `references/decision-rubric.md` for escalation |
| Propose a date | `references/templates.md` Date transition | `references/boundaries.md` if unsure |
| Report outcome / learning | `references/outcome-learning.md` | `references/user-model.md` for model updates |
| Safety concern, rate limit, block | `safety.md` | Stop and ask user |
| "What should I say?" | `references/message-kernel.md` → `references/examples.md` | `references/voiceprint.md` for calibration |
| "What is going on here?" | `references/profile-conversation-read.md` + `references/decision-rubric.md` | `references/context.md` for platform-specific tone |
| "Make this more [tone]" | `references/voiceprint.md` + `references/message-kernel.md` | — |

## Key invariants

- Never send a message without passing the user's configured consent gate.
- Never swipe without rubric scoring (unless user explicitly overrides).
- Human-like timing between all automated actions. See `safety.md`.
- Stop on any block, CAPTCHA, auth redirect, or suspicious page state.
- Never handle login credentials or modify account settings without explicit request.
- Log all automated actions in `.private-data/outcome-log.md`.

## File map

```
overview.md              ← you are here — navigation/routing contract
pipeline.md              ← stage definitions and state transitions (Stage 0–7)
onboarding.md            ← structured interview flow (always required to confirm)
chat-audit.md            ← three extraction paths: GDPR export, UI crawl, manual paste
safety.md                ← consent gates (canonical), rate limits, block handling, audit log
surface-map.json         ← machine-readable browser primitive contracts
platforms/
  tinder.md              ← Tinder selectors, swipe mechanics, gotchas (CONFIRMED)
  hinge.md               ← deferred (mobile-first, web feasibility unconfirmed)
  feeld.md               ← deferred (mobile-first, web feasibility unconfirmed)
references/              ← AI decision layer (17 files; see Stage→reference map below)
  copilot-instructions.md   ← identity, objective, output contract, mode routing
  operating-model.md        ← control stack, core loop, action taxonomy, live formats
  intake.md                 ← artifact discipline, long-context handling
  user-model.md             ← portable user model template + fast-start interview
  voiceprint.md             ← voice template + calibration + rewrite pass
  positioning.md            ← market identity: scarcity stack, screening diagnostic, felt-experience target
  research-user.md          ← deep research from digital footprint
  scoring.md                ← rubric scoring for profiles + conversations
  decision-rubric.md        ← move selection + operational escalation/dormancy thresholds
  profile-conversation-read.md  ← read dimensions, reciprocal investment ladder
  message-kernel.md         ← Hook+State+Reveal+Tension+Return; chemistry check
  examples.md               ← few-shot bad→better and gold examples
  templates.md              ← reusable output formats (send-first, calibrated, exit, ...)
  context.md                ← platform tone modifiers, location, event/community
  outcome-learning.md       ← outcome capture + closed-loop Watch verdict
  thread-state.md           ← per-thread JSON schema + read/write protocol (Stages 4–7)
  boundaries.md             ← quality boundary, redirect lane
evals/regression-prompts.md ← AI-layer regression checks
.private-data/             ← user-specific data (gitignored: user-model, voiceprint, outcome-log, extraction-state, threads/<match_id>.json)
```

## Stage → reference map

Each pipeline stage attaches to specific references. Read these in order during the stage.

| Pipeline stage | Primary references | Output format |
|---|---|---|
| 0. Onboarding | `references/user-model.md`, `references/voiceprint.md`, `references/positioning.md`, `references/research-user.md` | User model + voiceprint + positioning files |
| 1. Platform Connect | `safety.md` (login posture) | Logged-in confirmation |
| 2. Swiping | `references/scoring.md` → `references/decision-rubric.md` | LIKE / PASS / MAYBE + Read/Watch |
| 3. Match Review | `references/profile-conversation-read.md` → `references/scoring.md` | Ranked match list |
| 4. Opener | `references/intake.md` → `references/positioning.md` (felt-experience target + scarcity stack) → `references/message-kernel.md` → `references/voiceprint.md` → `references/examples.md` → `references/thread-state.md` (create) | Send / Read / Watch |
| 5. Conversation | `references/thread-state.md` (read) → `references/outcome-learning.md` (closed loop) → `references/profile-conversation-read.md` → `references/positioning.md` (screening diagnostic) → `references/decision-rubric.md` → `references/message-kernel.md` → `references/voiceprint.md` → `references/thread-state.md` (write) | Send / Read / Watch |
| 6. Escalation | `references/thread-state.md` (`escalation_readiness` gate) → `references/templates.md` (Date transition) → `references/boundaries.md` | Readiness / Invite / Why now / Fallback |
| 7. Date Coordination | `references/templates.md`, `references/voiceprint.md`, `references/thread-state.md` (lifecycle fields) | Logistics messages |
| Any stage — outcome reported | `references/outcome-learning.md` → `references/thread-state.md` (predictions / verdicts) → `references/user-model.md` (state consistency) | Update / Evidence / Confidence / Implication |

## Browser automation approach

This skill runs through the Claude/browser-harness conversation loop — no standalone scripts. The pattern:

1. Browser produces artifact (`capture_screenshot()`, `js()`)
2. Claude reads artifact (multimodal: screenshots + extracted text)
3. Claude consults knowledge base (rubric, user model, references)
4. Claude produces decision (`LIKE/PASS/MAYBE`, or `Send/Read/Watch`)
5. User consents (per configured level)
6. Claude issues browser command (`click_at_xy`, `type_text`)

Use `capture_screenshot()` + coordinate clicks as the primary interaction method, per harness conventions. Drop to DOM/selector work only when the target has no visible geometry.
