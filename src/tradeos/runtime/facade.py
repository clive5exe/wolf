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
from tradeos.domain.clock import Clock
from tradeos.domain.policy import InvestmentPolicy, TradingMode
from tradeos.domain.portfolio import PortfolioSnapshot
from tradeos.events.model import Event
from tradeos.events.store import EventStore, InMemoryEventStore
from tradeos.execution.executor import Executor
from tradeos.market_data.quotes import QuoteSource, StaticQuoteSource
from tradeos.notifications.base import Notifier, NullNotifier
from tradeos.portfolio.stats import PortfolioStats, compute_stats
from tradeos.providers.base import ModelProvider, ProviderStatus
from tradeos.providers.claude_code import ClaudeCodeProvider
from tradeos.risk.engine import RiskEngine
from tradeos.runtime.cycle import CycleOutcome, DecisionCycle, DecisionCycleDeps
from tradeos.runtime.killswitch import KillSwitch
from tradeos.runtime.policy_service import PolicyService
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
                strategy=TargetAllocationRebalance(),
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

    def run_cycle(self, trigger: str = "manual") -> CycleOutcome:
        return self._cycle.run(trigger)

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
