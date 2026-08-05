"""Safety suite: no path moves money without an approved ValidatedOrder.

These tests are release gates (RISK_POLICY_SPEC §7.3, THREAT_MODEL T1/T4/T8).
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from tests.conftest import NOW, make_action, make_ctx, make_policy, make_proposal, make_snapshot
from tradeos.brokers.base import BrokerProtocolError, assert_submittable
from tradeos.brokers.fake import FakeBroker
from tradeos.domain.clock import FixedClock
from tradeos.domain.market import Quote
from tradeos.domain.orders import OrderSide, OrderStatus
from tradeos.domain.risk import RiskCheckResult, RiskVerdict, ValidatedOrder, client_order_id_for
from tradeos.events.store import InMemoryEventStore
from tradeos.execution.executor import ExecutionHalted, Executor
from tradeos.risk.engine import RiskEngine
from tradeos.runtime.killswitch import KillSwitch

D = Decimal


def approved_order() -> ValidatedOrder:
    snapshot = make_snapshot(D("10000"), prices={"AAPL": D("200")})
    validation = RiskEngine().validate_proposal(
        make_proposal((make_action(OrderSide.BUY, "AAPL", D("5")),)),
        make_ctx(make_policy(), snapshot),
    )
    assert validation.fully_approved
    return validation.validated_orders[0]


def fake_broker() -> FakeBroker:
    account = make_snapshot(D("10000"), prices={"AAPL": D("200")}).account
    quotes = {"AAPL": Quote(symbol="AAPL", price=D("200"), as_of=NOW, source="test")}
    return FakeBroker(account, quotes, now=NOW)


def test_broker_rejects_non_validated_objects() -> None:
    broker = fake_broker()
    for bogus in ({"symbol": "AAPL"}, make_action(OrderSide.BUY, "AAPL", D("5")), None, "buy"):
        with pytest.raises(BrokerProtocolError):
            broker.submit_order(bogus)  # type: ignore[arg-type]


def test_validated_order_cannot_exist_unapproved() -> None:
    failed = RiskCheckResult(
        rule_id="max_position_pct",
        passed=False,
        blocking=True,
        observed="90%",
        limit="10%",
        message="veto",
    )
    verdict = RiskVerdict(
        verdict_id="v1",
        proposal_id="p1",
        action_index=0,
        policy_version=1,
        evaluated_at=NOW,
        results=(failed,),
        approved=False,
    )
    action = make_action(OrderSide.BUY, "AAPL", D("5"))
    with pytest.raises(ValidationError, match="unapproved"):
        ValidatedOrder(
            order_id="o1",
            proposal_id="p1",
            action=action,
            verdict=verdict,
            policy_version=1,
            client_order_id=client_order_id_for("p1", 0, action),
            valid_until=NOW + timedelta(minutes=10),
        )


def test_tampered_order_caught_at_broker_boundary() -> None:
    """model_construct bypasses validation (simulated tampering) — the
    adapter boundary must still refuse it."""
    failed = RiskCheckResult(
        rule_id="kill_switch",
        passed=False,
        blocking=True,
        observed="engaged",
        limit="disengaged",
        message="veto",
    )
    verdict = RiskVerdict.model_construct(
        verdict_id="v1",
        proposal_id="p1",
        action_index=0,
        policy_version=1,
        evaluated_at=NOW,
        results=(failed,),
        approved=True,  # forged flag
    )
    action = make_action(OrderSide.BUY, "AAPL", D("5"))
    forged = ValidatedOrder.model_construct(
        order_id="o1",
        proposal_id="p1",
        action=action,
        verdict=verdict,
        policy_version=1,
        client_order_id=client_order_id_for("p1", 0, action),
        valid_until=NOW + timedelta(minutes=10),
    )
    with pytest.raises(BrokerProtocolError, match="not approved"):
        assert_submittable(forged, now=NOW)
    with pytest.raises(BrokerProtocolError):
        fake_broker().submit_order(forged)


def test_kill_switch_halts_executor() -> None:
    events = InMemoryEventStore()
    kill = KillSwitch(events)
    executor = Executor(
        broker=fake_broker(), event_store=events, kill_switch=kill, clock=FixedClock(NOW)
    )
    kill.engage("test", source="safety-test")
    with pytest.raises(ExecutionHalted):
        executor.submit(approved_order())
    kill.disengage(source="safety-test")
    assert executor.submit(approved_order()).status == OrderStatus.FILLED


def test_executor_deduplicates_by_client_order_id() -> None:
    events = InMemoryEventStore()
    executor = Executor(
        broker=fake_broker(),
        event_store=events,
        kill_switch=KillSwitch(events),
        clock=FixedClock(NOW),
    )
    order = approved_order()
    first = executor.submit(order)
    second = executor.submit(order)
    assert first.status == OrderStatus.FILLED
    assert second.status == OrderStatus.DUPLICATE


def test_expired_order_refused() -> None:
    events = InMemoryEventStore()
    late_clock = FixedClock(NOW + timedelta(minutes=11))  # past valid_until
    executor = Executor(
        broker=fake_broker(),
        event_store=events,
        kill_switch=KillSwitch(events),
        clock=late_clock,
    )
    result = executor.submit(approved_order())
    assert result.status == OrderStatus.REJECTED
    assert result.error is not None and "expired" in result.error


def test_kill_switch_vetoes_inside_engine_too() -> None:
    ctx = make_ctx(
        make_policy(),
        make_snapshot(D("10000"), prices={"AAPL": D("200")}),
        kill_switch_engaged=True,
    )
    validation = RiskEngine().validate_proposal(
        make_proposal((make_action(OrderSide.BUY, "AAPL", D("5")),)), ctx
    )
    assert not validation.fully_approved
    assert validation.validated_orders == ()
