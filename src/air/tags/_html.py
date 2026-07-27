"""HTML parsing and serialization built from WebAssembly-safe dependencies."""

from __future__ import annotations

import re
from copy import deepcopy
from html import escape
from io import StringIO
from typing import TYPE_CHECKING, Any, cast
from xml.etree.ElementTree import Comment, Element, ParseError, TreeBuilder, XMLParser, indent, iterparse

from ._tinyhtml5 import is_valueless_attribute, parse_document, parse_fragment

if TYPE_CHECKING:
    from collections.abc import Iterator

_DOCUMENT_FRAGMENT = "DOCUMENT_FRAGMENT"
_HTML_WHITESPACE = r"[ \t\n\f\r]"
_DOCTYPE_RE = re.compile(
    rf"^{_HTML_WHITESPACE}*(?:<!--.*?-->{_HTML_WHITESPACE}*)*"
    rf"(<!doctype{_HTML_WHITESPACE}+html(?={_HTML_WHITESPACE}|>)[^>]*>)",
    re.IGNORECASE | re.DOTALL,
)
_FIRST_TAG_RE = re.compile(
    rf"^{_HTML_WHITESPACE}*"
    rf"(?:<!doctype{_HTML_WHITESPACE}+html(?={_HTML_WHITESPACE}|>)[^>]*>{_HTML_WHITESPACE}*)?"
    rf"<([a-z][a-z0-9:-]*)(?={_HTML_WHITESPACE}|/?>)",
    re.IGNORECASE,
)
_HTML_DOCUMENT_RE = re.compile(
    rf"^{_HTML_WHITESPACE}*(?:<!--.*?-->{_HTML_WHITESPACE}*)*"
    rf"(?:<!doctype{_HTML_WHITESPACE}+html(?={_HTML_WHITESPACE}|>)[^>]*>"
    rf"|(?:<!--.*?-->{_HTML_WHITESPACE}*)*<html(?={_HTML_WHITESPACE}|/?>))",
    re.IGNORECASE | re.DOTALL,
)
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
_RAW_TEXT_ELEMENTS = frozenset({"iframe", "noembed", "noframes", "plaintext", "script", "style", "xmp"})
_SVG_FRAGMENT_ROOTS = frozenset({"image", "svg"})
_HTML_NAMESPACE = "http://www.w3.org/1999/xhtml"
_SVG_NAMESPACE = "http://www.w3.org/2000/svg"
_XLINK_NAMESPACE = "http://www.w3.org/1999/xlink"
_XML_NAMESPACE = "http://www.w3.org/XML/1998/namespace"
_XMLNS_NAMESPACE = "http://www.w3.org/2000/xmlns/"
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
_WHITESPACE_RE = re.compile(r"[ \t\n\f\r]+")


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
        return parse_document(source)
    return parse_fragment(source)


def has_html_document_root(source: str) -> bool:
    """Return whether source starts with an HTML doctype or document root."""
    return bool(_HTML_DOCUMENT_RE.match(source))


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
    rendered = serialize_html(parse_html(source, document=document), compact=True)
    doctype_match = _DOCTYPE_RE.match(source) if document else None
    if doctype_match:
        return doctype_match.group(1) + rendered
    return rendered


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
        rendered.extend((
            _serialize_node(child, compact=compact),
            _serialize_text(child.tail),
        ))
    return "".join(rendered)


def _serialize_node(
    node: Element,
    *,
    compact: bool = False,
    namespace_prefixes: dict[str, str] | None = None,
) -> str:
    """Serialize one element and its descendants as HTML."""
    if is_comment(node):
        return f"<!--{node.text or ''}-->"
    namespace_prefixes = namespace_prefixes_for_node(node, inherited=namespace_prefixes)
    name = qualified_element_name(node.tag, namespace_prefixes=namespace_prefixes)
    attributes = "".join(
        _serialize_attribute(
            key,
            value,
            compact=compact,
            namespace_prefixes=namespace_prefixes,
        )
        for key, value in node.attrib.items()
    )
    opening = f"<{name}{attributes}>"
    if _is_html_void_element(node.tag, name=name):
        return opening
    rendered = [opening, _serialize_text(node.text, parent=name)]
    for child in node:
        rendered.extend((
            _serialize_node(child, compact=compact, namespace_prefixes=namespace_prefixes),
            _serialize_text(child.tail, parent=name),
        ))
    rendered.append(f"</{name}>")
    return "".join(rendered)


def _serialize_attribute(
    name: str,
    value: str,
    *,
    compact: bool,
    namespace_prefixes: dict[str, str],
) -> str:
    """Serialize one attribute with conservative compact-mode quote omission."""
    name = _serialize_attribute_name(name, namespace_prefixes=namespace_prefixes)
    if is_valueless_attribute(value):
        return f" {name}"
    if compact and not value:
        return f" {name}"
    quote = "'" if '"' in value and "'" not in value else '"'
    escaped = value.replace("&", "&amp;").replace("<", "&lt;")
    escaped = escaped.replace(quote, "&quot;" if quote == '"' else "&#39;")
    if compact and _UNQUOTED_ATTRIBUTE_RE.fullmatch(escaped):
        return f" {name}={escaped}"
    return f" {name}={quote}{escaped}{quote}"


