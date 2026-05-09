"""Tests for stealth_helpers module (mocked Patchright)."""
import sys
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_page():
    return MagicMock()


@pytest.fixture
def mock_context():
    return MagicMock()


@pytest.fixture
def mock_browser():
    return MagicMock()


@pytest.fixture
def mock_pw():
    pw = MagicMock()
    return pw


class TestStealthPage:
    def test_js_evaluates_and_returns(self, mock_page):
        from browser_harness.stealth_helpers import StealthPage
        mock_page.evaluate.return_value = "hello"
        sp = StealthPage(mock_page, MagicMock(), MagicMock(), MagicMock())
        assert sp.js("document.title") == "hello"
        mock_page.evaluate.assert_called_once_with("document.title")

    def test_content_returns_html(self, mock_page):
        from browser_harness.stealth_helpers import StealthPage
        mock_page.content.return_value = "<html>test</html>"
        sp = StealthPage(mock_page, MagicMock(), MagicMock(), MagicMock())
        assert sp.content() == "<html>test</html>"

    def test_text_returns_body_text(self, mock_page):
        from browser_harness.stealth_helpers import StealthPage
        mock_page.inner_text.return_value = "body text"
        sp = StealthPage(mock_page, MagicMock(), MagicMock(), MagicMock())
        assert sp.text() == "body text"

    def test_goto_navigates(self, mock_page):
        from browser_harness.stealth_helpers import StealthPage
        sp = StealthPage(mock_page, MagicMock(), MagicMock(), MagicMock())
        sp.goto("https://example.com")
        mock_page.goto.assert_called_once_with(
            "https://example.com",
            wait_until="domcontentloaded",
            timeout=30000,
        )

    def test_cookies_returns_list(self, mock_page, mock_context):
        from browser_harness.stealth_helpers import StealthPage
        mock_context.cookies.return_value = [{"name": "cf", "value": "abc"}]
        sp = StealthPage(mock_page, mock_context, MagicMock(), MagicMock())
        assert sp.cookies() == [{"name": "cf", "value": "abc"}]

    def test_add_cookies_delegates(self, mock_page, mock_context):
        from browser_harness.stealth_helpers import StealthPage
        sp = StealthPage(mock_page, mock_context, MagicMock(), MagicMock())
        cookies = [{"name": "session", "value": "xyz"}]
        sp.add_cookies(cookies)
        mock_context.add_cookies.assert_called_once_with(cookies)

    def test_close_idempotent(self, mock_page, mock_context, mock_browser, mock_pw):
        from browser_harness.stealth_helpers import StealthPage
        sp = StealthPage(mock_page, mock_context, mock_browser, mock_pw)
        sp.close()
        sp.close()  # second call is no-op
        mock_browser.close.assert_called_once()

    def test_page_property(self, mock_page):
        from browser_harness.stealth_helpers import StealthPage
        sp = StealthPage(mock_page, MagicMock(), MagicMock(), MagicMock())
        assert sp.page is mock_page

    def test_context_manager(self, mock_page, mock_context, mock_browser, mock_pw):
        from browser_harness.stealth_helpers import StealthPage
        sp = StealthPage(mock_page, mock_context, mock_browser, mock_pw)
        with sp as s:
            assert s is sp
        mock_browser.close.assert_called_once()


class TestStealthSession:
    @patch("browser_harness.stealth_helpers.sync_playwright")
    def test_session_creates_stealth_page(self, mock_sync_pw):
        from browser_harness.stealth_helpers import stealth_session

        mock_pw_instance = MagicMock()
        mock_sync_pw.return_value = mock_pw_instance
        mock_page = MagicMock()
        mock_context = MagicMock()
        mock_context.pages = [mock_page]
        mock_pw_instance.chromium.launch_persistent_context.return_value = mock_context

        with stealth_session() as s:
            assert hasattr(s, "js")
            assert hasattr(s, "goto")

        mock_pw_instance.stop.assert_called()

    @patch("browser_harness.stealth_helpers.sync_playwright")
    def test_session_cleans_up_on_exception(self, mock_sync_pw):
        from browser_harness.stealth_helpers import stealth_session

        mock_pw_instance = MagicMock()
        mock_sync_pw.return_value = mock_pw_instance
        mock_page = MagicMock()
        mock_context = MagicMock()
        mock_context.pages = [mock_page]
        mock_pw_instance.chromium.launch_persistent_context.return_value = mock_context

        with pytest.raises(ValueError):
            with stealth_session() as s:
                raise ValueError("test error")

        mock_pw_instance.stop.assert_called()

    @patch("browser_harness.stealth_helpers.sync_playwright")
    def test_session_with_channel(self, mock_sync_pw):
        from browser_harness.stealth_helpers import stealth_session

        mock_pw_instance = MagicMock()
        mock_sync_pw.return_value = mock_pw_instance
        mock_page = MagicMock()
        mock_context = MagicMock()
        mock_context.pages = [mock_page]
        mock_pw_instance.chromium.launch_persistent_context.return_value = mock_context

        with stealth_session(channel="chrome") as s:
            pass

        call_kwargs = mock_pw_instance.chromium.launch_persistent_context.call_args[1]
        assert call_kwargs["channel"] == "chrome"
        assert "--disable-blink-features=AutomationControlled" in call_kwargs["args"]

    @patch("browser_harness.stealth_helpers.sync_playwright")
    def test_session_no_viewport(self, mock_sync_pw):
        from browser_harness.stealth_helpers import stealth_session

        mock_pw_instance = MagicMock()
        mock_sync_pw.return_value = mock_pw_instance
        mock_page = MagicMock()
        mock_context = MagicMock()
        mock_context.pages = [mock_page]
        mock_pw_instance.chromium.launch_persistent_context.return_value = mock_context

        with stealth_session() as s:
            pass

        call_kwargs = mock_pw_instance.chromium.launch_persistent_context.call_args[1]
        assert call_kwargs["no_viewport"] is True


class TestStealthFetch:
    @patch("browser_harness.stealth_helpers.sync_playwright")
    def test_fetch_returns_status_dict(self, mock_sync_pw):
        from browser_harness.stealth_helpers import stealth_fetch

        mock_pw_instance = MagicMock()
        mock_sync_pw.return_value = mock_pw_instance
        mock_page = MagicMock()
        mock_page.url = "https://example.com/page"
        mock_page.inner_text.return_value = "x" * 300
        mock_page.content.return_value = "<html>content</html>"
        mock_context = MagicMock()
        mock_context.pages = [mock_page]
        mock_pw_instance.chromium.launch_persistent_context.return_value = mock_context

        result = stealth_fetch("https://example.com/page")

        assert result["ok"] is True
        assert result["textLength"] == 300
        assert result["block"]["blocked"] is False
        assert result["url"] == "https://example.com/page"

    @patch("browser_harness.stealth_helpers.sync_playwright")
    def test_fetch_detects_block(self, mock_sync_pw):
        from browser_harness.stealth_helpers import stealth_fetch

        mock_pw_instance = MagicMock()
        mock_sync_pw.return_value = mock_pw_instance
        mock_page = MagicMock()
        mock_page.url = "https://example.com/blocked"
        mock_page.inner_text.return_value = "short"
        mock_page.content.return_value = "<html>blocked</html>"
        mock_context = MagicMock()
        mock_context.pages = [mock_page]
        mock_pw_instance.chromium.launch_persistent_context.return_value = mock_context

        result = stealth_fetch("https://example.com/blocked")

        assert result["ok"] is False
        assert result["block"]["blocked"] is True
