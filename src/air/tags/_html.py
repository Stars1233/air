"""HTML parsing and serialization built from WebAssembly-safe dependencies."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import TYPE_CHECKING, Any
from xml.etree.ElementTree import Comment, Element, ParseError, fromstring, indent

import html5lib
from html5lib.serializer import serialize

if TYPE_CHECKING:
    from collections.abc import Iterator

_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_FIRST_TAG_RE = re.compile(r"^\s*(?:<!doctype\s+html\b[^>]*>\s*)?<([a-z][a-z0-9:-]*)\b", re.IGNORECASE)
_SVG_FRAGMENT_ROOTS = frozenset({"image", "svg"})
_SVG_NAMESPACE = "http://www.w3.org/2000/svg"


def parse_html(source: str, *, document: bool) -> Element:
    """Parse an HTML document or fragment into a standard-library element tree.

    Raises:
        ValueError: If the source is empty.
    """
    if not source:
        msg = "HTML source must not be empty."
        raise ValueError(msg)
    match = _FIRST_TAG_RE.match(source) if not document else None
    if match and match.group(1).lower() in _SVG_FRAGMENT_ROOTS:
        return _parse_svg_fragment(source, root_name=match.group(1).lower())
    parse = html5lib.parse if document else html5lib.parseFragment
    return parse(source, treebuilder="etree", namespaceHTMLElements=False)


def serialize_html(
    root: Element,
    *,
    pretty: bool = False,
    compact: bool = False,
) -> str:
    """Serialize an html5lib element tree as HTML."""
    root = deepcopy(root)
    if compact:
        _remove_comments(root)
        return serialize(
            root,
            tree="etree",
            alphabetical_attributes=False,
            minimize_boolean_attributes=True,
            omit_optional_tags=True,
            quote_attr_values="spec",
            strip_whitespace=True,
        )
    if pretty:
        return _serialize_pretty(root)
    return serialize(
        root,
        tree="etree",
        alphabetical_attributes=False,
        minimize_boolean_attributes=False,
        omit_optional_tags=False,
        quote_attr_values="always",
        strip_whitespace=False,
    )


def compact_html(source: str, *, document: bool) -> str:
    """Parse and compact HTML while preserving HTML5 semantics."""
    source = _HTML_COMMENT_RE.sub("", source)
    return serialize_html(parse_html(source, document=document), compact=True)


def is_comment(node: Element) -> bool:
    """Return whether an ElementTree node represents an HTML comment."""
    return node.tag is Comment


def local_name(tag: Any) -> str:
    """Return an element tag without an XML namespace prefix."""
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1]


def iter_content(node: Element) -> Iterator[Element | str]:
    """Yield meaningful text and child nodes from an element in source order."""
    if node.text and not node.text.isspace():
        yield node.text
    for child in node:
        yield child
        if child.tail and not child.tail.isspace():
            yield child.tail


def _serialize_pretty(root: Element) -> str:
    if local_name(root.tag) == "DOCUMENT_FRAGMENT":
        rendered: list[str] = []
        if root.text and not root.text.isspace():
            rendered.append(root.text)
        for child in root:
            child.tail = None
            indent(child, space="  ")
            rendered.append(
                serialize(
                    child,
                    tree="etree",
                    alphabetical_attributes=False,
                    minimize_boolean_attributes=False,
                    omit_optional_tags=False,
                    quote_attr_values="always",
                    strip_whitespace=False,
                )
            )
        return "".join(rendered) + "\n"

    indent(root, space="  ")
    return (
        serialize(
            root,
            tree="etree",
            alphabetical_attributes=False,
            minimize_boolean_attributes=False,
            omit_optional_tags=False,
            quote_attr_values="always",
            strip_whitespace=False,
        )
        + "\n"
    )


def _remove_comments(node: Element) -> None:
    for child in list(node):
        if is_comment(child):
            if child.tail:
                previous = list(node).index(child) - 1
                if previous >= 0:
                    sibling = list(node)[previous]
                    sibling.tail = (sibling.tail or "") + child.tail
                else:
                    node.text = (node.text or "") + child.tail
            node.remove(child)
        else:
            _remove_comments(child)


def _parse_svg_fragment(source: str, *, root_name: str) -> Element:
    xmlns: str | None = None
    try:
        if root_name == "svg":
            root = fromstring(source)
            xmlns_match = re.search(r"""\bxmlns\s*=\s*(['"])(.*?)\1""", source, re.IGNORECASE)
            if xmlns_match:
                xmlns = xmlns_match.group(2)
        else:
            wrapper = fromstring(f'<svg xmlns="{_SVG_NAMESPACE}">{source}</svg>')
            root = wrapper[0]
    except ParseError:
        return html5lib.parseFragment(source, treebuilder="etree", namespaceHTMLElements=False)
    _lowercase_svg_names(root)
    if xmlns:
        root.attrib = {"xmlns": xmlns, **root.attrib}
    return root


def _lowercase_svg_names(node: Element) -> None:
    if isinstance(node.tag, str):
        namespace = node.tag.partition("}")[0] + "}" if node.tag.startswith("{") else ""
        node.tag = namespace + local_name(node.tag).lower()
    node.attrib = {local_name(name).lower(): value for name, value in node.attrib.items()}
    for child in node:
        _lowercase_svg_names(child)
