"""Contract tests every BrokerAdapter implementation must pass (ADR-0004)."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

import pytest

from tests.conftest import NOW, make_action, make_ctx, make_policy, make_proposal, make_snapshot
from tradeos.brokers.base import BrokerAdapter, BrokerCapability, BrokerProtocolError
from tradeos.brokers.fake import FakeBroker
from tradeos.brokers.paper import PaperBroker
from tradeos.domain.clock import FixedClock
from tradeos.domain.market import Quote
from tradeos.domain.orders import OrderSide
from tradeos.domain.risk import ValidatedOrder
from tradeos.events.store import InMemoryEventStore
from tradeos.market_data.quotes import StaticQuoteSource
from tradeos.risk.engine import RiskEngine

D = Decimal
PRICES = {"AAPL": D("200")}


def _fake() -> FakeBroker:
    account = make_snapshot(D("50000"), prices=PRICES).account
    return FakeBroker(
        account, {"AAPL": Quote(symbol="AAPL", price=D("200"), as_of=NOW, source="t")}, now=NOW
    )


def _paper() -> PaperBroker:
    return PaperBroker(
        event_store=InMemoryEventStore(),
        quote_source=StaticQuoteSource(PRICES),
        clock=FixedClock(NOW),
        initial_cash=D("50000"),
    )


BROKERS: list[tuple[str, Callable[[], BrokerAdapter]]] = [
    ("fake", _fake),
    ("paper", _paper),
]


def approved_order() -> ValidatedOrder:
    snapshot = make_snapshot(D("50000"), prices=PRICES)
    validation = RiskEngine().validate_proposal(
        make_proposal((make_action(OrderSide.BUY, "AAPL", D("5")),)),
        make_ctx(make_policy(), snapshot),
    )
    return validation.validated_orders[0]


@pytest.mark.parametrize(("name", "factory"), BROKERS)
def test_implements_protocol(name: str, factory: Callable[[], BrokerAdapter]) -> None:
    broker = factory()
    assert isinstance(broker, BrokerAdapter)
    caps = broker.capabilities()
    assert BrokerCapability.READ in caps
    assert BrokerCapability.TRADE not in caps  # nothing trades for real in v0.1


@pytest.mark.parametrize(("name", "factory"), BROKERS)
def test_account_and_quote_reads(name: str, factory: Callable[[], BrokerAdapter]) -> None:
    broker = factory()
    account = broker.get_account()
    assert account.cash >= 0
    quote = broker.get_quote("AAPL")
    assert quote is not None and quote.price == D("200")
    assert broker.get_quote("UNKNOWN") is None


@pytest.mark.parametrize(("name", "factory"), BROKERS)
def test_rejects_unvalidated_submissions(name: str, factory: Callable[[], BrokerAdapter]) -> None:
    with pytest.raises(BrokerProtocolError):
        factory().submit_order(make_action(OrderSide.BUY, "AAPL", D("1")))  # type: ignore[arg-type]


@pytest.mark.parametrize(("name", "factory"), BROKERS)
def test_fills_carry_full_audit_fields(name: str, factory: Callable[[], BrokerAdapter]) -> None:
    result = factory().submit_order(approved_order())
    assert result.client_order_id
    assert result.fill is not None
    assert result.fill.price > 0 and result.fill.quantity == D("5")
    assert result.fill.slippage_bps >= 0
