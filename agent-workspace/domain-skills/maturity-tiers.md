# Domain Skill Maturity Tiers

Use these tiers to describe how much evidence a domain skill has.

The evaluator is `domain_skill_maturity.evaluate_domain_skill(path)`.

| Tier | Evidence |
|---|---|
| `documented` | `overview.md` or `README.md` exists. |
| `scripted` | `scripts/*.py` and `scripts/README.md` exist. |
| `fixture-tested` | `fixtures/` has examples and `tests/test*.py` exists in the domain folder. |
| `live-smoked` | A smoke script exists and redacted `receipts/*.json` evidence exists. |
| `packaged-safe` | `surface-map.json` exists and no private/generated dirs are in the package path. |

Maturity is evidence, not prestige. A single-file public static skill may only
need `documented`; browser-heavy or authenticated skills should aim for
`fixture-tested` or higher before being treated as robust.
