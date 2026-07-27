"""Utilities for the Air Tag system."""

from __future__ import annotations

import base64
import html
import re
import tempfile
import webbrowser
from collections import UserString
from io import StringIO
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.error import URLError

from air.exceptions import BrowserOpenError

from ._html import compact_html, has_html_document_root, local_name, parse_html, serialize_html
from .constants import (
    _LOOKS_LIKE_FULL_HTML_UNICODE_RE,
    _LOOKS_LIKE_HTML_UNICODE_RE,
    ATTRIBUTES_TO_AIR,
    ATTRIBUTES_TO_HTML,
    BLOB_URL_PRESET,
    DATA_URL_MAX,
    DEFAULT_ENCODING,
    DEFAULT_THEME,
    HOMEPAGE_FILE_NAME,
    HTML_DOCTYPE,
    HTML_LEXER,
    HTML_PANEL_TITLE,
    HTML_SUFFIX,
    LOCALS_CLEANUP_EXCLUDED_KEYS,
    PANEL_BORDER_STYLE,
    PANEL_TITLE_STYLE,
    PYTHON_LEXER,
    PYTHON_PANEL_TITLE,
    PanelTitleType,
)

if TYPE_CHECKING:
    from rich.console import Console

    from .types import LexerType, StrPath

_HEAD_FRAGMENT_RE = re.compile(
    r"^\s*<(?:base|head|link|meta|script|style|title)\b",
    re.IGNORECASE,
)


def is_full_html_document(text: str) -> bool:
    """Check if a string looks like a full HTML document using a simple heuristic

    The check allows an optional <!doctype html> at the start, requires a root
    <html>...</html> element that spans the whole input, and requires at least
    one complete <head>...</head> or <body>...</body> pair somewhere inside the
    <html> element. Whitespace anywhere in the input is ignored as far as HTML
    normally ignores it.

    Args:
        text: HTML source string to test.

    Returns:
        True if the input looks like a full HTML document,
        otherwise False.
    """
    return bool(_LOOKS_LIKE_FULL_HTML_UNICODE_RE.fullmatch(text))


def looks_like_html(text: str) -> bool:
    """
    Determines if the given text appears to be in HTML format.

    The function checks whether the provided text both passes an HTML detection
    test and matches a specific regular expression for HTML-like Unicode strings.

    `_LOOKS_LIKE_HTML_UNICODE_RE.fullmatch(text)` enforces this project's
    HTML-like string shape requirements, such as allowing leading and trailing
    whitespace, an optional doctype, and balanced outer tags.

    Args:
        text: HTML source string to test.

    Returns:
        bool: True if the text is detected as HTML and matches the HTML-like
            Unicode pattern; otherwise, False.
    """
    return bool(_LOOKS_LIKE_HTML_UNICODE_RE.fullmatch(text))


def migrate_attribute_name_to_html(attr_name: str) -> str:
    """Normalize attribute names to align with HTML conventions.

    Args:
        attr_name: Attribute name supplied by the caller.

    Returns:
        The normalized attribute name compatible with HTML.

    Notes:
        Proxies such as ``class_``, ``for_``, ``id_``, ``as_``, and ``async_`` are converted to their
        standard HTML counterparts. Leading underscores are stripped and remaining underscores become
        dashes to match HTML attribute naming rules.
    """
    attr_name = ATTRIBUTES_TO_HTML.get(attr_name, attr_name)
    return attr_name.lstrip("_").replace("_", "-")


def migrate_attribute_name_to_air_tag(attr_name: str) -> str:
    """Normalize HTML attribute names for Air tag reconstruction.

    Args:
        attr_name: An uncleaned HTML attribute key.

    Returns:
        Normalized attribute key compatible with Air tags.

    Notes:
        HTML-reserved attribute names such as ``class``, ``for``, ``id``, ``as``, and ``async`` are
        mapped to the underscore-suffixed proxies used by Air tags. Leading underscores are stripped
        and remaining underscores become dashes to normalize the key.
    """
    attr_name = ATTRIBUTES_TO_AIR.get(attr_name, attr_name)
    return attr_name.replace("-", "_")


