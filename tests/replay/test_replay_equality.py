"""Replay guarantee (EVALUATION_SPEC §2): derived state rebuilt from the event
log is byte-identical to live state. This is a release gate."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from tradeos.brokers.paper import PaperBroker
from tradeos.domain.clock import Clock
from tradeos.domain.common import canonical_json
from tradeos.market_data.quotes import StaticQuoteSource
from tradeos.notifications.base import NullNotifier
from tradeos.runtime.facade import DEMO_PRICES, RuntimeConfig, TradeOSRuntime
from tradeos.storage.sqlite_store import SQLiteEventStore

D = Decimal


def derived_state_hashable(broker: PaperBroker) -> str:
    account = broker.get_account()
    return canonical_json(
        {
            "cash": str(account.cash),
            "positions": sorted(
                (p.symbol, str(p.quantity), str(p.avg_cost)) for p in account.positions
            ),
        }
    )


def test_replay_reproduces_identical_paper_state(tmp_path: Path) -> None:
    data_dir = tmp_path / "replaycase"
    runtime = TradeOSRuntime(RuntimeConfig(data_dir=data_dir, notifier=NullNotifier()))
    runtime.ensure_sample_policy()
    first = runtime.run_cycle(trigger="replay-capture")
    assert first.status == "completed" and first.approved_actions == 5
    live_hash = derived_state_hashable(runtime.broker)

    # A fresh process over the same event log must reduce to identical state.
    store = SQLiteEventStore(data_dir / "tradeos.db")
    rebuilt = PaperBroker(
        event_store=store,
        quote_source=StaticQuoteSource(DEMO_PRICES),
        clock=Clock(),
        initial_cash=D("1"),  # must be ignored. History wins
    )
    assert derived_state_hashable(rebuilt) == live_hash


def test_replay_is_stable_across_repeated_reduction(tmp_path: Path) -> None:
    data_dir = tmp_path / "replaycase2"
    runtime = TradeOSRuntime(RuntimeConfig(data_dir=data_dir, notifier=NullNotifier()))
    runtime.ensure_sample_policy()
    runtime.run_cycle(trigger="c1")
    runtime.run_cycle(trigger="c2")  # converges to no_action

    store = SQLiteEventStore(data_dir / "tradeos.db")
    hashes = set()
    for _ in range(3):
        rebuilt = PaperBroker(
            event_store=store,
            quote_source=StaticQuoteSource(DEMO_PRICES),
            clock=Clock(),
        )
        hashes.add(derived_state_hashable(rebuilt))
    assert len(hashes) == 1, "replay must be deterministic"
