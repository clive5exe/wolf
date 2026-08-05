"""Scheduler timing and safety.

Timing is pure, so every awkward case is tested without a single sleep. The
safety-relevant property is that the scheduler is a *trigger only*: it decides
when to ask for a cycle and can never widen what a cycle is permitted to do.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tradeos.domain.clock import FixedClock
from tradeos.notifications.base import NullNotifier
from tradeos.runtime.facade import RuntimeConfig, TradeOSRuntime
from tradeos.runtime.schedule import (
    Schedule,
    ScheduleConfig,
    Scheduler,
    SkipReason,
)

# A Wednesday inside regular NYSE hours (14:00Z == 10:00 New York).
OPEN = datetime(2026, 8, 5, 14, 0, tzinfo=UTC)
# A Saturday.
CLOSED = datetime(2026, 8, 8, 14, 0, tzinfo=UTC)


class TestScheduleDecisions:
    def test_first_run_happens_immediately_by_default(self) -> None:
        decision = Schedule().decide(now=OPEN, last_run=None, kill_engaged=False)
        assert decision.should_run

    def test_first_run_can_wait_for_a_full_interval(self) -> None:
        schedule = Schedule(ScheduleConfig(run_on_start=False))
        decision = schedule.decide(now=OPEN, last_run=None, kill_engaged=False)
        assert not decision.should_run
        assert decision.skip is SkipReason.TOO_SOON

    def test_waits_out_the_interval(self) -> None:
        schedule = Schedule(ScheduleConfig(interval_s=900))
        decision = schedule.decide(
            now=OPEN + timedelta(seconds=300), last_run=OPEN, kill_engaged=False
        )
        assert not decision.should_run
        assert "10m" in decision.reason

    def test_runs_once_the_interval_elapses(self) -> None:
        schedule = Schedule(ScheduleConfig(interval_s=900))
        decision = schedule.decide(
            now=OPEN + timedelta(seconds=900), last_run=OPEN, kill_engaged=False
        )
        assert decision.should_run
        assert "schedule/15m" in decision.reason

    def test_market_hours_gate(self) -> None:
        schedule = Schedule(ScheduleConfig(market_hours_only=True))
        assert not schedule.decide(now=CLOSED, last_run=None, kill_engaged=False).should_run
        assert schedule.decide(now=OPEN, last_run=None, kill_engaged=False).should_run

    def test_any_hours_ignores_the_market_clock(self) -> None:
        schedule = Schedule(ScheduleConfig(market_hours_only=False))
        assert schedule.decide(now=CLOSED, last_run=None, kill_engaged=False).should_run

    def test_kill_switch_stops_scheduling_entirely(self) -> None:
        decision = Schedule().decide(now=OPEN, last_run=None, kill_engaged=True)
        assert not decision.should_run
        assert decision.skip is SkipReason.KILL_SWITCH

    def test_kill_switch_is_reported_ahead_of_timing_reasons(self) -> None:
        """A halted runtime should say so, not blame the market calendar."""
        decision = Schedule().decide(now=CLOSED, last_run=None, kill_engaged=True)
        assert decision.skip is SkipReason.KILL_SWITCH
        assert "kill switch" in decision.reason

    def test_a_cycle_overrunning_its_interval_does_not_stack(self) -> None:
        decision = Schedule(ScheduleConfig(interval_s=1)).decide(
            now=OPEN + timedelta(seconds=60),
            last_run=OPEN,
            kill_engaged=False,
            cycle_in_flight=True,
        )
        assert not decision.should_run
        assert decision.skip is SkipReason.ALREADY_RUNNING

    @pytest.mark.parametrize(
        ("seconds", "label"),
        [(30, "schedule/30s"), (900, "schedule/15m"), (3600, "schedule/1h")],
    )
    def test_trigger_labels(self, seconds: int, label: str) -> None:
        assert ScheduleConfig(interval_s=seconds).label == label

    def test_nonsense_config_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="interval_s"):
            ScheduleConfig(interval_s=0)
        with pytest.raises(ValueError, match="poll_s"):
            ScheduleConfig(poll_s=0)


class TestSchedulerAgainstTheRuntime:
    def _runtime(self, clock: FixedClock | None = None) -> TradeOSRuntime:
        runtime = TradeOSRuntime(
            RuntimeConfig(in_memory=True, notifier=NullNotifier(), clock=clock)
        )
        runtime.ensure_sample_policy()
        return runtime

    def test_a_tick_runs_a_real_cycle_and_records_the_trigger(self) -> None:
        runtime = self._runtime()
        config = ScheduleConfig(market_hours_only=False)
        scheduler = Scheduler(runtime, config, clock=FixedClock(OPEN))

        outcome = scheduler.tick()
        assert outcome is not None

        record = runtime.latest_cycle()
        assert record is not None
        assert record.trigger == "schedule/15m"

    def test_the_second_tick_is_skipped_until_the_interval_passes(self) -> None:
        clock = FixedClock(OPEN)
        runtime = self._runtime(clock)
        scheduler = Scheduler(
            runtime, ScheduleConfig(interval_s=900, market_hours_only=False), clock=clock
        )
        assert scheduler.tick() is not None
        assert scheduler.tick() is None  # too soon

        clock.advance_to(OPEN + timedelta(seconds=901))
        assert scheduler.tick() is not None

    def test_an_engaged_kill_switch_prevents_any_cycle(self) -> None:
        """The cycle would veto anyway. The scheduler must not even start one."""
        runtime = self._runtime()
        runtime.engage_kill_switch("testing")
        before = len(runtime.journal())

        scheduler = Scheduler(
            runtime, ScheduleConfig(market_hours_only=False), clock=FixedClock(OPEN)
        )
        assert scheduler.tick() is None
        assert len(runtime.journal()) == before

    def test_last_run_survives_a_restart(self) -> None:
        """Derived from the log, so a fresh scheduler does not re-run immediately."""
        clock = FixedClock(OPEN)
        runtime = self._runtime(clock)
        config = ScheduleConfig(interval_s=900, market_hours_only=False)
        Scheduler(runtime, config, clock=clock).tick()

        restarted = Scheduler(runtime, config, clock=clock)
        assert restarted.tick() is None

    def test_repeated_skips_are_reported_once(self) -> None:
        """An overnight scheduler must not emit thousands of identical lines."""
        runtime = self._runtime()
        runtime.engage_kill_switch("testing")
        messages: list[str] = []
        scheduler = Scheduler(
            runtime,
            ScheduleConfig(market_hours_only=False),
            clock=FixedClock(OPEN),
            on_event=messages.append,
        )
        for _ in range(5):
            scheduler.tick()
        assert len(messages) == 1

    def test_a_failing_cycle_does_not_kill_the_loop(self, monkeypatch) -> None:
        """A scheduler that dies silently leaves a runtime that looks alive."""
        runtime = self._runtime()

        def explode(*args: object, **kwargs: object) -> None:
            raise RuntimeError("boom")

        monkeypatch.setattr(runtime, "run_cycle", explode)
        messages: list[str] = []
        scheduler = Scheduler(
            runtime,
            ScheduleConfig(market_hours_only=False, poll_s=0.001),
            clock=FixedClock(OPEN),
            on_event=messages.append,
        )
        assert scheduler.run_forever(max_iterations=2) == 2
        assert any("boom" in m for m in messages)

    def test_stop_ends_the_loop(self) -> None:
        runtime = self._runtime()
        scheduler = Scheduler(
            runtime,
            ScheduleConfig(market_hours_only=False, poll_s=0.001),
            clock=FixedClock(OPEN),
        )
        scheduler.stop()
        assert scheduler.run_forever(max_iterations=10) == 0


class TestCadence:
    """The poll interval must not silently floor the requested interval."""

    def test_a_short_interval_is_honoured_not_rounded_up_to_the_poll(self) -> None:
        schedule = Schedule(ScheduleConfig(interval_s=2, poll_s=5.0, market_hours_only=False))
        decision = schedule.decide(
            now=OPEN + timedelta(seconds=1), last_run=OPEN, kill_engaged=False
        )
        assert not decision.should_run
        # 1s until due. Waiting the full 5s poll would make a 2s interval a 5s one.
        assert decision.wait_s == pytest.approx(1.0)

    def test_a_long_wait_is_capped_by_the_poll(self) -> None:
        """So a kill switch engaged elsewhere is noticed within a poll."""
        schedule = Schedule(ScheduleConfig(interval_s=3600, poll_s=5.0, market_hours_only=False))
        decision = schedule.decide(now=OPEN, last_run=OPEN, kill_engaged=False)
        assert decision.wait_s == pytest.approx(5.0)
