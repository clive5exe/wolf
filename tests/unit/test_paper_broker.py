"""Paper engine: fills, slippage, accounting, rejection, event-sourced rebuild."""

from __future__ import annotations

from decimal import Decimal

import pytest

from tests.conftest import NOW, make_action, make_ctx, make_policy, make_proposal, make_snapshot
from tradeos.brokers.paper import PaperBroker
from tradeos.domain.clock import FixedClock
from tradeos.domain.orders import OrderSide, OrderStatus
from tradeos.domain.risk import ValidatedOrder
from tradeos.events.store import InMemoryEventStore
from tradeos.market_data.quotes import StaticQuoteSource
from tradeos.risk.engine import RiskEngine

D = Decimal
PRICES = {"AAPL": D("200"), "MSFT": D("400")}


def validated_order(side: OrderSide, symbol: str, qty: Decimal) -> ValidatedOrder:
    """Orders can only be minted by the risk engine — tests included.

    The minting snapshot is deliberately richer than the broker's actual
    state so the broker's independent guards (insufficient cash/holdings)
    can be exercised — the real-world "state changed between validation
    and execution" case.
    """
    snapshot = make_snapshot(
        D("1000000"),
        holdings={"AAPL": (D("100"), D("150"))},
        prices=PRICES,
    )
    policy = make_policy(
        max_position_pct=D("0.98"),
        max_sector_pct=D("1"),
        min_cash_pct=D("0"),
        max_order_value_usd=D("1000000"),
    )
    validation = RiskEngine().validate_proposal(
        make_proposal((make_action(side, symbol, qty),)), make_ctx(policy, snapshot)
    )
    assert validation.fully_approved, validation.verdicts[0].results
    return validation.validated_orders[0]


@pytest.fixture()
def broker() -> PaperBroker:
    return PaperBroker(
        event_store=InMemoryEventStore(),
        quote_source=StaticQuoteSource(PRICES),
        clock=FixedClock(NOW),
        initial_cash=D("100000"),
        slippage_bps=D("5"),
    )


def test_buy_fill_applies_slippage_against_trader(broker: PaperBroker) -> None:
    result = broker.submit_order(validated_order(OrderSide.BUY, "AAPL", D("10")))
    assert result.status == OrderStatus.FILLED
    assert result.fill is not None
    assert result.fill.price == D("200.10")  # 200 * (1 + 5/10000)
    account = broker.get_account()
    assert account.cash == D("100000") - D("2001.00")
    position = account.position_for("AAPL")
    assert position is not None and position.quantity == D("10")


def test_sell_fill_receives_less(broker: PaperBroker) -> None:
    broker.submit_order(validated_order(OrderSide.BUY, "AAPL", D("10")))
    result = broker.submit_order(validated_order(OrderSide.SELL, "AAPL", D("4")))
    assert result.status == OrderStatus.FILLED
    assert result.fill is not None
    assert result.fill.price == D("199.90")  # 200 * (1 - 5/10000)
    account = broker.get_account()
    position = account.position_for("AAPL")
    assert position is not None and position.quantity == D("6")
    assert account.cash == D("100000") - D("2001.00") + D("799.60")


def test_insufficient_cash_rejected(broker: PaperBroker) -> None:
    result = broker.submit_order(validated_order(OrderSide.BUY, "AAPL", D("600")))
    assert result.status == OrderStatus.REJECTED
    assert result.error is not None and "insufficient cash" in result.error
    assert broker.get_account().cash == D("100000")  # unchanged


def test_oversell_rejected(broker: PaperBroker) -> None:
    result = broker.submit_order(validated_order(OrderSide.SELL, "AAPL", D("5")))
    assert result.status == OrderStatus.REJECTED
    assert result.error is not None and "insufficient holdings" in result.error


def test_avg_cost_blends_on_rebuy(broker: PaperBroker) -> None:
    broker.submit_order(validated_order(OrderSide.BUY, "AAPL", D("10")))  # @200.10
    broker.submit_order(validated_order(OrderSide.BUY, "MSFT", D("1")))
    broker.submit_order(validated_order(OrderSide.BUY, "AAPL", D("10")))  # @200.10
    position = broker.get_account().position_for("AAPL")
    assert position is not None
    assert position.quantity == D("20")
    assert position.avg_cost == D("200.1000")


def test_state_rebuilds_identically_from_events() -> None:
    store = InMemoryEventStore()
    clock = FixedClock(NOW)
    source = StaticQuoteSource(PRICES)
    live = PaperBroker(
        event_store=store, quote_source=source, clock=clock, initial_cash=D("100000")
    )
    live.submit_order(validated_order(OrderSide.BUY, "AAPL", D("10")))
    live.submit_order(validated_order(OrderSide.SELL, "AAPL", D("3")))
    rebuilt = PaperBroker(
        event_store=store, quote_source=source, clock=clock, initial_cash=D("999")
    )  # initial_cash ignored: history wins
    live_account = live.get_account()
    rebuilt_account = rebuilt.get_account()
    assert rebuilt_account.cash == live_account.cash
    assert rebuilt_account.positions == live_account.positions
