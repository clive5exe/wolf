"""Rebalance strategy math. Hand-computed Decimal expectations."""

from __future__ import annotations

from decimal import Decimal

from tests.conftest import NOW, make_package, make_policy, make_snapshot
from tradeos.domain.orders import OrderSide
from tradeos.domain.policy import TargetAllocation
from tradeos.strategies.rebalance import TargetAllocationRebalance

D = Decimal


def run(strategy: TargetAllocationRebalance, policy, snapshot):
    return strategy.generate(
        snapshot=snapshot,
        policy=policy,
        package=make_package(),
        now=NOW,
        correlation_id="corr-test",
    )


def test_all_cash_generates_expected_buys() -> None:
    # 10_000 total. Targets: AAPL 30% → 3000/200 = 15 shares. MSFT 20% → 2000/400 = 5.
    policy = make_policy()
    snapshot = make_snapshot(D("10000"), prices={"AAPL": D("200"), "MSFT": D("400")})
    proposal = run(TargetAllocationRebalance(), policy, snapshot)
    assert [(a.side, a.symbol, a.quantity) for a in proposal.actions] == [
        (OrderSide.BUY, "AAPL", D("15")),
        (OrderSide.BUY, "MSFT", D("5")),
    ]


def test_within_threshold_is_no_action() -> None:
    # AAPL at 29.3%, MSFT at 19.5% of 12_300 total → both drifts < 2%
    policy = make_policy()
    snapshot = make_snapshot(
        D("6300"),
        holdings={"AAPL": (D("18"), D("150")), "MSFT": (D("6"), D("350"))},
        prices={"AAPL": D("200"), "MSFT": D("400")},
    )
    proposal = run(TargetAllocationRebalance(), policy, snapshot)
    assert proposal.is_no_action
    assert "no action" in proposal.rationale


def test_overweight_position_generates_sell_first() -> None:
    # AAPL 50 sh @200 = 10_000 of 12_000 (83%) vs target 30% → sell to ~3600 → sell 32.
    policy = make_policy(max_position_pct=D("0.90"))
    snapshot = make_snapshot(
        D("2000"),
        holdings={"AAPL": (D("50"), D("100"))},
        prices={"AAPL": D("200"), "MSFT": D("400")},
    )
    proposal = run(TargetAllocationRebalance(), policy, snapshot)
    sells = [a for a in proposal.actions if a.side == OrderSide.SELL]
    buys = [a for a in proposal.actions if a.side == OrderSide.BUY]
    assert sells and sells[0].symbol == "AAPL" and sells[0].quantity == D("32")
    assert proposal.actions[0].side == OrderSide.SELL  # sells sort first
    assert buys and buys[0].symbol == "MSFT" and buys[0].quantity == D("6")  # 2400/400


def test_fractional_quantities_when_allowed() -> None:
    policy = make_policy(fractional_shares_allowed=True)
    snapshot = make_snapshot(D("10000"), prices={"AAPL": D("300"), "MSFT": D("400")})
    proposal = run(TargetAllocationRebalance(), policy, snapshot)
    aapl = next(a for a in proposal.actions if a.symbol == "AAPL")
    assert aapl.quantity == D("10")  # 3000/300 exactly
    # and whole-share flooring when not allowed:
    floored = run(TargetAllocationRebalance(), make_policy(), snapshot)
    aapl_floor = next(a for a in floored.actions if a.symbol == "AAPL")
    assert aapl_floor.quantity == D("10")


def test_unpriced_portfolio_is_explicit_no_action() -> None:
    policy = make_policy()
    snapshot = make_snapshot(
        D("1000"),
        holdings={"AAPL": (D("5"), D("100"))},
        prices={},  # no quotes at all
    )
    proposal = run(TargetAllocationRebalance(), policy, snapshot)
    assert proposal.is_no_action
    assert "priceable" in proposal.rationale


def test_min_trade_value_guard() -> None:
    # Drift just over threshold but trade value tiny → skipped.
    policy = make_policy(
        target_allocations=(TargetAllocation(symbol="AAPL", weight=Decimal("0.30")),),
    )
    # total 1000. AAPL 11 sh @25 = 275 → 27.5% vs target 30% (drift 2.5% > 2%).
    # gap 25 → one whole share worth 25, below the $50 minimum → skipped.
    snapshot = make_snapshot(
        D("725"),
        holdings={"AAPL": (D("11"), D("20"))},
        prices={"AAPL": D("25")},
    )
    proposal = run(TargetAllocationRebalance(min_trade_value=D("50")), policy, snapshot)
    assert proposal.is_no_action
    assert "below minimum" in proposal.rationale


def test_no_targets_is_no_action() -> None:
    policy = make_policy(target_allocations=())
    snapshot = make_snapshot(D("10000"), prices={"AAPL": D("200")})
    proposal = run(TargetAllocationRebalance(), policy, snapshot)
    assert proposal.is_no_action
