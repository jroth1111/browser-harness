# Backend Capability

Use this when a page is "loaded" but contains no useful content, or when a
non-Chrome backend such as Lightpanda or headless Chrome behaves differently from
the user's persistent browser.

## Diagnose before selectors

`wait_for_load()` only proves the browser saw a load event. It does not prove the
site served the application page. Protected sites can return a small challenge or
access-denied shell with `document.readyState == "complete"`.

```python
diag = diagnose_url_capability(
    "https://example.com/protected/page",
    min_text=500,
    timeout=20,
)
print(diag["backend"]["kind"], diag["reason"], diag["block"], diag["recommendation"])
```

Result shape:

```python
{
    "ok": False,
    "reason": "blocked",
    "block": {"blocked": True, "kind": "kasada_kpsdk", "evidence": [...]},
    "backend": {"kind": "headless_chrome", "risks": [...]},
    "recommendation": "...",
}
```

If `reason == "blocked"`, stop debugging selectors. The page did not serve the
content you are trying to extract.

## Backend meanings

- `chromium`: Chrome/Chromium/Edge-like backend. A persistent headful profile may
  have enough profile state and browser surface for protected sites.
- `headless_chrome`: Chromium engine, but common fingerprint and profile-state
  differences can still trigger challenges.
- `lightpanda`: useful for fast DOM/JS pages, but not a full Chrome rendering and
  fingerprint surface.
- `unknown`: run the diagnostic and rely on the served/blocked result.

## Backend-invariant extraction

Backend choice is an implementation detail, not a data-shape choice. For the
same URL, auth state, date range, filters, device, currency, and observation
window, every supported backend must produce the same canonical records after
normalization. Equivalent output does not require byte-identical DOM; it requires
the same required fields, ordering semantics, prices, IDs, availability signals,
and confidence classification for the workflow.

Treat a backend as unsupported for a source when it loads a page but cannot
produce the workflow's required fields. Do not silently emit a weaker dataset
from the cheaper backend.

Capability is scoped to a source context: domain/origin, auth state, account
scope, date range, filters, currency, device, and observation window. A backend
that works for one domain or public/auth state is not proven for another.

Use field-level acceptance gates:

- page-level success: load event, title, non-empty `innerText`, HTTP/UI status
- field-level success: required selectors/text/API fields are present and
  attributable to the requested source context
- canonical success: extracted fields normalize to the same schema as the
  reference backend or export

For Lightpanda-specific CDP runs, use `lightpanda_control.evaluate_field_contract`
or `wait_for_field_contract` to check named required fields instead of accepting
non-empty page text.

Example:

```python
from lightpanda_control import wait_for_field_contract

result = wait_for_field_contract(
    client,
    {
        "item_links": 'document.querySelectorAll("a[href*=items]").length > 0',
        "prices": '/\\$[\\d,]+/.test(document.body.innerText)',
    },
    min_text=500,
    timeout=20,
)
if not result["ok"]:
    raise RuntimeError(("backend_capability_failed", result["missing"], result["page"]))
```

## Solved-session bridge

When a persistent headful browser can load a protected site but a lightweight
backend cannot, use the headful profile to seed/fetch the HTML or API data, then
hand extracted data to the lightweight workflow.

```python
result = fetch_with_browser_session(
    "https://example.com/protected/page",
    seed_url="https://example.com/",
    retries=1,
)
if not result["ok"]:
    raise RuntimeError((result["reason"], result["block"], result["attempts"]))
html = result["text"]
```

`fetch_with_browser_session()` is still same-domain cookie reuse, not a challenge
solver. If the seed browser cannot load useful content, the backend is not
capable for that domain/session.

## Concrete example

For `realestate.com.au`, fresh headless Chrome and Lightpanda have been observed
to return a Kasada/KPSDK shell. The domain-specific URLs, field order, and
Argonaut payload keys live in `domain-skills/realestate-com-au/scraping.md`; the
general diagnosis and solved-session mechanics belong here.
