# Thread State

Per-conversation state that survives across sessions. Without it, every reply re-derives the read from raw transcript and the system has no memory of trajectory, predictions, or revival history.

## File location

`.private-data/threads/<match_id>.json` — one file per match, gitignored, written by pipeline Stages 4–6.

## Schema

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

## Field definitions

| Field | Type | Source |
|---|---|---|
| `match_id` | string | Tinder URL `/app/messages/<id>` |
| `stage` | enum | `opening` / `early_rally` / `banter` / `compatibility_discovery` / `flirty_escalation` / `escalation_ready` / `date_proposed` / `date_coordinating` / `stalled` / `revived` / `dead` (per `references/profile-conversation-read.md` stages, plus thread-state stages) |
| `trajectory[]` | array | Each received message classified per `references/profile-conversation-read.md` reciprocal-investment ladder. Append-only. Keep last 10. |
| `escalation_readiness` | object | Updated every cycle in Stage 5. See operational triggers in `references/decision-rubric.md`. Includes `charge_level_attempted_max` (highest level the user has sent on the `references/message-kernel.md` Charge ladder, 0–7) and `charge_level_reciprocated_max` (highest level she has matched or exceeded). The booleans `charge_attempted` and `charge_landed` are derived: `charge_attempted := charge_level_attempted_max ≥ 2`; `charge_landed := charge_level_reciprocated_max ≥ 2`. |
| `predictions[]` | array | Watch-line predictions; verdict written by closed loop (`references/outcome-learning.md`). Append-only. |
| `false_chemistry_flags[]` | array | `{at, type, evidence}` per `references/profile-conversation-read.md` false-chemistry checks. |
| `revival_state` | object | Tracks the one-revive-per-thread budget (per `references/decision-rubric.md` dormancy policy). |
| `deprioritized` | bool | Set by decision-rubric deprioritize triggers; pipeline skips deprioritized threads in Stage 5 unless user explicitly reopens. |
| `lead_tier` | enum | `high` / `medium` / `low` / `false-positive` per `references/scoring.md` Lead tiers. Default `medium` after first reply; updated each cycle. Drives investment level and message length. |
| `lead_tier_reason` | string | Free text — one phrase naming the dominant signal that set the current tier. |

## Read/write protocol

| Pipeline stage | Read | Write |
|---|---|---|
| Stage 4 (Opener sent) | nothing (file may not exist yet) | create file with `stage: "opening"`, append first prediction |
| Stage 5 (Conversation, message received) | full file | classify trajectory, run closed loop on prior prediction (`references/outcome-learning.md`), update `escalation_readiness` (incl. `charge_level_reciprocated_max` from her latest reply per `references/message-kernel.md` Charge ladder), **re-evaluate `lead_tier`** per `references/scoring.md`, update stage, append new prediction when user sends reply (incl. `charge_level_attempted_max` if the new draft attempts a higher level) |
| Stage 5 (Conversation, dormancy check) | full file | apply `references/decision-rubric.md` dormancy policy; set `stage: "stalled"` or trigger revive; update `revival_state` |
| Stage 6 (Escalation) | full file | gate on `escalation_readiness.ready === true`; on send, set `date_proposed_at` |
| Stage 7 (Date Coordination) | full file | set `date_confirmed_at` on confirmation; user reports outcome → `date_outcome` |

## Stage transitions

```
opening → early_rally (≥2 exchanges, both sides engaging)
early_rally → banter (humor/play landing)
banter → compatibility_discovery (real revelations from each side)
compatibility_discovery → flirty_escalation (charge attempted and reciprocated)
flirty_escalation → escalation_ready (escalation_readiness.ready === true)
escalation_ready → date_proposed (Stage 6 sends)
date_proposed → date_coordinating (they accept)
any → stalled (dormancy thresholds in decision-rubric.md)
stalled → revived (one revive sent) → either re-enters prior stage or → dead
any → dead (deprioritized OR exit OR 30d+ silent)
```

## Privacy and retention

- All thread state stays in `.private-data/threads/`, gitignored along with the rest of `.private-data/`.
- Reference matches by first name only in any cross-thread log.
- Never store match photos.
- When a thread is `dead` for 90+ days, the user may request deletion; default is retention so cross-thread learning has ground truth.

## Cross-thread queries

These read across all `threads/*.json` files; used by `references/outcome-learning.md` and `safety.md` session summary:

- **Funnel rates**: counts of openers sent / replies received / conversations / date proposals / dates confirmed.
- **Recurring falsified-prediction patterns**: when ≥3 threads show the same `watch` → `falsified` outcome, surface as a model update candidate.
- **Voice-style outcomes**: aggregate `verdict` distribution by message style (extracted from message text + voiceprint tags) to detect what reliably lands.
- **Dormancy candidates**: threads matching the dormancy policy thresholds for revive eligibility or hard exit.
