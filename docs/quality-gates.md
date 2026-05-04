# Quality Gates

Run the repo-native gate before publishing or handing off robustness work:

```bash
python3 scripts/quality_gate.py
```

The default gate runs:

1. `uv run --group dev pytest -q`
2. `python3 scripts/release_proof.py --json`
3. A hygiene scan that rejects tracked private/generated artifacts and visible
   build/test artifacts such as `build/`, `dist/`, `*.egg-info/`, coverage
   output, and cache directories.

Optional live/browser probes are explicit:

```bash
python3 scripts/quality_gate.py --live
```

The live mode sets `BROWSER_HARNESS_DATA_DISPLAY_BROWSER_SMOKE=1` and runs the
browser-backed data-display smoke test. Do not enable it unless a configured
browser-harness session is available.

Use `--skip-pytest` or `--skip-release-proof` only when isolating a failure; a
release or final handoff should use the default gate.
