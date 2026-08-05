"""Quote source abstraction. Real sources arrive with the Robinhood MCP
adapter (T-024). Static/callable sources power tests, demos, and paper mode."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Protocol, runtime_checkable

from tradeos.domain.market import Quote


@runtime_checkable
class QuoteSource(Protocol):
    name: str

    def get_quote(self, symbol: str, *, now: datetime) -> Quote | None: ...


class StaticQuoteSource:
    """Fixed price table. Quotes are stamped ``as_of=now`` (always fresh) unless
    a fixed ``as_of`` is supplied (useful for staleness tests)."""

    name = "static"

    def __init__(self, prices: dict[str, Decimal], *, as_of: datetime | None = None) -> None:
        self._prices = {k.upper(): v for k, v in prices.items()}
        self._as_of = as_of

    def get_quote(self, symbol: str, *, now: datetime) -> Quote | None:
        price = self._prices.get(symbol.upper())
        if price is None:
            return None
        return Quote(symbol=symbol.upper(), price=price, as_of=self._as_of or now, source=self.name)
