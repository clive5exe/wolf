"""TradeOSRuntime — the single facade interfaces are allowed to talk to
(ARCHITECTURE §2). Wires storage, brokers, risk, strategy, notifications.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from tradeos.brokers.paper import PaperBroker
from tradeos.context.assembler import ContextAssembler
from tradeos.context.ttl import DEFAULT_TTLS
from tradeos.domain.clock import Clock
from tradeos.domain.policy import InvestmentPolicy, TradingMode
from tradeos.domain.portfolio import PortfolioSnapshot
from tradeos.events.model import Event
from tradeos.events.store import EventStore, InMemoryEventStore
from tradeos.events.types import EventType
from tradeos.execution.executor import Executor
from tradeos.market_data.quotes import QuoteSource, StaticQuoteSource
from tradeos.notifications.base import Notifier, NullNotifier
from tradeos.portfolio.stats import PortfolioStats, compute_stats
from tradeos.providers.base import ModelProvider, ProviderStatus
from tradeos.providers.claude_code import ClaudeCodeProvider
from tradeos.risk.engine import RiskEngine
from tradeos.runtime.cycle import CycleOutcome, DecisionCycle, DecisionCycleDeps
from tradeos.runtime.diagnostics import DoctorCheck, run_checks
from tradeos.runtime.journal import (
    CycleRecord,
    EquityPoint,
    build_journal,
    day_change,
    equity_history,
    max_drawdown,
)
from tradeos.runtime.killswitch import KillSwitch
from tradeos.runtime.policy_service import PolicyService
from tradeos.runtime.progress import CycleProgress
from tradeos.runtime.views import DashboardView, HoldingView, KillSwitchState
from tradeos.storage.sqlite_store import SQLiteEventStore
from tradeos.strategies.rebalance import TargetAllocationRebalance

# Demo universe: prices are static fixtures, sectors power the sector rules.
DEMO_PRICES: dict[str, Decimal] = {
    "VTI": Decimal("285.10"),
    "AAPL": Decimal("232.50"),
    "MSFT": Decimal("418.20"),
    "JNJ": Decimal("161.35"),
    "XOM": Decimal("118.90"),
}
DEMO_SECTORS: dict[str, str] = {
    "VTI": "BROAD_MARKET",
    "AAPL": "TECHNOLOGY",
    "MSFT": "TECHNOLOGY",
    "JNJ": "HEALTHCARE",
    "XOM": "ENERGY",
}


def default_data_dir() -> Path:
    override = os.environ.get("TRADEOS_DATA_DIR")
    if override:
        return Path(override)
    return Path.home() / "Library" / "Application Support" / "TradeOS"


@dataclass
class RuntimeConfig:
    data_dir: Path | None = None  # None => default_data_dir(); in_memory ignores it
    in_memory: bool = False
    use_provider: bool = False  # AI synthesis is opt-in per invocation
    notifier: Notifier | None = None
    quote_source: QuoteSource | None = None
    initial_cash: Decimal = Decimal("100000")


class TradeOSRuntime:
    def __init__(self, config: RuntimeConfig | None = None) -> None:
        cfg = config or RuntimeConfig()
        self._clock = Clock()
        self.events: EventStore
        if cfg.in_memory:
            self.events = InMemoryEventStore()
        else:
            data_dir = cfg.data_dir or default_data_dir()
            self.events = SQLiteEventStore(data_dir / "tradeos.db")
        self.kill_switch = KillSwitch(self.events)
        self.policy_service = PolicyService(self.events, self._clock)
        self.provider: ModelProvider = ClaudeCodeProvider(event_store=self.events)
        quote_source = cfg.quote_source or StaticQuoteSource(DEMO_PRICES)
        self.broker = PaperBroker(
            event_store=self.events,
            quote_source=quote_source,
            clock=self._clock,
            initial_cash=cfg.initial_cash,
            sector_map=DEMO_SECTORS,
        )
        self.notifier: Notifier = cfg.notifier if cfg.notifier is not None else NullNotifier()
        self._engine = RiskEngine()
        self._strategy = TargetAllocationRebalance()
        self._executor = Executor(
            broker=self.broker,
            event_store=self.events,
            kill_switch=self.kill_switch,
            clock=self._clock,
        )
        self._cycle = DecisionCycle(
            DecisionCycleDeps(
                events=self.events,
                broker=self.broker,
                policy_service=self.policy_service,
                strategy=self._strategy,
                engine=self._engine,
                executor=self._executor,
                kill_switch=self.kill_switch,
                notifier=self.notifier,
                clock=self._clock,
                assembler=ContextAssembler(),
                provider=self.provider if cfg.use_provider else None,
                sector_map=DEMO_SECTORS,
            )
        )

    # -- commands -------------------------------------------------------------

    def ensure_sample_policy(self) -> InvestmentPolicy:
        existing = self.policy_service.active_policy()
        if existing is not None:
            return existing
        return self.policy_service.create_sample_policy(mode=TradingMode.PAPER)

    def run_cycle(
        self, trigger: str = "manual", progress: CycleProgress | None = None
    ) -> CycleOutcome:
        """Run one decision cycle. ``progress`` is a display-only observer —
        it is notified of stage transitions and can never change the outcome."""
        return self._cycle.run(trigger, progress)

    def engage_kill_switch(self, reason: str) -> None:
        self.kill_switch.engage(reason, source="interface")

    def disengage_kill_switch(self) -> None:
        self.kill_switch.disengage(source="interface")

    # -- queries --------------------------------------------------------------

    def active_policy(self) -> InvestmentPolicy | None:
        return self.policy_service.active_policy()

    def provider_status(self) -> ProviderStatus:
        return self.provider.detect()

    def provider_health(self) -> object | None:
        """Structured round-trip probe; returns the ProviderResult or None if
        the active provider has no health check."""
        if isinstance(self.provider, ClaudeCodeProvider):
            return self.provider.health_check()
        return None

    def portfolio_stats(self) -> PortfolioStats:
        now = self._clock.now()
        account = self.broker.get_account()
        quotes = {}
        for position in account.positions:
            quote = self.broker.get_quote(position.symbol)
            if quote is not None:
                quotes[position.symbol] = quote
        policy = self.active_policy()
        targets = {t.symbol: t.weight for t in policy.target_allocations} if policy else {}
        for symbol in targets:
            if symbol not in quotes:
                quote = self.broker.get_quote(symbol)
                if quote is not None:
                    quotes[symbol] = quote
        snapshot = PortfolioSnapshot(account=account, quotes=quotes, as_of=now)
        return compute_stats(snapshot, targets)

    def events_tail(self, limit: int = 50) -> list[Event]:
        if isinstance(self.events, SQLiteEventStore):
            return self.events.tail(limit)
        return list(self.events.iter_events())[-limit:]

    def kill_state(self) -> KillSwitchState:
        """Kill-switch status with its provenance, read back from the event log."""
        engaged = self.kill_switch.is_engaged()
        if not engaged:
            return KillSwitchState(engaged=False)
        event = self.events.last_event(EventType.KILLSWITCH_ENGAGED)
        if event is None:
            return KillSwitchState(engaged=True)
        return KillSwitchState(
            engaged=True,
            since=event.occurred_at,
            reason=str(event.payload.get("reason", "")),
            source=str(event.payload.get("source", "")),
        )

    def risk_rule_ids(self) -> tuple[str, ...]:
        """Every rule the engine will run — the armed-rule count interfaces show."""
        return self._engine.rule_ids

    def diagnostics(self, *, full: bool = False) -> list[DoctorCheck]:
        """Environment checks, used by both `wolf doctor` and the TUI boot screen."""
        return run_checks(self, full=full)

    def journal(self, limit: int | None = None) -> tuple[CycleRecord, ...]:
        """Decision history, newest first. Vetoes and no-actions are records too."""
        records = build_journal(self.events.iter_events())
        return records[:limit] if limit is not None else records

    def cycle_detail(self, correlation_id: str) -> CycleRecord | None:
        for record in self.journal():
            if record.correlation_id == correlation_id:
                return record
        return None

    def latest_cycle(self) -> CycleRecord | None:
        records = self.journal(1)
        return records[0] if records else None

    def equity_points(self) -> tuple[EquityPoint, ...]:
        return equity_history(self.events.iter_events())

    def dashboard(self) -> DashboardView:
        """The den screen's single source — every displayed number resolved here."""
        now = self._clock.now()
        policy = self.active_policy()
        account = self.broker.get_account()
        targets = {t.symbol: t.weight for t in policy.target_allocations} if policy else {}

        quotes = {}
        for symbol in {p.symbol for p in account.positions} | set(targets):
            quote = self.broker.get_quote(symbol)
            if quote is not None:
                quotes[symbol] = quote

        snapshot = PortfolioSnapshot(account=account, quotes=quotes, as_of=now)
        stats = compute_stats(snapshot, targets)
        quantities = {p.symbol: p.quantity for p in account.positions}
        quote_ttl = DEFAULT_TTLS["quote"]
        if policy is not None:
            quote_ttl = policy.stale_quote_max_age_s

        holdings = tuple(
            HoldingView(
                symbol=row.symbol,
                quantity=quantities.get(row.symbol, Decimal("0")),
                value=row.value,
                weight=row.weight,
                target_weight=row.target_weight,
                drift=row.drift,
                unrealized_pnl=row.unrealized_pnl,
                sector=DEMO_SECTORS.get(row.symbol, ""),
                quote_age_s=(quotes[row.symbol].age_s(now) if row.symbol in quotes else None),
                quote_ttl_s=quote_ttl,
                price=quotes[row.symbol].price if row.symbol in quotes else None,
            )
            for row in stats.rows
        )

        points = self.equity_points()
        return DashboardView(
            as_of=now,
            mode=policy.mode.value.upper() if policy else "NO POLICY",
            policy_version=policy.version if policy else None,
            kill_engaged=self.kill_switch.is_engaged(),
            rules_armed=len(self.risk_rule_ids()),
            nav=stats.total_value,
            cash=stats.cash,
            cash_weight=stats.cash_weight,
            cash_floor=policy.min_cash_pct if policy else None,
            holdings=holdings,
            top3_concentration=stats.top3_concentration,
            hhi=stats.hhi,
            drift_threshold=self._strategy.drift_threshold,
            equity=points,
            day_change=day_change(points, now=now),
            max_drawdown=max_drawdown(points),
            last_cycle=self.latest_cycle(),
        )
