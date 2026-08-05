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

#: Chrome is drawn to a fixed width so every screen's frame lines up.
FRAME_WIDTH = 78


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
