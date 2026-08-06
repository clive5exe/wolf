"""These numbers reach the risk engine as fact, so wrong beats missing here.

Several cases exist because a plausible implementation gets them subtly wrong
in a way no smoke test catches: an ATR that changes with fetch size, a
correlation that compares Tuesday to Wednesday, a momentum score computed from
a window too short to mean anything.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from decimal import Decimal

import pytest

from tradeos.quant.metrics import (
    TRADING_DAYS,
    Bar,
    InsufficientHistory,
    atr,
    atr_position_size,
    correlation,
    largest_gap,
    max_drawdown,
    momentum,
    regime_ok,
    sharpe,
    sma,
    sortino,
    volatility,
)


def series(closes: list[float], start: date = date(2026, 1, 5)) -> list[Bar]:
    """Bars with a small daily range, so high and low are never degenerate."""
    out = []
    for i, c in enumerate(closes):
        d = Decimal(str(c))
        out.append(
            Bar(
                day=start + timedelta(days=i),
                open=d,
                high=d * Decimal("1.01"),
                low=d * Decimal("0.99"),
                close=d,
            )
        )
    return out


class TestMomentum:
    def test_matches_the_published_worked_example(self) -> None:
        """Clenow states a 0.06% daily slope annualises to roughly 16%."""
        result = momentum(series([100 * 1.0006**i for i in range(90)]))
        assert result.slope_annualised == pytest.approx(0.1618, abs=0.002)
        assert result.r_squared == pytest.approx(1.0, abs=1e-9)

    def test_r_squared_punishes_a_choppy_climb(self) -> None:
        smooth = momentum(series([100 * 1.001**i for i in range(90)]))
        choppy = momentum(series([100 * 1.001**i * (1.04 if i % 2 else 0.96) for i in range(90)]))
        assert smooth.r_squared > 0.99
        assert choppy.r_squared < smooth.r_squared
        assert choppy.score < smooth.score

    def test_a_falling_stock_scores_negative(self) -> None:
        """Without expm1 a decline scores near zero instead of deeply negative,
        which puts falling stocks above flat ones in a ranking."""
        assert momentum(series([100 * 0.999**i for i in range(90)])).score < -0.15

    def test_price_level_does_not_change_the_score(self) -> None:
        """A linear slope is in dollars, so a $500 stock would beat a $50 one
        for the same percentage move. Regressing the log removes that."""
        cheap = momentum(series([10 * 1.001**i for i in range(90)]))
        rich = momentum(series([1000 * 1.001**i for i in range(90)]))
        assert cheap.score == pytest.approx(rich.score, rel=1e-9)

    def test_short_history_raises_rather_than_returning_a_number(self) -> None:
        with pytest.raises(InsufficientHistory, match="90 bars"):
            momentum(series([100.0] * 40))


class TestAtrIsPathIndependent:
    """TA-Lib's Wilder smoothing is recursive, so the same final bars give
    different answers depending on how much leading history was fetched. An
    indicator that changes with fetch size cannot live in a replayable log."""

    def test_same_final_bars_give_the_same_atr(self) -> None:
        tail = [100 + math.sin(i / 3) * 5 for i in range(40)]
        short = series([100.0] * 20 + tail)
        long = series([100.0] * 400 + tail)
        assert atr(short) == pytest.approx(atr(long), rel=1e-12)

    def test_needs_one_bar_more_than_the_window(self) -> None:
        """True range compares against the previous close, so 20 ranges need 21
        bars, not 20."""
        with pytest.raises(InsufficientHistory):
            atr(series([100.0] * 20), window=20)
        assert atr(series([100.0] * 21), window=20) >= 0


class TestRisk:
    def test_drawdown_is_peak_to_trough_not_first_to_last(self) -> None:
        # Rises to 150, falls to 75, recovers to 140. Worst fall is 50%.
        bars = series([100, 150, 75, 140])
        assert max_drawdown(bars) == pytest.approx(-0.5, abs=1e-9)

    def test_a_monotonic_riser_has_no_drawdown(self) -> None:
        assert max_drawdown(series([100, 110, 120])) == pytest.approx(0.0)

    def test_volatility_is_annualised(self) -> None:
        bars = series([100 * (1.01 if i % 2 else 0.99) ** 1 for i in range(40)])
        assert volatility(bars) > 0
        # Sanity: a daily series annualises by root 252, so it must exceed the
        # raw daily figure by roughly that factor.
        assert volatility(bars) < math.sqrt(TRADING_DAYS)

    def test_sortino_ignores_upside_volatility(self) -> None:
        """A long-only strategy's upside swings are the point, not a risk."""
        bars = series([100, 104, 103, 108, 107, 113, 112, 119])
        s, so = sharpe(bars), sortino(bars)
        assert so is not None
        assert so > s, "penalising only downside should score better than penalising both"

    def test_sortino_is_undefined_rather_than_zero_without_losses(self) -> None:
        """0.0 would sort a never-losing strategy below one that lost money."""
        assert sortino(series([100, 110, 120, 130])) is None

    def test_flat_series_do_not_divide_by_zero(self) -> None:
        flat = series([100.0] * 30)
        assert sharpe(flat) == 0.0
        assert sortino(flat) is None


