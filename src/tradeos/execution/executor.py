"""Idempotent order execution (RISK_POLICY_SPEC §2, THREAT_MODEL T4).

The executor does not reason about whether a trade is good — that already
happened. It: re-checks the kill switch, enforces order TTL, deduplicates by
client_order_id against the event log, records the submission, and reports
exactly what the broker returned.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from tradeos.brokers.base import BrokerAdapter, BrokerProtocolError
from tradeos.domain.clock import Clock
from tradeos.domain.orders import OrderResult, OrderStatus
from tradeos.domain.risk import ValidatedOrder
from tradeos.events.store import EventStore
from tradeos.events.types import EventType


@runtime_checkable
class KillSwitchLike(Protocol):
    """Structural dependency on the kill switch: execution (a lower layer)
    must not import the runtime's concrete implementation (ARCHITECTURE §2)."""

    def is_engaged(self) -> bool: ...


class ExecutionHalted(RuntimeError):
    """Raised when execution is refused before reaching any broker."""


class Executor:
    def __init__(
        self,
        *,
        broker: BrokerAdapter,
        event_store: EventStore,
        kill_switch: KillSwitchLike,
        clock: Clock,
    ) -> None:
        self._broker = broker
        self._events = event_store
        self._kill = kill_switch
        self._clock = clock

    def submit(self, order: ValidatedOrder) -> OrderResult:
        if not isinstance(order, ValidatedOrder):
            raise BrokerProtocolError(
                f"executor accepts only ValidatedOrder, got {type(order).__name__}"
            )
        if self._kill.is_engaged():
            raise ExecutionHalted("kill switch engaged — execution refused")
        now = self._clock.now()
        if not order.is_valid_at(now):
            self._events.append(
                EventType.ORDER_REJECTED,
                {
                    "order_id": order.order_id,
                    "client_order_id": order.client_order_id,
                    "reason": "validated order expired before execution",
                },
                correlation_id=order.proposal_id,
            )
            return OrderResult(
                order_id=order.order_id,
                client_order_id=order.client_order_id,
                status=OrderStatus.REJECTED,
                error="validated order expired before execution",
            )
        if self._already_submitted(order.client_order_id):
            self._events.append(
                EventType.ORDER_DUPLICATE,
                {
                    "order_id": order.order_id,
                    "client_order_id": order.client_order_id,
                },
                correlation_id=order.proposal_id,
            )
            return OrderResult(
                order_id=order.order_id,
                client_order_id=order.client_order_id,
                status=OrderStatus.DUPLICATE,
                error="client_order_id already submitted — not re-executed",
            )

        self._events.append(
            EventType.ORDER_SUBMITTED,
            {
                "order_id": order.order_id,
                "client_order_id": order.client_order_id,
                "symbol": order.action.symbol,
                "side": order.action.side.value,
                "quantity": str(order.action.quantity),
                "broker": self._broker.name,
                "policy_version": order.policy_version,
                "verdict_id": order.verdict.verdict_id,
            },
            occurred_at=now,
            correlation_id=order.proposal_id,
        )
        return self._broker.submit_order(order)

    def _already_submitted(self, client_order_id: str) -> bool:
        for event in self._events.iter_events(event_types=(EventType.ORDER_SUBMITTED,)):
            if event.payload.get("client_order_id") == client_order_id:
                return True
        return False
