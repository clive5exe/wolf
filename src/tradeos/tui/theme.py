"""WOLF terminal palette.

Colour discipline (the whole point of this file): **amber is the wolf** — brand,
targets, and keys. **Green and red are money, and only money.** **Cyan is data
and history.** Nothing else gets colour, so anything coloured on screen means
something. Adding a new hue here should feel like a decision, not a convenience.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Final


class Ink:
    """Terminal ink roles. Values are the approved palette — do not inline hexes."""

    # surfaces
    BG: Final = "#0E1219"
    CHROME: Final = "#161C26"
    SELECTED: Final = "#1D2634"

    # text weights
    BRIGHT: Final = "#EAF0F8"  # emphasis: symbols, NAV, headline numbers
    INK: Final = "#C7D0DC"  # body
    DIM: Final = "#57616F"  # labels, chrome, secondary
    FAINT: Final = "#39424E"  # leaders, rules, inactive scaffolding

    # semantic
    AMBER: Final = "#F0B45C"  # the wolf: brand, targets, key hints
    GREEN: Final = "#7ED491"  # money up / passed / fresh
    RED: Final = "#F08C8C"  # money down / vetoed / halted
    CYAN: Final = "#83D2E4"  # data, history, sparklines

    # badge fills (dark text on a colour block)
    ON_AMBER: Final = "#161207"
    ON_RED: Final = "#2A0D0D"


#: Brand mark. The amber eye is the one piece of colour that is purely identity.
WORDMARK: Final = f"[{Ink.BRIGHT}]W[/][{Ink.AMBER}]◉[/][{Ink.BRIGHT}]LF[/]"
WORDMARK_PLAIN: Final = "W◉LF"
TAGLINE: Final = "wealth orchestration, local-first"

#: Legal stance, shown wherever the product introduces itself.
DISCLAIMER: Final = "experimental · paper trading · not investment advice"


def badge(text: str, *, danger: bool = False) -> str:
    """A filled block badge (PAPER, HALTED) — dark ink on a colour field."""
    fg, bg = (Ink.ON_RED, Ink.RED) if danger else (Ink.ON_AMBER, Ink.AMBER)
    return f"[{fg} on {bg}] {text} [/]"


def key(label: str, rest: str = "") -> str:
    """A footer key hint: amber bracketed key, dim description.

    The opening bracket is escaped — unescaped ``[c]`` is parsed as a style tag
    and vanishes from the footer entirely.
    """
    return f"[{Ink.AMBER}]\\[{label}][/][{Ink.DIM}]{rest}[/]"


def money_ink(value: Decimal | None) -> str:
    """Green above zero, red below, dim at exactly zero.

    Compared as Decimal — money never becomes a float, not even to pick a colour.
    """
    if value is None:
        return Ink.DIM
    if value > 0:
        return Ink.GREEN
    if value < 0:
        return Ink.RED
    return Ink.DIM
