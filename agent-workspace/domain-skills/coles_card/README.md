# Coles Card

Use this domain skill to sync the user's own Coles credit card balance and
transactions from the logged-in Online Service Centre into a local SQLite
database.

## Quick Start

```bash
REPO=/Users/gwizz/.claude/skills/browser-harness
S=$REPO/agent-workspace/domain-skills/coles_card/scripts

python3 $S/sync.py
```

The default database is:

```text
agent-workspace/domain-skills/coles_card/.private-data/coles_card.sqlite3
```

The `.private-data/` directory is ignored by git.

## Interactive Login Refresh

If the browser session is not already logged in, run:

```bash
python3 $S/sync.py --interactive-login --export-csv --login-timeout 180
```

The script starts at the authenticated account dashboard, then opens the
official Coles/NAB login flow only if the browser profile is not already
accepted. The user completes login, MFA, or account selection manually. The
script does not type credentials, read cookies, persist storage state, or
redirect auth callbacks away from Coles/NAB.

When Coles/NAB redirects to `auth.colesgroupprofile.com.au`, the tool rewrites
the generated OAuth `max_age` parameter to `20` seconds by default instead of
leaving `max_age=0`. This avoids the strictest "fresh auth only" request, but it
does not override Coles/NAB server-side session expiry or SMS/MFA policy.

If the authenticated Coles card tab is already open, use:

```bash
python3 $S/sync.py --current-tab --require-transactions
```

For the broadest transaction import, use the authenticated transaction export:

```bash
python3 $S/sync.py --interactive-login --export-csv --require-transactions
```

The CSV export currently exposes more transaction fields than the rendered
screen rows, including account number/card ending, transaction type, category,
merchant name, and processed date when Coles/NAB provides it. When the CSV
export returns one or more rows the script uses it as the sole transaction
source; the rendered DOM rows are only ingested when no export rows are
available, to avoid duplicate inserts under different normalization.

To keep the local `account_key` stable when the page-derived label drifts, pass
`--account-label`:

```bash
python3 $S/sync.py --export-csv --account-label "Coles Mastercard ending 1234"
```

## Persistent Session Profile

Session reuse should live in the browser profile, not in exported credentials or
copied auth tokens. To create a durable Coles-only profile for recurring syncs:

```bash
browser-harness --launch-profile agent-workspace/domain-skills/coles_card/.private-data/chrome-profile \
  --port 9222 \
  --url https://secure.coles.com.au/home/account_dashboard
```

Log in manually in that Chrome window once. Future syncs can reuse the same
profile while Coles/NAB keeps the browser session valid:

```bash
python3 $S/sync.py --export-csv --require-transactions
```

If the session expires, rerun the interactive command and complete login/MFA in
the browser. The sync tool deliberately does not export cookies, local storage,
session storage, passwords, or bearer tokens into its own files.

## Daily Run Shape

Use the same command from cron, launchd, or a Codex automation. A daily
non-interactive run should not use `--interactive-login`; if the session has
expired, the run is recorded as `blocked` and no credential data is collected.
