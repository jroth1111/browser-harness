# State Schemas — `.private-data/`

All user-specific state lives under `.private-data/` (gitignored). This file is the schema reference. Action files (`onboard.md`, `swipe.md`, `reply.md`, `escalate.md`, `chat-audit.md`) read and write these artifacts; this file defines their shape.

## Layout

```
.private-data/
  user-model.md              ← who the user is, who they want, what they reject
  voiceprint.md              ← how the user sounds; charge ceiling
  positioning.md             ← market identity, scarcity stack, felt-experience target
  outcome-log.md             ← cross-thread learnings; what landed, what missed
  extraction-state.json      ← chat-audit checkpoint (Path 2 progress)
  threads/
    <match_id>.json          ← per-thread state, predictions, escalation readiness
```

`onboard.md` produces user-model + voiceprint + positioning. `chat-audit.md` writes extraction-state and seeds outcome-log. `reply.md` reads/writes thread state and appends to outcome-log via the closed loop.

---

## `user-model.md`

```text
User Model

1. Identity and orientation fields
- Pronouns/gender:
- Sexuality/orientation:
- Relationship orientation/style:
- Current relationship structure/status:
- Target partner gender(s)/people:
- Location/practical radius:
- Disclosure needs:

2. Dating objective
- Current goal:
- Definition of seriousness:
- Desired pace:
- Desired relationship structures:
- Openness / limits around partnered people, hierarchy, nesting, metamours, exclusivity, or other structures:

3. Desired partner traits
- Emotional traits:
- Lifestyle/ambition traits:
- Intellectual/creative/professional traits:
- Values:
- Must-have signals:
- Signals that matter only with context:

4. Attraction and pattern map
- What reliably attracts the user:
- What has historically worked:
- What has historically failed:
- What the user overvalues early:
- What the user undervalues early:
- Attractive but unsuitable patterns:
- Known blind spots:

5. Flirt and communication preferences
- Desired tone:
- Edge level:
- Teasing comfort:
- Directness comfort:
- Vulnerability comfort:
- Message length:
- Humour style:

6. Green / yellow / red flags
- Green:
- Yellow:
- Red:
- Hard dealbreakers:
- Soft dealbreakers:

7. Open questions
- Unknown fields:
- Hypotheses to test:
- Calibration questions:

8. Profile copy (polarising filter)
- Filter line:
- Green flags:
- Not-for line:
```

**No default identity assumptions.** Every field is configurable. Use only supplied facts, artifact evidence, or clearly labelled provisional inference.

**State consistency rule.** A user correction is a state update, not a one-off comment. A voice correction may affect Voiceprint, flirt intensity, overhit risk, preferred examples, future draft style. A relationship-goal correction may affect target signals, pacing, challenge handling, exit criteria. Update all affected fields.

---

## `voiceprint.md`

```text
User Voiceprint

Sentence rhythm:
Typical length:
Directness:
Warmth:
Edge:
Humour:
Flirt style:
Question style:
Emoji/punctuation:
Words/phrases that sound natural:
Words/phrases to avoid:
Too much:
Too little:
Example messages that feel like the user:
Example messages that do not feel like the user:

Erotic charge calibration:
- Charge ceiling (max ladder level the user is comfortable sending; see reply.md Charge ladder):
- Comfort with embodied implication (Level 6: physical real-world possibility):
- Comfort with vulnerability-as-charge (small/specific/owned reveals):
- Restraint vs explicitness preference:
- Sexual vocabulary the user uses (and avoids):
- Charge moves that feel native:
- Charge moves that feel forced or off-voice:
```

**Frame stance.** The voice should communicate, without ever stating it: has taste, has standards, is warm, is playful, is not needy, rewards good energy, does not rescue bad energy. Implicit frame: filter, not applicant.

**Polarisation is the goal.** A draft the right person will love and the wrong person will find too direct, too specific, or too playful is working as intended. Drafts that try to be liked by everyone produce no signal.

---

## `positioning.md`

