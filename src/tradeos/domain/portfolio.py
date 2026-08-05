"""Portfolio state models."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from tradeos.domain.market import Quote
from tradeos.domain.policy import AssetType


class Position(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    quantity: Decimal
    asset_type: AssetType
    avg_cost: Decimal  # per-share average cost basis
    sector: str | None = None


class AccountState(BaseModel):
    model_config = ConfigDict(frozen=True)

    account_id: str
    cash: Decimal
    positions: tuple[Position, ...]
    as_of: datetime

    def position_for(self, symbol: str) -> Position | None:
        symbol = symbol.upper()
        for p in self.positions:
            if p.symbol == symbol:
                return p
        return None


class PortfolioSnapshot(BaseModel):
    """Account state priced with quotes. The risk engine's view of the world.

    ``total_value`` includes cash. Weights are fractions of total value.
    Symbols without a usable quote appear in ``unpriced`` and make any
    dependent risk rule fail closed.
    """

    model_config = ConfigDict(frozen=True)

    account: AccountState
    quotes: dict[str, Quote]
    as_of: datetime

    @property
    def unpriced(self) -> tuple[str, ...]:
        return tuple(p.symbol for p in self.account.positions if p.symbol not in self.quotes)

    def position_value(self, symbol: str) -> Decimal | None:
        pos = self.account.position_for(symbol)
        if pos is None:
            return Decimal("0")
        quote = self.quotes.get(pos.symbol)
        if quote is None:
            return None
        return pos.quantity * quote.price

    @property
    def total_value(self) -> Decimal | None:
        total = self.account.cash
        for p in self.account.positions:
            quote = self.quotes.get(p.symbol)
            if quote is None:
                return None  # unpriceable portfolio: dependent rules fail closed
            total += p.quantity * quote.price
        return total

    def weight(self, symbol: str) -> Decimal | None:
        total = self.total_value
        value = self.position_value(symbol)
        if total is None or value is None or total == 0:
            return None
        return value / total

    @property
    def cash_weight(self) -> Decimal | None:
        total = self.total_value
        if total is None or total == 0:
            return None
        return self.account.cash / total

    def sector_weight(self, sector: str) -> Decimal | None:
        """Combined weight of positions in ``sector``. None if any member is
        unpriced or total is unknown (fail-closed semantics upstream)."""
        total = self.total_value
        if total is None or total == 0:
            return None
        acc = Decimal("0")
        for p in self.account.positions:
            if (p.sector or "").upper() == sector.upper():
                quote = self.quotes.get(p.symbol)
                if quote is None:
                    return None
                acc += p.quantity * quote.price
        return acc / total
