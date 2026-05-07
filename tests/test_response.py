from browser_harness.response import Response, _MAX_RESPONSE_CHARS


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


# --- Extraction helpers ---


def test_next_data_extracts_json():
    html = '<html><script id="__NEXT_DATA__">{"props":{"pageProps":{"items":[1,2,3]}}}</script></html>'
    r = Response(html=html, text="", url="https://x.com", status=200, source="http")
    assert r.next_data() == {"props": {"pageProps": {"items": [1, 2, 3]}}}


def test_next_data_handles_flexible_script_attributes():
    html = (
        "<html><script nonce='abc' type='application/json' "
        "id='__NEXT_DATA__'>{\"props\":{\"pageProps\":{\"ok\":true}}}</script></html>"
    )
    r = Response(html=html, text="", url="https://x.com", status=200, source="http")
    assert r.next_data() == {"props": {"pageProps": {"ok": True}}}


def test_next_data_returns_none_when_absent():
    r = Response(html="<p>no next data</p>", text="x", url="https://x.com",
                 status=200, source="http")
    assert r.next_data() is None


def test_next_data_returns_none_for_malformed_json():
    html = '<script id="__NEXT_DATA__">{"props":</script>'
    r = Response(html=html, text="", url="https://x.com", status=200, source="http")
    assert r.next_data() is None


def test_json_ld_extracts_blocks():
    html = '<script type="application/ld+json">{"@type":"Product","name":"Widget"}</script>'
    r = Response(html=html, text="", url="https://x.com", status=200, source="http")
    results = r.json_ld()
    assert len(results) == 1
    assert results[0]["name"] == "Widget"


def test_json_ld_handles_flexible_script_attributes():
    html = "<script nonce='abc' data-rh='true' type='application/ld+json'>{\"@type\":\"Product\",\"name\":\"Widget\"}</script>"
    r = Response(html=html, text="", url="https://x.com", status=200, source="http")
    assert r.json_ld("Product")[0]["name"] == "Widget"


def test_json_ld_filters_by_type():
    html = (
        '<script type="application/ld+json">{"@type":"Product","name":"A"}</script>'
        '<script type="application/ld+json">{"@type":"BreadcrumbList","name":"B"}</script>'
    )
    r = Response(html=html, text="", url="https://x.com", status=200, source="http")
    products = r.json_ld("Product")
    assert len(products) == 1
    assert products[0]["name"] == "A"


def test_json_ld_handles_array_with_type_filter():
    html = '<script type="application/ld+json">[{"@type":"Product","name":"A"},{"@type":"Review","name":"B"}]</script>'
    r = Response(html=html, text="", url="https://x.com", status=200, source="http")
    products = r.json_ld("Product")
    assert len(products) == 1
    assert products[0]["name"] == "A"


def test_json_ld_handles_string_type():
    html = '<script type="application/ld+json">{"@type":"Product","name":"Widget"}</script>'
    r = Response(html=html, text="", url="https://x.com", status=200, source="http")
    products = r.json_ld("Product")
    assert len(products) == 1


def test_json_ld_returns_empty_when_absent():
    r = Response(html="<p>no json-ld</p>", text="x", url="https://x.com",
                 status=200, source="http")
    assert r.json_ld() == []


def test_json_ld_skips_invalid_json():
    html = (
        '<script type="application/ld+json">{"@type":"Product","name":"A"}</script>'
        '<script type="application/ld+json">NOT JSON</script>'
    )
    r = Response(html=html, text="", url="https://x.com", status=200, source="http")
    assert len(r.json_ld()) == 1


def test_embedded_json_extracts_window_assignment():
    html = '<script>window.MY_DATA={"key": "value"};</script>'
    r = Response(html=html, text="", url="https://x.com", status=200, source="http")
    assert r.embedded_json("MY_DATA") == {"key": "value"}


def test_embedded_json_handles_whitespace_aliases_and_arrays():
    html = "<script>globalThis.MY_DATA = [{\"key\": \"value\"}, {\"nested\": [1, 2]}];</script>"
    r = Response(html=html, text="", url="https://x.com", status=200, source="http")
    assert r.embedded_json("MY_DATA") == [{"key": "value"}, {"nested": [1, 2]}]


def test_embedded_json_handles_bare_assignment():
    html = "<script>MY_DATA = {\"text\": \"brace } in string\"};</script>"
    r = Response(html=html, text="", url="https://x.com", status=200, source="http")
    assert r.embedded_json("MY_DATA") == {"text": "brace } in string"}


def test_embedded_json_returns_none_when_absent():
    r = Response(html="<p>no js</p>", text="x", url="https://x.com",
                 status=200, source="http")
    assert r.embedded_json("MY_DATA") is None


def test_embedded_json_returns_none_for_malformed_assignment():
    html = "<script>window.MY_DATA={\"key\": };</script>"
    r = Response(html=html, text="", url="https://x.com", status=200, source="http")
    assert r.embedded_json("MY_DATA") is None
