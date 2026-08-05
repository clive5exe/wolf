"""Market data primitives."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class MarketStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    SIMULATED = "simulated"  # paper-mode sessions outside real market hours
    UNKNOWN = "unknown"


class Quote(BaseModel):
    """A point-in-time price. ``as_of`` is the quote's own timestamp, not ingestion."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    price: Decimal
    as_of: datetime
    source: str

    def age_s(self, now: datetime) -> int:
        return max(0, int((now - self.as_of).total_seconds()))
