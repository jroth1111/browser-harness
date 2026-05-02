# WAF Bypass — Universal Fallback for Blocked Scraping

When a domain skill's primary fetch method (browser, `http_get`, `curl`) returns
403 / bot-detection pages, use cookie extraction + TLS impersonation as the
universal fallback. This works against Akamai, Cloudflare, and other modern WAFs
that fingerprint the TLS stack and browser session.

## Why Standard Clients Fail

Sites with modern WAF fingerprint the TLS handshake, not just the User-Agent
header. All of these return 403 on flagged sessions:

| Client | Result | Reason |
|--------|--------|--------|
| `curl` | 403 | TLS fingerprint is `curl/libcurl` |
| Python `requests` | 403 | TLS fingerprint is `urllib3/openssl` |
| Python `httpx` (HTTP/2) | 403 | HTTP/2 doesn't help; TLS fingerprint still wrong |
| `curl_cffi` without cookies | 403 | Correct TLS fingerprint but no valid session cookies |
| `curl_cffi` + extracted cookies | **200** | Correct TLS + valid session from user's browser |

The only combination that works is **TLS impersonation** (matching Chrome's exact
handshake) **plus valid session cookies** (from a browser that has already passed
the WAF challenge).

## Prerequisites

```bash
pip install curl_cffi browser_cookie3
```

- `curl_cffi`: HTTP client using libcurl with browser TLS fingerprints
- `browser_cookie3`: Reads and decrypts cookies from Chrome/Firefox profiles

## Method: Cookie Extraction + TLS Impersonation

```python
import browser_cookie3
from curl_cffi import requests as cffi_requests

# 1. Extract cookies from the user's browser for the target domain
cj = browser_cookie3.chrome(domain_name="example.com.au")
cookies = {c.name: c.value for c in cj}

# 2. Build headers matching the impersonated browser version
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    "sec-ch-ua": '"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="8"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
              "image/avif,image/webp,*/*;q=0.8",
}

# 3. Fetch with TLS impersonation + extracted cookies
r = cffi_requests.get(
    "https://www.example.com.au/protected/page",
    headers=HEADERS,
    cookies=cookies,
    impersonate="chrome136",
    timeout=15,
)
```

### Available impersonate values (curl_cffi 0.15+)

Tested working: `chrome124`, `chrome131`, `chrome136`, `chrome142`.

Use the version that matches your User-Agent header. If the User-Agent says
Chrome 136, use `impersonate="chrome136"`.

## Recovery Strategy

The scrape-then-block pattern is inevitable for live testing:

```
1. Primary method (http_get / browser)
   ↓ returns 403 / bot page?
2. Cookie extraction + curl_cffi fallback
   ↓ cookies not found or also blocked?
3. User must load site in their browser to seed cookies
   then retry step 2
```

Domain skills should document their primary fetch method and link here for the
fallback. Do not duplicate this technique in every domain skill.

## WAF Detection

Check for common block signatures before parsing:

```python
def is_waf_blocked(html):
    """Generic WAF block detection."""
    if len(html) < 20_000:
        return True
    for sig in ("Pardon Our Interruption", "Access Denied",
                "Just a moment", "Checking your browser",
                "Please Wait", "cf-browser-verification"):
        if sig in html:
            return True
    return False
```

Domain-specific `is_blocked()` functions can extend this with site-specific
signatures.

## Gotchas

- **Cookie extraction requires the user to have visited the site in Chrome.**
  If they haven't, `browser_cookie3` returns an empty jar and the request
  will still be blocked. The user must load the site once in their browser.

- **Chrome encrypts cookies on macOS using the Keychain.** `browser_cookie3`
  handles decryption automatically but requires Keychain access (prompts on
  first use).

- **The block is session-level, not IP-level.** Akamai fingerprints the
  TLS/browser session. A fresh browser context on the same IP with different
  cookies will still be blocked. Valid cookies from an established session
  are required.

- **Cookies expire.** If the user's browser session expires, extracted cookies
  stop working. Re-extract after the user revisits the site.

- **Rate limiting still applies.** Cookie extraction bypasses the initial WAF
  challenge, but aggressive scraping (10+ rapid requests) will trigger
  secondary rate limiting. Use 3-5 second delays between requests.

- **`browser_cookie3` reads the default Chrome profile.** If the user's working
  session is in a different profile, specify the profile path explicitly.

## Relationship to Other Skills

- `cookies.md`: Same-domain HTTP with browser cookies (for sites where the
  browser is already connected via CDP). Use that when the browser works.
  Use *this* document when the browser is blocked and you need a standalone
  Python fallback.
- `session-continuity.md`: Long-term auth state management. This document
  is about one-shot WAF bypass, not persistent sessions.
- Domain skills: Each domain skill documents site-specific block signatures,
  headers, and extractors. They link here for the universal bypass method.