def extract_html_comment(text: str) -> str:
    """Extract the inner content of an HTML comment string.

    Args:
        text: Raw HTML comment, including the ``<!--`` and ``-->`` markers.

    Returns:
        The comment body with surrounding whitespace stripped.

    Raises:
        ValueError: If the input is not a well-formed HTML comment.

    Examples:
        >>> extract_html_comment("<!-- hello -->")
        'hello'
    """
    if match := re.fullmatch(r"\s*<!--\s*(.*?)\s*-->\s*", text, flags=re.DOTALL):
        return match.group(1).strip()
    msg = "Input is not a valid HTML comment"
    raise ValueError(msg)


def compact_format_html(source: str) -> str:
    """Minify HTML markup with HTML5-aware safe defaults.

    Args:
        source: Raw HTML markup to compress.

    Returns:
        Space-efficient HTML suitable for inline embedding or network transfer.

    Comments and repeated whitespace are removed, and safe attribute quotes are
    omitted, while preserving HTML5 parsing semantics.
    """
    return compact_html(source, document=has_html_document_root(source))


def pretty_format_html(
    source: str,
    *,
    with_body: bool = False,
    with_head: bool = False,
    with_doctype: bool = False,
) -> str:
    """Pretty-print HTML and unescape common entities in the result.

    Args:
        source: Raw HTML markup to format.
        with_body: Whether to wrap the markup in a `<body>` element.
        with_head: Whether to include a `<head>` element when `with_body` is set.
        with_doctype: Whether to prefix the result with a doctype declaration.

    Returns:
        The formatted HTML string with entities such as `&lt;` unescaped.

    Note:
        Entity unescaping applies to attribute values as well; use this helper only with trusted HTML.
    """
    return html.unescape(
        format_html(source, with_body=with_body, with_head=with_head, with_doctype=with_doctype, pretty=True)
    )


def format_html(
    source: str,
    *,
    with_body: bool = False,
    with_head: bool = False,
    with_doctype: bool = False,
    pretty: bool = False,
) -> str:
    """Format HTML markup using the HTML5 parsing algorithm.

    Args:
        source: Raw HTML markup to format.
        with_body: Whether to ensure a `<body>` element is present.
        with_head: Whether to add a `<head>` element when `with_body` is enabled.
        with_doctype: Whether to include a doctype declaration in the result.
        pretty: Whether to indent the output for readability.

    Returns:
        HTML serialized from the parsed element tree.
    """
    source_is_document = has_html_document_root(source)
    head_fragment = bool(_HEAD_FRAGMENT_RE.match(source))
    parse_as_document = with_body or source_is_document or head_fragment
    root = parse_html(source, document=parse_as_document)
    if parse_as_document:
        source_has_head = bool(re.search(r"<head\b", source, re.IGNORECASE))
        source_has_body = bool(re.search(r"<body\b", source, re.IGNORECASE))
        for child in list(root):
            name = local_name(child.tag)
            has_content = bool(child.attrib or len(child) or (child.text and not child.text.isspace()))
            keep_head = with_head or source_has_head or has_content
            keep_body = with_body or source_has_body or has_content
            if (name == "head" and not keep_head) or (name == "body" and not keep_body):
                root.remove(child)
    rendered = serialize_html(root, pretty=pretty)
    return f"{HTML_DOCTYPE}\n{rendered}" if with_doctype else rendered


def open_local_file_in_the_browser(path: StrPath) -> None:
    """Open a local HTML file in the default browser.

    Args:
        path: Path to a file or directory containing an `index.html`.

    Raises:
        FileNotFoundError: The path does not exist or `index.html` is missing.
    """
    path = Path(path)
    if path.is_dir():
        path /= HOMEPAGE_FILE_NAME
    if not path.exists():
        raise FileNotFoundError(path)

    url = path.expanduser().resolve().as_uri()
    _open_new_tab(url)


