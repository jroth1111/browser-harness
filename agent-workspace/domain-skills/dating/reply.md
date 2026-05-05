# Reply — Read, Decide, Draft, Send, Learn

Use when the user wants to draft an opener, reply, rewrite, revive, exit, or "what should I say?" message. This is the main generation file.

Reads: this file + `.private-data/{user-model.md, voiceprint.md, positioning.md, threads/<match_id>.json}`. Thread-state JSON shape is defined in `state.md`; consult only if the file is missing or you need to construct one.
Writes: thread state, outcome log (closed-loop verdict + new prediction).

## Output contract

Lead with the message. Reasoning sits underneath.

```text
Send: [the message]
Read: [one-line read of the thread / artifact]
Watch: [what their response will reveal]
```

`Watch:` is the prediction. Every send creates a small experiment.

Use the **calibrated** form when the user asks why or when ambiguity is the point:

```text
Read:
Frame:
State:
Shot:
Send:
Watch:
```

For challenge handling:

```text
Classification:
Frame:
State:
Shot:
Send:
Watch:
```

For charge progression (when picking the next ladder step):

```text
Her last level (reciprocated):
User last level (attempted):
Mutuality read:
Next level target:
Lever to lean on (specificity / restraint / mutuality / pace):
Send:
Read:
Watch:
```

For revives, rewrites, exits, see **Templates** below.

## Master rules (re-stated)

These three rules outrank any tactical move. Repeated from `overview.md` because every draft passes through them.

1. **Asymmetric investment.** The primary signal is voluntary investment from her side — asks back, reveals specifics, plays back, references earlier threads, suggests availability, qualifies herself against a stated standard. Match her energy when good. Slightly elevate when she increases. **Do not compensate when she is low-effort** — that is the over-function failure and it inverts the dynamic.
2. **Embody standards, do not perform value.** Drafts that demonstrate worth audition; drafts that act from standards already held filter. Every voice/tone/charge/vulnerability decision reduces to this.
3. **"I am real, and responsible for myself"** — not "I am real, and now you are responsible for me". The first invites; the second obligates. Drafts that fail this land as a request she did not sign up for.

### Operational forms of asymmetric investment

- Reply length should not materially exceed her last message length when she is `maintaining` or `decreasing`.
- Charge level should not exceed her last reciprocated level by more than one step. Concretely: `charge_level_attempted_next ≤ charge_level_reciprocated_max + 1`. Skipping levels is the most common erotic-charge failure.
- A long reply to a short reply is a draft red flag; rewrite or shorten before sending.
- Carrying the energy for two consecutive cycles when she is not investing → set `deprioritized: true`.
- Carrying the charge for two consecutive cycles when she is not reciprocating it → drop the charge level back to her last reciprocated level; if that fails, treat the thread as platonic-only or apply the over-escalation deprioritise trigger.

## Read first — the incoming artifact

Before drafting, read the latest message and the recent trajectory.

### Reciprocal investment ladder

A reply is not investment. **Responding** keeps the thread polite. **Investing** is voluntary effort. Classify her latest reply:

1. **Increasing** — adds detail, asks back, teases, references earlier threads, suggests next steps.
2. **Matching** — responds with similar effort and keeps the thread alive.
3. **Maintaining** — polite but minimal; user is doing most of the work. Responding-without-investing.
4. **Decreasing** — shorter, delayed, flatter, avoids openings.
5. **Draining** — demands performance, repeatedly ignores hooks, or makes the user carry the exchange.

Recommended moves:
- increasing → escalate one step;
- matching → continue and add a little charge;
- maintaining → improve signal with one stronger shot, then stop carrying;
- decreasing → revive once or let go;
- draining → exit or deprioritise.

Length and warmth measure presence; questions, specificity, and forward motion measure investment. A long warm reply is not evidence of investment. A short reply that asks something specific back is.

Append the classification to `trajectory[]` in thread state.

### Charge mutuality

Investment classifies whether she is participating in the thread. Charge mutuality classifies whether she is participating in the **erotic build**. Both are needed before any conversion move.

**Reciprocation signals** — her charge matches or exceeds the user's last attempted level:
- teases back at the user;
- escalates the language (more vivid, more specific, more charged);
- makes a date-shaped hint or names a setting;
- asks a personal question that pulls the thread closer;
- plays with the frame the user offered ("definitely actually dangerous" / "maybe your plans need ruining");
- responds with warmth and momentum, not just length.

**Non-reciprocation signals** — her charge is below the user's attempted level:
- topic shift away from the charged frame;
- politeness substitute ("haha", "that's funny");
- response to the literal content but not to the implication;
- significant delay paired with shorter reply;
- visible discomfort or pulling back into safer ground.

Update `escalation_readiness.charge_level_reciprocated_max` based on her highest reciprocated level across the thread.

Combined read drives the next move:
- Investment increasing AND charge reciprocated → continue the build, optionally raise one level.
- Investment increasing AND charge not reciprocated → drop charge a level; deepen warmth or specificity instead.
- Investment maintaining/decreasing → do not raise charge regardless of mutuality reading; address investment first.

### Path classification (signal-responsive routing)

The skill is not a fixed funnel. The conversation routes by path and message category, not by step number.

**Master rule.** Do not impose sequence. Read invitation. Match pace. Keep standards. Escalate cleanly.

**Operating question** for every incoming message: *what is she opening the door to right now, and do I want to walk through?*

Recognise which conversational path is active. Paths can change mid-thread; re-classify when the signal shifts. When the path materially shapes the next move, name it in `Read:`.

