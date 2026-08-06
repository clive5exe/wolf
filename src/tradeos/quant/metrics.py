"""The continuous quant layer: numbers the model never has to compute.

Ask a language model for a Sharpe ratio and it returns a plausible wrong
number. Ask it to size a position and it is confidently off. So it never
computes anything here. This module produces exact values from bars, and the
model reads them as facts and does what it is actually good at, which is
weighing evidence and arguing about it.

Everything here is **deterministic and pure**: same bars in, same numbers out,
no clock reads and no I/O. That is what lets a decision replay byte for byte
months later, and it is why the arithmetic lives outside the model rather than
inside a prompt.

Floats internally, because that is what numpy and scipy speak and a Sharpe
ratio is an estimate over noisy data where the fifteenth decimal place is
meaningless. Money stays Decimal everywhere else in the system, and the
conversion happens at this boundary, deliberately and in one place.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from itertools import pairwise
from typing import Final

import numpy as np
from numpy.typing import NDArray

#: US equity sessions in a year. Used to annualise, and stated as a constant so
#: a reported Sharpe cannot silently change because someone assumed 250.
TRADING_DAYS: Final[int] = 252

#: Clenow's momentum window. Long enough to be a trend, short enough to turn.
MOMENTUM_WINDOW: Final[int] = 90


class InsufficientHistory(ValueError):
    """Not enough bars to compute this honestly.

    Raised rather than returning a number from a short window. A momentum score
    over eleven days is not a small error, it is a different quantity, and
    NaN would sort silently to one end of a ranking.
    """


@dataclass(frozen=True, slots=True)
class Bar:
    """One session, as stored. Decimal because these are prices."""

    day: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None = None


def closes(bars: Sequence[Bar]) -> NDArray[np.float64]:
    return np.array([float(b.close) for b in bars], dtype=np.float64)


def _require(bars: Sequence[Bar], n: int, what: str) -> None:
    if len(bars) < n:
        raise InsufficientHistory(f"{what} needs {n} bars, got {len(bars)}")


# -- trend --------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Momentum:
    """Clenow's volatility-adjusted momentum, decomposed.

    ``score`` is what ranks. The parts are kept because the interface shows the
    arithmetic: a high slope with a low R squared is one gap pretending to be a
    trend, and hiding that behind a single number is how the ranking gets
    trusted for the wrong reason.
    """

    slope_annualised: float
    r_squared: float
    score: float


def momentum(bars: Sequence[Bar], window: int = MOMENTUM_WINDOW) -> Momentum:
    """Annualised exponential regression slope, multiplied by R squared.

    Exponential rather than linear because a linear slope is in dollars, so a
    $500 stock beats a $50 one for moving the same percentage. Regressing the
    log puts every symbol in percent and makes them comparable.
    """
    _require(bars, window, "momentum")
    y = np.log(closes(bars)[-window:])
    if not np.all(np.isfinite(y)):
        raise InsufficientHistory("momentum needs strictly positive closes")
    x = np.arange(window, dtype=np.float64)

    dx, dy = x - x.mean(), y - y.mean()
    ss_xx = float(dx @ dx)
    slope = float(dx @ dy) / ss_xx
    annualised = float(np.expm1(slope * TRADING_DAYS))

    residuals = y - ((y.mean() - slope * x.mean()) + slope * x)
    ss_res, ss_tot = float(residuals @ residuals), float(dy @ dy)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return Momentum(annualised, r2, annualised * r2)


def sma(bars: Sequence[Bar], window: int) -> float:
    _require(bars, window, f"sma({window})")
    return float(closes(bars)[-window:].mean())


def atr(bars: Sequence[Bar], window: int = 20) -> float:
    """Average true range, simple mean.

    Simple rather than Wilder's smoothing on purpose. Wilder's is recursive, so
    its value depends on how much leading history you happened to fetch: the
    same final bars give different answers from a 300 bar window and a 600 bar
    one. An indicator that changes with your fetch size cannot go in an
    append-only log that has to replay identically.
    """
    _require(bars, window + 1, f"atr({window})")
    recent = bars[-(window + 1) :]
    trs = [
        max(
            float(b.high - b.low),
            abs(float(b.high - prev.close)),
            abs(float(b.low - prev.close)),
        )
        for prev, b in pairwise(recent)
    ]
    return float(np.mean(trs))


def largest_gap(bars: Sequence[Bar], window: int = MOMENTUM_WINDOW) -> float:
    """Biggest single-session move in the window, as a fraction.

    Clenow disqualifies on this separately from R squared, and the two are not
    redundant: a single large gap can still leave a high score, because the
    move it adds outweighs the fit it costs.
    """
    _require(bars, 2, "gap")
    c = closes(bars)[-(window + 1) :]
    return float(np.max(np.abs(np.diff(c) / c[:-1]))) if len(c) > 1 else 0.0


# -- risk ---------------------------------------------------------------------


def returns(bars: Sequence[Bar]) -> NDArray[np.float64]:
    _require(bars, 2, "returns")
    c = closes(bars)
    return np.diff(c) / c[:-1]


def volatility(bars: Sequence[Bar], window: int = 20) -> float:
    """Annualised realised volatility."""
    _require(bars, window + 1, f"volatility({window})")
    return float(np.std(returns(bars)[-window:], ddof=1) * np.sqrt(TRADING_DAYS))


def max_drawdown(bars: Sequence[Bar]) -> float:
    """Worst peak-to-trough fall, as a negative fraction."""
    _require(bars, 2, "drawdown")
    c = closes(bars)
    peak = np.maximum.accumulate(c)
    return float(np.min(c / peak - 1.0))


def sharpe(bars: Sequence[Bar], risk_free: float = 0.0) -> float:
    """Annualised Sharpe. ``risk_free`` is an annual rate, stated not assumed."""
    r = returns(bars) - risk_free / TRADING_DAYS
    sd = float(np.std(r, ddof=1))
    return 0.0 if sd == 0 else float(np.mean(r) / sd * np.sqrt(TRADING_DAYS))


def sortino(bars: Sequence[Bar], risk_free: float = 0.0) -> float | None:
    """Like Sharpe but only downside moves count against you.

    The better measure for a long-only strategy, where upside volatility is the
    thing you were hoping for rather than a risk.

    Returns ``None`` when there were no losing sessions, because the ratio is
    then mathematically undefined: dividing by zero downside. The first version
    returned ``0.0``, which is worse than wrong. A strategy that never had a
    down day would have sorted *last* in any ranking, exactly below the ones
    that lost money. A caller now has to decide what an undefined ratio means
    rather than being handed a number that reads as terrible.
    """
    r = returns(bars) - risk_free / TRADING_DAYS
    downside = r[r < 0]
    if downside.size == 0:
        return None
    dd = float(np.sqrt(np.mean(downside**2)))
    return None if dd == 0 else float(np.mean(r) / dd * np.sqrt(TRADING_DAYS))


def correlation(a: Sequence[Bar], b: Sequence[Bar]) -> float:
    """Return correlation over the overlapping sessions.

    Aligned on date rather than by position. Two symbols can have different bar
    counts because of halts or listing dates, and zipping them blind silently
    compares Tuesday against Wednesday.
    """
    by_day = {bar.day: bar for bar in b}
    shared = [(x, by_day[x.day]) for x in a if x.day in by_day]
    if len(shared) < 3:
        raise InsufficientHistory(f"correlation needs 3 shared sessions, got {len(shared)}")
    ra = returns([x for x, _ in shared])
    rb = returns([y for _, y in shared])
    if np.std(ra) == 0 or np.std(rb) == 0:
        return 0.0
    return float(np.corrcoef(ra, rb)[0, 1])


# -- sizing -------------------------------------------------------------------


def atr_position_size(account_value: Decimal, atr_value: float, risk_fraction: float) -> int:
    """Clenow's sizing: every position risks the same daily move.

    ``shares = account_value * risk_fraction / ATR``. Equalising risk rather
    than dollars is the point: a volatile name gets a smaller position, so one
    holding cannot dominate the portfolio's daily swing.

    Returns whole shares, floored. Rounding up would exceed the risk budget the
    formula exists to enforce.
    """
    if atr_value <= 0 or risk_fraction <= 0:
        return 0
    return max(0, int(float(account_value) * risk_fraction / atr_value))


def regime_ok(index_bars: Sequence[Bar], window: int = 200) -> bool:
    """Whether the index is above its long moving average.

    Gates entries only, never exits. That asymmetry is deliberate: forced
    selling on a regime flip turns a drawdown into a realised loss, whereas
    refusing to buy lets the book scale out on its own as positions close.
    """
    _require(index_bars, window, f"regime({window})")
    return float(index_bars[-1].close) > sma(index_bars, window)