def _open_new_tab(url: str) -> None:
    """Launch a new browser tab for the provided URL.

    Args:
        url: The URL to open.

    Raises:
        BrowserOpenError: The browser invocation returned a failure signal.
    """
    open_new_tab_successfully = webbrowser.open_new_tab(url)
    if not open_new_tab_successfully:
        msg = f"Could not open browser for URI: {url}. "
        raise BrowserOpenError(msg)


def open_html_blob_in_the_browser(html_source: str, *, data_url_max: int = DATA_URL_MAX) -> None:
    """Open HTML content encoded as a data URL in the browser.

    Args:
        html_source: HTML markup to embed in a data URL.
        data_url_max: Maximum permitted URL length before falling back to a file.

    Raises:
        URLError: The data URL exceeds the configured maximum length.
    """
    source_bytes = html_source.encode()
    url = BLOB_URL_PRESET + base64.b64encode(source_bytes).decode("ascii")
    if len(url) >= data_url_max:
        msg = "html_source is to long!"
        raise URLError(msg)
    _open_new_tab(url)


def open_html_in_the_browser(html_source: str) -> None:
    """Open an HTML string in the browser via a temporary file.

    Args:
        html_source: HTML markup to render in the browser.
    """
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=HTML_SUFFIX, encoding=DEFAULT_ENCODING) as f:
        f.write(html_source)
        path = Path(f.name)

    _open_new_tab(path.as_uri())


def save_text(text: str, file_path: StrPath) -> None:
    """Saves the provided text to a specified file path.

    This function writes the given string data to a file at the provided path
    using a specified encoding.

    Args:
        text: The text content to be saved in the file.
        file_path: The path to the file where the text will be saved.
    """
    Path(file_path).write_text(data=text, encoding=DEFAULT_ENCODING)


def read_text(file_path: StrPath) -> str:
    """Reads the content of a text file and returns it as a string.

    This function reads the text from the file at the specified path using the
    default encoding.

    Args:
        file_path: The path to the file to be read.

    Returns:
        str: The content of the file as a string.
    """
    return Path(file_path).read_text(encoding=DEFAULT_ENCODING)


def read_html(file_path: StrPath) -> str:
    """
    Reads the content of an HTML file from the given file path. Handles both directory
    paths (by appending 'index.html' to the directory) and explicit file paths, ensuring
    that only files with the '.html' extension are processed.

    Args:
        file_path: The path to the HTML file or a directory containing the file.

    Returns:
        str: The content of the HTML file.

    Raises:
        ValueError: If the file path does not have an '.html' extension.
    """
    file_path = Path(file_path)
    if file_path.is_dir():
        file_path /= HOMEPAGE_FILE_NAME
    elif file_path.suffix != HTML_SUFFIX:
        msg = "Expected a .html file extension."
        raise ValueError(msg)
    return read_text(file_path=file_path)


def save_pretty_html(
    source: str,
    *,
    theme: str = DEFAULT_THEME,
    file_path: StrPath,
) -> None:
    """Persist syntax-highlighted HTML to a file.

    Args:
        source: HTML markup to render with syntax highlighting.
        theme: Rich syntax highlighting theme name.
        file_path: Destination file path for the exported HTML.
    """
    console = _get_pretty_html_console(source, theme=theme, record=True)
    console.save_html(path=str(file_path))


def display_pretty_html_in_the_browser(
    source: str,
    *,
    theme: str = DEFAULT_THEME,
) -> None:
    """Open syntax-highlighted HTML in the browser.

    Args:
        source: HTML markup to render with syntax highlighting.
        theme: Rich syntax highlighting theme name.
    """
    open_html_in_the_browser(export_pretty_html(source, theme=theme))


