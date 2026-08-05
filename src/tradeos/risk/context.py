"""RiskContext: the complete, injected world-view a rule may consult.

Rules are pure functions over (action, index, ctx) — no I/O, no clocks, no
globals. The runtime assembles this once per cycle; the engine derives
per-action working copies as it simulates the proposal's cumulative effect.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from tradeos.domain.policy import InvestmentPolicy
from tradeos.domain.portfolio import PortfolioSnapshot


@dataclass(frozen=True)
class RiskContext:
    policy: InvestmentPolicy  # pinned at cycle trigger
    active_policy_version: int  # currently active version (policy_changed rule)
    snapshot: PortfolioSnapshot  # priced portfolio (working copy during validation)
    now: datetime  # injected — the single time source for all rules
    market_open: bool
    market_note: str  # e.g. "regular session" / "simulated session (paper)"
    orders_today: int
    last_order_time_by_symbol: dict[str, datetime] = field(default_factory=dict)
    day_start_equity: Decimal | None = None
    high_water_mark: Decimal | None = None
    kill_switch_engaged: bool = False
    submitted_client_order_ids: frozenset[str] = frozenset()
    context_missing: tuple[str, ...] = ()
    sector_map: dict[str, str] = field(default_factory=dict)
