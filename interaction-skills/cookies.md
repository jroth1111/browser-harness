# Cookies

Cookies are browser session state. Treat them as sensitive and task-local:
inspect them only when needed, never print full values in normal output, and
never commit captured cookies to domain skills or tests.

## Same-domain HTTP with browser cookies

Use `http_get_browser_session(url)` after the attached browser has already loaded
the site successfully. It reads the browser user agent and matching cookies, then
does a direct HTTP GET.

```python
new_tab("https://www.realestate.com.au/")
wait_for_load()
status = wait_for_content(min_text=500, timeout=20)
if not status["ok"]:
    raise RuntimeError(status["block"])

html = http_get_browser_session("https://www.realestate.com.au/buy/in-melbourne,+vic+3000/list-1")
print(len(html), detect_block_page(html=html))
```

Rules:

- Use this for same-domain fetches after a real browser has passed a challenge.
- It does not solve challenges on its own; invalid or absent cookies still return block pages.
- Cookie matching is domain/path/secure filtered for the target URL.
- Do not use broad manual `Cookie` headers that send one site's cookies to another site.

## Cookie inspection

```python
cookies = browser_cookies(["https://www.realestate.com.au/"])
print([{"name": c["name"], "domain": c.get("domain"), "path": c.get("path")} for c in cookies])
```

Log names/domains/paths only unless the user explicitly asks for raw cookie
values for a local debugging task.
