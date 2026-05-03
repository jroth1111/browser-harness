from response import Response, _MAX_RESPONSE_CHARS


def test_small_response_not_truncated():
    r = Response(html="<p>hi</p>", text="hi", url="https://x.com",
                 status=200, source="http")
    assert r.html == "<p>hi</p>"
    assert r.text == "hi"
    assert not r.truncated


def test_oversized_html_truncated():
    big = "x" * (_MAX_RESPONSE_CHARS + 1000)
    r = Response(html=big, text="ok", url="https://x.com",
                 status=200, source="http")
    assert len(r.html) == _MAX_RESPONSE_CHARS
    assert r.text == "ok"
    assert r.truncated


def test_oversized_text_truncated():
    big = "y" * (_MAX_RESPONSE_CHARS + 500)
    r = Response(html="<p/>", text=big, url="https://x.com",
                 status=200, source="http")
    assert len(r.text) == _MAX_RESPONSE_CHARS
    assert r.truncated


def test_exactly_at_limit_not_truncated():
    exact = "z" * _MAX_RESPONSE_CHARS
    r = Response(html=exact, text=exact, url="https://x.com",
                 status=200, source="http")
    assert len(r.html) == _MAX_RESPONSE_CHARS
    assert len(r.text) == _MAX_RESPONSE_CHARS
    assert not r.truncated


def test_summary_includes_truncated_flag():
    r = Response(html="x" * (_MAX_RESPONSE_CHARS + 1), text="", url="https://x.com",
                 status=200, source="browser")
    s = r.summary()
    assert "truncated" in s
    assert "browser" in s


def test_summary_omits_truncated_when_false():
    r = Response(html="ok", text="ok", url="https://x.com",
                 status=200, source="http")
    assert "truncated" not in r.summary()


def test_repr_matches_summary():
    r = Response(html="a", text="b", url="https://x.com",
                 status=200, source="http")
    assert repr(r) == r.summary()


def test_none_html_text_handled():
    r = Response(html=None, text=None, url="", status=0, source="auto")
    assert r.html == ""
    assert r.text == ""
    assert not r.truncated