```text
User Positioning

Core statement (one sentence, in the user's voice):

Scarcity stack — how each shows up for this user:
- Erotic intelligence:
- Selective warmth:
- Low-chaos directness (and ENM/poly framing if relevant):
- A felt life:
- Good logistics:

Profile copy alignment:
- Filter line:
- Green flags:
- Not-for line:

Felt-experience target (what the right woman should feel after three exchanges):

Anti-positioning (what the user must not lean on, even if it sometimes works for others):
```

**Default positioning statement** (override per user during onboarding):

> Erotic charge without chaos. Depth without heaviness. Directness without pressure. Standards without bitterness.

The five scarcity-stack levers — erotic intelligence, selective warmth, low-chaos directness, a felt life, good logistics — are the levers `reply.md` checks when a thread is warm but stalling. None alone is positioning; the combination is.

---

## `threads/<match_id>.json`

One file per match. Created by `reply.md` on first opener; updated every cycle.

```json
{
  "match_id": "abc123",
  "name": "Ale",
  "platform": "tinder",
  "first_contact_at": "2026-05-01T10:00:00Z",
  "last_user_message_at": "2026-05-04T14:00:00Z",
  "last_their_message_at": "2026-05-04T15:30:00Z",
  "exchange_count": 8,
  "stage": "compatibility_discovery",
  "trajectory": [
    { "at": "2026-05-04T15:30:00Z", "from": "them", "investment": "increasing", "note": "asked back, added detail" }
  ],
  "escalation_readiness": {
    "consecutive_increasing_or_matching": 3,
    "logistical_signal_seen": true,
    "real_revelation_user": true,
    "real_revelation_them": true,
    "charge_attempted": true,
    "charge_landed": true,
    "charge_level_attempted_max": 5,
    "charge_level_reciprocated_max": 4,
    "ready": true
  },
  "predictions": [
    {
      "sent_at": "2026-05-04T13:55:00Z",
      "message": "I like the way your mind moves...",
      "watch": "Whether they riff back or flatten the energy.",
      "verdict": "confirmed",
      "evidence": "Riffed back with a specific tease.",
      "verdict_at": "2026-05-04T15:30:00Z"
    }
  ],
  "false_chemistry_flags": [],
  "revival_state": { "revived_once": false, "last_revive_at": null, "callback_used": null },
  "deprioritized": false,
  "deprioritized_reason": null,
  "lead_tier": "high",
  "lead_tier_reason": "asks back, reveals specifics, plays back, charge landed",
  "date_proposed_at": null,
  "date_confirmed_at": null,
  "date_outcome": null
}
```

### Field semantics

| Field | Type | Notes |
|---|---|---|
| `stage` | enum | `opening` / `early_rally` / `banter` / `compatibility_discovery` / `flirty_escalation` / `escalation_ready` / `date_proposed` / `date_coordinating` / `stalled` / `revived` / `dead` |
| `trajectory[]` | array | Each received message classified per the reciprocal-investment ladder (`reply.md`). Append-only. Keep last 10. |
| `escalation_readiness` | object | Updated every cycle in Stage 5. Booleans `charge_attempted` / `charge_landed` are derived: `charge_attempted := charge_level_attempted_max ≥ 2`; `charge_landed := charge_level_reciprocated_max ≥ 2`. |
| `predictions[]` | array | Watch-line predictions; verdict written by closed loop. Append-only. |
| `false_chemistry_flags[]` | array | `{at, type, evidence}` per `reply.md` false-chemistry checks. |
| `revival_state` | object | One-revive-per-thread budget. |
| `deprioritized` | bool | Set by deprioritise triggers; pipeline skips deprioritized threads unless user explicitly reopens. |
| `lead_tier` | enum | `high` / `medium` / `low` / `false-positive`. Default `medium` after first reply; updated each cycle. Drives investment level and message length. |

### Stage transitions

```
opening → early_rally (≥2 exchanges, both sides engaging)
early_rally → banter (humor/play landing)
banter → compatibility_discovery (real revelations from each side)
compatibility_discovery → flirty_escalation (charge attempted and reciprocated)
flirty_escalation → escalation_ready (escalation_readiness.ready === true)
escalation_ready → date_proposed (escalate.md sends)
date_proposed → date_coordinating (they accept)
any → stalled (dormancy thresholds)
stalled → revived (one revive sent) → either re-enters prior stage or → dead
any → dead (deprioritized OR exit OR 30d+ silent)
```

