from xml.etree.ElementTree import Element

import pytest

from air.tags._html import compact_html, local_name, parse_html, serialize_html  # noqa: PLC2701


def test_pretty_fragment_preserves_leading_text() -> None:
    root = Element("DOCUMENT_FRAGMENT")
    root.text = "before"
    root.append(Element("span"))

    assert serialize_html(root, pretty=True) == "before<span></span>\n"


def test_compact_html_removes_comments_without_losing_tails() -> None:
    source = "<div>a<!-- first --> b<span>c</span><!-- second --> d</div>"

    result = compact_html(source, document=False)

    assert "<!--" not in result
    assert "a b" in result
    assert "</span> d" in result


def test_compact_html_preserves_document_doctype() -> None:
    source = "<!doctype html><html><body><p>x</p></body></html>"

    assert compact_html(source, document=True).startswith("<!doctype html><html>")


def test_compact_html_preserves_nonbreaking_space() -> None:
    source = "<p>a&nbsp;b</p>"

    assert compact_html(source, document=False) == "<p>a\u00a0b</p>"


def test_compact_html_does_not_turn_escaped_noscript_text_into_markup() -> None:
    source = "<noscript>&lt;/noscript&gt;&lt;script&gt;alert(1)&lt;/script&gt;</noscript>"

    assert compact_html(source, document=False) == source


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ('<script>const marker = "<!--keep-->";</script>', "<!--keep-->"),
        ('<div data-marker="<!--keep-->">x</div>', "&lt;!--keep-->"),
        ("<textarea><!--keep--></textarea>", "&lt;!--keep--&gt;"),
    ],
)
def test_compact_html_preserves_comment_syntax_in_content(source: str, expected: str) -> None:
    result = compact_html(source, document=False)

    assert expected in result


def test_malformed_svg_falls_back_to_html5_parser() -> None:
    root = parse_html("<image><broken", document=False)

    assert local_name(root.tag) == "DOCUMENT_FRAGMENT"
    assert local_name(root[0].tag) == "img"


def test_svg_names_are_normalized() -> None:
    root = parse_html("<svg><linearGradient></linearGradient></svg>", document=False)

    assert local_name(root.tag) == "svg"
    assert local_name(root[0].tag) == "lineargradient"


def test_svg_fragment_preserves_comments() -> None:
    root = parse_html("<svg><!--keep--><circle/></svg>", document=False)

    assert serialize_html(root) == "<svg><!--keep--><circle></circle></svg>"


def test_svg_fragment_preserves_namespaced_attributes() -> None:
    source = (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:xlink="http://www.w3.org/1999/xlink"><use xlink:href="#x"/></svg>'
    )

    assert serialize_html(parse_html(source, document=False)) == (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:xlink="http://www.w3.org/1999/xlink"><use xlink:href="#x"></use></svg>'
    )


def test_svg_fragment_preserves_scoped_namespace_rebindings() -> None:
    source = (
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:foo="urn:one">'
        '<g foo:bar="one"><g xmlns:foo="urn:two" foo:bar="two"></g>'
        '<g foo:bar="three"></g></g></svg>'
    )

    assert serialize_html(parse_html(source, document=False)) == source


def test_svg_fragment_preserves_qualified_element_names_and_children() -> None:
    source = (
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:foo="urn:foo"><foo:br><foo:thing></foo:thing></foo:br></svg>'
    )

    assert serialize_html(parse_html(source, document=False)) == source


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("<image/>tail", "<image></image>tail"),
        ("<image/><image/>", "<image></image><image></image>"),
    ],
)
def test_svg_image_fragment_preserves_following_content(source: str, expected: str) -> None:
    assert serialize_html(parse_html(source, document=False)) == expected


def test_html5_parser_inserts_table_body() -> None:
    root = parse_html("<table><tr><td>x</table>", document=False)

    assert serialize_html(root) == "<table><tbody><tr><td>x</td></tr></tbody></table>"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("<head><title>x</title></head>", "<head><title>x</title></head>"),
        ("<body><p>x</p></body>", "<body><p>x</p></body>"),
        ("<caption>x</caption>", "<caption>x</caption>"),
        ("<colgroup><col></colgroup>", "<colgroup><col></colgroup>"),
        ("<col>", "<col>"),
        ("<tbody><tr><td>x</td></tr></tbody>", "<tbody><tr><td>x</td></tr></tbody>"),
        ("<thead><tr><th>x</th></tr></thead>", "<thead><tr><th>x</th></tr></thead>"),
        ("<tfoot><tr><td>x</td></tr></tfoot>", "<tfoot><tr><td>x</td></tr></tfoot>"),
        ("<tr><td>x</td></tr>", "<tr><td>x</td></tr>"),
        ("<td>x</td>", "<td>x</td>"),
        ("<th>x</th>", "<th>x</th>"),
    ],
)
def test_fragment_parser_preserves_context_sensitive_roots(source: str, expected: str) -> None:
    assert serialize_html(parse_html(source, document=False)) == expected


def test_fragment_parser_uses_context_after_leading_comment() -> None:
    source = "<!--keep--><tr><td>x</td></tr>"

    assert serialize_html(parse_html(source, document=False)) == source


def test_head_fragment_does_not_treat_script_text_as_an_explicit_body() -> None:
    source = '<head><script>const marker = "<body>";</script></head>'

    assert serialize_html(parse_html(source, document=False)) == source


def test_serializer_removes_foreign_content_namespace_prefixes() -> None:
    root = parse_html("<div><svg><circle></circle></svg><math><mi>x</mi></math></div>", document=False)

    assert serialize_html(root) == "<div><svg><circle></circle></svg><math><mi>x</mi></math></div>"


@pytest.mark.parametrize("value", ["foo\vbar", "foo\u00a0bar", "foo`bar"])
def test_compact_serializer_quotes_legacy_unsafe_attribute_values(value: str) -> None:
    root = Element("div", {"title": value})

    assert serialize_html(root, compact=True) == f'<div title="{value}"></div>'


def test_serializer_escapes_less_than_in_attributes() -> None:
    root = Element("div", {"title": "a < b"})

    assert serialize_html(root) == '<div title="a &lt; b"></div>'
