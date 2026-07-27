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


def test_html5_parser_inserts_table_body() -> None:
    root = parse_html("<table><tr><td>x</table>", document=False)

    assert serialize_html(root) == "<table><tbody><tr><td>x</td></tr></tbody></table>"


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
