# Connection & Tab Visibility

## The omnibox popup problem

When Chrome opens fresh, the only CDP `type: "page"` targets are `chrome://inspect` and `chrome://omnibox-popup.top-chrome/` (a 1px invisible viewport). If the daemon attaches to the omnibox popup, all subsequent work — including `new_tab()` and `goto_url()` — happens on tabs that exist in CDP but may not be visible in the Chrome UI.

The daemon handles this internally by creating an `about:blank` tab when no real pages exist. If you still end up on an invisible tab, use `switch_tab()` which calls `Target.activateTarget` to bring the tab to front.

## Startup sequence

`run.py` starts the daemon automatically before executing any code — you never call
`ensure_daemon()` or `daemon_alive()` yourself. If `browser-harness --doctor` reports
problems, the daemon socket may be stale. The socket lives at `/tmp/bh-default.sock`
(or `/tmp/bh-{name}.sock` when `BH_NAME` is set).

If you need to recover from a stale daemon manually:

```bash
browser-harness --doctor
```

For tab-level recovery from a helper script:

```python
tabs = list_tabs()
for t in tabs:
    print(t["url"][:60])

tab = ensure_real_tab()
```

## Bringing Chrome to front

If Chrome is behind other windows or on another desktop:

```python
import subprocess
subprocess.run(["osascript", "-e", 'tell application "Google Chrome" to activate'])
```

## Navigating

Prefer navigating an existing tab over `new_tab()`. Tabs created via CDP's `Target.createTarget` are visible but may open behind the active tab.

```python
tab = ensure_real_tab()
goto_url("https://example.com")
```
