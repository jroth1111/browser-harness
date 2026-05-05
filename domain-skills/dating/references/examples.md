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

## Gold example: qualification as flirtation

Input: The thread has warmth and the user wants to test seriousness without making it heavy.

Output:
```text
Send:
What kind of connection actually keeps your attention once the novelty wears off?

Read:
Tests seriousness; gives her a frame she can step into rather than an interview question.

Watch:
Whether she answers with depth, deflects with a joke, or treats it as too much.
```

## Gold example: standards in frame

Input: Early rally, she is playing back, user wants to plant a standard so she can self-qualify.

Output:
```text
Send:
I tend to like women who are playful but not avoidant. Dangerous distinction.

Read:
Standard stated as observation; she can step in by clarifying which side she's on.

Watch:
Whether she steps in ("I'm playful but actually pretty direct"), deflects, or ignores.
```

## Gold example: rewarding a real reveal

Input:
> I'm probably a secret softie with a chaos-gremlin streak.

Output:
```text
Send:
That is a dangerous combination. Secret softie is promising. Chaos gremlin requires further investigation — what brings out the softie?

Read:
Rewards the specific reveal, then deepens on the half worth pulling on.

Watch:
Whether she gives a real answer or pulls back into ambiguity.
```

## Gold example: conversion move with rhythm

Input: Three or four warm exchanges, both sides have revealed something specific, charge has landed at least once.

Output:
```text
Send:
I like the rhythm here. Want to test the chemistry over a drink this week?

Read:
Short, direct, not over-explained. Names the signal that's been built and proposes the next-smallest real-world step.

Watch:
Whether logistics get easier (day, place), get redirected warmly, or get avoided.
```

## Bad -> Better: over-functioning on low effort

Input:
> haha maybe

Bad:
> That's fair! I totally get it, no pressure at all. I just thought you seemed really cool and I wanted to put it out there. If you'd rather just keep chatting that's completely fine.

Better:
> That was suspiciously diplomatic. I'll allow one more attempt.

Why: matches her energy with one calibrated shot instead of supplying paragraphs. A long reply to a short reply is the over-function failure.

## Bad -> Better: hedged conversion move

Input: Warmth and rhythm have been established.

Bad:
> Hey so I was wondering, if you'd maybe possibly be interested at some point, no pressure but, would you maybe want to grab coffee or a drink or something sometime?

Better:
> This has enough signal that I'd rather not leave it trapped in app limbo. Want to continue it over a drink?

Why: states the read, names the move, doesn't apologise for the invitation.

## Gold example: charge progression across a thread

Multi-turn build, Levels 1 → 6 of the `references/message-kernel.md` Charge ladder. The user only climbs after reciprocation.

```text
Her: I'm usually sweet but I have a chaotic side.

User (L3 flirtatious frame):
That is exactly the kind of sentence that sounds innocent until it ruins someone's plans.

Her: Maybe your plans need ruining.   ← she escalated; reciprocated at L4

User (L4 personal reveal):
That was a very confident escalation. I respect it.

Her: I'm confident when I'm right.   ← reciprocated, sustained

User (L5–L6 personal reveal + embodied implication):
Dangerous. I have a weakness for women who can flirt and hold eye contact like they mean it.

Her: Good to know.   ← matched, holding the frame

User (L7 direct escalation / conversion move):
I think this needs to be tested somewhere with low lighting and decent drinks.
```

Watch what each user reply did: noticed her line specifically, named the dynamic, climbed only when she had reciprocated, and converted at L7 only after L6 was held.

## Gold example: restraint line

Input: She just made a charged line; the urge is to match-or-exceed explicitly.

Output:
```text
Send:
There are several replies I could send here. I'm choosing the one that keeps us both pretending to be respectable.

Read:
Restraint signals desire and self-possession in the same line; she fills in the rest.

Watch:
Whether she pushes the frame further or laughs and pulls back to a safer level.
```

## Gold example: embodied implication

Input: Charge has held at Level 5; the natural next step is L6 without yet inviting.

Output:
```text
Send:
I have a feeling this would be much more dangerous over a drink and eye contact.

Read:
Names the physical, real-world possibility while the restraint preserves the build.

Watch:
Whether she suggests logistics, escalates the charge further, or redirects warmly.
```

## Gold example: vulnerability as charge

Input: The thread is warm and playful; the user wants to add depth without making it heavy.

Output:
```text
Send:
I pretend to be rational, but warmth and good questions undo me pretty quickly.

Read:
Small, specific, owned, lightly playful — gives her a doorway without asking her to manage it.

Watch:
Whether she walks through (asks back, reveals her own version) or sidesteps.
```

## Bad -> Better: over-escalation

Input:
> haha you seem fun

Bad:
> I have to admit I can't stop thinking about you. There's something about your energy that's making it really hard to focus on anything else.

Better:
> "Fun" is a suspiciously diplomatic verdict. Are you grading on a curve?

Why: she gave Level 2; the bad reply jumped to Level 4–5 with no reciprocation. The better reply matches her level + 1 and gives her a frame to step into.

## Bad -> Better: porn-brain message

Input: Mid-thread, charge has reached Level 3.

Bad:
> I keep imagining what you'd taste like.

Better:
> You are not making it easy to maintain my calm, reasonable dating-app persona.

Why: the bad form supplies physical content she did not opt into; the better form keeps the desire visible and the restraint intact, leaving her room to play.

## Bad -> Better: fake dominance

Input: She makes a playful tease.

Bad:
> Careful, I'm trouble. You probably couldn't handle me.

Better:
> I'm only trouble in highly specific, well-referenced contexts.

Why: posed dominance reads as performance; the specific self-aware version lands the charge through wit instead of posture.

## Bad -> Better: seeking permission for desire

Input: Mid-thread, the user wants to express attraction.

Bad:
> I hope this isn't too forward but is it okay if I say I find you really attractive?

Better:
> I'm finding you very easy to be curious about.

Why: the bad form makes her manage the user's discomfort; the better form states attraction with restraint and lets her receive it.

## Quality-bar note

These examples set the upper bound of runtime output. Prefer fewer examples that are highly sendable, specific, voice-shaped, and socially alive over many acceptable variants.
