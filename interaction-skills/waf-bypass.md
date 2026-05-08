# Handling WAF Blocks and Access Denied Responses

When a site returns 403, bot-detection pages, or WAF challenge shells, the
correct response is to diagnose the block, try authorized recovery paths, and
stop if access is not authorized. Do not attempt to circumvent security controls.

## Diagnose the block

Use `detect_block_page(html=html)` to identify the block type. It returns:

```python
{"blocked": True, "kind": "kasada_kpsdk", "evidence": [...]}
```

Common block types and their signatures:

| WAF vendor | Typical signatures |
|---|---|
| Cloudflare | "Just a moment", `cf-browser-verification`, Turnstile iframe |
| Kasada | `kadira`, `challenge-platform`, `kpsdk` cookies |
| Akamai | "Access Denied", `errors.edgesuite.net` |
| PerimeterX | `_px3`, `pxcaptcha`, Human Challenge |
| Imperva/Incapsula | `incident_id`, `_incap_ses_` cookies |

The helper `detect_block_page()` covers these and more — see `helpers.py` for
the full signature list.

Also check response characteristics:

```python
def is_waf_blocked(html):
    """Quick heuristic for common block pages."""
    if len(html) < 20_000:
        return True
    for sig in ("Pardon Our Interruption", "Access Denied",
                "Just a moment", "Checking your browser",
                "Please Wait", "cf-browser-verification"):
        if sig in html:
            return True
    return False
```

## Authorized recovery paths

When a page is blocked, try these in order:

1. **Use `fetch()` with `source="auto"`.** The authority pipeline routes through
   the AccessPlane, trying HTTP, then browser session, then full browser render.
   PolicyEngine governs each step through risk levels (R0-R5). This covers the
   common case where a headless fetch fails but a real browser session succeeds.

2. **Fetch with browser session cookies.** Use `fetch(url, source="session")` to
   fetch pages with the browser's cookies and user agent via the authority pipeline.
   This works for same-domain pages that rely on session cookies.

3. **Check for alternative data sources.** Many sites offer APIs, data exports,
   or structured backends that don't trigger WAF challenges. See
   `data-source-exploration.md` for the source discovery workflow and
   `api-schema-audit.md` for API schema discovery.

4. **Ask the user to complete login.** If the block is an auth wall or expired
   session, ask the user to log in through their browser, then retry with
   `fetch(url, source="session")`.

5. **Challenge handoff.** When a challenge cannot be solved automatically
   (Cloudflare Turnstile, Datadome, etc.), the authority pipeline produces a
   handoff ID. This is a diagnostic signal — it indicates the challenge type
   and that automated recovery was not possible. See
   `interaction-skills/stealth-browser.md` for escalation options.

## When to stop

If none of the authorized recovery paths work:

- **Report the block.** Include the block type, URL, and what was attempted.
- **Emit `__UNOBSERVABLE__`** for extraction fields (see
  `extraction-coverage.md`). A blocked page is not an empty source — it is an
  unobservable source.
- **Do not attempt to circumvent the WAF.** Do not extract cookies from the
  user's browser for standalone HTTP clients, do not use TLS impersonation
  libraries, and do not try to fool fingerprinting.
- **Suggest the user obtain authorized access** (log in, use an API key,
  request an export, etc.).

## Cloudflare Turnstile

For Cloudflare sites, challenges produce a handoff ID through the authority
pipeline rather than being solved automatically. The handoff ID is a diagnostic
signal indicating the challenge type. This is not a bypass — it is an
observation that the challenge exists and requires user intervention or an
alternative approach. See `interaction-skills/stealth-browser.md` for when the
standard path fails entirely.

## Dialog handling

When a page shows alert/confirm/prompt/beforeunload dialogs that block the JS thread:

1. **CDP dismiss (preferred, undetectable):** `dismiss_dialog(accept=True)` dismisses via
   `Page.handleJavaScriptDialog` and returns `{type, message, url}`. Works even when
   JS is frozen. No page JS is touched — invisible to antibot.
2. **JS stub (proactive, detectable):** `capture_dialogs()` before the triggering action,
   then `dialogs()` to read messages. Auto-approves all `confirm()` calls.
   Detectable via `window.alert.toString()` — use only for known flows.
3. **Detection:** `page_info()` returns `{dialog: {type, message, ...}}` when a native
   dialog is open.

## OS-native popup detection

Use `pending_blockers()` to detect permission prompts, file pickers, print dialogs,
and download bars that Chrome renders outside the page viewport. Returns
`{cdp: [...], js: [...]}` combining CDP-side events with JS-side probe results.

Call `install_blocker_probe()` to inject a diagnostic wrapper around permission-gated
APIs (geolocation, notifications, mediaDevices, clipboard, bluetooth/usb/serial/hid,
file pickers, print). This is a diagnostic tool — it observes API calls without
changing behavior.

## Permission pre-granting

To prevent popups rather than detect them:

- `grant_permissions(origin, permissions)` — wraps `Browser.grantPermissions`.
  Common permissions: geolocation, notifications, microphone, camera, clipboard-read.
- `set_geolocation(lat, lon, accuracy)` — wraps `Emulation.setGeolocationOverride`.
  Pair with `grant_permissions` for geolocation — Chrome may still fall back to OS
  Core Location without the override.

## Relationship to Other Skills

- `session-continuity.md`: Long-term auth state management across sessions.
- `cookies.md`: Cookie extraction and setting for same-domain HTTP.
- `extraction-coverage.md`: The `__UNOBSERVABLE__` field state for blocked pages.
- `data-source-exploration.md`: Finding alternative data sources when browser
  access is blocked.
- Domain skills: Each domain skill documents site-specific block signatures and
  recovery notes.
