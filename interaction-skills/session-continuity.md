# Session Continuity

Use this for tasks that need authenticated browser continuity across agent
sessions.

For Python code, prefer the generic `login_session.py` module. It accepts any CDP
client that can send methods and can create redacted session manifests, build
same-domain browser-session HTTP headers, and open a login page while waiting for
the user to complete credentials/MFA manually.

When the user explicitly wants to avoid logging in again, create a separate
private auth-state bundle with `login_session.session_state(...)`. That bundle
contains raw cookie/storage values and belongs only in an ignored private path
such as `.private-data/`. The redacted `.session-store/` manifest should point to
the private bundle and record verification receipts, but must not copy secrets.

## What belongs here

Generalizable:

- use the user's persistent browser profile as the primary auth store
- local ignored paths for session metadata and private temporary files
- cookie safety rules
- capability receipts
- profile labels and recheck cadence

Site-specific details belong in `domain-skills/<site>/`:

- safe seed URLs
- private source names
- expected cookie names or storage keys, without values
- login/MFA/account-selection quirks
- source-specific capability receipts

## Security posture

- Do not type credentials from screenshots.
- Stop at login, MFA, or account selection and ask the user to complete it.
- Do not commit cookies, local storage, session storage, screenshots, exports,
  downloaded reports, private payloads, or user data.
- Store only redacted metadata and capability receipts in the repository.
- Use `redaction_scan.scan_paths(...)` on public fixtures, receipts, manifests,
  and package candidates before committing or publishing them.
- If raw cookie export is explicitly requested, write it outside the repo or to
  an encrypted local store; record only a redacted manifest.
- If restorable auth state is explicitly requested, store the raw bundle under
  an ignored private path with restrictive permissions, and verify restore in a
  separate browser profile/process. Opening a new tab in the same logged-in
  browser profile is not a valid restore test.

## Ignored local stores

Domain skills can use these ignored paths:

```text
domain-skills/<site>/.session-store/
domain-skills/<site>/.private-data/
```

Use `.session-store/` for local continuity manifests and capability receipts.
Use `.private-data/` only for temporary local private files the user explicitly
wants kept outside git.

Restorable auth bundles go under `.private-data/auth-state/` by default because
they contain live session secrets.

Recommended layout:

```text
domain-skills/<site>/.session-store/
  profiles/
    <profile-label>.json
  capability/
    <date>-<backend>-<source>.json
  manifests/
    <task-or-account-label>.json
```

## Session manifest

Do not store raw cookie values.

Fields:

- `session_manifest_id`
- `site`
- `profile_label`
- `browser_backend`
- `cdp_endpoint_label`
- `account_label`
- `logged_in_observed`
- `mfa_required_observed`
- `last_successful_private_url`
- `last_private_capture_at`
- `cookie_names`
- `cookie_domains`
- `local_storage_keys`
- `session_storage_keys`
- `capability_receipt_refs`
- `expires_or_recheck_after`
- `notes`

## Capability receipt

Example shape:

```json
{
  "source": "private_dashboard",
  "backend": "chromium",
  "profile_label": "main",
  "logged_in": true,
  "url_or_path_redacted": "https://example.com/account",
  "observed_at": "2026-04-27T00:00:00Z",
  "ok": true,
  "fields_visible": ["field_a", "field_b"],
  "cookie_names": ["session_cookie_name"],
  "download_available": false,
  "notes": "Do not store cookie values."
}
```

## Browser profile flow

1. Attach browser-harness to the user's normal browser profile.
2. Navigate to a safe private account page.
3. If login/MFA/account selection appears, ask the user to complete it.
4. Run `seed_browser_session()` against a safe same-domain page.
5. Record cookie names/domains and capability, not cookie values.
6. Use `http_get_browser_session()` only for same-domain authenticated fetches
   after the profile has loaded useful private content.

Generic module example:

```python
from login_session import prompt_user_login, session_manifest

prompt_user_login(cdp_client, "https://example.com/login", success_url_contains="/account")
manifest = session_manifest(cdp_client, "https://example.com/account", site="example")
print(manifest["cookie_names"])
```

Private auth-state example:

```python
from login_session import session_state, restore_session_state

state = session_state(cdp_client, "https://example.com/account", site="example")
# Write state to an ignored private file with mode 0600.
# In a fresh browser profile, navigate to the origin, then restore:
restore_session_state(cdp_client, state, include_session_storage=True)
```

Restore verification must use a fresh browser profile or separate browser
process. Same-profile tabs reuse the already-authenticated browser store and do
not prove that the saved state is sufficient.

Use `restore_session_state_and_verify(...)` when possible. It restores cookies
and origin storage into the supplied CDP client, navigates to authenticated URLs,
and marks login redirects as failed verification. The caller still must provide
a fresh browser profile/process when proving that a saved bundle avoids re-login.

## Lightweight backend rule

Lightweight backends can reuse already-extracted data, but they should not be the
primary backend for private authenticated pages unless a capability receipt proves
that source works with that backend.
