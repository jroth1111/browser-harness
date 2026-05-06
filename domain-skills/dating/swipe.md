# Swipe — Profile Read, Score, Decision

Use when the user is browsing a dating platform and wants to swipe. Replaces the Stage 2 swiping pipeline + scoring + decision rubric for profiles.

Reads: this file + `platforms/<platform>.md` (selectors) + `surface-map.json` (primitives) + `.private-data/user-model.md` (rubric inputs).
Writes: `.private-data/outcome-log.md` (action log per swipe).

## Output contract

```text
Decision: LIKE / PASS / MAYBE
Score: [compatibility summary — one line]
Read: [one-line profile read]
Watch: [what to look for if matched]
```

For MAYBE or LOW-confidence cases, escalate to the **Profile / chat read** format from `overview.md`:

```text
Read:
Fit:
Move:
Why:
Watch:
```

## Per-card loop

1. `capture_screenshot()` of the current profile card.
2. `js()` to extract profile text — name, age, bio, prompts, job, education, distance.
3. Run **Read dimensions** (below).
4. Run **Score** (below).
5. Render decision in the contract above.
6. Consent gate per `safety.md`:
   - configured swipe level `manual` / `approve-non-obvious` / `full-auto` / `auto-threshold`;
   - hard consent for any LOW-confidence action (<50%);
   - hard consent if user-set `auto-threshold` is exceeded.
7. If MAYBE: show to user for manual decision.
8. If LIKE/PASS: execute swipe via `click_at_xy` on the appropriate button (selectors in `platforms/<platform>.md`).
9. `wait(1.5 + random * 3.5)` — human-like timing per `safety.md`.
10. Check for match notification. If match: append to match queue with `Read:` and `Watch:` lines.
11. Append action to `.private-data/outcome-log.md`.
12. Loop until: user says stop, rate limit hit, no more profiles, or session swipe limit reached.

Stop on any block, CAPTCHA, auth redirect, or unexpected popup state. See `safety.md`.

## Read dimensions

Assess only what the artifact supports — never invent signal. Score each LOW / MEDIUM / HIGH / UNCLEAR:

- attraction / chemistry potential — photos (visual), described interests, energy;
- relationship / intent fit — bio clues, prompts, profile structure;
- communication quality — prompt answers, bio writing quality;
- values and lifestyle signals — bio text, prompts, photo context;
- availability and practical fit — location, distance, stated availability;
- relationship-structure compatibility (when relevant) — explicit mentions or implied structure;
- real-person / real-intent quality — profile completeness, photo quality, specificity;
- fit with the User Model — match against the user's stated preferences;
- risk of false chemistry / overinvestment — attractive-but-unsuitable patterns.

UNCLEAR carries neutral weight. Do not promote UNCLEAR to MEDIUM to round up a decision.

### Profile-text signal

**Bio text**: specific self-expression vs generic clichés; values and lifestyle clues (ambition, creativity, social habits); relationship-style clues (explicit or implied structure); humour, intelligence, emotional range.

**Prompts**: effort level (detailed vs one-word); personality dimensions (playful, serious, thoughtful, adventurous); compatibility signals (shared interests, complementary traits); communication style preview.

**Photo choices**: activity diversity (active, social, creative, domestic); self-presentation style (curated, casual, artistic); social context (friends, solo, pets, travel); confidence and authenticity indicators.

**Absence**: empty bio = low effort or privacy-focused; no prompts = lower engagement; sparse profile = could be new, inactive, or bot.

## Score

### Step 1 — Hard dealbreaker check

Scan profile against the hard dealbreakers from `user-model.md`. If any match → **Instant PASS**. No further scoring.

### Step 2 — Green flag check

Scan for multiple strong green flags from `user-model.md`. If present → **Fast-track LIKE** with high confidence. Brief scoring only.

### Step 3 — Dimension scoring

For profiles that pass dealbreaker check but lack strong green flags, score each Read dimension LOW / MEDIUM / HIGH / UNCLEAR.

### Step 4 — Composite decision

- **LIKE** — dealbreaker-free AND majority of scored dimensions are MEDIUM+.
- **PASS** — any dimension scores LOW on a strong preference, OR majority scored dimensions are LOW.
- **MAYBE** — one strong signal but one unclear dimension. Show to user.

### Confidence calibration

- **HIGH** — multiple converging signals across dimensions; clear match or clear mismatch.
- **MEDIUM** — enough signal for a decision; some uncertainty. Most common.
- **LOW** — sparse evidence. Lean PASS unless one very strong signal. Consider showing to user.

### Score output (verbose form, when the user asks)

```text
Profile: [name, age, location]
Compatibility: [HIGH/MEDIUM/LOW]
Attraction: [HIGH/MEDIUM/LOW/UNCLEAR]
Intent fit: [HIGH/MEDIUM/LOW/UNCLEAR]
Communication: [HIGH/MEDIUM/LOW/UNCLEAR]
Real-person: [HIGH/MEDIUM/LOW]
Dealbreakers: [none / listed]
Decision: [LIKE/PASS/MAYBE]
Confidence: [HIGH/MEDIUM/LOW]
Read: [one-line profile read]
Watch: [what to look for if matched]
```

## False-chemistry checks at swipe time

Before LIKE on a high-attraction profile, scan for false-chemistry patterns:

- attractive-but-unsuitable signals (status sparkle without values fit, charged photos with no compatibility data);
- visible mismatch the user is rationalising;
- repeated pattern from `user-model.md` "Attractive but unsuitable patterns";
- profile that is essentially fantasy fuel — no logistical / lifestyle / values evidence.

If false-chemistry risk is HIGH → downgrade to MAYBE and show to the user with the flag named.

## Match handling

When a swipe produces a match, do NOT immediately open Stage 4 (Opener). Append to a match queue with the swipe-time `Read:` and `Watch:` lines. The user explicitly requests an opener pass when ready — that is a separate consent boundary (the opener itself is hard-consent per `safety.md`).

If the user wants a quick read of the new match queue, use the **Match Review** format:

```text
1. [Name] — Fit: [HIGH/MED/LOW] — Read: [one-line] — Move: [recommended action]
2. [Name] — Fit: [HIGH/MED/LOW] — ...
```

Inspect only the visible, user-selected subset. Do not enumerate or export all matches.

## Pacing and safety

| Action | Delay range | Notes |
|---|---|---|
| Between swipes | 1.5–5s | Uniform random |
| After every 10 swipes | 30–60s | Break |
| After every 100 swipes | Stop | Session cap; resume in a new session |

Stop immediately on: CAPTCHA, account restriction, auth redirect, suspicious page state, unexpected modal that does not match a known dismissal pattern. Screenshot, log, ask the user.

Never override rubric scoring without explicit per-card user request. The hard rule is: never swipe without a rubric pass (or an explicit per-card override).

## Cold-start checklist for a swipe session

1. Confirm `.private-data/user-model.md` exists. If not → run `onboard.md`.
2. Read this file + `platforms/<platform>.md` + `surface-map.json`.
3. Verify logged-in session on the platform.
4. Confirm consent levels with the user (one-line confirmation of swipe-level token from `user-model.md`).
5. Begin per-card loop.
