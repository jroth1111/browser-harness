# Outcome Learning

Use this file when the user reports what happened after a message, profile decision, date transition, event, or conversation.

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
