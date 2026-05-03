# UI Mechanics

Quick guidance for browser UI mechanics. For the full helper API, see
`docs/reference.md`.

## Page load timing

For extraction workflows, prefer `wait_for_content()` over `wait_for_load()` +
fixed delay. `wait_for_content(min_text=200)` polls until meaningful content
appears AND detects WAF blocks — it replaces both the load wait and the fixed
delay. See `extraction-coverage.md` for the full readiness sequence.

`wait_for_load()` is appropriate when you only need the load event (clicking
buttons, checking URL redirects) and don't need to verify content rendered.

If `capture_screenshot()` shows empty or partially-loaded content after
`wait_for_load()`, use `wait_for_content()` instead of adding a fixed delay.
Observed delays by domain: Amazon 2s, Letterboxd 2s, Airbnb 0.4-2s
depending on page.

## Interaction vs extraction

Use coordinate clicks (`click_at_xy`) for **interaction** — clicking buttons,
navigating, submitting forms, selecting options. Coordinate clicks bypass
iframes, Shadow DOM, and complex DOM structures.

Use CSS selectors (`querySelector`/`querySelectorAll`) for **extraction** —
reading structured data from the DOM. Selectors are the primary tool for data
extraction because they provide precise field-level access to text content,
attributes, and nested structures.

The "no selector hunt" rule applies to clicking, not to data extraction. When
extracting data, investing in the right selector is worthwhile because it runs
reliably across many pages. When clicking a button, coordinates are faster and
more robust than selector-based approaches.

## Cross-page data accumulation via localStorage

When paginating through search results or navigating between pages that destroy
JavaScript state (full page loads), accumulate extracted data in `localStorage`
rather than `window` variables. `localStorage` survives full page navigations;
`window` variables do not.

Pattern (three JS functions executed via `js()`):

```javascript
// 1. Extract + accumulate (run after each page load)
() => {
  const stored = localStorage.getItem('__results');
  const results = stored ? JSON.parse(stored) : [];
  const existing = new Set(results.map(r => r.id));
  // ... extract new items from DOM ...
  const newItems = [...document.querySelectorAll(selector)]
    .map(el => ({ id: el.dataset.id, title: el.textContent }))
    .filter(item => !existing.has(item.id));
  results.push(...newItems);
  localStorage.setItem('__results', JSON.stringify(results));
  return newItems.length;
}

// 2. Dump accumulated results (run after all pages visited)
() => JSON.parse(localStorage.getItem('__results') || '[]')

// 3. Reset before starting a new search
() => { localStorage.removeItem('__results'); return true; }
```

This pattern works on any site where you navigate between pages and need to
preserve data across navigations.

**Durability limits:** localStorage is same-origin scoped and tab-attached.
Data is lost when the tab closes or navigates cross-origin. Dump accumulated
results before closing tabs — don't wait until the entire crawl finishes.
For multi-level crawls, dump after each level completes.

**Quota overflow:** localStorage has a ~5MB limit per origin. Accumulation
snippets that silently fill it lose all data. Guard every `setItem` call:

```javascript
try { localStorage.setItem(key, JSON.stringify(results)); }
catch (e) {
  return { total: results.length, added: added, url: location.href,
           _quota_error: true, _message: 'localStorage quota exceeded — dump now' };
}
```

When `_quota_error` appears, immediately run the dump snippet and clear
before continuing. Lost data is unrecoverable.

## Concurrent tabs

`new_tab()` creates a new CDP target but only one tab receives CDP events
at a time (the daemon tracks a single `_tid`). Opening multiple tabs without
extracting from the first causes the daemon to switch context, and
`close_tab()` switches back to a potentially different tab than expected.

**Rule:** one tab per extraction workflow. Open, extract, dump localStorage,
close — then move to the next tab. Never accumulate open tabs hoping to
return to them later.

## Screenshots

Separate full-page screenshots from targeted section screenshots, and note when
screenshots are only for discovery versus verification.

Helpers: `capture_screenshot(path, full)`, `capture_screenshot_trace(directory, frames, interval, full)`.

## Scrolling

Separate page scroll, nested containers, virtualized lists, and dropdown menus.
Identify which element is actually consuming wheel events before scrolling.

Helper: `scroll(x, y, dy, dx)`.

## Viewport

Viewport size changes affect layout and coordinate clicks. Any workflow that
depends on stable geometry should check `page_info()` for current dimensions.

## Downloads

Separate browser-triggered downloads from direct `http_get(...)` fetches.
Document the minimal signals that prove a download actually started.

## Print as PDF

Cover both direct PDF generation via CDP and sites that only expose a visible
"Print" button which must be clicked before handling the browser print flow.

## Drag and Drop

Focus on when drag-and-drop can be driven with low-level input events versus
when the site really expects a file upload or DOM-specific drag sequence.
Coordinate clicks via `click_at_xy()` often handle drag targets without DOM
traversal.

## Uploads

Helper: `upload_file(selector, path)`. Uses CDP `DOM.setFileInputFiles`. The
`path` argument must be absolute (use `tempfile.mkstemp` if needed).

## Dropdowns

Split dropdowns into native selects, custom overlays, searchable comboboxes, and
virtualized menus. Always re-measure after opening because option geometry often
appears late.

## Iframes (same-origin)

Cover same-origin iframe traversal through `contentDocument` / `contentWindow`,
and keep the frame-local versus page-coordinate warning explicit for clicks.

Helper: `iframe_target(url_substr)` returns the first iframe target whose URL
contains `url_substr`. Use with `js(..., target_id=...)` for DOM inspection
inside the iframe.

## Cross-Origin Iframes

Focus on `iframe_target(url_substr)`, target attachment, and when compositor-level
coordinate clicks (`click_at_xy`) are lower-friction than cross-target DOM work.
Compositor clicks pass through cross-origin boundaries without extra handling.

## Shadow DOM

Focus on recursive `shadowRoot` traversal, and note when coordinate clicking is
simpler than piercing deeply nested component trees.

## Network Requests

Watch or infer network activity when page state is ambiguous, especially for
submit flows, downloads, and SPA actions that succeed without obvious DOM changes.

Helper: `drain_events()` returns buffered CDP events from the daemon. The daemon
buffers up to 500 events including `Page.javascriptDialogOpening`,
`Page.loadEventFired`, and all other CDP domain events.
