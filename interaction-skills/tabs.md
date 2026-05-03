# Tabs

Use **CDP for control**, **UI automation for user-visible order**.

## Pure CDP (portable: macOS / Linux / Windows)

```python
tabs = list_tabs()                    # includes chrome:// pages too
real_tabs = list_tabs(include_chrome=False)
tid = new_tab("https://example.com")  # create + attach
switch_tab(tid)                       # attach harness to tab
cdp("Target.activateTarget", targetId=tid)  # show it in Chrome
close_tab(tid)                        # close by targetId or tab dict
close_tab()                           # close current tab, then attach to another real tab if possible
close_tabs([tid])                     # close many task-owned tabs
print(current_tab())
print(page_info())
```

What CDP is good at:
- attach to a tab
- open a tab
- close a known tab
- activate a known target
- inspect URL/title/viewport
- capture the attached tab's screenshot even if another tab is visibly frontmost

What CDP is bad at:
- matching the **left-to-right tab strip order** the user sees
- telling whether the attached target is an omnibox popup / internal page without URL filtering

## Visible order (platform UI)

### macOS

```applescript
tell application "Google Chrome"
  set out to {}
  set i to 1
  repeat with t in every tab of front window
    set end of out to {tab_index:i, tab_title:(title of t), tab_url:(URL of t)}
    set i to i + 1
  end repeat
  return out
end tell
```

```applescript
tell application "Google Chrome"
  set active tab index of front window to 2
  activate
end tell
```

### Linux

No AppleScript. Same split still applies:
- use CDP for `new_tab`, attach, inspect, activate known targets
- use window-manager / browser UI automation when the user means visible order

Typical tools:
- `xdotool`
- `wmctrl`
- desktop-environment scripting (`gdbus`, KWin, GNOME Shell extensions, etc.)

## Rules that held up in practice

- `switch_tab()` is **not enough** if the user expects Chrome to visibly change.
- `Target.activateTarget` is the CDP-side "show this tab".
- `list_tabs()` includes `chrome://newtab/` by default; ask for `include_chrome=False` when you want only real pages.
- `chrome://omnibox-popup.top-chrome/` can appear as a fake page target; ignore it for user-facing tab lists.
- If a page has `w=0 h=0`, you may be attached to the wrong target or a non-window surface.
- For dynamic UIs, re-read element rects after opening dropdowns / modals before coordinate-clicking.

## Robust tab ownership for research/scraping

Open as many tabs as the task needs, but make ownership explicit. The harness is
attached to the user's real Chrome, so the safe invariant is: track target IDs you
created, close only those target IDs unless the user asks otherwise, and restore a
valid attached session after cleanup.

Use one of these patterns when a task opens browser state:

```python
# Pattern A: many tabs, explicit task-owned cleanup
opened = []
try:
    for url in urls:
        tid = new_tab(url)
        opened.append(tid)
        wait_for_load()
        # Extract what you need now, or switch back to this target later.
        text = js("document.body.innerText.slice(0, 4000)")
        print(text)
finally:
    close_tabs(opened)
```

```python
# Pattern B: keep tabs open during cross-page comparison, then clean up
opened = [new_tab(url) for url in urls]
try:
    for tid in opened:
        switch_tab(tid)
        wait_for_load()
        print(page_info())
finally:
    close_tabs(opened)
```

```python
# Pattern C: reusable scratch tab when preserving parallel tabs is not useful
tid = new_tab("about:blank")
try:
    for url in urls:
        switch_tab(tid)
        goto_url(url)
        wait_for_load()
        print(js("document.body.innerText.slice(0, 4000)"))
finally:
    close_tab(tid)
```

```python
# Pattern D: close each evidence tab immediately after extraction
for url in urls:
    tid = new_tab(url)
    wait_for_load()
    try:
        print(js("document.body.innerText.slice(0, 4000)"))
    finally:
        close_tab(tid)
```

Rules:

- Do not bias against opening tabs. Bias toward knowing which tabs are task-owned.
- Record every `targetId` returned by `new_tab()` before doing work that may fail.
- Use `try/finally` around browser work so cleanup runs after errors.
- Close result/evidence tabs after extracting text, screenshots, or source URLs unless the user asked to preserve them.
- Use `list_tabs(include_chrome=False)` before and after a large scrape to confirm you did not leak tabs.
- Do not close tabs that pre-existed the task unless the user asked you to clean the browser. Track target IDs you opened and close only those.
- If you close the attached tab, `close_tab()` and `close_tabs()` re-attach to another real tab when one exists. This avoids the next non-Target CDP command hitting a stale session.

## Non-Chrome CDP backend caveats

Some CDP-compatible browsers do not implement Chrome's full multi-target model.
Treat this as capability detection, not a reason to avoid tabs on Chrome.

Lightpanda nightly `1.0.0-nightly.5816+a578f4d6` on 2026-04-27:

- `Target.createTarget` can fail with `TargetAlreadyLoaded`; use `goto_url()` on the current target for sequential extraction, or use Chrome when the task requires true parallel tabs.
- `Target.getTargetInfo` can report `about:blank` even when `location.href` and the DOM are on the navigated page. Use `js("location.href")` and `js("document.title")` to verify page identity.
- `list_tabs()` may report a frame-like target ID while `current_tab()` reports `TID-STARTUP`; avoid visible-order assumptions on this backend.
