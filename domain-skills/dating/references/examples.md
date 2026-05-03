# Examples

Use this file for few-shot conditioning. Pick only the one or two closest examples for the task. Adapt to the actual person, platform, artifact, User Model, and Voiceprint. Quality beats quantity.

## Bad -> Better: bland politeness

Input: The other person mentions a niche hobby.

Bad:
> That's interesting. What made you get into that?

Better:
> That is a suspiciously specific interest. I respect it, but I have questions about how deep this rabbit hole goes.

Why: specific, playful, and easy to return.

## Bad -> Better: eager approval-seeking

Input: The chat has warmth and the user wants to suggest meeting.

Bad:
> Wow you seem amazing, I would love to take you out sometime if you are interested.

Better:
> I like the energy here. Feels worth testing whether it survives real life.

Why: direct interest without auditioning.

## Bad -> Better: platonic warmth

Input: The other person gives a thoughtful answer.

Bad:
> You seem like a thoughtful person and I appreciate your perspective.

Better:
> I like the way your mind moves. Slightly inconvenient, because now I am curious.

Why: keeps warmth and adds romantic charge.

## Bad -> Better: over-explained compatibility question

Input: The user wants to understand relationship intent without making the chat heavy.

Bad:
> I am asking because I value communication and want to understand whether our intentions align before we continue.

Better:
> I am enjoying the spark. I am also curious what kind of connection actually keeps your attention after the novelty wears off.

Why: compatibility invitation without turning the chat into a form.

## Bad -> Better: accepting an audition frame

Input:
> Convince me you are worth my time.

Bad:
> I think I am worth your time because I am thoughtful, ambitious, and emotionally available.

Better:
> I am better at mutual curiosity than auditions. But I am happy to see if we actually enjoy each other.

Why: preserves frame without hostility.

## Bad -> Better: low-effort thread

Input:
> haha true

Bad:
> Haha yeah. So how was your day?

Better:
> That is a dangerously small amount of effort, but I will allow one recovery attempt. What detail did you almost add?

Why: one clean revive with playful standard.

## Bad -> Better: over-soft concern response

Input: The other person raises skepticism about the user's relationship style or intent.

Bad:
> I completely understand your concern and I really want you to feel safe, so please ask me anything.

Better:
> Fair skepticism. I care less about labels than whether people are clear, kind, and actually available. What would you need to see for it to feel real rather than messy?

Why: acknowledges the concern, states a standard, and invites a useful signal.

## Bad -> Better: too much certainty

Input: The user wants to compliment a profile with a strong aesthetic.

Bad:
> You are exactly my type.

Better:
> Your profile has a very particular kind of chaos-with-taste energy. I am intrigued, possibly against my better judgment.

Why: attraction with specificity, restraint, and play.

## Gold example: warm disagreement

Input: The other person states a strong but playful opinion.

Output:
```text
Send:
I mostly agree, which is annoying because I was hoping to make a better counterargument.

Read:
Warm disagreement keeps the thread playful without turning it into debate.

Watch:
Whether they keep playing or make it adversarial.
```

## Gold example: playful reframe

Input: The other person calls the user's claim optimistic.

Output:
```text
Send:
I prefer the term evidence-light optimism. Much more sophisticated.

Read:
This accepts the tease and reframes it with charm.

Watch:
Whether they riff back or require explanation.
```

## Gold example: playful challenge

Input:
> You seem like trouble.

Output:
```text
Send:
Reasonable suspicion. I am mostly trouble in the makes-good-reservations and asks-too-good-questions sense.

Read:
Playful skepticism, not rejection.

Watch:
Whether they tease back or flatten the energy.
```

## Gold example: date transition

Input: There is warmth, reciprocity, and logistical plausibility.

Output:
```text
Send:
I am enjoying this enough that the app is starting to feel like the least interesting place for it. Want to test the chemistry over a drink or coffee this week?

Read:
Enough signal to move from writing to a real-world read.

Watch:
Whether they make logistics easier, redirect warmly, or avoid the invitation.
```

## Edge case: mismatch exit

Input: The fit is clearly off.

Output:
```text
Send:
I think we are probably looking for different shapes of connection, but I enjoyed the exchange. Wishing you good things.

Read:
Clear mismatch; no need to over-explain.

Watch:
No further investment needed unless they respond with real clarification.
```

## Quality-bar note

These examples set the upper bound of runtime output. Prefer fewer examples that are highly sendable, specific, voice-shaped, and socially alive over many acceptable variants.
