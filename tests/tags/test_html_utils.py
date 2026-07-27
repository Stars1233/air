# tests/test_html_utils.py
from __future__ import annotations

import pytest

from air.tags.constants import HTML_DOCTYPE

# Adjust this import path if needed for your project layout.
from air.tags.utils import (
    format_html,
    pretty_format_html,
)

# -----------------------
# Helpers for expectations
# -----------------------


def _expected_format_html_fragment(*, pretty: bool, with_doctype: bool) -> str:
    base: str = "<p>Hi</p>\n" if pretty else "<p>Hi</p>"
    return (HTML_DOCTYPE + "\n" + base) if with_doctype else base


def _expected_format_html_document(*, with_head: bool, pretty: bool, with_doctype: bool) -> str:
    if not pretty:
        base: str = (
            "<html><head></head><body><p>Hi</p></body></html>" if with_head else "<html><body><p>Hi</p></body></html>"
        )
    else:
        base = (
            "<html>\n  <head></head>\n  <body>\n    <p>Hi</p>\n  </body>\n</html>\n"
            if with_head
            else "<html>\n  <body>\n    <p>Hi</p>\n  </body>\n</html>\n"
        )
    return (HTML_DOCTYPE + "\n" + base) if with_doctype else base


def _expected_pretty_fragment_unescaped(*, with_doctype: bool) -> str:
    base: str = "<div data-x=\"A & B and 'quote'\">C < D & E</div>\n"
    return (HTML_DOCTYPE + "\n" + base) if with_doctype else base


def _expected_pretty_document_unescaped(*, with_head: bool, with_doctype: bool) -> str:
    inner: str = "    <div data-x=\"A & B and 'quote'\">C < D & E</div>\n"
    if with_head:
        base: str = f"<html>\n  <head></head>\n  <body>\n{inner}  </body>\n</html>\n"
    else:
        base = f"<html>\n  <body>\n{inner}  </body>\n</html>\n"
    return (HTML_DOCTYPE + "\n" + base) if with_doctype else base


# -----------------------
# format_html: all combos
# -----------------------


@pytest.mark.parametrize(
    ("with_body", "with_head", "pretty", "with_doctype"),
    [(wb, wh, pr, wd) for wb in (False, True) for wh in (False, True) for pr in (False, True) for wd in (False, True)],
    ids=lambda v: "T" if v else "F",
)
def test_format_html_all_parameter_combinations(
    *, with_body: bool, with_head: bool, pretty: bool, with_doctype: bool
) -> None:
    src: str = "<p>Hi</p>"

    if not with_body:
        expected: str = _expected_format_html_fragment(pretty=pretty, with_doctype=with_doctype)
    else:
        expected = _expected_format_html_document(with_head=with_head, pretty=pretty, with_doctype=with_doctype)

    result: str = format_html(
        src,
        with_body=with_body,
        with_head=with_head,
        with_doctype=with_doctype,
        pretty=pretty,
    )
    assert result == expected


# -----------------------------------------
# pretty_format_html: all 8 flag combos
# (always uses pretty=True under the hood)
# -----------------------------------------


@pytest.mark.parametrize(
    ("with_body", "with_head", "with_doctype"),
    [(wb, wh, wd) for wb in (False, True) for wh in (False, True) for wd in (False, True)],
    ids=lambda v: "T" if v else "F",
)
def test_pretty_format_html_all_parameter_combinations(*, with_body: bool, with_head: bool, with_doctype: bool) -> None:
    # Include entities that will be unescaped by pretty_format_html.
    src: str = '<div data-x="A &amp; B and &#x27;quote&#x27;">C &lt; D &amp; E</div>'

    if not with_body:
        expected: str = _expected_pretty_fragment_unescaped(with_doctype=with_doctype)
    else:
        expected = _expected_pretty_document_unescaped(with_head=with_head, with_doctype=with_doctype)

    result: str = pretty_format_html(src, with_body=with_body, with_head=with_head, with_doctype=with_doctype)
    assert result == expected


@pytest.mark.parametrize(
    "source",
    [
        "<span>a</span> between <span>b</span>",
        "<b>a</b>, <i>b</i>!",
        "prefix <span>a</span> suffix",
    ],
)
def test_pretty_format_html_preserves_top_level_text(source: str) -> None:
    assert pretty_format_html(source) == f"{source}\n"


# -----------------------------
# Edge case: empty input raises
# -----------------------------


def test_format_html_empty_raises_value_error() -> None:
    with pytest.raises(ValueError, match="HTML source must not be empty") as exc:
        _ = format_html("")  # no defaults passed
    assert exc.type is ValueError


def test_pretty_format_html_empty_raises_value_error() -> None:
    with pytest.raises(ValueError, match="HTML source must not be empty") as exc:
        _ = pretty_format_html("")  # no defaults passed
    assert exc.type is ValueError