| Path | Signature signals | Best move | Common failure |
|---|---|---|---|
| Banter-first | playful tease, callback play, light topic shifts | keep light; add subtext gradually (charge ladder 1–3 across turns) | turning banter into sex talk before she has earned it |
| Depth-first | values surface early; slower pace; meaning-laden questions | vulnerability with edge, not therapy mode | therapist mode |
| Direct-sexual | charged language early; embodied/physical hints; explicit sexual frame | match directness; keep frame clean; pass the *fast-is-not-careless* check | crude jump |
| Compatibility-first | values/structure questions early; ENM/poly framing | answer clearly and matter-of-factly; then reintroduce play | over-explaining ENM, poly manifesto |
| Low-effort validation | hot profile; weak replies; no questions back; no escalation | one playful test shot; deprioritise if no upgrade | continuing to carry energy past the test |
| Fantasy trap | high charge; vague availability; structure unclear; logistics dodged | enjoy the signal; qualify before over-investing; do not convert on charge alone | converting on charge alone (false-chemistry) |

### Message classification

For every incoming message, identify the dominant category. Orthogonal to investment ladder — this classifies *what she is doing*.

- **Invitation** — she is opening a door (charged hint, date-shaped suggestion, vulnerability reveal). Step in. Match the door's register.
- **Test** — she is checking frame, confidence, or clarity. Stay grounded; do not over-defend or over-perform. Route via Challenge response below.
- **Bid** — she is asking for attention, warmth, or play. Reward when it carries effort; do not feed when it does not.
- **Boundary** — she is signalling a limit (slowing down, declining a topic, asking for space). Respect immediately and explicitly; do not press or negotiate.
- **Logistics window** — she is making meeting possible (mentions schedule, location, availability). Lead. Convert per `escalate.md`.
- **Noise** — she is giving nothing (low-effort, generic, off-topic). Do not feed it. Apply asymmetric investment.

Most messages carry one dominant category; some carry two. Pick the dominant one; surface the secondary if it materially affects `Watch:`.

### Signal-category gradient

Used to decide *speed*, not direction.

- **Green — accelerate.** Asks questions back; teases the user; sexual or date-shaped hints; mirrors the user's frame; suggests availability; qualifies herself voluntarily; uses physical/embodied language; sends "you'd probably…" hypotheticals.
- **Yellow — test one unknown, do not kill the vibe.** Warm but vague; flirts but avoids logistics; sexual but unclear on boundaries; interested but inconsistent; chemistry without compatibility data; jokes about chaos.
- **Red — exit, slow down, or hard-consent gate.** Repeated low effort; dodges ENM/poly clarity; pressures or guilt-trips; pushes past stated boundaries; appears intoxicated or unstable; asks the user to hide material facts; creates drama before meeting.

Yellow → one targeted test (the single missing fact, not a barrage). Red → deprioritise or `safety.md` depending on type.

### Challenge classification

When an artifact contains challenge, skepticism, teasing, or a hard frame, classify the function before drafting.

- **Playful challenge** — warmth or humour is present; respond with play.
- **Compatibility probe** — she is testing fit or intent; answer with clarity and a little edge.
- **Protective skepticism** — concern may be reasonable; acknowledge and state the user's standard.
- **Low-effort audition frame** — the user is being asked to perform while she gives little; decline the audition frame and invite mutual curiosity.
- **Boundary check** — she is clarifying limits or comfort; respond plainly and respectfully.
- **Disrespect / exit signal** — contempt, repeated dismissal, or hostile framing; deprioritise or exit.

A challenge is not automatically flirtation or rejection. Read warmth, reciprocity, and effort before choosing the move.

### Positioning diagnostic (silent)

Run silently when reading the thread: do the user's last few moves answer the screening questions in `positioning.md`?

> Will this be worth the effort? Will he be weird in a bad way? Will he understand pacing? Will he make me feel desired or consumed? Will I have to manage his emotions? Will he be clear? Will he be fun? Will he be safe without being boring? Will he be direct without being pushy?

If three or more remain unanswered (or answered against the user), the next move should reinforce the missing scarcity-stack lever rather than escalate. Common gaps that stall otherwise warm threads are specific recognition (lever 1), visible standard (lever 4), and clean logistics (lever 5).

### False-chemistry checks

Flag when chemistry may be masking weak fit:

- strong banter but no availability;
- intense flirtation but no depth;
- ambiguity that the user is rationalising;
- status sparkle without values fit;
- charged conversation with low reciprocal investment;
- repeated challenge frames with little warmth.

Append flags to `false_chemistry_flags[]` in thread state.

## The kernel

```text
Message = Hook + State + Reveal + Tension + Return
```

- **Hook** — respond to the actual artifact.
- **State** — transmit an emotional state, not just information.
- **Reveal** — show something real about the user.
- **Tension** — add attraction, contrast, playful challenge, direct interest, or romantic subtext.
- **Return** — leave an easy ball to hit back.

Shorter form: `Respond + Reveal + Flirt + Invite`.

### State palette

Pick one — amused curiosity, warm mischief, grounded directness, soft intrigue, playful suspicion, romantic clarity, decisive invitation, calm boundary.

### Tension moves

Pick one when appropriate — playful hypothesis, warm challenge, specific compliment, playful standard, callback, romantic subtext, compatibility invitation, date-shaped suggestion, warmth with restraint, light disqualification about fit or taste.

### Chemistry check (3 of 5)

A useful message usually contains at least three of these:

- **Recognition** — notices something specific in the artifact.
- **Warmth** — feels human and inviting.
- **Tension** — contrast, play, flirtation, romantic subtext.
- **Revelation** — shows something real about the user.
- **Momentum** — gives the exchange somewhere to go.

If a draft is accurate but flat, add recognition or tension. If charged but thin, add warmth or revelation. If pleasant but stagnant, add momentum.

### Frame stance

The voice should communicate, without ever stating it: has taste, has standards, is warm, is playful, is not needy, rewards good energy, does not rescue bad energy. Implicit frame: **filter, not applicant**.

Polarisation is the goal. A draft the right person will love and the wrong person will find too direct, too specific, or too playful is working as intended.

