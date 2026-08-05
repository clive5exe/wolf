"""Read models for interfaces.

Screens render these and nothing else: every number a human sees is computed
here, in tested runtime code, rather than in a widget. That keeps the TUI dumb
enough to trust and lets the same view feed the CLI, a future web surface, or a
snapshot test without re-deriving anything.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from tradeos.runtime.journal import CycleRecord, EquityPoint


class KillSwitchState(BaseModel):
    """Who halted trading, when, and why — the kill screen's headline."""

    model_config = ConfigDict(frozen=True)

    engaged: bool
    since: datetime | None = None
    reason: str = ""
    source: str = ""


class HoldingView(BaseModel):
    """One dashboard row: how much, how far from plan, how fresh, what it costs."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    quantity: Decimal
    value: Decimal
    weight: Decimal
    target_weight: Decimal | None = None
    drift: Decimal | None = None
    unrealized_pnl: Decimal | None = None
    sector: str = ""
    quote_age_s: int | None = None
    quote_ttl_s: int = 60
    price: Decimal | None = None

    @property
    def is_priced(self) -> bool:
        return self.price is not None

    @property
    def is_stale(self) -> bool:
        """No quote at all, or one older than its TTL."""
        if self.quote_age_s is None:
            return True
        return self.quote_age_s > self.quote_ttl_s


class DashboardView(BaseModel):
    """Everything the den screen shows, resolved at one instant."""

    model_config = ConfigDict(frozen=True)

    as_of: datetime
    mode: str  # PAPER | READ_ONLY | ... | NO POLICY
    policy_version: int | None = None
    kill_engaged: bool = False
    rules_armed: int = 0

    nav: Decimal | None = None
    cash: Decimal = Decimal("0")
    cash_weight: Decimal | None = None
    #: Policy floor (``min_cash_pct``). Deliberately NOT a target: holding more
    #: cash than the minimum is compliance, not drift, and must not render as one.
    cash_floor: Decimal | None = None

    @property
    def cash_above_floor(self) -> bool | None:
        if self.cash_weight is None or self.cash_floor is None:
            return None
        return self.cash_weight >= self.cash_floor

    holdings: tuple[HoldingView, ...] = ()
    top3_concentration: Decimal | None = None
    hhi: Decimal | None = None
    #: Drift at which the strategy proposes a trade — the drift gauge's full scale.
    drift_threshold: Decimal = Decimal("0.02")

    equity: tuple[EquityPoint, ...] = ()
    day_change: Decimal | None = None
    max_drawdown: Decimal | None = None

    last_cycle: CycleRecord | None = None

    @property
    def oldest_quote_age_s(self) -> int | None:
        ages = [h.quote_age_s for h in self.holdings if h.quote_age_s is not None]
        return max(ages) if ages else None

    @property
    def any_stale(self) -> bool:
        return any(h.is_stale for h in self.holdings)