def _serialize_attribute_name(name: str, *, namespace_prefixes: dict[str, str]) -> str:
    """Return an attribute name while retaining a known XML namespace prefix."""
    if not name.startswith("{"):
        return name
    namespace, _, unqualified_name = name[1:].partition("}")
    if namespace == _XMLNS_NAMESPACE and unqualified_name == "xmlns":
        return "xmlns"
    if prefix := namespace_prefixes.get(namespace):
        return f"{prefix}:{unqualified_name}"
    return unqualified_name


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
    return parse_fragment(source)


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


def namespace_prefixes_for_node(
    node: Element,
    *,
    inherited: dict[str, str] | None = None,
) -> dict[str, str]:
    """Return namespace prefixes in scope for one element."""
    prefixes = (
        dict(inherited)
        if inherited is not None
        else {
            _XLINK_NAMESPACE: "xlink",
            _XML_NAMESPACE: "xml",
            _XMLNS_NAMESPACE: "xmlns",
        }
    )
    for name, value in node.attrib.items():
        if name.startswith("xmlns:"):
            prefixes[value] = name.partition(":")[2]
        elif name.startswith(f"{{{_XMLNS_NAMESPACE}}}") and local_name(name) != "xmlns":
            prefixes[value] = local_name(name)
    return prefixes


def qualified_attribute_name(name: str, *, namespace_prefixes: dict[str, str]) -> str:
    """Return a parsed attribute name with its in-scope namespace prefix."""
    return _serialize_attribute_name(name, namespace_prefixes=namespace_prefixes)


def qualified_element_name(tag: Any, *, namespace_prefixes: dict[str, str]) -> str:
    """Return a parsed element name with its in-scope namespace prefix."""
    name = local_name(tag)
    if isinstance(tag, str) and tag.startswith("{"):
        namespace = tag[1:].partition("}")[0]
        if prefix := namespace_prefixes.get(namespace):
            return f"{prefix}:{name}"
    return name


def _is_html_void_element(tag: Any, *, name: str) -> bool:
    """Return whether a parsed tag is an HTML void element."""
    if name not in _VOID_ELEMENTS or not isinstance(tag, str):
        return False
    if tag.startswith("{"):
        return tag[1:].partition("}")[0] == _HTML_NAMESPACE
    return ":" not in tag


def _parse_svg_fragment(source: str, *, root_name: str) -> Element:
    if root_name == "svg":
        try:
            root = _parse_xml_with_comments(source)
        except ParseError:
            return _parse_fragment(source)
        _lowercase_svg_names(root)
        return root
    try:
        wrapper = _parse_xml_with_comments(f'<svg xmlns="{_SVG_NAMESPACE}">{source}</svg>')
    except ParseError:
        return _parse_fragment(source)
    if len(wrapper) == 1 and wrapper.text is None and wrapper[0].tail is None:
        root = wrapper[0]
        _lowercase_svg_names(root)
        return root
    fragment = Element(_DOCUMENT_FRAGMENT)
    fragment.text = wrapper.text
    for child in wrapper:
        _lowercase_svg_names(child)
        fragment.append(child)
    return fragment


def _parse_xml_with_comments(source: str) -> Element:
    """Parse XML-compatible SVG while retaining comments and namespace scopes.

    Raises:
        ParseError: If the source has no root element or is not well-formed XML.
    """
    parser = XMLParser(target=TreeBuilder(insert_comments=True))
    iterator = iterparse(StringIO(source), events=("start-ns", "start"), parser=parser)
    pending_namespaces: list[tuple[str, str]] = []
    root: Element | None = None
    for event, value in iterator:
        if event == "start-ns":
            pending_namespaces.append(cast("tuple[str, str]", value))
            continue
        node = cast("Element", value)
        if root is None:
            root = node
        if pending_namespaces:
            declarations = {
                "xmlns" if not prefix else f"xmlns:{prefix}": namespace for prefix, namespace in pending_namespaces
            }
            node.attrib = {**declarations, **node.attrib}
            pending_namespaces.clear()
    if root is None:
        msg = "XML-compatible SVG must have a root element."
        raise ParseError(msg)
    return root


def _lowercase_svg_names(node: Element) -> None:
    if isinstance(node.tag, str):
        namespace = node.tag.partition("}")[0] + "}" if node.tag.startswith("{") else ""
        node.tag = namespace + local_name(node.tag).lower()
    node.attrib = {_lowercase_qualified_name(name): value for name, value in node.attrib.items()}
    for child in node:
        _lowercase_svg_names(child)


def _lowercase_qualified_name(name: str) -> str:
    """Lowercase a local XML name without discarding its namespace URI."""
    if not name.startswith("{"):
        return name.lower()
    namespace, _, unqualified_name = name[1:].partition("}")
    return f"{{{namespace}}}{unqualified_name.lower()}"
