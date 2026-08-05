"""WOLF terminal palette.

Colour discipline, which is the whole point of this file. **Infrared is the
wolf**: brand, targets, and keys. **Green and red are money, and only money.**
**Cyan is data and history.** Nothing else gets colour, so anything coloured on
screen means something. Adding a hue here should feel like a decision.

**Infrared never renders a value.** It labels, marks and points. Values are
BRIGHT when they matter and INK when they do not, and signed money is green or
red. This rule is load-bearing rather than stylistic: at ``#FF2247`` the brand
sits at hue 350, which is red, and measurement says no money-down red can be
told apart from it. Every candidate scored between 1.04 and 1.62 contrast
against the brand, and shifting the hue far enough to separate them turns the
loss colour orange. Since the collision cannot be solved with a hex value, it
is solved with a rule: the two colours never do the same job, so they never
appear in the same role and the ambiguity has nowhere to arise.

For the same reason every signed number carries an explicit ▲ or ▼. Direction
then survives greyscale, colour blindness, and a terminal with a mangled
palette, none of which are rare.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Final


class Ink:
    """Terminal ink roles. Values are the approved palette. Do not inline hexes."""

    # surfaces. True black ground
    BG: Final = "#000000"
    CHROME: Final = "#121212"
    SELECTED: Final = "#1C1C1C"

    # text weights
    BRIGHT: Final = "#F5F5F5"  # emphasis: symbols, NAV, headline numbers
    INK: Final = "#D4D4D4"  # body
    DIM: Final = "#8A8A8A"  # labels, chrome, secondary
    FAINT: Final = "#4A4A4A"  # leaders, rules, inactive scaffolding

    # semantic
    INFRARED: Final = "#FF2247"  # the wolf: brand, targets, key hints
    GREEN: Final = "#7ED491"  # money up / passed / fresh
    RED: Final = "#F08C8C"  # money down / vetoed / halted
    CYAN: Final = "#83D2E4"  # data, history, sparklines

    #: Retained so existing call sites keep reading naturally. The hue moved
    #: from amber to infrared, the meaning did not.
    AMBER: Final = INFRARED

    # badge fills (dark text on a colour block)
    ON_AMBER: Final = "#1A0307"
    ON_RED: Final = "#2A0D0D"


#: Inline brand mark, for headers where there is no room for the full lockup.
WORDMARK: Final = f"[{Ink.BRIGHT}]W[/][{Ink.INFRARED}]◉[/][{Ink.BRIGHT}]LF[/]"
WORDMARK_PLAIN: Final = "W◉LF"

#: Splash lockup. Block lettering rather than art: a hand-drawn wolf reads as
#: hobbyist next to an interface whose whole argument is precision.
WORDMARK_BLOCK: Final = r"""██╗    ██╗ ██████╗ ██╗     ███████╗
██║    ██║██╔═══██╗██║     ██╔════╝
██║ █╗ ██║██║   ██║██║     █████╗
██║███╗██║██║   ██║██║     ██╔══╝
╚███╔███╔╝╚██████╔╝███████╗██║
 ╚══╝╚══╝  ╚═════╝ ╚══════╝╚═╝"""

#: The expansion. A joke, and simultaneously the most accurate four-word
#: description of the architecture: it monitors continuously, and the component
#: with veto power is deterministic code that cannot be argued with.
ACRONYM: Final = "watches obsessively, lacks feelings"

#: Deliberately *not* "local-first". That phrase is accurate about where state
#: lives (ADR-0002) but overclaims as a tagline. Prompts, quotes, filings, and
#: the broker all cross the network, and a reader would be right to call it out.
#: This says the thing that is true and checkable instead: the model may advise,
#: but deterministic local code holds the veto (ADR-0008).
TAGLINE: Final = "the model advises · your machine decides"

#: Legal stance, shown wherever the product introduces itself.
DISCLAIMER: Final = "experimental · paper trading · not investment advice"


def badge(text: str, *, danger: bool = False) -> str:
    """A filled block badge (PAPER, HALTED): dark ink on a colour field."""
    fg, bg = (Ink.ON_RED, Ink.RED) if danger else (Ink.ON_AMBER, Ink.INFRARED)
    return f"[{fg} on {bg}] {text} [/]"


def key(label: str, rest: str = "") -> str:
    """A footer key hint: infrared bracketed key, dim description.

    The opening bracket is escaped. Unescaped ``[c]`` is parsed as a style tag
    and vanishes from the footer entirely.
    """
    return f"[{Ink.AMBER}]\\[{label}][/][{Ink.DIM}]{rest}[/]"


def money_ink(value: Decimal | None) -> str:
    """Green above zero, red below, dim at exactly zero.

    Compared as Decimal. Money never becomes a float, not even to pick a colour.
    """
    if value is None:
        return Ink.DIM
    if value > 0:
        return Ink.GREEN
    if value < 0:
        return Ink.RED
    return Ink.DIM
