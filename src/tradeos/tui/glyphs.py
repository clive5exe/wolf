"""Pure text renderers: gauges, sparklines, freshness, number formatting.

No Textual imports and no runtime access — these take values and return
strings, which is what makes the dense parts of the dashboard unit-testable
without a terminal.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal, InvalidOperation

from tradeos.tui.theme import Ink

# -- freshness ----------------------------------------------------------------

FRESH: str = "●"
AGING: str = "◐"
STALE: str = "○"
EXPIRED: str = "✕"


def freshness_glyph(age_s: int | None, ttl_s: int) -> str:
    """● fresh · ◐ aging · ○ stale · ✕ no data at all.

    Freshness is never hidden: an absent quote is louder than an old one, and
    a stale source stops pulsing so you notice the *absence* of motion.
    """
    if age_s is None:
        return EXPIRED
    if ttl_s <= 0:
        return FRESH if age_s == 0 else STALE
    if age_s <= ttl_s // 2:
        return FRESH
    if age_s <= ttl_s:
        return AGING
    return STALE


def freshness_ink(age_s: int | None, ttl_s: int) -> str:
    glyph = freshness_glyph(age_s, ttl_s)
    if glyph == FRESH:
        return Ink.GREEN
    if glyph == AGING:
        return Ink.AMBER
    return Ink.RED


# -- drift gauge --------------------------------------------------------------

GAUGE_WIDTH: int = 8
GAUGE_TARGET_INDEX: int = 3
#: Drift at which the marker reaches the end of the track. Defaults to the
#: rebalance threshold, so "at the edge" literally means "about to trade".
GAUGE_FULL_SCALE: Decimal = Decimal("0.02")

_TRACK = "─"
_TARGET = "┼"
_MARKER = "◆"
_UNDER_EDGE = "◀"
_OVER_EDGE = "▶"


def drift_gauge(drift: Decimal | None, *, full_scale: Decimal = GAUGE_FULL_SCALE) -> str:
    """Render drift *spatially*: ``──◆┼────`` is under target, ``───┼◆───`` over.

    ``┼`` is always the target and always sits in the same column, so a column
    of holdings reads as one aligned ruler. The track is scaled to
    ``full_scale`` — the rebalance threshold — which makes position on the
    gauge mean something specific: reaching the edge is the point at which the
    strategy proposes a trade. Drift past that pins to ◀ / ▶ rather than
    silently clamping, because off-scale must look off-scale.
    """
    if drift is None:
        return " " * GAUGE_WIDTH
    if full_scale <= 0:
        raise ValueError("gauge full_scale must be positive")

    cell = full_scale / GAUGE_TARGET_INDEX
    offset = int((drift / cell).to_integral_value(rounding="ROUND_HALF_UP"))
    index = GAUGE_TARGET_INDEX + offset
    cells = [_TRACK] * GAUGE_WIDTH
    cells[GAUGE_TARGET_INDEX] = _TARGET

    if index < 0:
        cells[0] = _UNDER_EDGE
    elif index >= GAUGE_WIDTH:
        cells[GAUGE_WIDTH - 1] = _OVER_EDGE
    else:
        cells[index] = _MARKER
    return "".join(cells)


def paint_gauge(drift: Decimal | None, *, full_scale: Decimal = GAUGE_FULL_SCALE) -> str:
    """The gauge as markup: amber marker and target, faint track."""
    raw = drift_gauge(drift, full_scale=full_scale)
    out: list[str] = []
    for char in raw:
        if char in (_MARKER, _TARGET, _UNDER_EDGE, _OVER_EDGE):
            out.append(f"[{Ink.AMBER}]{char}[/]")
        else:
            out.append(f"[{Ink.FAINT}]{char}[/]")
    return "".join(out)


# -- sparkline ----------------------------------------------------------------

BLOCKS: str = "▁▂▃▄▅▆▇█"


def sparkline(values: Sequence[Decimal], width: int = 22) -> str:
    """Block sparkline over the last ``width`` values.

    A flat or single-point series renders mid-height rather than at the floor,
    because a bottomed-out line reads as a crash that did not happen.
    """
    if not values:
        return ""
    points = list(values[-width:])
    if len(points) == 1:
        return BLOCKS[len(BLOCKS) // 2]
    low, high = min(points), max(points)
    if high == low:
        return BLOCKS[len(BLOCKS) // 2] * len(points)
    span = high - low
    top = Decimal(len(BLOCKS) - 1)
    out = []
    for value in points:
        level = int(((value - low) / span * top).to_integral_value(rounding="ROUND_HALF_UP"))
        out.append(BLOCKS[max(0, min(len(BLOCKS) - 1, level))])
    return "".join(out)


# -- number formatting --------------------------------------------------------


def fmt_money(value: Decimal | None, *, places: int = 2) -> str:
    if value is None:
        return "—"
    quant = Decimal(1).scaleb(-places)
    return f"${value.quantize(quant):,}"


def fmt_signed(value: Decimal | None, *, places: int = 2) -> str:
    if value is None:
        return "—"
    quant = Decimal(1).scaleb(-places)
    rounded = value.quantize(quant)
    return f"{'+' if rounded > 0 else '−' if rounded < 0 else ''}{abs(rounded):,}"


def fmt_pct(value: Decimal | None, *, places: int = 1) -> str:
    """A 0..1 fraction as a percentage."""
    if value is None:
        return "—"
    quant = Decimal(1).scaleb(-places)
    return f"{(value * 100).quantize(quant)}%"


def fmt_signed_pct(value: Decimal | None, *, places: int = 1) -> str:
    """A signed percentage using a true minus sign, so columns align."""
    if value is None:
        return "—"
    quant = Decimal(1).scaleb(-places)
    rounded = (value * 100).quantize(quant)
    sign = "+" if rounded > 0 else "−" if rounded < 0 else ""
    return f"{sign}{abs(rounded)}%"


def fmt_qty(value: Decimal | None) -> str:
    """Share counts: integers stay integers, fractions keep their precision.

    Uses fixed-point formatting throughout — ``normalize`` alone renders 140 as
    ``1.4E+2``, which is never what a share count should look like.
    """
    if value is None:
        return "—"
    normalized = value.normalize()
    if normalized == normalized.to_integral_value():
        return f"{int(normalized):,}"
    return f"{normalized:,f}"


def fmt_completeness(raw: str) -> str:
    """Context completeness is stored as a 0..1 decimal string; show it as a percent."""
    if not raw:
        return "—"
    try:
        return fmt_pct(Decimal(raw), places=0)
    except (InvalidOperation, ValueError):
        return raw


def fmt_age(age_s: int | None) -> str:
    if age_s is None:
        return "no data"
    if age_s < 60:
        return f"{age_s}s"
    if age_s < 3600:
        return f"{age_s // 60}m"
    return f"{age_s // 3600}h"


def truncate(text: str, limit: int) -> str:
    """Ellipsize to ``limit`` display columns."""
    if limit <= 0:
        return ""
    return text if len(text) <= limit else text[: max(0, limit - 1)] + "…"
