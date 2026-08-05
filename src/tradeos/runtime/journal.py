"""The journal: the event log reduced into decisions a human can read.

This module is a pure reducer — events in, records out, no I/O and no clock
reads. That matters twice over: the journal is replayable (same events always
produce the same records), and "we did not trade" is a first-class result here,
carrying exactly the same structure as a fill.

Order events correlate by ``proposal_id`` (the executor's correlation key)
while cycle events correlate by the cycle id, so the reducer bridges the two
via ``proposal.created``.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, ConfigDict

from tradeos.events.model import Event
from tradeos.events.types import EventType


def _decimal(raw: object) -> Decimal | None:
    if raw is None:
        return None
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return None


class RuleOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    rule_id: str
    passed: bool
    blocking: bool
    observed: str = ""
    limit: str = ""
    message: str = ""

    @property
    def is_veto(self) -> bool:
        return self.blocking and not self.passed

    @property
    def is_advisory_flag(self) -> bool:
        """Non-blocking rule that did not pass — recorded, never vetoed."""
        return not self.blocking and not self.passed


class ActionVerdict(BaseModel):
    model_config = ConfigDict(frozen=True)

    action_index: int
    approved: bool
    policy_version: int
    side: str = ""
    symbol: str = ""
    quantity: Decimal | None = None
    rationale: str = ""
    results: tuple[RuleOutcome, ...] = ()

    @property
    def rules_total(self) -> int:
        return len(self.results)

    @property
    def rules_passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def vetoes(self) -> tuple[RuleOutcome, ...]:
        return tuple(r for r in self.results if r.is_veto)

    @property
    def advisories(self) -> tuple[RuleOutcome, ...]:
        return tuple(r for r in self.results if r.is_advisory_flag)


class ThesisRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    confidence: Decimal | None = None
    recommended_action_index: int | None = None
    bull_case: str = ""
    bear_case: str = ""
    why_now: str = ""
    what_changed: str = ""
    invalidation_conditions: tuple[str, ...] = ()
    data_gaps: tuple[str, ...] = ()
    citations: tuple[str, ...] = ()


class FillRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    side: str
    quantity: Decimal | None = None
    fill_price: Decimal | None = None
    quote_price: Decimal | None = None
    slippage_bps: Decimal | None = None
    client_order_id: str = ""
    filled: bool = True
    note: str = ""

    @property
    def slippage_cost(self) -> Decimal | None:
        """Signed price impact versus the quote at decision time."""
        if self.quantity is None or self.fill_price is None or self.quote_price is None:
            return None
        return ((self.fill_price - self.quote_price) * self.quantity).quantize(Decimal("0.01"))

    @property
    def slippage_drag(self) -> Decimal | None:
        """What slippage *cost*, always a positive number.

        A buy fills above the quote and a sell below it, so the signed impact
        flips direction while the economic effect does not — both are money lost
        to execution. Reporting the signed figure would render half of all
        slippage as a gain.
        """
        signed = self.slippage_cost
        return abs(signed) if signed is not None else None


class CycleRecord(BaseModel):
    """One decision, whatever its outcome — fill, veto, or deliberate no-action."""

    model_config = ConfigDict(frozen=True)

    correlation_id: str
    occurred_at: datetime
    trigger: str = ""
    status: str = "in_progress"  # completed | no_action | aborted | in_progress
    reason: str = ""
    proposal_id: str | None = None
    strategy: str = ""
    context_package_id: str = ""
    context_items: int = 0
    context_completeness: str = ""
    thesis: ThesisRecord | None = None
    verdicts: tuple[ActionVerdict, ...] = ()
    fills: tuple[FillRecord, ...] = ()

    @property
    def approved_count(self) -> int:
        return sum(1 for v in self.verdicts if v.approved)

    @property
    def vetoed_count(self) -> int:
        return sum(1 for v in self.verdicts if not v.approved)

    @property
    def filled_count(self) -> int:
        return sum(1 for f in self.fills if f.filled)

    @property
    def rules_total(self) -> int:
        return self.verdicts[0].rules_total if self.verdicts else 0

    @property
    def rules_passed(self) -> int:
        """Passed-rule count for the first action — the headline 20/20 figure."""
        return self.verdicts[0].rules_passed if self.verdicts else 0

    @property
    def veto_reasons(self) -> tuple[str, ...]:
        seen: list[str] = []
        for verdict in self.verdicts:
            for rule in verdict.vetoes:
                if rule.rule_id not in seen:
                    seen.append(rule.rule_id)
        return tuple(seen)

    @property
    def headline(self) -> str:
        """One phrase describing what this decision actually did."""
        if self.status == "aborted":
            return "aborted"
        if self.veto_reasons:
            return "vetoed"
        if self.filled_count:
            return f"{self.filled_count} fill{'s' if self.filled_count != 1 else ''}"
        return "no action"


class _Draft:
    """Mutable accumulator; frozen into a CycleRecord once the log is consumed."""

    def __init__(self, correlation_id: str, occurred_at: datetime) -> None:
        self.correlation_id = correlation_id
        self.occurred_at = occurred_at
        self.trigger = ""
        self.status = "in_progress"
        self.reason = ""
        self.proposal_id: str | None = None
        self.strategy = ""
        self.context_package_id = ""
        self.context_items = 0
        self.context_completeness = ""
        self.thesis: ThesisRecord | None = None
        self.actions: list[dict[str, object]] = []
        self.verdicts: dict[int, ActionVerdict] = {}
        self.fills: list[FillRecord] = []

    def freeze(self) -> CycleRecord:
        return CycleRecord(
            correlation_id=self.correlation_id,
            occurred_at=self.occurred_at,
            trigger=self.trigger,
            status=self.status,
            reason=self.reason,
            proposal_id=self.proposal_id,
            strategy=self.strategy,
            context_package_id=self.context_package_id,
            context_items=self.context_items,
            context_completeness=self.context_completeness,
            thesis=self.thesis,
            verdicts=tuple(self.verdicts[i] for i in sorted(self.verdicts)),
            fills=tuple(self.fills),
        )


_ORDER_EVENTS = (
    EventType.ORDER_FILLED,
    EventType.ORDER_REJECTED,
    EventType.ORDER_DUPLICATE,
)


def build_journal(events: Iterable[Event]) -> tuple[CycleRecord, ...]:
    """Reduce an event stream into decision records, newest first."""
    drafts: dict[str, _Draft] = {}
    proposal_to_cycle: dict[str, str] = {}
    pending_orders: list[Event] = []

    for event in events:
        cid = event.correlation_id
        payload = event.payload

        if event.event_type == EventType.CYCLE_TRIGGERED and cid:
            draft = drafts.setdefault(cid, _Draft(cid, event.occurred_at))
            draft.trigger = str(payload.get("trigger", ""))
            continue

        if event.event_type in _ORDER_EVENTS:
            pending_orders.append(event)
            continue

        if not cid or cid not in drafts:
            continue
        draft = drafts[cid]

        if event.event_type == EventType.CONTEXT_ASSEMBLED:
            draft.context_package_id = str(payload.get("package_id", ""))
            draft.context_items = int(payload.get("items", 0) or 0)
            draft.context_completeness = str(payload.get("completeness", ""))

        elif event.event_type == EventType.PROPOSAL_CREATED:
            proposal_id = str(payload.get("proposal_id", ""))
            draft.proposal_id = proposal_id or None
            draft.strategy = str(payload.get("strategy", ""))
            raw_actions = payload.get("actions") or []
            if isinstance(raw_actions, list):
                draft.actions = [a for a in raw_actions if isinstance(a, dict)]
            if proposal_id:
                proposal_to_cycle[proposal_id] = cid

        elif event.event_type == EventType.THESIS_GENERATED:
            draft.thesis = ThesisRecord(
                confidence=_decimal(payload.get("confidence")),
                recommended_action_index=payload.get("recommended_action_index"),
                bull_case=str(payload.get("bull_case", "")),
                bear_case=str(payload.get("bear_case", "")),
                why_now=str(payload.get("why_now", "")),
                what_changed=str(payload.get("what_changed", "")),
                invalidation_conditions=tuple(payload.get("invalidation_conditions") or ()),
                data_gaps=tuple(payload.get("data_gaps") or ()),
                citations=tuple(payload.get("supporting_item_ids") or ()),
            )

        elif event.event_type == EventType.RISK_EVALUATED:
            index = int(payload.get("action_index", 0) or 0)
            action = draft.actions[index] if index < len(draft.actions) else {}
            results = tuple(
                RuleOutcome(
                    rule_id=str(r.get("rule_id", "")),
                    passed=bool(r.get("passed")),
                    blocking=bool(r.get("blocking")),
                    observed=str(r.get("observed", "")),
                    limit=str(r.get("limit", "")),
                    message=str(r.get("message", "")),
                )
                for r in (payload.get("results") or [])
                if isinstance(r, dict)
            )
            draft.verdicts[index] = ActionVerdict(
                action_index=index,
                approved=bool(payload.get("approved")),
                policy_version=int(payload.get("policy_version", 0) or 0),
                side=str(action.get("side", "")),
                symbol=str(action.get("symbol", "")),
                quantity=_decimal(action.get("quantity")),
                rationale=str(action.get("rationale", "")),
                results=results,
            )

        elif event.event_type == EventType.CYCLE_COMPLETED:
            draft.status = str(payload.get("status", "completed"))
            draft.reason = str(payload.get("reason", ""))

        elif event.event_type == EventType.CYCLE_NO_ACTION:
            draft.status = "no_action"
            draft.reason = str(payload.get("reason", ""))

        elif event.event_type == EventType.CYCLE_ABORTED:
            draft.status = "aborted"
            draft.reason = str(payload.get("reason", ""))

    # Order events correlate by proposal_id, resolved only after proposal.created.
    for event in pending_orders:
        cycle_id = proposal_to_cycle.get(event.correlation_id or "")
        if cycle_id is None:
            continue
        payload = event.payload
        filled = event.event_type == EventType.ORDER_FILLED
        drafts[cycle_id].fills.append(
            FillRecord(
                symbol=str(payload.get("symbol", "")),
                side=str(payload.get("side", "")),
                quantity=_decimal(payload.get("quantity")),
                fill_price=_decimal(payload.get("fill_price")),
                quote_price=_decimal(payload.get("quote_price")),
                slippage_bps=_decimal(payload.get("slippage_bps")),
                client_order_id=str(payload.get("client_order_id", "")),
                filled=filled,
                note="" if filled else str(payload.get("reason", event.event_type.value)),
            )
        )

    records = [d.freeze() for d in drafts.values()]
    records.sort(key=lambda r: r.occurred_at, reverse=True)
    return tuple(records)


class EquityPoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    at: datetime
    equity: Decimal


def equity_history(events: Iterable[Event]) -> tuple[EquityPoint, ...]:
    """Equity points in recording order — the dashboard sparkline's only source."""
    points: list[EquityPoint] = []
    for event in events:
        if event.event_type != EventType.PORTFOLIO_SNAPSHOT:
            continue
        value = _decimal(event.payload.get("equity"))
        if value is not None:
            points.append(EquityPoint(at=event.occurred_at, equity=value))
    return tuple(points)


def max_drawdown(points: Iterable[EquityPoint]) -> Decimal | None:
    """Largest peak-to-trough decline as a 0..1 fraction.

    Formula: max over t of (peak_upto_t − equity_t) ÷ peak_upto_t. Computed from
    recorded equity snapshots only, so it measures the observed history — not
    intraday extremes the runtime never sampled (a documented limitation).
    """
    peak: Decimal | None = None
    worst = Decimal("0")
    seen = False
    for point in points:
        seen = True
        if peak is None or point.equity > peak:
            peak = point.equity
        if peak and peak > 0:
            decline = (peak - point.equity) / peak
            if decline > worst:
                worst = decline
    return worst if seen else None


def day_change(points: Iterable[EquityPoint], *, now: datetime) -> Decimal | None:
    """Change versus the first equity snapshot recorded on ``now``'s UTC date."""
    ordered = list(points)
    if not ordered:
        return None
    today = [p for p in ordered if p.at.date() == now.date()]
    if len(today) < 2:
        return None
    opening = today[0].equity
    if opening == 0:
        return None
    return (today[-1].equity - opening) / opening
