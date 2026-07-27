"""HTML parsing and serialization built from WebAssembly-safe dependencies."""

from __future__ import annotations

import re
from copy import deepcopy
from html import escape
from typing import TYPE_CHECKING, Any, cast
from xml.etree.ElementTree import Comment, Element, ParseError, fromstring, indent

import tinyhtml5
from tinyhtml5.parser import HTMLParser

if TYPE_CHECKING:
    from collections.abc import Iterator

_DOCUMENT_FRAGMENT = "DOCUMENT_FRAGMENT"
_FIRST_TAG_RE = re.compile(r"^\s*(?:<!doctype\s+html\b[^>]*>\s*)?<([a-z][a-z0-9:-]*)\b", re.IGNORECASE)
_PRESERVE_WHITESPACE_ELEMENTS = frozenset({
    "iframe",
    "noembed",
    "noframes",
    "noscript",
    "plaintext",
    "pre",
    "script",
    "style",
    "textarea",
    "xmp",
})
_RAW_TEXT_ELEMENTS = frozenset({"iframe", "noembed", "noframes", "noscript", "plaintext", "script", "style", "xmp"})
_SVG_FRAGMENT_ROOTS = frozenset({"image", "svg"})
_SVG_NAMESPACE = "http://www.w3.org/2000/svg"
_UNQUOTED_ATTRIBUTE_RE = re.compile(r"[A-Za-z0-9._:/@+?#%&,;~-]+")
_VOID_ELEMENTS = frozenset({
    "area",
    "base",
    "basefont",
    "bgsound",
    "br",
    "col",
    "embed",
    "frame",
    "hr",
    "img",
    "input",
    "keygen",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
})
_WHITESPACE_RE = re.compile(r"\s+")


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
    if document:
        return cast("Element", tinyhtml5.parse(source, namespace_html_elements=False))
    return _parse_fragment(source)


def serialize_html(
    root: Element,
    *,
    pretty: bool = False,
    compact: bool = False,
) -> str:
    """Serialize an HTML element tree."""
    root = deepcopy(root)
    if compact:
        _remove_comments(root)
        _collapse_whitespace(root)
    if pretty:
        return _serialize_pretty(root)
    return _serialize_root(root, compact=compact)


def compact_html(source: str, *, document: bool) -> str:
    """Parse and compact HTML while preserving HTML5 semantics."""
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
    if local_name(root.tag) == _DOCUMENT_FRAGMENT:
        rendered: list[str] = []
        if root.text and not root.text.isspace():
            rendered.append(root.text)
        for child in root:
            tail = child.tail
            child.tail = None
            indent(child, space="  ")
            rendered.append(_serialize_node(child))
            if tail and not tail.isspace():
                rendered.append(tail)
        return "".join(rendered) + "\n"

    indent(root, space="  ")
    return _serialize_node(root) + "\n"


def _serialize_root(root: Element, *, compact: bool) -> str:
    """Serialize a document element or synthetic fragment root."""
    if local_name(root.tag) != _DOCUMENT_FRAGMENT:
        return _serialize_node(root, compact=compact)
    rendered = [_serialize_text(root.text)]
    for child in root:
        rendered.extend((_serialize_node(child, compact=compact), _serialize_text(child.tail)))
    return "".join(rendered)


def _serialize_node(node: Element, *, compact: bool = False) -> str:
    """Serialize one element and its descendants as HTML."""
    if is_comment(node):
        return f"<!--{node.text or ''}-->"
    name = local_name(node.tag)
    attributes = "".join(_serialize_attribute(key, value, compact=compact) for key, value in node.attrib.items())
    opening = f"<{name}{attributes}>"
    if name in _VOID_ELEMENTS:
        return opening
    rendered = [opening, _serialize_text(node.text, parent=name)]
    for child in node:
        rendered.extend((_serialize_node(child, compact=compact), _serialize_text(child.tail, parent=name)))
    rendered.append(f"</{name}>")
    return "".join(rendered)


def _serialize_attribute(name: str, value: str, *, compact: bool) -> str:
    """Serialize one attribute with conservative compact-mode quote omission."""
    name = local_name(name)
    if compact and not value:
        return f" {name}"
    quote = "'" if '"' in value and "'" not in value else '"'
    escaped = value.replace("&", "&amp;").replace("<", "&lt;")
    escaped = escaped.replace(quote, "&quot;" if quote == '"' else "&#39;")
    if compact and _UNQUOTED_ATTRIBUTE_RE.fullmatch(escaped):
        return f" {name}={escaped}"
    return f" {name}={quote}{escaped}{quote}"


def _serialize_text(value: str | None, *, parent: str = "") -> str:
    """Escape normal text while preserving raw-text element contents."""
    if not value:
        return ""
    return value if parent in _RAW_TEXT_ELEMENTS else escape(value, quote=False)


def _collapse_whitespace(node: Element, *, preserve: bool = False) -> None:
    """Collapse repeated whitespace except inside whitespace-sensitive elements."""
    preserve = preserve or local_name(node.tag) in _PRESERVE_WHITESPACE_ELEMENTS
    if node.text and not preserve:
        node.text = _WHITESPACE_RE.sub(" ", node.text)
    for child in node:
        _collapse_whitespace(child, preserve=preserve)
        if child.tail and not preserve:
            child.tail = _WHITESPACE_RE.sub(" ", child.tail)


def _parse_fragment(source: str) -> Element:
    """Parse an HTML5 fragment using tinyhtml5's fragment-capable parser."""
    parser = HTMLParser(namespace_html_elements=False)
    return cast("Element", parser.parse_fragment(source))


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
        return _parse_fragment(source)
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
