"""End-to-end paper decision cycle (PRODUCT.md §7.3): every stage emits events,
fills land, the second cycle converges to first-class no-action."""

from __future__ import annotations

from decimal import Decimal

from tradeos.events.types import EventType
from tradeos.notifications.base import NullNotifier
from tradeos.runtime.facade import RuntimeConfig, TradeOSRuntime

D = Decimal


def make_runtime() -> tuple[TradeOSRuntime, NullNotifier]:
    notifier = NullNotifier()
    runtime = TradeOSRuntime(RuntimeConfig(in_memory=True, notifier=notifier))
    return runtime, notifier


def test_full_cycle_emits_complete_event_trail() -> None:
    runtime, notifier = make_runtime()
    runtime.ensure_sample_policy()
    outcome = runtime.run_cycle(trigger="integration-test")

    assert outcome.status == "completed"
    assert outcome.approved_actions == 5  # VTI, AAPL, MSFT, JNJ, XOM buys
    assert outcome.vetoed_actions == 0
    assert len(outcome.fills) == 5

    types = [e.event_type for e in runtime.events.iter_events()]
    for expected in (
        EventType.POLICY_CREATED,
        EventType.CYCLE_TRIGGERED,
        EventType.CONTEXT_ASSEMBLED,
        EventType.PROPOSAL_CREATED,
        EventType.RISK_EVALUATED,
        EventType.ORDER_SUBMITTED,
        EventType.ORDER_FILLED,
        EventType.CYCLE_COMPLETED,
        EventType.EVALUATION_RECORDED,
        EventType.NOTIFICATION_SENT,
    ):
        assert expected in types, f"missing {expected} in event trail"

    # every cycle event carries the correlation id
    cycle_events = [e for e in runtime.events.iter_events(correlation_id=outcome.correlation_id)]
    assert len(cycle_events) >= 8

    # notification carries action detail + audit id (COMMS contract)
    assert len(notifier.sent) == 1
    _, body = notifier.sent[0]
    assert "approved" in body and outcome.correlation_id[:8] in body


def test_second_cycle_is_first_class_no_action() -> None:
    runtime, _ = make_runtime()
    runtime.ensure_sample_policy()
    first = runtime.run_cycle(trigger="t1")
    assert first.status == "completed"
    second = runtime.run_cycle(trigger="t2")
    assert second.status == "no_action"
    assert "threshold" in second.reason or "within" in second.reason
    types = [e.event_type for e in runtime.events.iter_events()]
    assert EventType.CYCLE_NO_ACTION in types


def test_risk_verdicts_recorded_with_every_rule_result() -> None:
    runtime, _ = make_runtime()
    runtime.ensure_sample_policy()
    runtime.run_cycle(trigger="t1")
    verdicts = list(runtime.events.iter_events(event_types=(EventType.RISK_EVALUATED,)))
    assert len(verdicts) == 5
    for event in verdicts:
        rule_ids = {r["rule_id"] for r in event.payload["results"]}
        assert {"kill_switch", "max_position_pct", "stale_quote", "duplicate_order"} <= rule_ids


def test_kill_switch_blocks_next_cycle_execution() -> None:
    runtime, _ = make_runtime()
    runtime.ensure_sample_policy()
    runtime.engage_kill_switch("integration test")
    outcome = runtime.run_cycle(trigger="t1")
    # cycle completes analytically but every action is vetoed and nothing fills
    assert outcome.approved_actions == 0
    assert outcome.fills == ()
    assert runtime.events.count(EventType.ORDER_FILLED) == 0


def test_no_policy_aborts_cleanly() -> None:
    runtime, _ = make_runtime()
    outcome = runtime.run_cycle(trigger="t1")
    assert outcome.status == "aborted"
    assert "policy" in outcome.reason