### Stance failure modes (reject before sending)

- **over-explanation** (defending a position that needs no defence);
- **over-compliment** (warmth without restraint);
- **over-softening** (hedging an invitation until it loses shape);
- **approval-seeking** ("I would love to", "if you're interested", "no pressure but");
- **performed indifference** (false unavailability, late replies as a tactic, contrived scarcity);
- **jealousy moves, negs, or status displays**;
- **length asymmetry** — a paragraph in response to a one-liner.

These are stance leaks, not voice issues. Fix by removing the leak, not by polishing the surface.

## Charge ladder

**Erotic charge is desire under restraint.** It is the felt current of mutual attraction, possibility, and anticipation that builds across a thread when both sides are participating. Distinct from sexualisation — sexualisation states wanting; charge creates the shared frame in which wanting becomes legible without being declared.

```text
safety + specificity + desire + restraint + reciprocity = erotic charge
```

Remove safety → pressure. Remove specificity → generic. Remove desire → platonic. Remove restraint → crude. Remove reciprocity → broadcasting.

### Seven levels

Move up only when the previous level is reciprocated. **Skipping levels is the most common failure.** The voiceprint's `charge ceiling` field caps which level the copilot may generate at all.

| Level | Register | Example |
|---|---|---|
| 1. Warm recognition | Make her feel specifically noticed. | "There's a very specific kind of mischief in your profile. I'm not sure whether to trust it yet." |
| 2. Playful tension | Introduce small friction; give her something to push against. | "I like that answer, but I'm not ready to give you full credit. You're at 'promising, under investigation.'" |
| 3. Flirtatious frame | Mutual discovery, not interview. | "You seem like trouble in the way that makes people make slightly worse but more memorable decisions." |
| 4. Personal reveal | A true thing about your taste or desire — vulnerable, not needy. | "I have a weakness for women who are warm, direct, and a little bit dangerous to my concentration." |
| 5. Romantic subtext | Name the charge lightly without grabbing her with it. | "This conversation is getting inconveniently distracting." |
| 6. Embodied implication | Bring physical, real-world possibility — still with restraint. | "I have a feeling this would be much more dangerous over a drink and eye contact." |
| 7. Direct escalation | When the signal is there, move. | "I like the charge here. Let's test it in person." |

### Four levers

1. **Specificity** — generic charge feels cheap. *"It's the combination of softness and sharpness. That's the dangerous part"* beats "you're sexy". Specificity makes desire feel earned.
2. **Restraint** — the explicit version is rarely the most charged version. *"There is a lot I could say here, but I'm choosing maturity for at least one more message"* creates more imagination than the explicit version. Restraint creates room to want.
3. **Mutuality** — without her energy back, you are broadcasting into a wall. If reciprocation is absent, do not climb the ladder; build warmth first.
4. **Pace** — sexual tension needs rhythm. `tease → warmth → desire → restraint → challenge → reward → subtext → normality`. Every message charged becomes try-hard. No message charged becomes platonic.

### Notice → tease → reveal → imply → invite

The full charge build pattern *across* a thread, not within one message:

- **Notice** — warm specificity (Level 1).
- **Tease** — playful tension (Level 2).
- **Reveal** — personal reveal (Level 4).
- **Imply** — romantic subtext + embodied implication (Levels 5–6).
- **Invite** — direct escalation (Level 7), the conversion move in `escalate.md`.

Within a single message you typically combine two adjacent steps, not all five.

### Charge calibration check (silent, before any Level 4+)

- Has she earned escalation (reciprocated the previous level)?
- Is there warmth in the thread, not just engagement?
- Is this desire, or pressure dressed as desire?
- Does this leave her room to play, decline, or redirect?
- Would this feel exciting from her side, not merely expressive from the user's?
- Is `charge_level_attempted_max` within `charge_level_reciprocated_max + 1`?

If any answer is no, drop one level or build warmth first.

### Working register: charged but not crude

Use as register, not boilerplate. Each carries desire under restraint:

- *"There are several replies I could send here. I'm choosing the one that keeps us both pretending to be respectable."* (restraint)
- *"You are not making it easy to maintain my calm, reasonable dating-app persona."* (composure)
- *"I suspect this conversation would become significantly less innocent with eye contact."* (eye-contact)
- *"You seem like someone who would be much more dangerous in person."* (dangerous-in-person)
- *"I'm attracted to the energy here. Not just the profile. The rhythm."* (controlled direct)
- *"I'm a little more affected by this conversation than I planned to be."* (small vulnerability)

### Shared implication

Give her a role inside the tension rather than declaring attraction at her. Statements that invite her to play with the frame:

- *"I'm trying to work out whether you're actually dangerous or just well-branded."*
- *"You seem like the kind of woman who knows exactly when she's being distracting."*

If she steps in (*"definitely actually dangerous"* / *"maybe"*), the next move acknowledges the step. She is now helping build the charge with the user, not receiving it from the user.

## Vulnerability framework

Small, specific, owned vulnerability is one of the strongest charge ingredients when used correctly and one of the most repulsive when misused. The distinction is structural.

**Master distinction.** Attractive vulnerability is *"I am real, and I am responsible for myself"*. Unattractive vulnerability is *"I am real, and now you are responsible for me"*. Drafts that fail this distinction land as obligation, not invitation, regardless of how honest they are.

**Formula:**

```text
truth + ownership + proportion + invitation = attractive vulnerability
```

- **Truth** — a real thing, not a curated reveal designed to look vulnerable.
- **Ownership** — held by the user, not handed to her to manage.
- **Proportion** — fits the stage of the thread; does not exceed earned depth.
- **Invitation** — leaves a doorway for her to step in, not a duty to absorb.

### Vulnerability ladder

Five levels. Move up only as the thread earns it.

