"""The risk engine: sole issuer of ValidatedOrder (ADR-0008).

Pure: no I/O, no clock reads — everything arrives via RiskContext. The engine
simulates the proposal's cumulative effect action-by-action so a buy that only
fits because an earlier sell freed cash is judged against that reality, while
vetoed actions contribute nothing.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import ROUND_HALF_EVEN, Decimal

from pydantic import BaseModel, ConfigDict

from tradeos.domain.common import new_ulid
from tradeos.domain.orders import OrderSide, ProposedAction, TradeProposal
from tradeos.domain.policy import AssetType
from tradeos.domain.portfolio import PortfolioSnapshot, Position
from tradeos.domain.risk import RiskVerdict, ValidatedOrder, client_order_id_for
from tradeos.risk.context import RiskContext
from tradeos.risk.rules import DEFAULT_RULES, RiskRule, make_duplicate_rule

ORDER_VALIDITY = timedelta(minutes=10)
_CENT = Decimal("0.01")


class ProposalValidation(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    proposal_id: str
    verdicts: tuple[RiskVerdict, ...]
    validated_orders: tuple[ValidatedOrder, ...]  # only approved actions, in order

    @property
    def fully_approved(self) -> bool:
        return all(v.approved for v in self.verdicts)


class RiskEngine:
    def __init__(self, rules: tuple[RiskRule, ...] = DEFAULT_RULES) -> None:
        self._rules = rules

    def validate_proposal(self, proposal: TradeProposal, ctx: RiskContext) -> ProposalValidation:
        verdicts: list[RiskVerdict] = []
        orders: list[ValidatedOrder] = []
        working_ctx = ctx
        all_rules = (*self._rules, make_duplicate_rule(proposal.proposal_id))

        for index, action in enumerate(proposal.actions):
            results = tuple(rule.check(action, index, working_ctx) for rule in all_rules)
            approved = all(r.passed for r in results if r.blocking)
            verdict = RiskVerdict(
                verdict_id=new_ulid(),
                proposal_id=proposal.proposal_id,
                action_index=index,
                policy_version=ctx.policy.version,
                evaluated_at=ctx.now,
                results=results,
                approved=approved,
            )
            verdicts.append(verdict)
            if approved:
                orders.append(
                    ValidatedOrder(
                        order_id=new_ulid(),
                        proposal_id=proposal.proposal_id,
                        action=action,
                        verdict=verdict,
                        policy_version=ctx.policy.version,
                        client_order_id=client_order_id_for(proposal.proposal_id, index, action),
                        valid_until=ctx.now + ORDER_VALIDITY,
                    )
                )
                working_ctx = replace(
                    working_ctx, snapshot=_apply_simulated(working_ctx.snapshot, action)
                )
        return ProposalValidation(
            proposal_id=proposal.proposal_id,
            verdicts=tuple(verdicts),
            validated_orders=tuple(orders),
        )


def _apply_simulated(snapshot: PortfolioSnapshot, action: ProposedAction) -> PortfolioSnapshot:
    """Working-state update at quote price (slippage is an execution concern;
    the sizing approximation is documented in RISK_POLICY_SPEC §3)."""
    quote = snapshot.quotes.get(action.symbol)
    if quote is None:  # rules already failed closed; keep state unchanged
        return snapshot
    notional = (quote.price * action.quantity).quantize(_CENT, rounding=ROUND_HALF_EVEN)
    positions = {p.symbol: p for p in snapshot.account.positions}
    held = positions.get(action.symbol)
    if action.side == OrderSide.BUY:
        cash = snapshot.account.cash - notional
        if held is None:
            positions[action.symbol] = Position(
                symbol=action.symbol,
                quantity=action.quantity,
                asset_type=AssetType(action.asset_type),
                avg_cost=quote.price,
            )
        else:
            positions[action.symbol] = held.model_copy(
                update={"quantity": held.quantity + action.quantity}
            )
    else:
        cash = snapshot.account.cash + notional
        if held is not None:
            remaining = held.quantity - action.quantity
            if remaining <= 0:
                del positions[action.symbol]
            else:
                positions[action.symbol] = held.model_copy(update={"quantity": remaining})
    account = snapshot.account.model_copy(
        update={"cash": cash, "positions": tuple(positions.values())}
    )
    return snapshot.model_copy(update={"account": account})
