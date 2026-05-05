# Outcome Learning

Use this file when the user reports what happened, AND every time a new message arrives in an active thread (closed loop below). The closed loop runs automatically against `references/thread-state.md` predictions; user-reported outcomes layer on top.

## Outcome capture

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

## Learning rules

- One outcome is evidence, not proof.
- Repeated outcomes become a pattern.
- Separate message quality from compatibility.
- A reply can land while the person remains poor fit.
- A non-reply can reflect context, timing, mismatch, or weak signal; do not overfit.
- Preserve useful edge cases: sometimes a message is well-crafted because it reveals mismatch quickly.

## Update categories

- **Voice**: length, rhythm, tone, humour, directness, edge, words to use more or less.
- **Message style that landed**: what produced warmth, play, clarity, or movement.
- **Message style that missed**: what felt too intense, too flat, too clever, too soft, or too confusing.
- **Flirt style that felt authentic**: the kind of charge the user would actually send again.
- **Flirt style that felt forced**: any move that worked on paper but felt unlike the user.
- **Attraction**: what creates chemistry and what only creates noise.
- **Fit**: what predicts compatibility, availability, and values alignment.
- **Blind spot**: what pulls the user into weak-signal dynamics.
- **Platform**: what style works in that context.
- **Timing**: when to escalate, slow down, clarify, revive, or exit.
- **Confirmed compatibility signal**: repeated signal that predicts good fit.
- **Misleading signal**: repeated signal that feels exciting but does not hold.

## Output

```text
Learned:
Do more:
Do less:
Model update:
Next time:
```

## No vague outcomes

Avoid treating "worked" or "did not work" as sufficient. Capture the exact message, the exact response or non-response, the energy change, the signal confirmed or falsified, and the model update.

## Failed interaction rule

A failed, awkward, flat, or wrong-feeling interaction is a missing watchpoint. Convert it into a future cue the copilot should notice earlier next time.

## Closed loop: predicted vs. observed

Every sent message stores its `Watch:` line as a prediction in `references/thread-state.md` `predictions[]`. When a reply arrives, run this loop **before** drafting the next message:

1. Read the prior unverified prediction from thread state (the user's most recently sent message that does not yet have a verdict).
2. Classify the observed reply against the `Watch:` line:
   - **confirmed**: the predicted signal appeared (positive or negative version, as long as the read was right).
   - **falsified**: the opposite signal appeared, or the predicted signal clearly didn't.
   - **inconclusive**: the reply doesn't speak to the prediction (e.g., topic shift, ambient delay, neutral acknowledgement).
3. Append `verdict`, `evidence` (one phrase from the reply), and `verdict_at` to that prediction entry in thread state.
4. If the verdict is `falsified` or `inconclusive`, run the **cross-thread query** (see `references/thread-state.md`) for similar predictions: same `Watch:` shape, same conversation stage. If ≥3 falsified across threads, surface as a model update candidate.

### Closed-loop output (compact)

```text
Predicted: [Watch line from prior message]
Observed: [one-phrase summary of their reply]
Verdict: confirmed | falsified | inconclusive
Cross-thread pattern: [none | N similar verdicts; falsified ≥3 → flag]
Update suggested: [if cross-thread pattern; otherwise none]
```

The `Update suggested` line, when present, follows the standard model-update protocol from `references/user-model.md` (Update / Evidence / Confidence / Implication). Apply only after the user confirms — predictions falsifying once is evidence, not proof; falsifying ≥3 times across distinct threads at the same stage is a pattern.

### What the loop is for

Without it, the rubric is static between onboarding sessions and the `Watch:` line is decorative. With it, every sent message becomes a small experiment whose result feeds back into the rubric and voiceprint within hours, not weeks.
