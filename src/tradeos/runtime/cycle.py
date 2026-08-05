"""The decision cycle (ARCHITECTURE §3): trigger → observe → retrieve →
candidates → optional AI synthesis → deterministic sizing → risk → mode gate →
record & notify. Stopping early with a reason is success, not failure."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, time
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from tradeos.brokers.base import BrokerAdapter
from tradeos.context.assembler import ContextAssembler
from tradeos.context.project import project_context
from tradeos.domain.clock import Clock
from tradeos.domain.common import new_ulid
from tradeos.domain.context import MarketContextPackage
from tradeos.domain.market import Quote
from tradeos.domain.orders import OrderResult, TradeProposal
from tradeos.domain.policy import InvestmentPolicy, TradingMode
from tradeos.domain.portfolio import PortfolioSnapshot
from tradeos.domain.thesis import StructuredThesis
from tradeos.events.store import EventStore
from tradeos.events.types import EventType
from tradeos.execution.executor import Executor
from tradeos.market_data.clock import is_regular_session
from tradeos.notifications.base import Notifier
from tradeos.providers.base import ModelProvider
from tradeos.providers.prompts import PROMPT_VERSION, build_thesis_prompt
from tradeos.risk.context import RiskContext
from tradeos.risk.engine import ProposalValidation, RiskEngine
from tradeos.runtime.killswitch import KillSwitch
from tradeos.runtime.policy_service import PolicyService
from tradeos.runtime.progress import CycleProgress, CycleStage, StageState, emit
from tradeos.strategies.base import Strategy


class CycleOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    correlation_id: str
    status: str  # "completed" | "no_action" | "aborted"
    reason: str
    proposal_id: str | None = None
    approved_actions: int = 0
    vetoed_actions: int = 0
    fills: tuple[str, ...] = ()  # human-readable fill lines
    thesis_confidence: str | None = None


@dataclass
class DecisionCycleDeps:
    events: EventStore
    broker: BrokerAdapter
    policy_service: PolicyService
    strategy: Strategy
    engine: RiskEngine
    executor: Executor
    kill_switch: KillSwitch
    notifier: Notifier
    clock: Clock
    assembler: ContextAssembler = field(default_factory=ContextAssembler)
    provider: ModelProvider | None = None
    sector_map: dict[str, str] = field(default_factory=dict)
    simulate_session_in_paper: bool = True


class DecisionCycle:
    def __init__(self, deps: DecisionCycleDeps) -> None:
        self._d = deps

    def run(self, trigger: str, progress: CycleProgress | None = None) -> CycleOutcome:
        d = self._d
        correlation_id = new_ulid()
        now = d.clock.now()

        def stage(step: CycleStage, state: StageState, detail: str = "") -> None:
            """Display-only notification. Never affects what this cycle decides."""
            emit(
                progress,
                correlation_id=correlation_id,
                stage=step,
                state=state,
                detail=detail,
                at=d.clock.now(),
            )

        # Stamped with the cycle's own clock rather than letting the store
        # default to wall time. The scheduler reads this event back to decide
        # when the next run is due, so a clock injected for replay or testing
        # has to reach the log. Otherwise the two disagree about "now".
        d.events.append(
            EventType.CYCLE_TRIGGERED,
            {"trigger": trigger},
            occurred_at=now,
            correlation_id=correlation_id,
        )

        policy = d.policy_service.active_policy()
        if policy is None:
            stage(CycleStage.OBSERVE, StageState.FAILED, "no active investment policy")
            return self._abort(correlation_id, "no active investment policy, run onboarding")
        if policy.mode == TradingMode.READ_ONLY:
            stage(CycleStage.OBSERVE, StageState.SKIPPED, "read-only mode")
            return self._no_action(correlation_id, None, "read-only mode: intelligence only")

        # -- observe ----------------------------------------------------------
        stage(CycleStage.OBSERVE, StageState.RUNNING, "reading account and quotes")
        account = d.broker.get_account()
        symbols = sorted(
            {t.symbol for t in policy.target_allocations} | {p.symbol for p in account.positions}
        )
        quotes: dict[str, Quote] = {}
        for symbol in symbols:
            quote = d.broker.get_quote(symbol)
            if quote is not None:
                quotes[symbol] = quote

        market_open = is_regular_session(now)
        if not market_open and policy.mode == TradingMode.PAPER and d.simulate_session_in_paper:
            market_open, market_note = True, "simulated session (paper)"
        else:
            market_note = "regular session" if market_open else "market closed"
        stage(
            CycleStage.OBSERVE,
            StageState.DONE,
            f"quotes {len(quotes)}/{len(symbols)} · {market_note}",
        )

        # -- retrieve ---------------------------------------------------------
        stage(CycleStage.RETRIEVE, StageState.RUNNING, "assembling context package")
        package = d.assembler.assemble(
            purpose=f"{trigger}:{','.join(symbols)}",
            account=account,
            quotes=quotes,
            required_symbols=tuple(t.symbol for t in policy.target_allocations),
            market_note=market_note,
            now=now,
            source_name=d.broker.name,
        )
        missing = package.missing(now)
        d.events.append(
            EventType.CONTEXT_ASSEMBLED,
            {
                "package_id": package.package_id,
                "items": len(package.items),
                "completeness": str(package.completeness(now)),
                "missing": list(missing),
            },
            correlation_id=correlation_id,
        )
        stage(
            CycleStage.RETRIEVE,
            StageState.DONE,
            f"{len(package.items)} items · completeness {package.completeness(now):.0%} · "
            f"{len(missing)} stale",
        )

        # -- candidates -------------------------------------------------------
        stage(CycleStage.PROPOSE, StageState.RUNNING, "generating candidates")
        snapshot = PortfolioSnapshot(account=account, quotes=quotes, as_of=now)
        proposal = d.strategy.generate(
            snapshot=snapshot,
            policy=policy,
            package=package,
            now=now,
            correlation_id=correlation_id,
        )
        d.events.append(
            EventType.PROPOSAL_CREATED,
            {
                "proposal_id": proposal.proposal_id,
                "strategy": f"{proposal.strategy_id}@{proposal.strategy_version}",
                "actions": [
                    {
                        "side": a.side.value,
                        "symbol": a.symbol,
                        "quantity": str(a.quantity),
                        "rationale": a.rationale,
                    }
                    for a in proposal.actions
                ],
                "rationale": proposal.rationale,
                "context_package_id": package.package_id,
            },
            correlation_id=correlation_id,
        )
        stage(
            CycleStage.PROPOSE,
            StageState.DONE,
            f"{proposal.strategy_id}@{proposal.strategy_version} → "
            f"{len(proposal.actions)} candidates",
        )
        if proposal.is_no_action:
            stage(CycleStage.THESIS, StageState.SKIPPED, "no candidates to reason about")
            stage(CycleStage.RISK, StageState.SKIPPED, "nothing to validate")
            stage(CycleStage.EXECUTE, StageState.SKIPPED, "no action")
            return self._no_action(correlation_id, proposal, proposal.rationale)

        # -- optional AI synthesis -------------------------------------------
        if d.provider is None:
            stage(CycleStage.THESIS, StageState.SKIPPED, "deterministic cycle · $0.00")
            thesis = None
        else:
            stage(CycleStage.THESIS, StageState.RUNNING, f"{d.provider.name} synthesising")
            thesis = self._synthesize(proposal, package, snapshot=snapshot, policy=policy, now=now)
        if thesis is not None:
            d.events.append(
                EventType.THESIS_GENERATED,
                {
                    "proposal_id": proposal.proposal_id,
                    "prompt_version": PROMPT_VERSION,
                    "recommended_action_index": thesis.recommended_action_index,
                    "confidence": str(thesis.confidence),
                    "bull_case": thesis.bull_case,
                    "bear_case": thesis.bear_case,
                    "why_now": thesis.why_now,
                    "what_changed": thesis.what_changed,
                    "supporting_item_ids": list(thesis.supporting_item_ids),
                    "invalidation_conditions": list(thesis.invalidation_conditions),
                    "data_gaps": list(thesis.data_gaps),
                },
                correlation_id=correlation_id,
            )
            stage(
                CycleStage.THESIS,
                StageState.DONE,
                f"confidence {thesis.confidence} · {len(thesis.supporting_item_ids)} citations",
            )
        elif d.provider is not None:
            stage(CycleStage.THESIS, StageState.FAILED, "no usable thesis, proceeding without")

        # -- risk -------------------------------------------------------------
        stage(CycleStage.RISK, StageState.RUNNING, "every rule runs · any veto stops everything")
        ctx = self._build_risk_context(policy, snapshot, missing, market_open, market_note, now)
        validation = d.engine.validate_proposal(proposal, ctx)
        for verdict in validation.verdicts:
            d.events.append(
                EventType.RISK_EVALUATED,
                {
                    "verdict_id": verdict.verdict_id,
                    "proposal_id": proposal.proposal_id,
                    "action_index": verdict.action_index,
                    "approved": verdict.approved,
                    "policy_version": verdict.policy_version,
                    "results": [r.model_dump() for r in verdict.results],
                },
                correlation_id=correlation_id,
            )
        vetoed = sum(1 for v in validation.verdicts if not v.approved)
        rules_run = len(validation.verdicts[0].results) if validation.verdicts else 0
        stage(
            CycleStage.RISK,
            StageState.FAILED if vetoed else StageState.DONE,
            f"{rules_run} rules · {len(validation.validated_orders)} approved, {vetoed} vetoed",
        )

        # -- mode gate + execution -------------------------------------------
        if policy.mode == TradingMode.PAPER:
            stage(CycleStage.EXECUTE, StageState.RUNNING, "paper broker")
            fills = self._execute_paper(validation)
            stage(CycleStage.EXECUTE, StageState.DONE, f"{len(fills)} order results")
        else:
            fills = []
            stage(CycleStage.EXECUTE, StageState.SKIPPED, f"mode {policy.mode.value}")

        outcome = CycleOutcome(
            correlation_id=correlation_id,
            status="completed",
            reason="cycle completed",
            proposal_id=proposal.proposal_id,
            approved_actions=len(validation.validated_orders),
            vetoed_actions=vetoed,
            fills=tuple(fills),
            thesis_confidence=str(thesis.confidence) if thesis else None,
        )
        d.events.append(
            EventType.CYCLE_COMPLETED,
            outcome.model_dump(mode="json"),
            correlation_id=correlation_id,
        )
        self._record_evaluation(correlation_id, package, thesis, validation, now)
        self._notify_outcome(outcome, proposal)
        return outcome

    # -- helpers --------------------------------------------------------------

    def _synthesize(
        self,
        proposal: TradeProposal,
        package: MarketContextPackage,
        *,
        snapshot: PortfolioSnapshot,
        policy: InvestmentPolicy,
        now: datetime,
    ) -> StructuredThesis | None:
        d = self._d
        if d.provider is None:
            return None
        # Absolutes stop here: the provider receives the relative-only
        # projection, whose type cannot express an amount or a share count.
        context = project_context(
            package,
            snapshot=snapshot,
            targets={t.symbol: t.weight for t in policy.target_allocations},
            candidates=proposal.actions,
            policy_summary=self._policy_summary(policy),
            now=now,
        )
        prompt = build_thesis_prompt(context)
        result = d.provider.query_structured(prompt=prompt, schema=StructuredThesis)
        if not result.ok or result.value is None:
            return None  # provider error already recorded by the adapter
        thesis = result.value
        unknown = set(thesis.supporting_item_ids) - set(package.citations)
        if unknown:
            d.events.append(
                EventType.PROVIDER_ERROR,
                {
                    "provider": d.provider.name,
                    "error": "unsupported_citation",
                    "detail": f"thesis cited unknown item ids: {sorted(unknown)}",
                },
            )
            return None  # a thesis with fabricated citations is discarded, not trimmed
        return thesis

    def _build_risk_context(
        self,
        policy: InvestmentPolicy,
        snapshot: PortfolioSnapshot,
        missing: tuple[str, ...],
        market_open: bool,
        market_note: str,
        now: datetime,
    ) -> RiskContext:
        d = self._d
        day_start = datetime.combine(now.date(), time.min, tzinfo=UTC)
        orders_today = d.events.count(EventType.ORDER_SUBMITTED, since=day_start)
        last_by_symbol: dict[str, datetime] = {}
        submitted_ids: set[str] = set()
        equities: list[Decimal] = []
        day_start_equity: Decimal | None = None
        for event in d.events.iter_events(event_types=(EventType.ORDER_SUBMITTED,)):
            symbol = event.payload.get("symbol")
            if symbol:
                last_by_symbol[symbol] = event.occurred_at
            cid = event.payload.get("client_order_id")
            if cid:
                submitted_ids.add(cid)
        for event in d.events.iter_events(event_types=(EventType.PORTFOLIO_SNAPSHOT,)):
            equity = Decimal(event.payload["equity"])
            equities.append(equity)
            if day_start_equity is None and event.occurred_at >= day_start:
                day_start_equity = equity
        current_total = snapshot.total_value
        if current_total is not None:
            self._d.events.append(EventType.PORTFOLIO_SNAPSHOT, {"equity": str(current_total)})
            equities.append(current_total)
            if day_start_equity is None:
                day_start_equity = current_total
        high_water = max(equities) if equities else None
        active = d.policy_service.active_policy()
        return RiskContext(
            policy=policy,
            active_policy_version=active.version if active else -1,
            snapshot=snapshot,
            now=now,
            market_open=market_open,
            market_note=market_note,
            orders_today=orders_today,
            last_order_time_by_symbol=last_by_symbol,
            day_start_equity=day_start_equity,
            high_water_mark=high_water,
            kill_switch_engaged=d.kill_switch.is_engaged(),
            submitted_client_order_ids=frozenset(submitted_ids),
            context_missing=missing,
            sector_map=d.sector_map,
        )

    def _execute_paper(self, validation: ProposalValidation) -> list[str]:
        fills: list[str] = []
        for order in validation.validated_orders:
            result: OrderResult = self._d.executor.submit(order)
            if result.fill is not None:
                fills.append(
                    f"{order.action.side.value.upper()} {result.fill.quantity} "
                    f"{order.action.symbol} @ ${result.fill.price} (paper)"
                )
            else:
                fills.append(
                    f"{order.action.side.value.upper()} {order.action.symbol}: "
                    f"{result.status.value} ({result.error})"
                )
        return fills

    def _record_evaluation(
        self,
        correlation_id: str,
        package: MarketContextPackage,
        thesis: StructuredThesis | None,
        validation: ProposalValidation,
        now: datetime,
    ) -> None:
        self._d.events.append(
            EventType.EVALUATION_RECORDED,
            {
                "context_completeness": str(package.completeness(now)),
                "thesis_present": thesis is not None,
                "citations": len(thesis.supporting_item_ids) if thesis else 0,
                "approved": len(validation.validated_orders),
                "vetoed": sum(1 for v in validation.verdicts if not v.approved),
            },
            correlation_id=correlation_id,
        )

    def _notify_outcome(self, outcome: CycleOutcome, proposal: TradeProposal) -> None:
        d = self._d
        body = (
            f"{proposal.strategy_id}@{proposal.strategy_version}: "
            f"{outcome.approved_actions} approved, {outcome.vetoed_actions} vetoed. "
            + (" · ".join(outcome.fills[:3]) if outcome.fills else "no fills")
            + f" [cycle {outcome.correlation_id[:8]}]"
        )
        sent = d.notifier.notify("WOLF · paper cycle", body)
        d.events.append(
            EventType.NOTIFICATION_SENT,
            {"channel": d.notifier.name, "ok": sent, "body": body},
            correlation_id=outcome.correlation_id,
        )

    def _no_action(
        self, correlation_id: str, proposal: TradeProposal | None, reason: str
    ) -> CycleOutcome:
        outcome = CycleOutcome(
            correlation_id=correlation_id,
            status="no_action",
            reason=reason,
            proposal_id=proposal.proposal_id if proposal else None,
        )
        self._d.events.append(
            EventType.CYCLE_NO_ACTION, {"reason": reason}, correlation_id=correlation_id
        )
        return outcome

    def _abort(self, correlation_id: str, reason: str) -> CycleOutcome:
        self._d.events.append(
            EventType.CYCLE_ABORTED, {"reason": reason}, correlation_id=correlation_id
        )
        return CycleOutcome(correlation_id=correlation_id, status="aborted", reason=reason)

    @staticmethod
    def _policy_summary(policy: InvestmentPolicy) -> str:
        targets = ", ".join(f"{t.symbol} {t.weight}" for t in policy.target_allocations)
        return (
            f"mode={policy.mode.value} · targets: {targets} · "
            f"max_position={policy.max_position_pct} · min_cash={policy.min_cash_pct}"
        )