def export_pretty_html(
    source: str,
    *,
    theme: str = DEFAULT_THEME,
) -> str:
    """Return syntax-highlighted HTML for display elsewhere.

    Args:
        source: HTML markup to render with syntax highlighting.
        theme: Rich syntax highlighting theme name.

    Returns:
        The rendered HTML containing the highlighted markup.
    """
    console = _get_pretty_html_console(source, theme=theme, record=True)
    return console.export_html()


def pretty_print_python(
    source: str,
    *,
    theme: str = DEFAULT_THEME,
    record: bool = False,
) -> None:
    """Render Python with syntax highlighting inside a styled terminal panel.

    Args:
        source: HTML markup to render.
        theme: Rich syntax highlighting theme name.
        record: Whether to buffer the output for later export.
    """
    _get_pretty_console(source, lexer=PYTHON_LEXER, panel_title=PYTHON_PANEL_TITLE, theme=theme, record=record)


def pretty_print_html(
    source: str,
    *,
    theme: str = DEFAULT_THEME,
    record: bool = False,
) -> None:
    """Render HTML with syntax highlighting inside a styled terminal panel.

    Args:
        source: HTML markup to render.
        theme: Rich syntax highlighting theme name.
        record: Whether to buffer the output for later export.
    """
    _get_pretty_html_console(source, theme=theme, record=record)


def _get_pretty_html_console(
    source: str,
    *,
    theme: str = DEFAULT_THEME,
    record: bool = False,
) -> Console:
    """Return a Rich console configured for HTML syntax highlighting.

    Args:
        source: HTML markup to render.
        theme: Rich syntax highlighting theme name.
        record: Whether to buffer the console output.

    Returns:
        A configured Rich console instance.
    """
    return _get_pretty_console(source, lexer=HTML_LEXER, panel_title=HTML_PANEL_TITLE, theme=theme, record=record)


def _get_pretty_console(
    source: str,
    lexer: LexerType,
    panel_title: PanelTitleType,
    *,
    theme: str = DEFAULT_THEME,
    record: bool = False,
) -> Console:
    """Generates a Rich console with formatted code syntax displayed within a styled panel.

    The console object is configured to display source code syntax highlighting using the
    specified lexer and theme within a panel with a title. Additionally, the console can
    optionally record its output to a buffer.

    Args:
        source: HTML markup to render.
        lexer: The syntax highlighter to use, either for HTML or Python code.
        panel_title: The title to display on the panel's border.
        theme: Rich syntax highlighting theme name.
        record: Whether to buffer the console output.

    Returns:
        A configured Console instance with the styled syntax and panel displayed.
    """
    from rich import box  # noqa: PLC0415
    from rich.console import Console  # noqa: PLC0415
    from rich.panel import Panel  # noqa: PLC0415
    from rich.syntax import Syntax  # noqa: PLC0415
    from rich.text import Text  # noqa: PLC0415

    syntax = Syntax(code=source, lexer=lexer, theme=theme, line_numbers=True, indent_guides=True, word_wrap=True)
    title = Text(panel_title, style=PANEL_TITLE_STYLE)
    panel = Panel(
        syntax,
        box=box.HEAVY,
        border_style=PANEL_BORDER_STYLE,
        title=title,
    )
    buffer = StringIO() if record else None
    console = Console(record=record, file=buffer)
    console.print(panel, soft_wrap=False)
    return console


def locals_cleanup(
    data: dict[str, Any],
    _skip: frozenset[str] = LOCALS_CLEANUP_EXCLUDED_KEYS,
) -> dict[str, Any]:
    """Filter local variables for keyword argument construction.

    Args:
        data: Dictionary of local variables to filter.
        _skip: Keys that should remain excluded from the result.

    Returns:
        A dictionary containing only keyword-safe values.
    """
    return {key: value for key, value in data.items() if value is not None and key[0] != "_" and key not in _skip}


class SafeStr(UserString):
    """String subclass that bypasses HTML escaping when rendered."""
