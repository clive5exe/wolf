"""Shared screen scaffolding: chrome, footers, and facade access.

Screens reach the runtime only through ``self.runtime`` (the facade). Nothing
in ``tui/`` may import brokers, providers, risk, or storage — if a screen needs
something the facade does not expose, the facade grows a tested method.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from textual.screen import Screen

from tradeos.runtime.facade import TradeOSRuntime
from tradeos.tui.markup import visible_len
from tradeos.tui.motion import Motion
from tradeos.tui.theme import WORDMARK, Ink

if TYPE_CHECKING:
    from tradeos.tui.app import WolfApp

#: Below this the tables stop fitting and the layout is not worth defending.
MIN_FRAME_WIDTH = 64
#: Above this a seven-column table stops being a table: the eye loses the row
#: as figures drift to opposite edges of an ultrawide terminal. Growing past
#: this buys whitespace, not information.
MAX_FRAME_WIDTH = 132
#: Fallback before a screen knows its own size.
FRAME_WIDTH = 78


def frame_width(available: int) -> int:
    """Chrome width for a terminal of ``available`` columns."""
    if available <= 0:
        return FRAME_WIDTH
    return max(MIN_FRAME_WIDTH, min(MAX_FRAME_WIDTH, available - 2))


class WolfScreen(Screen[None]):
    """Base for every WOLF screen."""

    @property
    def wolf(self) -> WolfApp:
        return cast("WolfApp", self.app)

    @property
    def runtime(self) -> TradeOSRuntime:
        return self.wolf.runtime

    @property
    def motion(self) -> Motion:
        return self.wolf.motion

    @property
    def frame(self) -> int:
        """Chrome width for this screen's current size."""
        return frame_width(self.size.width)

    def _section(self, title: str) -> str:
        """A labelled divider sized to this screen."""
        return section(title, width=self.frame)

    def on_resize(self) -> None:
        """Redraw at the new width. Screens paint into fixed-width strings, so
        without this a resize leaves the chrome measured for the old terminal."""
        paint = getattr(self, "_paint", None)
        if callable(paint):
            paint()


def header_bar(right: str, *, width: int = FRAME_WIDTH) -> str:
    """``┌─ W◉LF ────────── <status> ─┐`` — the brand and the truth on one line."""
    lead = f"[{Ink.DIM}]┌─[/] {WORDMARK} "
    fill = max(1, width - visible_len(lead) - visible_len(right) - 3)
    return f"{lead}[{Ink.DIM}]{'─' * fill}[/] {right} [{Ink.DIM}]┐[/]"


def footer_bar(keys: str, note: str = "", *, width: int = FRAME_WIDTH) -> str:
    """``└ \\[c]ycle  \\[j]ournal … <note> ┘`` — every screen ends with its keys.

    Keys always survive; the decorative note is dropped when it would push the
    bar past ``width``. Overflowing the frame would break the box alignment that
    the whole layout depends on, and a key hint outranks an atmosphere line.
    """
    body = f"[{Ink.DIM}]└[/] {keys}"
    gap = width - visible_len(body) - visible_len(note) - 2
    if not note or gap < 2:
        return f"{body} [{Ink.DIM}]┘[/]"
    return f"{body}{' ' * gap}{note} [{Ink.DIM}]┘[/]"


def section(title: str, *, width: int = FRAME_WIDTH) -> str:
    """``─ thesis ────────────────`` — a labelled divider."""
    lead = f"[{Ink.DIM}]─ {title} [/]"
    fill = max(1, width - visible_len(lead))
    return f"{lead}[{Ink.DIM}]{'─' * fill}[/]"
