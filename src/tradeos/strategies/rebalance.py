"""Target-allocation rebalancing, the v0.1 strategy (deliberately explicit).

Algorithm (all Decimal, deterministic):
1. For each policy target, drift = current_weight − target_weight.
2. If |drift| > drift_threshold, propose closing the gap at current quotes:
   delta_value = −drift × total_value, qty = delta_value ÷ price.
3. Whole-share flooring unless the policy allows fractional shares (sells
   also never exceed held quantity).
4. Trades below min_trade_value are skipped (churn guard).
5. Sells sort before buys so freed cash funds purchases within one proposal.
6. Anything unpriceable ⇒ explicit no-action with the reason recorded.

"No action" is a first-class, successful outcome.
"""

from __future__ import annotations

from datetime import datetime
from decimal import ROUND_DOWN, ROUND_HALF_EVEN, Decimal

from tradeos.domain.common import new_ulid, pct
from tradeos.domain.context import MarketContextPackage
from tradeos.domain.orders import OrderSide, OrderType, ProposedAction, TradeProposal
from tradeos.domain.policy import AssetType, InvestmentPolicy
from tradeos.domain.portfolio import PortfolioSnapshot

_CENT = Decimal("0.01")
_QTY_STEP = Decimal("0.0001")  # fractional-share resolution


class TargetAllocationRebalance:
    strategy_id = "target_allocation_rebalance"
    version = "1.0.0"

    def __init__(
        self,
        *,
        drift_threshold: Decimal = Decimal("0.02"),
        min_trade_value: Decimal = Decimal("50"),
    ) -> None:
        self._drift_threshold = drift_threshold
        self._min_trade_value = min_trade_value

    @property
    def drift_threshold(self) -> Decimal:
        """The band outside which this strategy proposes a trade.

        Public because interfaces scale the drift gauge to it: reaching the end
        of the track then means "this holding is at the point of action".
        """
        return self._drift_threshold

    def generate(
        self,
        *,
        snapshot: PortfolioSnapshot,
        policy: InvestmentPolicy,
        package: MarketContextPackage,
        now: datetime,
        correlation_id: str,
    ) -> TradeProposal:
        proposal_id = new_ulid()
        total = snapshot.total_value

        def no_action(reason: str) -> TradeProposal:
            return TradeProposal(
                proposal_id=proposal_id,
                correlation_id=correlation_id,
                created_at=now,
                strategy_id=self.strategy_id,
                strategy_version=self.version,
                actions=(),
                rationale=f"no action: {reason}",
                context_package_id=package.package_id,
            )

        if not policy.target_allocations:
            return no_action("policy defines no target allocations")
        if total is None or total <= 0:
            return no_action(f"portfolio not fully priceable (unpriced: {snapshot.unpriced})")

        sells: list[ProposedAction] = []
        buys: list[ProposedAction] = []
        notes: list[str] = []

        for target in policy.target_allocations:
            quote = snapshot.quotes.get(target.symbol)
            if quote is None:
                notes.append(f"{target.symbol}: skipped, no quote")
                continue
            current = snapshot.weight(target.symbol) or Decimal("0")
            drift = current - target.weight
            if abs(drift) <= self._drift_threshold:
                notes.append(f"{target.symbol}: drift {pct(drift)} within threshold")
                continue

            delta_value = (target.weight - current) * total
            raw_qty = (abs(delta_value) / quote.price).quantize(_QTY_STEP, rounding=ROUND_DOWN)
            side = OrderSide.BUY if delta_value > 0 else OrderSide.SELL
            held = snapshot.account.position_for(target.symbol)
            held_qty = held.quantity if held else Decimal("0")

            if not policy.fractional_shares_allowed:
                raw_qty = raw_qty.to_integral_value(rounding=ROUND_DOWN)
            if side == OrderSide.SELL:
                raw_qty = min(raw_qty, held_qty)
            if raw_qty <= 0:
                notes.append(f"{target.symbol}: gap too small for a whole share")
                continue
            trade_value = (raw_qty * quote.price).quantize(_CENT, rounding=ROUND_HALF_EVEN)
            if trade_value < self._min_trade_value:
                notes.append(
                    f"{target.symbol}: trade ${trade_value} below minimum ${self._min_trade_value}"
                )
                continue

            asset_type = held.asset_type if held else AssetType.EQUITY
            action = ProposedAction(
                side=side,
                symbol=target.symbol,
                quantity=raw_qty,
                asset_type=asset_type,
                order_type=OrderType.MARKET,
                rationale=(
                    f"drift {pct(drift)}: current {pct(current)} vs target "
                    f"{pct(target.weight)} · {side.value} {raw_qty} @ ~${quote.price} "
                    f"(~${trade_value}) to close the gap"
                ),
            )
            (sells if side == OrderSide.SELL else buys).append(action)

        actions = tuple(sells + buys)
        if not actions:
            return no_action(" · ".join(notes) if notes else "all targets within threshold")
        summary = (
            f"rebalance toward targets (threshold {pct(self._drift_threshold)}): "
            f"{len(sells)} sell(s), {len(buys)} buy(s). " + " · ".join(notes)
        )
        return TradeProposal(
            proposal_id=proposal_id,
            correlation_id=correlation_id,
            created_at=now,
            strategy_id=self.strategy_id,
            strategy_version=self.version,
            actions=actions,
            rationale=summary.strip(),
            context_package_id=package.package_id,
        )
