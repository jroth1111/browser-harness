"""Response wrapper with lazy lxml parsing for CSS/XPath queries."""


class Response:
    """Query wrapper around fetched HTML.

    Returned by ``fetch()`` in helpers.py. Lazily parses HTML on first
    ``.css()`` / ``.xpath()`` call so plain-text-only usage pays zero
    lxml overhead.
    """

    def __init__(self, html, text, url, status, source, headers=None, encoding="utf-8"):
        self.html = html or ""
        self.text = text or ""
        self.url = url
        self.status = status
        self.source = source  # "http" | "session" | "browser" | "auto"
        self.headers = headers or {}
        self.encoding = encoding
        self._tree = None

    @property
    def tree(self):
        """Parsed lxml tree. Built on first access."""
        if self._tree is None:
            from lxml.html import fromstring, HTMLParser

            self._tree = fromstring(
                self.html or "<html><body></body></html>",
                parser=HTMLParser(recover=True, encoding="utf-8"),
            )
        return self._tree

    def css(self, selector):
        """Return list of lxml Elements matching *selector*."""
        return self.tree.cssselect(selector)

    def css_text(self, selector):
        """Return list of stripped text content for elements matching *selector*."""
        return [el.text_content().strip() for el in self.css(selector)]

    def xpath(self, expr):
        """Return list of lxml Elements matching *expr*."""
        return self.tree.xpath(expr)

    def xpath_text(self, expr):
        """Return list of stripped text content for elements matching *expr*."""
        return [
            el.text_content().strip() if hasattr(el, "text_content") else str(el).strip()
            for el in self.xpath(expr)
        ]

    def __repr__(self):
        return (
            f"Response(url={self.url!r}, status={self.status}, "
            f"source={self.source!r}, html={len(self.html)}, text={len(self.text)})"
        )
