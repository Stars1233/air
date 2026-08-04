from air.tags._tinyhtml5 import is_valueless_attribute, parse_document, parse_fragment  # noqa: PLC2701


def test_fragment_parser_preserves_attribute_source_forms() -> None:
    root = parse_fragment('<div bare explicit="" spaced = "value"></div>')
    attributes = root[0].attrib

    assert is_valueless_attribute(attributes["bare"])
    assert not attributes["explicit"]
    assert not is_valueless_attribute(attributes["explicit"])
    assert attributes["spaced"] == "value"


def test_document_parser_retains_html5_tree_construction() -> None:
    root = parse_document("<!doctype html><table><tr><td>x</td></tr></table>")

    assert root.tag == "html"
    assert root.find("./body/table/tbody/tr/td").text == "x"
