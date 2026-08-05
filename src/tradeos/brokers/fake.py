"""Deterministic scripted broker for tests (ADR-0004).

Fills every valid order exactly at the scripted quote price (zero slippage)
so unit tests get exact Decimal arithmetic. Records everything it was asked
to do for assertion.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from tradeos.brokers.base import BrokerCapability, assert_submittable
from tradeos.domain.common import new_ulid
from tradeos.domain.market import Quote
from tradeos.domain.orders import Fill, OrderResult, OrderStatus
from tradeos.domain.portfolio import AccountState
from tradeos.domain.risk import ValidatedOrder


class FakeBroker:
    name = "fake"

    def __init__(
        self,
        account: AccountState,
        quotes: dict[str, Quote],
        *,
        now: datetime,
        reject_symbols: frozenset[str] = frozenset(),
    ) -> None:
        self._account = account
        self._quotes = {k.upper(): v for k, v in quotes.items()}
        self._now = now
        self._reject_symbols = reject_symbols
        self.submitted: list[ValidatedOrder] = []

    def capabilities(self) -> frozenset[BrokerCapability]:
        return frozenset({BrokerCapability.READ, BrokerCapability.PAPER})

    def get_account(self) -> AccountState:
        return self._account

    def get_quote(self, symbol: str) -> Quote | None:
        return self._quotes.get(symbol.upper())

    def submit_order(self, order: ValidatedOrder) -> OrderResult:
        validated = assert_submittable(order, now=self._now)
        self.submitted.append(validated)
        symbol = validated.action.symbol
        if symbol in self._reject_symbols:
            return OrderResult(
                order_id=validated.order_id,
                client_order_id=validated.client_order_id,
                status=OrderStatus.REJECTED,
                error=f"scripted rejection for {symbol}",
            )
        quote = self._quotes.get(symbol)
        if quote is None:
            return OrderResult(
                order_id=validated.order_id,
                client_order_id=validated.client_order_id,
                status=OrderStatus.REJECTED,
                error=f"no quote for {symbol}",
            )
        return OrderResult(
            order_id=validated.order_id,
            client_order_id=validated.client_order_id,
            status=OrderStatus.FILLED,
            broker_order_id=f"fake-{new_ulid()[:10]}",
            fill=Fill(
                price=quote.price,
                quantity=validated.action.quantity,
                filled_at=self._now,
                slippage_bps=Decimal("0"),
            ),
        )
