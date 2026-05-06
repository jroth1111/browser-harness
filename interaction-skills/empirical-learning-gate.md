# Empirical Learning Gate

Use this when a browser run reveals a durable rule that should update an
interaction skill or domain skill. The gate keeps empirical learning useful
without letting one observed workflow become an unsafe universal rule.

## Promotion Flow

1. Capture the browser observation as a skill improvement candidate.
2. Preserve the source context that made the observation true.
3. State the reusable final-state rule that belongs in the skill.
4. State the counterexample or forbidden overgeneralization.
5. Run redaction, canonical-artifact, positive-probe, and negative-probe checks.
6. Promote only candidates that pass the checks into the skill artifact.

The canonical skill edit should contain the durable operating rule. Keep the
candidate record, evidence receipts, run narration, and patch instructions
outside the skill artifact.

## Candidate Record

Store candidates as JSON when the learning is non-trivial or cross-domain. Use
the shared schema at `domain-skills/skill-learning-candidate.schema.json`.

Required source context:

- `domain`
- `affected_skill_paths`
- `observed_surface.origin`
- `observed_surface.url_pattern`
- `observed_surface.auth_context`
- `observed_surface.browser_backend`
- `observed_surface.source_family`
- `observed_surface.required_fields`
- `evidence_refs`

Required learning content:

- `observed_behavior`
- `proposed_rule`
- `forbidden_overgeneralization`
- `source_contextuality.scope`
- `source_contextuality.does_not_apply_when`
- `positive_probe`
- `negative_probe`

## Promotion Rules

A candidate may be promoted only when:

- it has source-context fields for the exact workflow and browser/backend path
- it has evidence references for the observed behavior
- it has a positive probe for the reusable behavior
- it has a negative probe for the old, direct, partial, or overgeneralized path
- it names at least one counterexample or condition where the rule does not apply
- redaction checks pass
- canonical-artifact checks pass for any proposed skill text

Reject or revise the candidate when:

- it stores secrets, cookies, session tokens, auth headers, raw private payloads,
  private screenshots, or user-specific state
- it collapses logged-in, logged-out, fresh-profile, persistent-profile, or
  mixed-state runs into a universal default
- it promotes a backend from one domain or source family to another by analogy
- it treats a loaded page as evidence when required fields were not observed
- it lacks a counterexample for a broad or cross-domain rule
- proposed skill text contains edit chronology, update notes, replacement
  instructions, preservation markers, or task narration

## Auth-State Rules

Auth state is a source context, not a global policy. A rule may say that a
specific public-rank workflow uses a fresh logged-out profile when rank and
price personalization would contaminate the observation. It must not say that
all work for that site should be logged out.

For authenticated dashboards, exports, account settings, listing editors,
messages, reservations, billing, or private analytics, persistent logged-in
state is usually the required source context. Public market observations and
private account observations must remain separate unless the task explicitly
asks for personalization comparison.

## Evidence Shape

Good evidence references point to durable receipts, screenshots, fixture names,
surface capability records, parser-contract fixtures, or browser-run summaries
with secrets removed. Do not place raw cookies, local storage, request
headers, private payload bodies, or unredacted screenshots in the candidate.

## Fixture Layout

Domain-specific learning fixtures live under:

```text
domain-skills/<site>/fixtures/skill-learning/
  accepted/
  rejected/
  holdout/
```

Use `accepted/` for promotable examples, `rejected/` for known unsafe patterns,
and `holdout/` for counterexamples that prevent overgeneralization.

## Local Gate

Run the gate before promoting a non-trivial candidate:

```bash
browser-harness --skill-learning-gate /absolute/path/to/domain-skills/<site>/fixtures/skill-learning/accepted/example.json
```

Installed packages also expose
`browser-harness-skill-learning-gate /absolute/path/to/CANDIDATE.json` as a
direct entrypoint.

The gate returns `accept`, `revise`, or `reject`. `accept` means the candidate is
safe to turn into a canonical skill patch; it does not apply the patch.
