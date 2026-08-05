"""Portfolio statistics with documented formulas (PRODUCT requirement).

Every function documents: formula, data source, window, assumptions,
limitations. Statistics that lack a sound input in v0.1 (benchmark-relative
measures) are reported as ``unavailable`` with the reason. Never faked.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from tradeos.domain.portfolio import PortfolioSnapshot


class AllocationRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    value: Decimal
    weight: Decimal
    target_weight: Decimal | None = None
    drift: Decimal | None = None  # weight - target
    unrealized_pnl: Decimal | None = None


class PortfolioStats(BaseModel):
    model_config = ConfigDict(frozen=True)

    total_value: Decimal | None
    cash: Decimal
    cash_weight: Decimal | None
    rows: tuple[AllocationRow, ...]
    top3_concentration: Decimal | None  # sum of 3 largest weights
    hhi: Decimal | None  # Herfindahl, Hirschman index over position weights
    unavailable: dict[str, str]  # stat name -> reason it cannot be computed honestly


def compute_stats(
    snapshot: PortfolioSnapshot,
    targets: dict[str, Decimal] | None = None,
) -> PortfolioStats:
    """Point-in-time allocation statistics.

    Formulas:
    - weight_i = quantity_i × price_i ÷ total_value (total includes cash)
    - drift_i = weight_i − target_i (only for symbols with targets)
    - unrealized_pnl_i = quantity_i × (price_i − avg_cost_i). Average-cost
      method, ignores lots/taxes (limitation)
    - top3_concentration = Σ of the 3 largest position weights
    - HHI = Σ weight_i² over positions (0..1. >0.25 is highly concentrated)

    Source: the provided priced snapshot (no history). Time-series stats
    (volatility, drawdown, Sharpe/Sortino, beta, turnover) are computed from
    equity history and land with T-026. Benchmark-dependent measures remain
    unavailable until a licensed benchmark series exists (ASSUMPTIONS A13).
    """
    targets = {k.upper(): v for k, v in (targets or {}).items()}
    unavailable = {
        "sharpe": "no benchmark/risk-free series configured (A13)",
        "sortino": "no benchmark/risk-free series configured (A13)",
        "beta": "no benchmark series configured (A13)",
        "volatility": "insufficient equity history in this view (T-026)",
        "max_drawdown": "insufficient equity history in this view (T-026)",
    }
    total = snapshot.total_value
    rows: list[AllocationRow] = []
    weights: list[Decimal] = []
    for position in snapshot.account.positions:
        quote = snapshot.quotes.get(position.symbol)
        if quote is None or total is None or total == 0:
            rows.append(
                AllocationRow(
                    symbol=position.symbol,
                    value=Decimal("0"),
                    weight=Decimal("0"),
                    target_weight=targets.get(position.symbol),
                )
            )
            continue
        value = position.quantity * quote.price
        weight = value / total
        weights.append(weight)
        target = targets.get(position.symbol)
        rows.append(
            AllocationRow(
                symbol=position.symbol,
                value=value.quantize(Decimal("0.01")),
                weight=weight,
                target_weight=target,
                drift=(weight - target) if target is not None else None,
                unrealized_pnl=(position.quantity * (quote.price - position.avg_cost)).quantize(
                    Decimal("0.01")
                ),
            )
        )
    # targets with no current position still deserve a drift row
    held = {r.symbol for r in rows}
    for symbol, target in sorted(targets.items()):
        if symbol not in held:
            rows.append(
                AllocationRow(
                    symbol=symbol,
                    value=Decimal("0"),
                    weight=Decimal("0"),
                    target_weight=target,
                    drift=Decimal("0") - target,
                )
            )
    sorted_weights = sorted(weights, reverse=True)
    top3 = sum(sorted_weights[:3], Decimal("0")) if sorted_weights else None
    hhi = sum((w * w for w in weights), Decimal("0")) if weights else None
    return PortfolioStats(
        total_value=total,
        cash=snapshot.account.cash,
        cash_weight=snapshot.cash_weight,
        rows=tuple(rows),
        top3_concentration=top3,
        hhi=hhi,
        unavailable=unavailable,
    )