### Read/write protocol per action file

| Action | Read | Write |
|---|---|---|
| `reply.md` opener | nothing (file may not exist yet) | create file with `stage: "opening"`, append first prediction |
| `reply.md` mid-conversation | full file | classify trajectory, run closed loop on prior prediction, update `escalation_readiness` (incl. `charge_level_reciprocated_max` from her latest reply), re-evaluate `lead_tier`, update stage, append new prediction when user sends reply |
| `reply.md` dormancy check | full file | apply dormancy policy; set `stage: "stalled"` or trigger revive; update `revival_state` |
| `escalate.md` | full file | gate on `escalation_readiness.ready === true`; on send, set `date_proposed_at` |
| Date coordination (in `escalate.md`) | full file | set `date_confirmed_at` on confirmation; user reports outcome → `date_outcome` |

---

## `outcome-log.md`

Append-only cross-thread learning log. Each entry uses one of three formats.

### Outcome capture (user-reported)

```text
Artifact:
Message/action sent:
Response/outcome:
What landed:
What missed:
Signal quality:
Update to User Model:
Update to Voiceprint:
Update to decision rules:
Next experiment:
```

### Closed-loop verdict (auto, every cycle when a reply arrives)

```text
Predicted: [Watch line from prior message]
Observed: [one-phrase summary of their reply]
Verdict: confirmed | falsified | inconclusive
Cross-thread pattern: [none | N similar verdicts; falsified ≥3 → flag]
Update suggested: [if cross-thread pattern; otherwise none]
```

### Action log (every automated browser action)

```text
At: <iso8601>
Action: <swipe/click/type/extract>
Target: <match_id or selector>
Platform: <tinder/hinge/feeld>
Result: <success/blocked/captcha/auth>
Note:
```

### Learning rules

- One outcome is evidence, not proof.
- Repeated outcomes become a pattern.
- Separate message quality from compatibility — a reply can land while the person remains poor fit; a non-reply can reflect context, timing, or weak signal.
- Preserve useful edge cases: sometimes a message is well-crafted because it reveals mismatch quickly.
- A failed/awkward/flat interaction is a missing watchpoint — convert it to a future cue.
- Cross-thread query: when ≥3 threads show the same `watch → falsified` outcome, surface as a model update candidate. Apply only after the user confirms.

---

## `extraction-state.json`

Used by `chat-audit.md` Path 2 (UI crawl) to checkpoint progress.

```json
{
  "started_at": "2026-05-06T10:00:00Z",
  "platform": "tinder",
  "audit_path": "ui_crawl",
  "session_consent_granted_at": "2026-05-06T10:00:00Z",
  "expected_total": null,
  "extracted_match_ids": ["abc123", "def456"],
  "skipped_match_ids": [],
  "current_match_id": "ghi789",
  "last_checkpoint_at": "2026-05-06T10:14:00Z",
  "rate_limit_state": {
    "actions_this_minute": 6,
    "actions_this_hour": 38,
    "last_action_at": "2026-05-06T10:14:00Z"
  },
  "completed": false
}
```

Path 2 audit consent is **session-scoped** — the audit run itself is the consented operation. The skill must not re-prompt per-conversation inside an active audit run. See `safety.md` for the audit-run clause.

---

## Privacy and retention

- All `.private-data/` is gitignored.
- Reference matches by first name only in any cross-thread log.
- Never store match photos.
- When a thread is `dead` for 90+ days, the user may request deletion; default is retention so cross-thread learning has ground truth.

## Cross-thread queries

Read across all `threads/*.json`; used by closed-loop and session summary:

- **Funnel rates**: openers sent / replies / conversations / date proposals / dates confirmed.
- **Recurring falsified-prediction patterns**: ≥3 threads, same `watch` shape → surface as model update candidate.
- **Voice-style outcomes**: aggregate `verdict` distribution by message style to detect what reliably lands.
- **Dormancy candidates**: threads matching dormancy thresholds for revive eligibility or hard exit.
