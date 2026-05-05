# Coles Card

Use this domain skill to sync the user's own Coles credit card balance and
transactions from the logged-in Online Service Centre into a local SQLite
database.

## Quick Start

```bash
REPO=/Users/gwizz/.claude/skills/browser-harness
S=$REPO/domain-skills/coles_card/scripts

python3 $S/sync.py
```

The default database is:

```text
domain-skills/coles_card/.private-data/coles_card.sqlite3
```

The `.private-data/` directory is ignored by git.

## Interactive Login Refresh

If the browser session is not already logged in, run:

```bash
python3 $S/sync.py --interactive-login --login-timeout 180
```

The script opens the official Coles/NAB login flow in the attached browser and
waits. The user completes login, MFA, or account selection manually. The script
does not type credentials, read cookies, persist storage state, or redirect auth
callbacks away from Coles/NAB.

If the authenticated Coles card tab is already open, use:

```bash
python3 $S/sync.py --current-tab --require-transactions
```

## Daily Run Shape

Use the same command from cron, launchd, or a Codex automation. A daily
non-interactive run should not use `--interactive-login`; if the session has
expired, the run is recorded as `blocked` and no credential data is collected.
