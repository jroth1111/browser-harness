# Dating Platform Copilot — Overview

Automated dating pipeline that operates Tinder, Hinge, and Feeld on the user's behalf via browser-harness CDP automation. Conducts a structured interview to build a user model and rubric, then runs a pipeline from swiping through conversation to first-date coordination.

## Prerequisites

- User must be logged into the target platform in their running Chrome.
- The skill does not handle login credentials. If not logged in, ask the user to log in manually.
- `.private-data/user-model.md` must exist before any platform automation. If absent, run onboarding first.

## Cold-start sequence

1. Read `references/copilot-instructions.md` for AI personality, objectives, and quality standards.
2. Check for `.private-data/user-model.md`. If absent, offer shortcuts in order: GDPR export (`chat-audit.md` Path 1, fastest), browser chat extraction (`chat-audit.md` Path 2), deep research (`references/research-user.md`), or manual interview (`onboarding.md`).
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
overview.md              ← you are here
pipeline.md              ← stage definitions and state transitions
onboarding.md            ← user interview flow
chat-audit.md            ← extract voiceprint + outcomes (GDPR export, browser crawl, or manual paste)
safety.md                ← consent gates, rate limits, anti-detection
surface-map.json         ← machine-readable primitive contracts
platforms/tinder.md      ← Tinder-specific selectors and flows
platforms/hinge.md       ← Hinge-specific selectors and flows (deferred)
platforms/feeld.md       ← Feeld-specific selectors and flows (deferred)
references/copilot-instructions.md  ← AI personality, objectives, quality contract
references/scoring.md    ← rubric scoring for profiles and conversations
references/research-user.md        ← deep research prompt for user profiling
references/              ← 15 copilot reference files for AI decision layer
evals/                   ← regression prompts for behavior testing
.private-data/           ← user-specific data (gitignored)
```

## Browser automation approach

This skill runs through the Claude/browser-harness conversation loop — no standalone scripts. The pattern:

1. Browser produces artifact (`capture_screenshot()`, `js()`)
2. Claude reads artifact (multimodal: screenshots + extracted text)
3. Claude consults knowledge base (rubric, user model, references)
4. Claude produces decision (`LIKE/PASS/MAYBE`, or `Send/Read/Watch`)
5. User consents (per configured level)
6. Claude issues browser command (`click_at_xy`, `type_text`)

Use `capture_screenshot()` + coordinate clicks as the primary interaction method, per harness conventions. Drop to DOM/selector work only when the target has no visible geometry.
