# Stealth Browser for WAF-Protected Sites

When the standard CDP browser path hits Cloudflare Turnstile, Datadome, Akamai,
or other bot detection that `solve_turnstile()` cannot pass, use the Patchright
stealth backend.

## When to use

- Cloudflare Turnstile blocks that `solve_turnstile()` cannot solve
- Datadome or Akamai blocks detected by `detect_block_page()`
- Sites that detect CDP via Runtime.enable / Console.enable fingerprints
- Any site where the CDP-controlled Chrome gets a "Verify you are human" loop

## When NOT to use

- The standard CDP path works fine (most sites)
- `solve_turnstile()` successfully passes the challenge
- HTTP-based extraction is sufficient (no DOM needed)
- You need Firefox/WebKit (Patchright is Chromium only)

## Quick pattern

```python
from stealth_helpers import stealth_session

with stealth_session() as s:
    s.goto("https://example.com")
    html = s.content()
    text = s.text()
    title = s.js("document.title")
```

## Cookie injection

```python
import json
from stealth_helpers import stealth_session

with stealth_session() as s:
    # Load saved cookies
    cookies = json.loads(Path(".private-data/site_cookies.json").read_text())
    s.add_cookies(cookies)
    s.goto("https://protected-site.com")
```

## Persistent profile

```python
from stealth_helpers import stealth_session

# Reuse the same browser profile across sessions
with stealth_session(user_data_dir="/tmp/my-profile") as s:
    s.goto("https://chatgpt.com")
    # Login state persists between invocations
```

## One-shot fetch

```python
from stealth_helpers import stealth_fetch

result = stealth_fetch("https://blocked-site.com/page")
if result["ok"]:
    print(result["text"])
```

## StealthPage API

| Method | Description |
|--------|-------------|
| `s.js(expression)` | Evaluate JS, return value. Accepts arrow functions and IIFEs. |
| `s.content()` | Page HTML |
| `s.text()` | Page body text |
| `s.goto(url)` | Navigate and wait |
| `s.screenshot(path)` | Capture screenshot |
| `s.click(selector)` | Click CSS selector |
| `s.fill(selector, value)` | Type into input |
| `s.wait_for_selector(sel)` | Wait for element |
| `s.cookies(urls=None)` | Get cookies |
| `s.add_cookies(cookies)` | Inject cookies (list of dicts) |
| `s.page` | Raw Playwright Page object |
| `s.context` | Raw BrowserContext object |

## Gotchas

- **Console API is disabled.** Patchright disables `Console.enable` to avoid detection. `console.log()` calls in page JS do not fire events. Use `s.js()` for debugging.
- **Chromium only.** No Firefox or WebKit support.
- **Each session launches a browser process.** Reuse sessions rather than creating many short-lived ones. A single session can navigate to many URLs.
- **Headed mode is more reliable.** `headless=False` (default) is harder for bot detectors to identify. Use `headless=True` only when no display is available.
- **`s.js()` accepts full JS expressions** — arrow functions, IIFEs, async/await all work. No SeleniumBase `return` prefix requirement.

## How it works

Patchright patches Playwright at the driver level:
1. Removes `Runtime.enable` CDP command (primary detection vector)
2. Removes `Console.enable` CDP command
3. Adds `--disable-blink-features=AutomationControlled`
4. Removes `--enable-automation` and 12+ other leaky Chrome flags
5. Injects init scripts at network level via Fetch domain (not `Page.addScriptToEvaluateOnNewDocument`)
6. Strips `//# sourceURL=` from evaluated scripts

## Escalation path

Three tiers. The domain skill records which tier works at field-test time:

1. **`curl_cffi`** — impersonates real TLS fingerprint. Sufficient for most sites.
2. **CDP browser** + `solve_turnstile()` — full Chrome rendering. Turnstile solving
   is a fix within this tier, not a separate one. If CDP is detected at the protocol
   level (`Runtime.enable` fingerprints), this tier fails entirely — skip to tier 3.
3. **Patchright** (`stealth_session()`) — different browser backend that avoids
   CDP detection entirely.

If Patchright also fails, the next option is **Camoufox** (`pip install camoufox`).
Camoufox patches Firefox at the C++ level — TLS, canvas, WebGL, audio, and font
fingerprints are all spoofed at the engine level. This is fundamentally harder to
detect than any Chromium-based approach.

## Relationship to Other Skills

- `waf-bypass.md`: Diagnosis and authorized recovery paths before escalating to stealth
- `cookies.md`: Cookie extraction for injection into stealth sessions
- `session-continuity.md`: Long-term auth state management
- Domain skills: Each domain skill documents when stealth is needed for that site
