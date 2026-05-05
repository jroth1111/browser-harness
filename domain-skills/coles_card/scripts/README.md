# Coles Card Sync Scripts

## `sync.py`

Runs a browser-harness probe against the official Coles credit card Online
Service Centre and writes balances and transactions to SQLite.

```bash
python3 domain-skills/coles_card/scripts/sync.py
```

Options:

- `--db PATH` sets the SQLite database path.
- `--start-url URL` overrides the start route.
- `--current-tab` extracts from an existing Coles/Coles Group tab instead of
  opening a new login route.
- `--interactive-login` lets the user complete login/MFA manually in the
  browser before extraction continues.
- `--login-timeout SECONDS` sets the interactive wait, default `180`.
- `--export-csv` opens transaction history and imports the CSV export when
  available. This usually exposes richer fields than screen rows.
- `--dry-run` prints the normalized browser payload without writing rows.
- `--require-transactions` exits non-zero if the authenticated page yields no
  transaction rows.

Daily non-interactive command:

```bash
python3 domain-skills/coles_card/scripts/sync.py
```

Manual session refresh:

```bash
python3 domain-skills/coles_card/scripts/sync.py --interactive-login --login-timeout 180
```

Authenticated current-tab E2E check:

```bash
python3 domain-skills/coles_card/scripts/sync.py --current-tab --require-transactions
```

Full export E2E check:

```bash
python3 domain-skills/coles_card/scripts/sync.py --interactive-login --export-csv --require-transactions
```

The script stores only normalized account, balance, transaction, and run-receipt
data in SQLite. Persistent login state remains inside the attached Chrome
profile.
