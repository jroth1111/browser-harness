# Profile and Conversation Read

Use this file when reading a profile, chat, reply draft, event listing, group post, or community context.

## Read dimensions

Assess only what the artifact supports:
- attraction / chemistry potential;
- relationship or intent signal;
- communication quality;
- warmth, effort, play, curiosity;
- values and lifestyle signals;
- availability and practical fit;
- relationship-structure compatibility if relevant;
- real-person and real-intent quality;
- fit with the User Model;
- risk of false chemistry or overinvestment.

## Reciprocal investment ladder

A reply is not investment. **Responding** is keeping the thread polite. **Investing** is voluntary effort: asking back, revealing specifics, playing, suggesting availability, qualifying herself against a standard. The classification below is the operating definition the rest of the rubric runs on.

Classify each response as:
1. **Increasing**: adds detail, asks back, teases, references earlier threads, suggests next steps.
2. **Matching**: responds with similar effort and keeps the thread alive.
3. **Maintaining**: polite but minimal; user is doing most work. Responding-without-investing.
4. **Decreasing**: shorter, delayed, flatter, avoids openings.
5. **Draining**: demands performance, repeatedly ignores hooks, or makes the user carry the exchange.

Recommended moves:
- increasing -> escalate one step;
- matching -> continue and add a little charge;
- maintaining -> improve signal with one stronger shot, then stop carrying;
- decreasing -> revive once or let go;
- draining -> exit or deprioritise.

A long warm reply is not evidence of investment. A short reply that asks something specific back is. Length and warmth measure presence; questions, specificity, and forward motion measure investment.

## Path detection

Identify which conversational path she is opening — banter-first, depth-first, direct-sexual, compatibility-first, low-effort validation, or fantasy trap — per `references/decision-rubric.md` Path classification. Also classify the latest incoming message as invitation / test / bid / boundary / logistics window / noise per the same file's Message classification.

Path and message category drive *which* move to choose; investment level and charge mutuality drive *how strongly* to make it. Both lenses run on every read; surface the path in `Read:` only when it materially shapes the move.

## Charge mutuality

Investment classifies whether she is participating in the thread. Charge mutuality classifies whether she is participating in the **erotic build** (`references/message-kernel.md` Erotic charge). Both are needed before the conversion move.

Reciprocation signals — if her reply contains any, her charge level matches or exceeds the user's last attempted level:
- teases back at the user;
- escalates the language (more vivid, more specific, more charged);
- makes a date-shaped hint or names a setting;
- asks a personal question that pulls the thread closer;
- plays with the frame the user offered ("definitely actually dangerous" / "maybe your plans need ruining");
- responds with warmth and momentum, not just length.

Non-reciprocation signals — her charge is below the user's attempted level:
- topic shift away from the charged frame;
- politeness substitute ("haha", "that's funny");
- response to the literal content but not to the implication;
- significant delay paired with shorter reply;
- visible discomfort or pulling back into safer ground.

Classify the latest received reply for **both** investment (ladder above) and charge mutuality. Update `escalation_readiness.charge_level_reciprocated_max` per `references/thread-state.md` based on her highest reciprocated level across the thread.

The combined read drives the next move:
- Investment increasing AND charge reciprocated → continue the build, optionally raise one level.
- Investment increasing AND charge not reciprocated → drop charge a level; deepen warmth or specificity instead.
- Investment maintaining/decreasing → do not raise charge regardless of mutuality reading; address investment first.

## Challenge classification

When an artifact contains challenge, skepticism, teasing, or a hard frame, classify the function before drafting.

- **Playful challenge**: warmth or humour is present; respond with play.
- **Compatibility probe**: the person is testing fit or intent; answer with clarity and a little edge.
- **Protective skepticism**: concern may be reasonable; acknowledge and state the user's standard.
- **Low-effort audition frame**: the user is being asked to perform while the other person gives little; decline the audition frame and invite mutual curiosity.
- **Boundary check**: the person is clarifying limits or comfort; respond plainly and respectfully.
- **Disrespect / exit signal**: contempt, repeated dismissal, or hostile framing; deprioritise or exit.

A challenge is not automatically flirtation or rejection. Read warmth, reciprocity, and effort before choosing the move.

## Profile read

Look for:
- specific self-expression;
- values and lifestyle clues;
- relationship-style clues;
- openness, curiosity, autonomy;
- emotional range and communication style;
- signs of low-effort, mismatch, or unavailable energy.

## Conversation read

Identify stage:
- opening;
- early rally;
- banter;
- compatibility discovery;
- emotional deepening;
- flirty escalation;
- date transition;
- low-energy ambiguity;
- mismatch / exit.

## Bond need

Name what the interaction needs next:
- warmth;
- play;
- depth;
- romantic signal;
- compatibility clarity;
- date momentum;
- clean exit.

## Current risk

Flag the highest risk:
- too platonic;
- too intense;
- too jokey;
- too interview-like;
- too ambiguous;
- chasing;
- false chemistry;
- low reciprocal investment.

## Positioning diagnostic

Investment classifies whether she is participating; charge mutuality classifies whether she is co-building the erotic frame. The positioning diagnostic classifies whether the user is *worth* her continued investment from her side.

Run silently when reading the thread: do the user's last few moves answer the screening questions in `references/positioning.md` What she is screening for? If three or more remain unanswered (or answered against the user), the next move should reinforce the missing scarcity-stack lever rather than escalate. Common gaps that stall otherwise warm threads are specific recognition (lever 1 of "what makes her run to meet"), visible standard (lever 4), and clean logistics (lever 5).

## False chemistry checks

Flag when chemistry may be masking weak fit:
- strong banter but no availability;
- intense flirtation but no depth;
- ambiguity that the user is rationalising;
- status sparkle without values fit;
- charged conversation with low reciprocal investment;
- repeated challenge frames with little warmth.

## Output

```text
Read:
Fit:
Move:
Why:
Watch:
```
