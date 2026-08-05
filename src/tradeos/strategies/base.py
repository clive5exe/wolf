"""Strategy protocol. Strategies read state and propose; they never execute,
never see brokers, and never touch risk parameters (ARCHITECTURE §2)."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from tradeos.domain.context import MarketContextPackage
from tradeos.domain.orders import TradeProposal
from tradeos.domain.policy import InvestmentPolicy
from tradeos.domain.portfolio import PortfolioSnapshot


@runtime_checkable
class Strategy(Protocol):
    strategy_id: str
    version: str

    def generate(
        self,
        *,
        snapshot: PortfolioSnapshot,
        policy: InvestmentPolicy,
        package: MarketContextPackage,
        now: datetime,
        correlation_id: str,
    ) -> TradeProposal: ...
