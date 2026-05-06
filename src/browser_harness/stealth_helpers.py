"""Patchright-based stealth browser for Cloudflare/WAF-protected sites.

Uses Patchright (patched Playwright) to launch a stealth Chromium that passes
Cloudflare Turnstile, Datadome, Akamai, and other bot detection. Patchright
avoids Runtime.enable and Console.enable CDP commands — the primary vectors
for automation detection.

Usage from scripts:
    from .stealth_helpers import stealth_session
    with stealth_session() as s:
        s.goto("https://chatgpt.com/c/abc123")
        html = s.content()
        text = s.text()
"""
import atexit
import tempfile
from pathlib import Path

try:
    from patchright.sync_api import sync_playwright
except ModuleNotFoundError:
    def sync_playwright():
        raise ModuleNotFoundError(
            "patchright is required for stealth browser sessions; "
            "install the stealth dependency group"
        )


class StealthPage:
    """Wraps a Patchright Page with helpers.py-flavored methods."""

    def __init__(self, page, context, browser, pw):
        self._page = page
        self._context = context
        self._browser = browser
        self._pw = pw
        self._closed = False

    def js(self, expression):
        return self._page.evaluate(expression)

    def content(self):
        return self._page.content()

    def text(self):
        return self._page.inner_text("body")

    def goto(self, url, wait_until="domcontentloaded", timeout=30000):
        self._page.goto(url, wait_until=wait_until, timeout=timeout)

    def screenshot(self, path):
        self._page.screenshot(path=path)

    def click(self, selector):
        self._page.click(selector)

    def fill(self, selector, value):
        self._page.fill(selector, value)

    def wait_for_selector(self, selector, timeout=10000):
        return self._page.wait_for_selector(selector, timeout=timeout)

    def cookies(self, urls=None):
        return self._context.cookies(urls)

    def add_cookies(self, cookies):
        self._context.add_cookies(cookies)

    @property
    def page(self):
        return self._page

    @property
    def context(self):
        return self._context

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            self._browser.close()
        except Exception:
            pass
        try:
            self._pw.stop()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class _StealthSession:
    """Context manager for stealth_session()."""

    def __init__(self, headless, user_data_dir, channel):
        self._headless = headless
        self._user_data_dir = user_data_dir
        self._channel = channel
        self._temp_dir = None
        self._stealth_page = None

    def __enter__(self):
        manager = sync_playwright()
        pw = manager if "chromium" in dir(manager) else manager.start()

        udd = self._user_data_dir
        if udd is None:
            self._temp_dir = tempfile.mkdtemp(prefix="patchright-")
            udd = self._temp_dir

        launch_kwargs = {
            "user_data_dir": str(udd),
            "headless": self._headless,
            "no_viewport": True,
            "args": ["--disable-blink-features=AutomationControlled"],
        }
        if self._channel:
            launch_kwargs["channel"] = self._channel

        context = pw.chromium.launch_persistent_context(**launch_kwargs)
        page = context.pages[0] if context.pages else context.new_page()

        self._stealth_page = StealthPage(page, context, context, pw)
        atexit.register(self._cleanup)
        return self._stealth_page

    def __exit__(self, *exc):
        self._cleanup()

    def _cleanup(self):
        if self._stealth_page:
            self._stealth_page.close()
            self._stealth_page = None
        if self._temp_dir:
            import shutil
            shutil.rmtree(self._temp_dir, ignore_errors=True)
            self._temp_dir = None


def stealth_session(headless=False, user_data_dir=None, channel=None):
    """Launch a Patchright stealth browser session.

    Yields a StealthPage with goto/js/content/cookies methods.
    Browser process is cleaned up on context exit.

    Args:
        headless: Run in headless mode (headed is more reliable against detection).
        user_data_dir: Persist browser profile here. None = temporary (deleted on exit).
        channel: Browser channel, e.g. "chrome" to use system Chrome.
    """
    return _StealthSession(headless, user_data_dir, channel)


def stealth_fetch(url, wait_until="domcontentloaded", timeout=30000):
    """One-shot fetch: open URL in stealth browser, return page status dict.

    Returns dict matching helpers.page_content_status() shape:
        {ok, text, html, url, textLength}
    """
    with stealth_session(headless=True) as s:
        s.goto(url, wait_until=wait_until, timeout=timeout)
        html = s.content()
        text = s.text()
        page_url = s.page.url
    text_len = len(text) if text else 0
    return {
        "ok": text_len > 200,
        "text": text,
        "html": html,
        "url": page_url,
        "textLength": text_len,
        "block": text_len < 200,
    }
