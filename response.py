"""Response wrapper with lazy lxml parsing for CSS/XPath queries."""

_MAX_RESPONSE_CHARS = 2 * 1024 * 1024  # 2MB


class Response:
    """Query wrapper around fetched HTML.

    Returned by ``fetch()`` in helpers.py. Lazily parses HTML on first
    ``.css()`` / ``.xpath()`` call so plain-text-only usage pays zero
    lxml overhead. HTML and text are truncated at 2MB; set ``truncated``
    when either field was cut.
    """

    def __init__(self, html, text, url, status, source, headers=None,
                 encoding="utf-8", turnstile_solved=False, reason=None,
                 block=None):
        raw_html = html or ""
        raw_text = text or ""
        self.html = raw_html[:_MAX_RESPONSE_CHARS]
        self.text = raw_text[:_MAX_RESPONSE_CHARS]
        self.truncated = len(raw_html) > _MAX_RESPONSE_CHARS or len(raw_text) > _MAX_RESPONSE_CHARS
        self.url = url or ""
        self.status = status
        self.source = source  # "http" | "session" | "browser" | "auto"
        self.headers = headers or {}
        self.encoding = encoding
        self.turnstile_solved = turnstile_solved
        self.reason = reason
        self.block = block or {"blocked": False, "kind": None, "evidence": []}
        self._tree = None

    @property
    def tree(self):
        """Parsed lxml tree. Built on first access."""
        if self._tree is None:
            from lxml.html import fromstring, HTMLParser
            try:
                self._tree = fromstring(
                    self.html.strip() or "<html><body></body></html>",
                    parser=HTMLParser(recover=True, encoding="utf-8"),
                )
            except Exception as e:
                raise RuntimeError(
                    f"HTML parse failed for {self.url} (source={self.source}, "
                    f"html={len(self.html)} chars): {e}"
                ) from e
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

    def summary(self):
        return (
            f"Response(url={self.url!r}, status={self.status}, "
            f"source={self.source!r}, html={len(self.html)}, text={len(self.text)}"
            f"{', reason=' + repr(self.reason) if self.reason else ''}"
            f"{', truncated' if self.truncated else ''})"
        )

    def __repr__(self):
        return self.summary()