| Level | Type | What it reveals | Earliest landable stage |
|---|---|---|---|
| 1. Taste | What the user is drawn to, finds funny, can't stop noticing. | Aesthetic and attraction shape. | Always. Profile and openers. |
| 2. Values | What the user organises life around. | Operating frame. | Early chat. |
| 3. Desire | What the user wants from this kind of connection. | Direction of interest. | Mid-thread, once mutual interest is clear. |
| 4. Pattern awareness | What the user knows about himself, including failure modes. | Self-knowledge under restraint. | Mid-to-late thread or first date. |
| 5. Wounds | Past hurt, relational damage, ongoing struggle. | Real history. | Date stage or later, only when reciprocated. |

Working examples:
- **Taste (1)**: *"I have a weakness for women who are warm, direct, and a little bit dangerous to my concentration."*
- **Values (2)**: *"I'm not built for relationships that try to be everything to everyone."*
- **Desire (3)**: *"When I actually like someone I move pretty directly. I don't have a 'play it cool' phase."*
- **Pattern awareness (4)**: *"I'm pretty good at making the early stage feel romantic and pretty bad at being patient if it doesn't turn into something real."*
- **Wounds (5)**: almost always premature in chat. Default to inspection: keep it for in-person.

Stay one level above hers unless the artifact clearly invites more.

### Calibration question (silent, before any vulnerable line)

> *Am I revealing this because it serves the connection, or because I want reassurance?*

If reassurance, the line is unowned. Rewrite into a smaller, owned version, or drop the reveal.

### Funnel-stage ceiling

| Stage | Vulnerability ceiling | Form |
|---|---|---|
| Profile copy | 2 | Taste and values inside the polarising filter line. |
| Opener / early chat | 2–3 | Taste; values when relevant; light desire as observation. |
| Qualification phase | 3 | Desire as preference; small pattern reveal if the moment warrants. |
| Date transition | 3–4 | Direct desire; pattern awareness only if it adds charge to the invite. |
| Post first date | 4–5 | Pattern awareness; wounds only when reciprocated. |

The ceiling is the maximum landable level, not the target. Most messages should sit one or two levels below.

## Move selection

### Move rules

- **Engage** — at least one strong specific hook and no clear mismatch.
- **Continue** — reciprocal investment is increasing or matching.
- **Add charge** — the thread is warm but too platonic.
- **Clarify** — attraction is present but a material compatibility field is unknown.
- **Escalate** — warmth, reciprocity, and logistical plausibility present. See operational triggers and `escalate.md`.
- **Revive once** — there was previous signal but the latest response is low-effort or flat.
- **Deprioritise** — effort is consistently one-sided, ambiguity is not resolving, or the user is rationalising weak signal.
- **Exit** — mismatch, disrespect, clear disinterest, or a pattern that drains attention.

### Challenge response routing

- Playful challenge → play back with warmth.
- Compatibility probe → answer clearly and invite their standard.
- Protective skepticism → acknowledge, state standard, distinguish intent, invite perspective.
- Low-effort audition frame → decline the audition frame and invite mutual curiosity.
- Boundary check → answer plainly and respectfully.
- Disrespect → exit or deprioritise.

### Direct-sexual escalation: fast is not careless

When she opens a direct-sexual window, fast can be the right answer — fast means fewer steps, not no standards. Before escalating to logistics, silently confirm:

- **Mutual frame** — she has stated alignment explicitly, not just charged ambiguity.
- **Sobriety and stability** — no signs of intoxication or volatility in the recent exchange.
- **ENM/poly disclosure complete** (when relevant) — structure is on the record before logistics.
- **Safer-sex expectations** — addressable plainly, not dodged.
- **Safe logistics** — location and meeting form are not coercive or risky.
- **Chaos/pressure scan** — no red signals from the gradient.
- **User-side fit check** — does the user actually want this, or is he reacting to opportunity? If reaction, decline cleanly without moralising.

Failing any check does not mean refusing the path; it means slowing one step to clarify before continuing. The clean register combines desire with standards: *"I'm attracted to the energy. I also like keeping it clear, mutual, and low-chaos. What are you actually wanting?"* Both crude acceptance and over-cautious moralising fail this register.

The operational escalation triggers below still gate any in-app date proposal.

## Operational triggers (read from `threads/<match_id>.json`)

### Escalation (`escalation_readiness.ready`)

Set `ready: true` only when **all** of:

- `consecutive_increasing_or_matching ≥ 3` across the most recent 4 trajectory entries;
- `logistical_signal_seen === true` — at least one location/availability/schedule reference from her;
- `real_revelation_user === true` AND `real_revelation_them === true` — each side has shared one personal/specific thing beyond surface banter;
- `charge_attempted === true` AND `charge_landed === true` — at least one deliberate flirtation/romantic-subtext attempt by the user that was reciprocated rather than flattened;
- `charge_level_reciprocated_max ≥ 4` — she has reciprocated at least at the personal-reveal level. A thread escalating to a date proposal at Level 1–3 reciprocation is premature and tends to fail or produce a no-show;
- confidence on the conversation read is at least MEDIUM.

If any clause is false, do not escalate. Continue, add charge, or clarify per the move rules.

### Deprioritise

Set `deprioritized: true` and stop active drafting on this thread when **any** of:

- two consecutive `maintaining` classifications immediately following a deliberate charge attempt;
- one `decreasing` classification with no warm reset within the next two exchanges;
- `draining` classification at any point;
- `false_chemistry_flags` raised in two or more consecutive cycles;
- two consecutive cycles of asymmetric investment (user supplying the energy; she responding only);
- **over-escalation without recovery** — `charge_level_attempted_max > charge_level_reciprocated_max + 2` AND the next exchange does not close the gap (either she does not climb or the user does not drop);
- disrespect or contempt observed → use Exit, not Deprioritize.

Deprioritized threads are not re-engaged automatically.

### Dormancy and revival

Time is measured from `last_their_message_at`. The user has **one** revive budget per thread, ever.

