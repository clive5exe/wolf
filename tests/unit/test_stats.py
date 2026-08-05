"""Portfolio statistics: hand-computed Decimal expectations, honest unavailability."""

from __future__ import annotations

from decimal import Decimal

from tests.conftest import make_snapshot
from tradeos.portfolio.stats import compute_stats

D = Decimal


def test_allocation_weights_and_drift() -> None:
    # cash 2000 + AAPL 10*200=2000 + MSFT 4*400=1600 → total 5600
    snapshot = make_snapshot(
        D("2000"),
        holdings={"AAPL": (D("10"), D("150")), "MSFT": (D("4"), D("350"))},
        prices={"AAPL": D("200"), "MSFT": D("400")},
    )
    stats = compute_stats(snapshot, targets={"AAPL": D("0.30"), "VTI": D("0.10")})
    assert stats.total_value == D("5600")
    aapl = next(r for r in stats.rows if r.symbol == "AAPL")
    assert aapl.weight == D("2000") / D("5600")
    assert aapl.drift == D("2000") / D("5600") - D("0.30")
    assert aapl.unrealized_pnl == D("500.00")  # 10 * (200 - 150)
    # target with no position gets a drift row of -target
    vti = next(r for r in stats.rows if r.symbol == "VTI")
    assert vti.weight == D("0") and vti.drift == D("-0.10")


def test_concentration_measures() -> None:
    snapshot = make_snapshot(
        D("0"),
        holdings={"AAPL": (D("10"), D("100")), "MSFT": (D("5"), D("100"))},
        prices={"AAPL": D("100"), "MSFT": D("200")},
    )  # AAPL 1000, MSFT 1000, total 2000 → each weight 0.5
    stats = compute_stats(snapshot)
    assert stats.top3_concentration == D("1")
    assert stats.hhi == D("0.5")  # 0.25 + 0.25


def test_benchmark_stats_reported_unavailable_not_faked() -> None:
    stats = compute_stats(make_snapshot(D("1000")))
    for key in ("sharpe", "sortino", "beta"):
        assert key in stats.unavailable
        assert "benchmark" in stats.unavailable[key]


def test_cash_weight() -> None:
    snapshot = make_snapshot(
        D("500"), holdings={"AAPL": (D("5"), D("100"))}, prices={"AAPL": D("100")}
    )
    stats = compute_stats(snapshot)
    assert stats.cash_weight == D("500") / D("1000")
