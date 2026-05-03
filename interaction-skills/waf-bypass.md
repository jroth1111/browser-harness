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

1. **Seed the browser session.** `seed_browser_session(url)` opens a real
   browser tab to the URL and waits for content. If the user's browser profile
   has a valid session (they previously completed a challenge or logged in),
   this refreshes cookies and returns `{"ok": True, ...}`.

2. **Fetch with browser session cookies.** After seeding, use
   `http_get_browser_session(url)` to fetch additional pages with the browser's
   cookies and user agent. This works for same-domain pages that rely on
   session cookies.

3. **Check for alternative data sources.** Many sites offer APIs, data exports,
   or structured backends that don't trigger WAF challenges. See
   `data-source-exploration.md` for the source discovery workflow and
   `api-schema-audit.md` for API schema discovery.

4. **Ask the user to complete login.** If the block is an auth wall or expired
   session, ask the user to log in through their browser, then retry with
   `seed_browser_session()`.

5. **Use `fetch()` with `source="auto"`.** The auto cascade tries HTTP, then
   browser, and handles Cloudflare Turnstile challenges when a visible browser
   is available. This covers the common case where a headless fetch fails but
   a real browser session succeeds.

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

For Cloudflare sites specifically, `detect_turnstile()` and `solve_turnstile()`
handle interactive and non-interactive challenges through the attached browser.
This is a browser-native interaction (clicking a checkbox or waiting for an
automatic verification), not a bypass. Requires a visible (non-headless) browser.

## Relationship to Other Skills

- `session-continuity.md`: Long-term auth state management across sessions.
- `cookies.md`: Cookie extraction and setting for same-domain HTTP.
- `extraction-coverage.md`: The `__UNOBSERVABLE__` field state for blocked pages.
- `data-source-exploration.md`: Finding alternative data sources when browser
  access is blocked.
- Domain skills: Each domain skill documents site-specific block signatures and
  recovery notes.
