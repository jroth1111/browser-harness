# Diagnostic Guidance for WAF-Protected Sites

When the standard CDP browser path hits Cloudflare Turnstile, Datadome, Akamai,
or other bot detection, use diagnostic tools to understand the block and attempt
authorized recovery before escalating.

## When to diagnose

- Cloudflare Turnstile blocks that the authority pipeline cannot pass
- Datadome or Akamai blocks detected by `detect_block_page()`
- Sites that detect CDP via Runtime.enable / Console.enable fingerprints
- Any site where the CDP-controlled Chrome gets a "Verify you are human" loop

## When NOT to diagnose

- The standard CDP path works fine (most sites)
- `fetch(source="auto")` successfully retrieves content through the authority pipeline
- HTTP-based extraction is sufficient (no DOM needed)

## Diagnostic approach

1. **Identify the block.** Use `detect_block_page(html=html)` to classify the
   challenge type (Cloudflare, Kasada, Akamai, PerimeterX, Imperva, or generic).
   See `waf-bypass.md` for the full signature table.

2. **Check the authority pipeline result.** `fetch(url, source="auto")` routes
   through the AccessPlane authority pipeline. If it returns a handoff ID instead
   of content, the challenge was not solvable automatically. The handoff ID
   encodes the challenge type for diagnostic purposes.

3. **Try alternative sources.** Use `fetch(url, source="session")` to reuse an
   existing browser session's cookies. If the user has previously completed a
   challenge in their browser, this may carry forward the solved state.

4. **Check for alternative data sources.** Many sites offer APIs, data exports,
   or structured backends that don't trigger WAF challenges. See
   `data-source-exploration.md` for the source discovery workflow.

## Escalation tiers

The authority pipeline and PolicyEngine (risk levels R0-R5) handle most cases.
When they cannot, these tiers are available:

1. **`curl_cffi`** — impersonates real TLS fingerprint. Sufficient for most sites
   that block plain HTTP requests.
2. **CDP browser** — full Chrome rendering through the authority pipeline. If CDP
   is detected at the protocol level (`Runtime.enable` fingerprints), this tier
   fails entirely — skip to tier 3.
3. **Patchright** — different browser backend that avoids CDP detection entirely.
   Use only when the authority pipeline and CDP browser both fail. Patchright
   patches Playwright at the driver level to remove `Runtime.enable`,
   `Console.enable`, and leaky Chrome flags.

If Patchright also fails, the next option is **Camoufox** (`pip install camoufox`).
Camoufox patches Firefox at the C++ level — TLS, canvas, WebGL, audio, and font
fingerprints are all spoofed at the engine level. This is fundamentally harder to
detect than any Chromium-based approach.

## What to report

When all paths fail:

- **Block type** from `detect_block_page()` (vendor + evidence)
- **URL** that triggered the block
- **What was attempted** (authority pipeline result, session fetch, alternative sources)
- **Handoff ID** if the authority pipeline produced one
- **Emit `__UNOBSERVABLE__`** for extraction fields (see `extraction-coverage.md`)

## Gotchas

- **Console API may be disabled** in Patchright sessions. Use JS evaluation for
  debugging rather than relying on console output.
- **Each Patchright session launches a browser process.** Reuse sessions rather
  than creating many short-lived ones.
- **Headed mode is more reliable.** `headless=False` (default) is harder for bot
  detectors to identify.

## Relationship to Other Skills

- `waf-bypass.md`: Diagnosis and authorized recovery paths (start here)
- `cookies.md`: Cookie extraction via `browser_cookies()` (returns redacted
  manifests — names and flags, no values)
- `session-continuity.md`: Long-term auth state management
- Domain skills: Each domain skill documents when diagnostic escalation is needed
  for that site
