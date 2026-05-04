# Source Selection Receipts

Use this whenever a workflow chooses between export, API, embedded JSON,
browser-session HTTP, browser UI, or a diagnostic fallback source.

The receipt records the decision boundary, not raw data. It should be compact
enough to commit when it is redacted, or stored under `.session-store/` when it
describes local authenticated capability.

## Required Shape

Use `source_receipts.build_source_receipt(...)` from repo scripts:

```python
from source_receipts import build_source_receipt

receipt = build_source_receipt(
    source_type="api",
    source_context={
        "domain": "example.com",
        "auth_state": "logged_out",
        "currency": "AUD",
    },
    backend={"kind": "chromium", "path_type": "api"},
    source_url_or_endpoint_shape="https://example.com/api/search?query={query}",
    fields_found=["title", "price", "stable_id"],
    fields_missing=["seller_rating"],
    block={"blocked": False, "kind": None, "evidence": []},
    canonical=True,
    diagnostic_only=False,
)
```

Required fields:

- `source_type`: `export`, `api`, `embedded_json`, `browser_session_http`,
  `browser_ui`, `http`, `hybrid`, or `local`.
- `source_context`: domain, origin/auth state, account scope, filter/date/currency
  settings, and any user-visible mode that changes the result.
- `backend`: browser/backend/source family used.
- `fields_found` and `fields_missing`: field-level outcome, not page-level load.
- `block`: `{blocked, kind, evidence}` from `detect_block_page()` or equivalent.
- `fallback_reason`: required for diagnostic-only receipts.
- `canonical` and `diagnostic_only`: mutually exclusive.

## Decision Rules

- A blocked source cannot be canonical.
- A diagnostic-only source must state why it was not used as canonical.
- A field cannot appear in both `fields_found` and `fields_missing`.
- A cheaper backend can become canonical only when the receipt proves required
  fields and reconciles counts, order, or stable IDs against the reference source.
- Do not store cookies, auth headers, bearer tokens, raw private payloads, or
  downloaded private files in receipts.