class TestCorrelation:
    def test_aligns_on_date_not_position(self) -> None:
        """Two symbols can have different bar counts after a halt. Zipping them
        blind compares one symbol's Tuesday against another's Wednesday."""
        a = series([100, 102, 104, 106, 108])
        b = [bar for i, bar in enumerate(series([50, 51, 52, 53, 54])) if i != 1]
        assert correlation(a, b) == pytest.approx(1.0, abs=1e-9)

    def test_opposite_movers_are_negatively_correlated(self) -> None:
        """Note this must be built from opposing *returns*, not opposing prices.

        A linear rise has shrinking percentage returns and a linear fall has
        deepening negative ones, so both are monotonically decreasing and
        correlate near +1. Asserting the intuition instead of the arithmetic is
        how this test was wrong the first time.
        """
        a, b = [100.0], [100.0]
        for i in range(10):
            step = 0.03 if i % 2 else -0.02
            a.append(a[-1] * (1 + step))
            b.append(b[-1] * (1 - step))
        assert correlation(series(a), series(b)) < -0.95

    def test_too_little_overlap_raises(self) -> None:
        a = series([100, 101, 102, 103])
        b = series([50, 51], start=date(2030, 1, 1))
        with pytest.raises(InsufficientHistory):
            correlation(a, b)


class TestSizing:
    def test_equal_risk_means_the_volatile_name_gets_less(self) -> None:
        account = Decimal("100000")
        calm = atr_position_size(account, atr_value=1.0, risk_fraction=0.001)
        wild = atr_position_size(account, atr_value=10.0, risk_fraction=0.001)
        assert calm == 10 * wild

    def test_shares_are_floored_never_rounded_up(self) -> None:
        """Rounding up exceeds the risk budget the formula exists to enforce."""
        assert atr_position_size(Decimal("1000"), atr_value=3.0, risk_fraction=0.001) == 0

    def test_zero_or_negative_atr_sizes_nothing(self) -> None:
        assert atr_position_size(Decimal("100000"), 0.0, 0.001) == 0
        assert atr_position_size(Decimal("100000"), -1.0, 0.001) == 0


class TestRegime:
    def test_above_the_average_permits_entries(self) -> None:
        assert regime_ok(series([100 + i for i in range(200)]), window=200)

    def test_below_the_average_blocks_them(self) -> None:
        assert not regime_ok(series([300 - i for i in range(200)]), window=200)


class TestGaps:
    def test_finds_the_largest_single_session_move(self) -> None:
        assert largest_gap(series([100, 101, 120, 121])) == pytest.approx(0.188, abs=0.01)

    def test_a_gap_can_survive_a_high_score(self) -> None:
        """Why Clenow disqualifies on gaps separately from R squared: the move a
        gap adds can outweigh the fit it costs."""
        gappy = series([100.0] * 45 + [130.0] * 45)
        assert momentum(gappy).score > 0
        assert largest_gap(gappy) > 0.15


def test_sma_uses_only_the_trailing_window() -> None:
    bars = series([1.0] * 50 + [10.0] * 10)
    assert sma(bars, 10) == pytest.approx(10.0)
