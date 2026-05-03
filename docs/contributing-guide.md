# Contributing Guide

If you learned anything non-obvious about how a site works, update the domain
skill before finishing. Default to contributing. The harness gets better only
because agents file what they learn.

## When to contribute

A finding is worth adding when it would save the next agent from rediscovering
a selector, route, wait condition, source priority, auth-state trap, UI quirk,
backend limitation, or confidence caveat.

Examples:
- A private API the page calls (XHR/fetch endpoint, request shape, auth) — often 10x faster than DOM scraping.
- A stable selector that beats the obvious one, or an obfuscated CSS-module class to avoid.
- A framework quirk — "the dropdown is a React combobox that only commits on Escape", "this Vue list only renders rows inside its own scroll container, so scrollIntoView on the row doesn't work — you have to scroll the container".
- A URL pattern — direct route, required query params (?lang=en, ?th=1), a variant that skips a loader.
- A wait that wait_for_load() misses, with the reason.
- A trap — stale drafts, legacy IDs that now return null, unicode quirks, beforeunload dialogs, CAPTCHA surfaces.

## What a domain skill should capture

The *durable* shape of the site — the map, not the diary. Focus on what the next
agent on this site needs to know before it starts:

- URL patterns and query params.
- Private APIs and their payload shape.
- Stable selectors (data-*, aria-*, role, semantic classes).
- Site structure — containers, items per page, framework, where state lives.
- Framework/interaction quirks unique to this site.
- Waits and the reasons they're needed.
- Traps and the selectors that *don't* work.

## What not to write

- Raw pixel coordinates. They break on viewport, zoom, and layout changes. Describe how to *locate* the target (selector, scrollIntoView, aria-label, visible text) — never where it happened to be on your screen.
- Run narration or step-by-step of the specific task you just did.
- Secrets, cookies, session tokens, user-specific state. domain-skills/ is shared and public.

## Skill update rules

For browser-backed workflows, follow the empirical skill update rule in
`interaction-skills/cross-domain-control-flow.md`: run against the real site
surface and source context the workflow depends on, then preserve durable
findings in the relevant domain skill.

For non-trivial or cross-domain learning, use
`interaction-skills/empirical-learning-gate.md` before promoting the observation
into a shared skill. The gate requires source context, evidence references,
redaction checks, canonical final-state wording, and positive/negative probes.

Shared skill artifacts are canonical final-state manuals. Put durable rules,
source context, confidence caveats, selectors, routes, waits, and traps in the
skill. Keep edit chronology, update notes, preservation markers, replacement
instructions, and task narration in the chat, patch envelope, PR description, or
an explicit history/audit artifact.
