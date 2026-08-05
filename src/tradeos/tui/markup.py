"""Markup measuring, using Textual's own parser.

Box-drawn chrome has to know how wide a styled string actually is, and the only
safe answer comes from the parser that will render it. Guessing with a regex
gets `\\[c]ycle` wrong. An unescaped ``[c]`` is silently eaten as a style tag,
which is exactly the bug this module exists to prevent.
"""

from __future__ import annotations

from textual.content import Content


def plain(markup: str) -> str:
    """The text a user will actually see, with styles and escapes resolved."""
    return Content.from_markup(markup).plain


def visible_len(markup: str) -> int:
    """Display width of a markup string, in columns."""
    return len(plain(markup))


def escape(text: str) -> str:
    """Escape literal square brackets so they survive as content, not tags."""
    return text.replace("[", r"\[")
