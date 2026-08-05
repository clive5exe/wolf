"""Assemble MarketContextPackages from live state (MARKET_CONTEXT_SPEC §5).

v0.1 assembles from broker account + quotes + market status. Ingestion-fed
kinds (filings, news, sentiment) join via the same item shape as connectors
land (T-023/T-025).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from tradeos.context.ttl import DEFAULT_TTLS
from tradeos.domain.common import new_ulid
from tradeos.domain.context import (
    ContextItem,
    ContextRequirement,
    MarketContextPackage,
    Provenance,
    SourceType,
)
from tradeos.domain.market import Quote
from tradeos.domain.portfolio import AccountState

_BROKER_CREDIBILITY = Decimal("0.95")
_QUOTE_CREDIBILITY = Decimal("0.85")


class ContextAssembler:
    def assemble(
        self,
        *,
        purpose: str,
        account: AccountState,
        quotes: dict[str, Quote],
        required_symbols: tuple[str, ...],
        market_note: str,
        now: datetime,
        source_name: str,
    ) -> MarketContextPackage:
        items: list[ContextItem] = [
            ContextItem(
                item_id=new_ulid(),
                source_name=source_name,
                source_type=SourceType.BROKER,
                entities=tuple(p.symbol for p in account.positions),
                event_time=account.as_of,
                ingested_at=now,
                ttl_s=DEFAULT_TTLS["positions"],
                credibility=_BROKER_CREDIBILITY,
                retrieval_reason="portfolio state for decision cycle",
                provenance=Provenance.NORMALIZED,
                payload={
                    "kind": "positions",
                    "cash": str(account.cash),
                    "positions": [
                        {"symbol": p.symbol, "quantity": str(p.quantity)} for p in account.positions
                    ],
                },
            ),
            ContextItem(
                item_id=new_ulid(),
                source_name=source_name,
                source_type=SourceType.MARKET_DATA,
                entities=(),
                event_time=now,
                ingested_at=now,
                ttl_s=DEFAULT_TTLS["market_status"],
                credibility=_BROKER_CREDIBILITY,
                retrieval_reason="session gating",
                provenance=Provenance.DERIVED,
                payload={"kind": "market_status", "note": market_note},
            ),
        ]
        for symbol, quote in sorted(quotes.items()):
            items.append(
                ContextItem(
                    item_id=new_ulid(),
                    source_name=quote.source,
                    source_type=SourceType.MARKET_DATA,
                    entities=(symbol,),
                    event_time=quote.as_of,
                    ingested_at=now,
                    ttl_s=DEFAULT_TTLS["quote"],
                    credibility=_QUOTE_CREDIBILITY,
                    retrieval_reason=f"pricing for {symbol}",
                    provenance=Provenance.NORMALIZED,
                    payload={"kind": f"quote:{symbol}", "price": str(quote.price)},
                )
            )
        requirements = [
            ContextRequirement(kind="positions"),
            ContextRequirement(kind="market_status"),
            *(ContextRequirement(kind=f"quote:{s}") for s in required_symbols),
        ]
        return MarketContextPackage(
            package_id=new_ulid(),
            created_at=now,
            purpose=purpose,
            requirements=tuple(requirements),
            items=tuple(items),
        )
