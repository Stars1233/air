"""Compatibility adapter for Air's tinyhtml5 2.x integration.

This is the only module that should depend on tinyhtml5 parser or tokenizer
internals. The dependency is capped below 3.0 because preserving the source
distinction between valueless and explicitly empty attributes requires these
private extension points.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast, override

from tinyhtml5.parser import HTMLParser, ReparseError
from tinyhtml5.tokenizer import HTMLTokenizer

if TYPE_CHECKING:
    from xml.etree.ElementTree import Element


class _ValuelessAttribute(str):  # noqa: FURB189
    """Marker for an attribute written without an equals sign."""


_VALUELESS_ATTRIBUTE = _ValuelessAttribute()


class _ValuelessHTMLTokenizer(HTMLTokenizer):
    """Retain whether an attribute was written without an equals sign."""

    def before_attribute_name_state(self) -> bool:
        """Mark attributes created by the base tokenizer as valueless."""
        attribute_count = len(self._current_attribute_data())
        result = super().before_attribute_name_state()
        self._mark_new_attribute(attribute_count)
        return result

    def after_attribute_name_state(self) -> bool:
        """Mark adjacent attributes created by the base tokenizer as valueless."""
        attribute_count = len(self._current_attribute_data())
        result = super().after_attribute_name_state()
        self._mark_new_attribute(attribute_count)
        return result

    def before_attribute_value_state(self) -> bool:
        """Replace the valueless marker after the tokenizer reads an equals sign."""
        self._current_attribute_data()[-1][1] = ""
        return super().before_attribute_value_state()

    def _current_attribute_data(self) -> list[list[Any]]:
        token = cast("dict[str, Any]", self.current_token)
        return cast("list[list[Any]]", token["data"])

    def _mark_new_attribute(self, previous_count: int) -> None:
        token = cast("dict[str, Any]", self.current_token)
        data = token["data"]
        if isinstance(data, list) and len(data) > previous_count:
            data[-1][1] = _VALUELESS_ATTRIBUTE


class _ValuelessHTMLParser(HTMLParser):
    """Use the HTML5 parser with valueless-attribute-aware tokens."""

    @override
    def _parse(
        self,
        stream: str,
        container: str | None = None,
        scripting: bool = False,
        **kwargs: Any,
    ) -> None:
        self.container = container
        self.scripting = scripting
        self.tokenizer = _ValuelessHTMLTokenizer(stream, parser=self, **kwargs)
        self.reset()
        try:
            self.main_loop()
        except ReparseError:
            self.reset()
            self.main_loop()


def parse_document(source: str) -> Element:
    """Parse an HTML document into an ElementTree root."""
    parser = _ValuelessHTMLParser(namespace_html_elements=False)
    return cast("Element", parser.parse(source))


def parse_fragment(source: str, *, container: str = "div") -> Element:
    """Parse an HTML fragment into a synthetic ElementTree root."""
    parser = _ValuelessHTMLParser(namespace_html_elements=False)
    return cast("Element", parser.parse_fragment(source, container=container))


def is_valueless_attribute(value: Any) -> bool:
    """Return whether an attribute value represents omitted source syntax."""
    return isinstance(value, _ValuelessAttribute)
