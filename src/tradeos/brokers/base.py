"""BrokerAdapter protocol and the boundary re-assertion every adapter runs.

Two invariants live here (RISK_POLICY_SPEC §2, THREAT_MODEL T1):
1. ``submit_order`` accepts only a ``ValidatedOrder`` instance.
2. ``assert_submittable`` re-verifies approval and TTL at the adapter
   boundary even though the risk engine already did. Defense in depth
   against object tampering or stale orders.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from tradeos.domain.market import Quote
from tradeos.domain.orders import OrderResult
from tradeos.domain.portfolio import AccountState
from tradeos.domain.risk import ValidatedOrder


class BrokerCapability(StrEnum):
    READ = "read"
    PAPER = "paper"
    TRADE = "trade"  # no v0.1 adapter declares this


class BrokerProtocolError(TypeError):
    """Raised when something other than an approved ValidatedOrder reaches a broker."""


class BrokerCapabilityError(RuntimeError):
    """Raised when an operation exceeds the adapter's declared capabilities."""


def assert_submittable(order: object, *, now: datetime) -> ValidatedOrder:
    """Boundary check used by every adapter at the top of submit_order."""
    if not isinstance(order, ValidatedOrder):
        raise BrokerProtocolError(
            f"submit_order requires a ValidatedOrder, got {type(order).__name__}"
        )
    # Re-derive approval instead of trusting the flag (tamper defense).
    failed = [r.rule_id for r in order.verdict.results if r.blocking and not r.passed]
    if failed or not order.verdict.approved:
        raise BrokerProtocolError(f"order not approved (failed rules: {failed})")
    if not order.is_valid_at(now):
        raise BrokerProtocolError(
            f"order expired at {order.valid_until.isoformat()} (now {now.isoformat()})"
        )
    return order


@runtime_checkable
class BrokerAdapter(Protocol):
    name: str

    def capabilities(self) -> frozenset[BrokerCapability]: ...

    def get_account(self) -> AccountState: ...

    def get_quote(self, symbol: str) -> Quote | None: ...

    def submit_order(self, order: ValidatedOrder) -> OrderResult: ...
