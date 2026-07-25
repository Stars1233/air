from xml.etree.ElementTree import Element

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


def test_malformed_svg_falls_back_to_html5_parser() -> None:
    root = parse_html("<image><broken", document=False)

    assert local_name(root.tag) == "DOCUMENT_FRAGMENT"
    assert local_name(root[0].tag) == "img"


def test_svg_names_are_normalized() -> None:
    root = parse_html("<svg><linearGradient></linearGradient></svg>", document=False)

    assert local_name(root.tag) == "svg"
    assert local_name(root[0].tag) == "lineargradient"