| Time since their last reply | State | Action |
|---|---|---|
| 0–24h | active | Continue normally. |
| 24–48h after the user's opener | likely-no-signal | Do not revive. Treat as a non-match for funnel metrics. |
| 48–72h on a warm thread | quiet-but-viable | Wait. Do not revive yet. |
| 72h–7d on a warm thread | dormant | One revive permitted (`revival_state.revived_once === false`). Required content rule below. |
| 7d–30d | cold | Hard-consent re-engagement only (per `safety.md`). Treat as a new opener. |
| 30d+ | dead | Exit. No further outreach. |

**Revive content rule.** A revive must reference a specific earlier moment from the thread (a callback she originated, a topic she raised, a detail she revealed). Generic re-openers ("hey", "how's your week") are not allowed and burn the revive budget without producing signal. If no specific callback is available, the thread is not viable for revival; mark `dead`.

After the revive: no response within 72h → mark `dead`. Response is `decreasing` or `maintaining` → mark `dead`. Response is `matching` or `increasing` → return to the prior stage and resume.

### Lead tier

Default `medium` after first reply. Update each cycle.

| Tier | Signals | Action | Investment policy |
|---|---|---|---|
| **high** | Asks back; reveals specifics; plays back; matches or escalates flirtation; logistically plausible; structurally compatible. | Invest, qualify, escalate when ready. | Match her energy; slightly elevate when she increases. |
| **medium** | Some warmth; inconsistent effort; one or more compatibility unknowns. | Test one key unknown with a single sharper shot. | Match her energy only; do not pre-invest. |
| **low** | Only responds, never asks; vague; dodges clarity; hot/cold. | Do not carry; let dormancy handle it. | Do not over-function; one revive max if structurally viable. |
| **false-positive** | High chemistry but low compatibility, low availability, or pure fantasy fuel. | Do not romanticise; clarify or exit. | Charge does not justify investment; check `false_chemistry_flags[]`. |

Tier rules:
- A thread can move up tiers when she invests; downgrade after two consecutive `maintaining` or one `decreasing`.
- `false-positive` is not a downgrade of `high` — it is a separate diagnosis. A thread can have high chemistry and still be false-positive.
- Lead tier informs message length: drafts to `low` and `false-positive` should be short or absent. Long replies to short replies are an over-function red flag.

## Closed loop — predicted vs observed

Every sent message stored its `Watch:` line as a prediction in `threads/<match_id>.json::predictions[]`. When a reply arrives, run this loop **before** drafting the next message:

1. Read the prior unverified prediction (the user's most recently sent message that does not yet have a verdict).
2. Classify the observed reply against the `Watch:` line:
   - **confirmed** — the predicted signal appeared (positive or negative version, as long as the read was right).
   - **falsified** — the opposite signal appeared, or the predicted signal clearly didn't.
   - **inconclusive** — the reply doesn't speak to the prediction (topic shift, ambient delay, neutral acknowledgement).
3. Append `verdict`, `evidence` (one phrase from the reply), `verdict_at` to that prediction entry in thread state.
4. If `falsified` or `inconclusive`, run a cross-thread query for similar predictions: same `Watch:` shape, same conversation stage. If ≥3 falsified across threads → surface as a model update candidate.

### Closed-loop output (compact, append to `outcome-log.md`)

```text
Predicted: [Watch line from prior message]
Observed: [one-phrase summary of their reply]
Verdict: confirmed | falsified | inconclusive
Cross-thread pattern: [none | N similar verdicts; falsified ≥3 → flag]
Update suggested: [if cross-thread pattern; otherwise none]
```

The `Update suggested` line, when present, follows the standard model-update protocol (Update / Evidence / Confidence / Implication). Apply only after the user confirms — predictions falsifying once is evidence, not proof; falsifying ≥3 times across distinct threads at the same stage is a pattern.

Without this loop, the rubric is static between onboarding sessions and `Watch:` is decorative. With it, every sent message becomes a small experiment whose result feeds back into the rubric and voiceprint within hours.

## Per-message protocol

### Opener (first message after match)

1. Read her full profile via the browser.
2. Generate opener using the kernel + voiceprint + positioning. Vulnerability ceiling 2–3.
3. Render `Send / Read / Watch`.
4. **Hard consent gate** — openers always require explicit user approval, regardless of the configured message consent level. `auto-send` does not apply.
5. Browser: type and send (selectors in `platforms/<platform>.md`).
6. Wait 2 + random*3 seconds.
7. **Create thread state** at `.private-data/threads/<match_id>.json` per `state.md`: `stage: "opening"`, append the opener as the first prediction with its `Watch:` line, set `last_user_message_at`.
8. Append action log entry to `.private-data/outcome-log.md` (include `predicted_watch:`).

### Reply (mid-conversation)

1. Read thread state. If absent (first reply to an opener sent in a prior session), reconstruct from outcome log + visible transcript.
2. **Run closed loop** on the prior prediction. Append verdict.
3. Read the new exchange. Classify her latest message on the **reciprocal investment ladder** + **path** + **message category** + **charge mutuality**. Append to `trajectory[]`.
4. Update `escalation_readiness` counters incl. `charge_level_reciprocated_max` from her latest reply.
5. Re-evaluate `lead_tier`. Tier downgrades take effect immediately and feed into draft length and consent gating for the next message.
6. **Dormancy check** — if `last_their_message_at` falls in a dormancy band, branch (wait / revive once with required callback / mark dead). Skip drafting when waiting or dead.
7. **Deprioritise check** — if any deprioritise trigger fires, set `deprioritized: true` and stop drafting on this thread; surface to user.
8. Choose move per **Move rules**.
9. Run **positioning diagnostic** silently. If three+ screening questions are unanswered, the next move reinforces the missing scarcity-stack lever instead of escalating.
10. Generate reply using the kernel. Run **chemistry check**, **stance failure modes**, **anti-patterns**, **anti-blandness pass**, **warm-edge pass**.
11. If draft is Level 4+ on the charge ladder, run **charge calibration check**.
12. If draft contains vulnerability, run the **vulnerability calibration question**.
13. Render `Send / Read / Watch`.
14. Pass consent gate (`safety.md`).
15. Browser: send.
16. **Append the new prediction** (`message`, `watch`, `sent_at`) to `predictions[]`; update `stage` and `last_user_message_at`. Set `charge_level_attempted_max` to the higher of its prior value and the level of the new draft.
17. Append action log entry to `.private-data/outcome-log.md` (include `predicted_watch:` and prior `verdict:`).

## Anti-blandness and warm-edge passes

### Anti-blandness pass (run before finalising)

Transform:
- generic → specific;
- polite → alive;
- question chain → statement + invitation;
- anxious → grounded;
- over-explained → compressed;
- platonic → romantically intentional;
- clever-only → warm and connected;
- over-edged → kind and playable.

### Warm-edge pass

- warm enough to feel human?
- edged enough to avoid blandness?
- self-respecting without contempt?
- desire without entitlement?
- tension without coercion?
- grounded rather than performative?

### Attractor score (silent, when useful)

Sendability, specificity, voice match, romantic charge, mutual agency, signal yield, compression.

## Anti-patterns (reject before sending)

### General quality failures

- **Over-compliment** — warmth without restraint; reads as approval-seeking.
- **Over-explain** — defending or justifying a position that did not need a defence.
- **Length asymmetry** — paragraph in response to a one-liner; supplying the energy she did not.
- **Reviving dead threads** — more than one revive per thread, or generic "hey" revive without callback.
- **Performed unavailability** — late replies as tactic, fake scarcity, contrived "busy" framing.
- **Jealousy moves** — mentioning other matches, ambiguous third parties.
- **Negs** — backhanded compliments, deliberate put-downs.
- **Indifference acts** — pretending not to care to manipulate engagement.
- **Sexualising before trust** — charged moves before mutual revelation.
- **Compatibility interview** — turning early chat into a values questionnaire instead of qualification through charge.
- **Qualification interrogation** — three-plus compatibility tests in one message. One charged qualification per message; more reads as audit.
- **Approval-seeking conversion moves** — hedged, apologetic, or permission-seeking date proposals.
- **Fake edge** — manufactured contrarianism; edginess that is not native to the user. Edge that is a costume, not a disposition, lowers signal.
- **Fake standards** — citing standards the user does not actually hold ("I only date women who…"). Standards must be lived, not declared.
- **Therapist mode** — turning early chat into emotional analysis or processing her feelings. The copilot is a romantic interest, not a counsellor.
- **Founder pitch-deck energy** — performing achievements, credentials, projects, status as romantic value.
- **Premature intensity** — soulmate energy, "I feel something here", "you might be different" before the thread has earned it.
- **Over-converting** — pulling for the date before rhythm and revelation are present. Premature invitation kills more leads than late invitation.
- **Compatibility audit framing** — treating every exchange as a fit-test, no warmth or play.

### ENM/poly disclosure failures

When the user's relationship structure is materially relevant:

- **Hiding the structure** — omitting non-monogamy until late in the funnel. Material relationship-honesty failure and slow-motion disqualification.
- **Over-explaining ENM** — paragraph-length justification, defensive framing, "ethical non-monogamy" as identity badge, primary/secondary glossary. Reads as apologising for the structure.
- **Unicorn-hunting framing** — presenting the user as shopping for a third to fit a pre-built configuration. Lead with her as a person; structural fit is qualification, not casting.
- **Structural disclosure as pre-emptive filter** — dropping the structure into message 1 as a defensive shield. Disclosure should be matter-of-fact and embedded in the user's actual frame.

Diagnostic: ENM disclosure is information about how the user lives, delivered with the same self-possession as any other reveal.

### Vulnerability anti-patterns

- **Trauma dump** — significant past hurt before the thread has earned it. Wounds are Level 5; almost never landable in chat.
- **Reassurance fishing** — vulnerability whose hidden ask is "tell me I'm okay".
- **Premature soulmate energy** — "you might be different", "I feel something I haven't felt in a while" before mutual revelation.
- **No-filter dumping** — confessional vulnerability marketed as authenticity. Authenticity without selectivity is a stance failure, not a strength.
- **Over-explaining standards** — long defences of why the user wants what he wants. Argued, not held.
- **Vulnerability as conversion tactic** — deploying a reveal because charge has stalled.
- **Wounded poet identity** — vulnerability as ongoing tone, not specific moment.
- **Authenticity without selectivity** — same depth to anyone who replies. Vulnerability that does not discriminate carries no signal.

### Erotic-charge anti-patterns

- **Crude jump** — explicit sexual language before mutual sexual frame. "I want to fuck you" sent at Level 2 reciprocity skips the build.
- **Porn-brain messaging** — describing what the user wants to do to her physically before mutual context exists.
- **Over-escalation** — jumping levels (she gives Level 2; draft replies at Level 6). Drop to her level + 1 or below.
- **Interviewing desire** — clinical questions about preferences before earned. Replace with charged forms.
- **Seeking permission for own desire** — "Is it okay if I say I find you attractive?" Replace with restrained directness: *"I'm finding you very easy to be curious about."*
- **Fake dominance** — "Careful, I'm trouble". Replace with specific self-aware version: *"I'm only trouble in highly specific, well-referenced contexts."*
- **Pressure dressed as desire** — a charged line into a thread that has not reciprocated.
- **Unowned vulnerability** — "I'm scared of getting hurt again". Vulnerability that adds charge is small, specific, owned, lightly playful.

Shared diagnostic: charge is desire under restraint with reciprocity. Anti-patterns either remove restraint (crude, porn-brain, seeking-permission) or remove reciprocity (over-escalation, pressure, broadcasting). Fix by dropping a level and waiting for her step, not softening the surface.

## Qualification as flirtation

Compatibility tests should not feel like an interview. Replace dead questions with charged forms that test the same thing.

| Testing for | Dead form | Charged form |
|---|---|---|
| Seriousness | "What are you looking for?" | *"What kind of connection actually keeps your attention once the novelty wears off?"* |
| Ambition | "What do you do?" | *"What are you building right now that you're quietly proud of?"* |
| Playfulness | "Are you fun?" | *"What's your most defensible red flag?"* |
| Emotional directness | "Are you emotionally mature?" | *"When you actually like someone, are you direct about it or do you make them complete a small emotional obstacle course first?"* |
| ENM/poly fit (when relevant) | "What do you think about non-monogamy?" | *"I'm allergic to chaos dressed up as freedom. What does good non-monogamy look like to you?"* |

The charged form gives her a frame to step into; people invest more when there is something to play with.

## Standards in frame

Plant the user's standard inside the message so she can self-qualify into it. State preference as observation, not demand. She can either step in or fall out.

- *"I tend to like women who are playful but not avoidant. Dangerous distinction."*
- *"I'm usually most drawn to women who have both softness and a spine."*
- *"I like chemistry, but I'm not really built for connections that are all spark and no substance."*

The good response is her stepping in: *"I'm playful but actually pretty direct when I like someone."* That is qualification working. A non-response or deflection is signal too.

Use once or twice across an early thread. Repeated standards-in-frame becomes lecturing.

## Reward investment

When she invests (specific reveal, real answer, plays back, asks a real question), reward it within one message. Two-step:

1. Acknowledge the specific thing — not "thanks for sharing" but a one-line read of what she revealed.
2. Either deepen (*"what brings out the [specific thing]?"*) or escalate (*"this is probably better tested over a drink"*).

Withholding warmth after a real reveal flattens the thread.

## Templates

### Send-first reply

```text
Send: [sendable message]
Read: [one-line read]
Watch: [what the response will reveal]
```

### Bond repair / momentum read

```text
Bond need:
Risk:
Move:
Send:
Watch:
```

### Rewrite request

```text
Send: [rewritten message]

Changed:
- [specific change]
- [specific change]

Why: [one-line explanation]
```

### Revive once

```text
Send: [one playful or warm revive with specific callback]

If energy does not return:
[deprioritise or exit]
```

### Clean exit

```text
Send: [short respectful exit]

Reason: [one-line compatibility rationale]

Do not add: [extra explanation, debate, guilt, or last-word energy]
```

## Examples (curated)

Use the closest one or two as conditioning. Do not flood the response with patterns.

### Bad → Better: bland politeness

She mentions a niche hobby.

Bad: *"That's interesting. What made you get into that?"*
Better: *"That is a suspiciously specific interest. I respect it, but I have questions about how deep this rabbit hole goes."*

### Bad → Better: eager approval-seeking

She has warm replies; user wants to suggest meeting.

Bad: *"Wow you seem amazing, I would love to take you out sometime if you are interested."*
Better: *"I like the energy here. Feels worth testing whether it survives real life."*

### Bad → Better: platonic warmth

She gives a thoughtful answer.

Bad: *"You seem like a thoughtful person and I appreciate your perspective."*
Better: *"I like the way your mind moves. Slightly inconvenient, because now I am curious."*

### Bad → Better: low-effort thread

Her: *"haha true"*

Bad: *"Haha yeah. So how was your day?"*
Better: *"That is a dangerously small amount of effort, but I will allow one recovery attempt. What detail did you almost add?"*

### Bad → Better: over-functioning on low effort

Her: *"haha maybe"*

Bad: *"That's fair! I totally get it, no pressure at all. I just thought you seemed really cool and I wanted to put it out there. If you'd rather just keep chatting that's completely fine."*
Better: *"That was suspiciously diplomatic. I'll allow one more attempt."*

### Bad → Better: over-escalation

Her: *"haha you seem fun"*

Bad: *"I have to admit I can't stop thinking about you. There's something about your energy that's making it really hard to focus on anything else."*
Better: *"'Fun' is a suspiciously diplomatic verdict. Are you grading on a curve?"*

She gave Level 2; the bad reply jumped to Level 4–5 with no reciprocation.

### Bad → Better: porn-brain

Mid-thread, charge at Level 3.

Bad: *"I keep imagining what you'd taste like."*
Better: *"You are not making it easy to maintain my calm, reasonable dating-app persona."*

### Bad → Better: seeking permission for desire

Bad: *"I hope this isn't too forward but is it okay if I say I find you really attractive?"*
Better: *"I'm finding you very easy to be curious about."*

### Bad → Better: fake dominance

Her: a playful tease.

Bad: *"Careful, I'm trouble. You probably couldn't handle me."*
Better: *"I'm only trouble in highly specific, well-referenced contexts."*

### Gold: rewarding a real reveal

Her: *"I'm probably a secret softie with a chaos-gremlin streak."*

```text
Send:
That is a dangerous combination. Secret softie is promising. Chaos gremlin requires further investigation — what brings out the softie?

Read:
Rewards the specific reveal, then deepens on the half worth pulling on.

Watch:
Whether she gives a real answer or pulls back into ambiguity.
```

### Gold: standards in frame

```text
Send:
I tend to like women who are playful but not avoidant. Dangerous distinction.

Read:
Standard stated as observation; she can step in by clarifying which side she's on.

Watch:
Whether she steps in ("I'm playful but actually pretty direct"), deflects, or ignores.
```

### Gold: vulnerability as charge

```text
Send:
I pretend to be rational, but warmth and good questions undo me pretty quickly.

Read:
Small, specific, owned, lightly playful — gives her a doorway without asking her to manage it.

Watch:
Whether she walks through (asks back, reveals her own version) or sidesteps.
```

### Gold: restraint line

She just made a charged line.

```text
Send:
There are several replies I could send here. I'm choosing the one that keeps us both pretending to be respectable.

Read:
Restraint signals desire and self-possession in the same line; she fills in the rest.

Watch:
Whether she pushes the frame further or laughs and pulls back to a safer level.
```

### Gold: charge progression across a thread

Multi-turn build, Levels 1 → 6. The user only climbs after reciprocation.

```text
Her: I'm usually sweet but I have a chaotic side.

User (L3 flirtatious frame):
That is exactly the kind of sentence that sounds innocent until it ruins someone's plans.

Her: Maybe your plans need ruining.   ← she escalated; reciprocated at L4

User (L4 personal reveal):
That was a very confident escalation. I respect it.

Her: I'm confident when I'm right.   ← reciprocated, sustained

User (L5–L6):
Dangerous. I have a weakness for women who can flirt and hold eye contact like they mean it.

Her: Good to know.   ← matched, holding

User (L7 conversion — see escalate.md):
I think this needs to be tested somewhere with low lighting and decent drinks.
```

Each user reply: noticed her line specifically, named the dynamic, climbed only on reciprocation, converted at L7 only after L6 was held.

### Edge case: mismatch exit

```text
Send:
I think we are probably looking for different shapes of connection, but I enjoyed the exchange. Wishing you good things.

Read:
Clear mismatch; no need to over-explain.

Watch:
No further investment needed unless they respond with real clarification.
```

## Examples — Transfer Cases

These preserve the high-leverage edge cases from the older reference set. Use them when the live artifact resembles the input class.

### Bad → Better: over-explained compatibility

Input: the user wants to understand relationship intent without making the chat heavy.

Bad: *"I am asking because I value communication and want to understand whether our intentions align before we continue."*
Better: *"I am enjoying the spark. I am also curious what kind of connection actually keeps your attention after the novelty wears off."*

Why: compatibility invitation without turning the chat into a form.

### Bad → Better: audition frame

Her: *"Convince me you are worth my time."*

Bad: *"I think I am worth your time because I am thoughtful, ambitious, and emotionally available."*
Better: *"I am better at mutual curiosity than auditions. But I am happy to see if we actually enjoy each other."*

Why: preserves frame without hostility.

### Bad → Better: over-soft concern

Input: she raises skepticism about the user's relationship style or intent.

Bad: *"I completely understand your concern and I really want you to feel safe, so please ask me anything."*
Better: *"Fair skepticism. I care less about labels than whether people are clear, kind, and actually available. What would you need to see for it to feel real rather than messy?"*

Why: acknowledges the concern, states a standard, and invites a useful signal.

### Bad → Better: too much certainty

Input: the user wants to compliment a profile with a strong aesthetic.

Bad: *"You are exactly my type."*
Better: *"Your profile has a very particular kind of chaos-with-taste energy. I am intrigued, possibly against my better judgment."*

Why: attraction with specificity, restraint, and play.

### Gold: warm disagreement

```text
Send:
I mostly agree, which is annoying because I was hoping to make a better counterargument.

Read:
Warm disagreement keeps the thread playful without turning it into debate.

Watch:
Whether they keep playing or make it adversarial.
```

### Gold: playful reframe

```text
Send:
I prefer the term evidence-light optimism. Much more sophisticated.

Read:
Accepts the tease and reframes it with charm.

Watch:
Whether they riff back or require explanation.
```

### Gold: playful challenge

Her: *"You seem like trouble."*

```text
Send:
Reasonable suspicion. I am mostly trouble in the makes-good-reservations and asks-too-good-questions sense.

Read:
Playful skepticism, not rejection.

Watch:
Whether they tease back or flatten the energy.
```

### Gold: date transition

Input: warmth, reciprocity, and logistical plausibility are present.

```text
Send:
I am enjoying this enough that the app is starting to feel like the least interesting place for it. Want to test the chemistry over a drink or coffee this week?

Read:
Enough signal to move from writing to a real-world read.

Watch:
Whether they make logistics easier, redirect warmly, or avoid the invitation.
```

### Gold: conversion rhythm

Input: three or four warm exchanges, both sides have revealed something specific, charge has landed at least once.

```text
Send:
I like the rhythm here. Want to test the chemistry over a drink this week?

Read:
Short, direct, not over-explained. Names the signal built so far and proposes the next-smallest real-world step.

Watch:
Whether logistics get easier, redirect warmly, or get avoided.
```

### Gold: embodied implication

Input: charge has held at Level 5; the natural next step is Level 6 without yet inviting.

```text
Send:
I have a feeling this would be much more dangerous over a drink and eye contact.

Read:
Names the physical, real-world possibility while restraint preserves the build.

Watch:
Whether she suggests logistics, escalates the charge further, or redirects warmly.
```

## Platform tone modifiers (lightweight)

Apply only when relevant; the live artifact and User Model are primary.

- **Tinder** — high-volume; sharper signal tests; avoid overinvestment; escalate only when reciprocity is clear.
- **Hinge** — relationship-forward; profile details and prompts matter; relationship-structure clarity may need warmth and restraint.
- **Feeld / alternative** — relationship structure and desire may be more explicit; still filter for intent, reciprocity, and real availability.
- **Bumble** — punchier and lower-friction; filter actively for intent and effort.
- **OkCupid** — use profile specificity and compatibility clues; avoid essay replies.
- **Meetup / community / Reddit / Discord / Facebook groups** — read social context first; community-aware first contact; respect community norms; not every post is a dating invitation.

## Conversion move

When there is rhythm, warmth, and at least one real revelation each side, stop chatting. The conversion move is short, direct, not over-explained, not softened into mush. Working forms in `escalate.md`. The conversion move is gated by `escalation_readiness.ready === true`.
