"""Paper trading engine (ADR-0009).

Simulation model (documented assumptions):
- Market orders fill entirely at quote price adjusted by ``slippage_bps``
  against the trader (buys pay more, sells receive less).
- No partial fills, no spread model, no market impact in v0.1 — these are
  recorded limitations, not hidden ones (fill events carry the assumption).
- State is event-sourced: every accepted order appends ``order.filled`` with
  the resulting cash balance; ``from_events`` rebuilds identical state
  (replay-equality tested).
"""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal

from tradeos.brokers.base import BrokerCapability, assert_submittable
from tradeos.domain.clock import Clock
from tradeos.domain.market import Quote
from tradeos.domain.orders import Fill, OrderResult, OrderSide, OrderStatus
from tradeos.domain.policy import AssetType
from tradeos.domain.portfolio import AccountState, Position
from tradeos.domain.risk import ValidatedOrder
from tradeos.events.store import EventStore
from tradeos.events.types import EventType
from tradeos.market_data.quotes import QuoteSource

_CENT = Decimal("0.01")
_BPS = Decimal("10000")


class PaperBroker:
    name = "paper"

    def __init__(
        self,
        *,
        event_store: EventStore,
        quote_source: QuoteSource,
        clock: Clock,
        account_id: str = "paper-1",
        initial_cash: Decimal = Decimal("100000"),
        slippage_bps: Decimal = Decimal("5"),
        sector_map: dict[str, str] | None = None,
    ) -> None:
        self._events = event_store
        self._quotes = quote_source
        self._clock = clock
        self._account_id = account_id
        self._slippage_bps = slippage_bps
        self._sector_map = {k.upper(): v for k, v in (sector_map or {}).items()}
        self._cash = initial_cash
        self._positions: dict[str, Position] = {}
        self._replayed = self._rebuild_from_events(initial_cash)
        if not self._replayed:
            self._events.append(
                EventType.PAPER_INITIALIZED,
                {"account_id": account_id, "initial_cash": str(initial_cash)},
            )

    # -- BrokerAdapter ---------------------------------------------------------

    def capabilities(self) -> frozenset[BrokerCapability]:
        return frozenset({BrokerCapability.READ, BrokerCapability.PAPER})

    def get_account(self) -> AccountState:
        return AccountState(
            account_id=self._account_id,
            cash=self._cash,
            positions=tuple(self._positions.values()),
            as_of=self._clock.now(),
        )

    def get_quote(self, symbol: str) -> Quote | None:
        return self._quotes.get_quote(symbol, now=self._clock.now())

    def submit_order(self, order: ValidatedOrder) -> OrderResult:
        now = self._clock.now()
        validated = assert_submittable(order, now=now)
        action = validated.action
        quote = self.get_quote(action.symbol)
        if quote is None:
            return self._reject(validated, f"no quote for {action.symbol}")

        fill_price = self._apply_slippage(quote.price, action.side)
        notional = (fill_price * action.quantity).quantize(_CENT, rounding=ROUND_HALF_EVEN)

        if action.side == OrderSide.BUY:
            if notional > self._cash:
                return self._reject(
                    validated, f"insufficient cash: need {notional}, have {self._cash}"
                )
            self._cash -= notional
            self._apply_buy(action.symbol, action.quantity, fill_price, action.asset_type)
        else:
            held = self._positions.get(action.symbol)
            if held is None or held.quantity < action.quantity:
                have = held.quantity if held else Decimal("0")
                return self._reject(
                    validated, f"insufficient holdings: sell {action.quantity}, have {have}"
                )
            self._cash += notional
            self._apply_sell(action.symbol, action.quantity)

        fill = Fill(
            price=fill_price,
            quantity=action.quantity,
            filled_at=now,
            slippage_bps=self._slippage_bps,
        )
        self._events.append(
            EventType.ORDER_FILLED,
            {
                "order_id": validated.order_id,
                "client_order_id": validated.client_order_id,
                "symbol": action.symbol,
                "side": action.side.value,
                "asset_type": action.asset_type.value,
                "quantity": str(action.quantity),
                "fill_price": str(fill_price),
                "quote_price": str(quote.price),
                "slippage_bps": str(self._slippage_bps),
                "cash_after": str(self._cash),
                "fill_model": "quote±slippage_bps, full fill, no spread/impact (v0.1)",
            },
            occurred_at=now,
            correlation_id=validated.proposal_id,
        )
        return OrderResult(
            order_id=validated.order_id,
            client_order_id=validated.client_order_id,
            status=OrderStatus.FILLED,
            broker_order_id=f"paper-{validated.client_order_id[:10]}",
            fill=fill,
        )

    # -- internals -------------------------------------------------------------

    def _apply_slippage(self, price: Decimal, side: OrderSide) -> Decimal:
        adj = price * self._slippage_bps / _BPS
        raw = price + adj if side == OrderSide.BUY else price - adj
        return raw.quantize(_CENT, rounding=ROUND_HALF_EVEN)

    def _apply_buy(self, symbol: str, qty: Decimal, price: Decimal, asset_type: AssetType) -> None:
        held = self._positions.get(symbol)
        if held is None:
            self._positions[symbol] = Position(
                symbol=symbol,
                quantity=qty,
                asset_type=asset_type,
                avg_cost=price,
                sector=self._sector_map.get(symbol),
            )
        else:
            new_qty = held.quantity + qty
            new_cost = ((held.avg_cost * held.quantity) + (price * qty)) / new_qty
            self._positions[symbol] = held.model_copy(
                update={"quantity": new_qty, "avg_cost": new_cost.quantize(Decimal("0.0001"))}
            )

    def _apply_sell(self, symbol: str, qty: Decimal) -> None:
        held = self._positions[symbol]
        remaining = held.quantity - qty
        if remaining == 0:
            del self._positions[symbol]
        else:
            self._positions[symbol] = held.model_copy(update={"quantity": remaining})

    def _reject(self, order: ValidatedOrder, reason: str) -> OrderResult:
        self._events.append(
            EventType.ORDER_REJECTED,
            {
                "order_id": order.order_id,
                "client_order_id": order.client_order_id,
                "symbol": order.action.symbol,
                "reason": reason,
            },
            correlation_id=order.proposal_id,
        )
        return OrderResult(
            order_id=order.order_id,
            client_order_id=order.client_order_id,
            status=OrderStatus.REJECTED,
            error=reason,
        )

    def _rebuild_from_events(self, initial_cash: Decimal) -> bool:
        """Replay prior paper events into state. Returns True if history existed."""
        initialized = False
        for event in self._events.iter_events(
            event_types=(EventType.PAPER_INITIALIZED, EventType.ORDER_FILLED)
        ):
            if event.event_type == EventType.PAPER_INITIALIZED:
                if event.payload.get("account_id") != self._account_id:
                    continue
                self._cash = Decimal(event.payload["initial_cash"])
                self._positions = {}
                initialized = True
            else:
                payload = event.payload
                qty = Decimal(payload["quantity"])
                price = Decimal(payload["fill_price"])
                side = OrderSide(payload["side"])
                asset_type = AssetType(payload.get("asset_type", "equity"))
                symbol = payload["symbol"]
                if side == OrderSide.BUY:
                    self._cash -= (price * qty).quantize(_CENT, rounding=ROUND_HALF_EVEN)
                    self._apply_buy(symbol, qty, price, asset_type)
                else:
                    self._cash += (price * qty).quantize(_CENT, rounding=ROUND_HALF_EVEN)
                    self._apply_sell(symbol, qty)
        return initialized
