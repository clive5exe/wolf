"""Charts drawn in character cells.

Pure, like ``glyphs``. Takes numbers, returns lines of markup. No Textual
imports and no runtime access, so every chart is unit-testable without a
terminal and reproduces exactly in an exported screenshot.

Two renderers, and the choice of glyph in each is the whole craft:

* :func:`candles` uses the light/heavy box-drawing verticals. A cell carries a
  top half and a bottom half independently, each empty, light (wick) or heavy
  (body), so one column gives half-cell resolution *and* tells a wick from a
  body. The heavy vertical is drawn narrower than the cell, so candles separate
  themselves without spending a column on a gap.

* :func:`line` uses quadrant blocks at 2x2. Braille packs 2x4 and is therefore
  the obvious choice, and it is wrong: on a volatile daily series its dots never
  touch, so the eye reads a scatter plot instead of a line. Quadrants are
  coarser on paper and better on screen.

Terminal image protocols would beat both, and were rejected: they render as
tofu in an exported screenshot, macOS Terminal supports none of them, and
several terminals advertise support then draw garbage.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from tradeos.tui.theme import Ink

# -- candlesticks -------------------------------------------------------------

#: (top half, bottom half) -> glyph.  0 empty · 1 light wick · 2 heavy body
_CANDLE: dict[tuple[int, int], str] = {
    (0, 0): " ",
    (1, 0): "╵",
    (2, 0): "╹",
    (0, 1): "╷",
    (1, 1): "│",
    (2, 1): "╿",
    (0, 2): "╻",
    (1, 2): "╽",
    (2, 2): "┃",
}

_WICK, _BODY = 1, 2


@dataclass(frozen=True, slots=True)
class Bar:
    """One session. Decimal throughout: these are prices."""

    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal

    @property
    def rising(self) -> bool:
        return self.close >= self.open


def _scale(value: Decimal, low: Decimal, high: Decimal, steps: int) -> int:
    """Value to a half-cell row index, 0 at the top."""
    if high <= low:
        return steps // 2
    frac = (value - low) / (high - low)
    index = int((Decimal(steps - 1) * (1 - frac)).to_integral_value(rounding="ROUND_HALF_UP"))
    return max(0, min(steps - 1, index))


def candles(bars: Sequence[Bar], *, rows: int = 14) -> list[str]:
    """An OHLC chart as markup, one string per row.

    Colour is direction and nothing else, which keeps green and red doing the
    single job they do everywhere in this interface: money.
    """
    if not bars or rows < 2:
        return []
    low = min(b.low for b in bars)
    high = max(b.high for b in bars)
    steps = rows * 2

    grid = [[(0, 0)] * len(bars) for _ in range(rows)]
    ink = [[Ink.FAINT] * len(bars) for _ in range(rows)]

    for x, bar in enumerate(bars):
        colour = Ink.GREEN if bar.rising else Ink.RED
        body_top = _scale(max(bar.open, bar.close), low, high, steps)
        body_bottom = _scale(min(bar.open, bar.close), low, high, steps)
        for step in range(
            _scale(bar.high, low, high, steps), _scale(bar.low, low, high, steps) + 1
        ):
            weight = _BODY if body_top <= step <= body_bottom else _WICK
            row, half = divmod(step, 2)
            top, bottom = grid[row][x]
            grid[row][x] = (max(top, weight), bottom) if half == 0 else (top, max(bottom, weight))
            ink[row][x] = colour

    return [_paint(row, tint) for row, tint in zip(grid, ink, strict=True)]


def _paint(cells: Sequence[tuple[int, int]], inks: Sequence[str]) -> str:
    """Emit colour runs rather than one span per character.

    A naive renderer wraps every cell in its own markup, which for a full chart
    is an order of magnitude more output than the picture needs.
    """
    out: list[str] = []
    run: list[str] = []
    current = ""
    for cell, tint in zip(cells, inks, strict=True):
        glyph = _CANDLE[cell]
        tint = tint if glyph != " " else ""
        if tint != current:
            if run:
                out.append(f"[{current}]{''.join(run)}[/]" if current else "".join(run))
            run, current = [], tint
        run.append(glyph)
    if run:
        out.append(f"[{current}]{''.join(run)}[/]" if current else "".join(run))
    return "".join(out)


# -- line ---------------------------------------------------------------------

#: Quadrant blocks, indexed by a 4-bit mask: TL=1, TR=2, BL=4, BR=8.
_QUAD = " ▘▝▀▖▌▞▛▗▚▐▜▄▙▟█"


def line(
    values: Sequence[Decimal], *, width: int = 60, rows: int = 8, ink: str = Ink.CYAN
) -> list[str]:
    """A connected line chart, 2x2 subpixels per cell.

    Successive points are joined rather than plotted, because a gap in a price
    line reads as missing data instead of a steep move.
    """
    if len(values) < 2 or width < 2 or rows < 1:
        return []
    low, high = min(values), max(values)
    px, py = width * 2, rows * 2
    mask = [[0] * width for _ in range(rows)]

    def put(x: int, y: int) -> None:
        if 0 <= x < px and 0 <= y < py:
            mask[y // 2][x // 2] |= 1 << ((y % 2) * 2 + (x % 2))

    def at(i: int) -> tuple[int, int]:
        x = i * (px - 1) // (len(values) - 1)
        return x, _scale(values[i], low, high, py)

    for i in range(1, len(values)):
        (x0, y0), (x1, y1) = at(i - 1), at(i)
        span = max(abs(x1 - x0), abs(y1 - y0), 1)
        for step in range(span + 1):
            put(round(x0 + (x1 - x0) * step / span), round(y0 + (y1 - y0) * step / span))

    return [
        f"[{ink}]{''.join(_QUAD[bit] for bit in row).rstrip()}[/]" if any(row) else ""
        for row in mask
    ]


def price_axis(low: Decimal, high: Decimal, rows: int) -> list[str]:
    """Right-hand labels for a chart of ``rows`` rows: top, middle, bottom."""
    if rows < 2:
        return []
    labels = [""] * rows
    labels[0] = f"${high:,.2f}"
    labels[-1] = f"${low:,.2f}"
    if rows >= 5:
        labels[rows // 2] = f"${(high + low) / 2:,.2f}"
    return labels
