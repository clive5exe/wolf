"""Scheduled decision cycles.

The README says WOLF continuously monitors a portfolio. Until this module
existed that was false: cycles only ran when a human pressed a key. This makes
the claim true.

**The scheduler is a trigger, not an authority.** It decides *when* to ask for
a cycle and nothing else — it calls the same ``run_cycle`` a keypress does, so
every rule, the mode gate, and the kill switch apply exactly as they would
otherwise. It cannot approve, size, or execute anything, and a bug here can
only cause a cycle to run at the wrong moment, never a bad trade to pass.

Timing is split from running on purpose. :class:`Schedule` is pure — given a
clock reading and the last run, it returns a decision — so the awkward cases
(market closed, kill switch engaged, a cycle overrunning its own interval) are
unit-testable without a single ``sleep``.

Last-run state is derived from the event log rather than stored. The log
already records every ``cycle.triggered``, so a restarted scheduler resumes
correctly with no new state to keep consistent.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from tradeos.domain.clock import Clock
from tradeos.market_data.clock import is_regular_session


class SkipReason(StrEnum):
    KILL_SWITCH = "kill_switch_engaged"
    MARKET_CLOSED = "market_closed"
    TOO_SOON = "interval_not_elapsed"
    ALREADY_RUNNING = "cycle_already_running"


@dataclass(frozen=True)
class ScheduleDecision:
    should_run: bool
    reason: str
    #: Seconds until the next evaluation is worth making.
    wait_s: float = 0.0
    skip: SkipReason | None = None


@dataclass(frozen=True)
class ScheduleConfig:
    """How often to think, and when it is worth thinking at all."""

    interval_s: int = 900  # 15 minutes
    #: Outside regular hours prices do not move, so a cycle would re-decide on
    #: identical inputs and record a no-action. Paper mode may still want them
    #: for demos, hence the switch rather than a hardcoded rule.
    market_hours_only: bool = True
    #: Run once immediately on start rather than waiting out a full interval.
    run_on_start: bool = True
    #: How often to re-evaluate while waiting. Short enough that a kill switch
    #: engaged elsewhere is noticed promptly.
    poll_s: float = 5.0

    def __post_init__(self) -> None:
        if self.interval_s <= 0:
            raise ValueError("interval_s must be positive")
        if self.poll_s <= 0:
            raise ValueError("poll_s must be positive")

    @property
    def label(self) -> str:
        """Trigger label recorded on the event, e.g. ``schedule/15m``."""
        if self.interval_s % 3600 == 0:
            return f"schedule/{self.interval_s // 3600}h"
        if self.interval_s % 60 == 0:
            return f"schedule/{self.interval_s // 60}m"
        return f"schedule/{self.interval_s}s"


class Schedule:
    """Pure timing decisions. No I/O, no clock reads — everything is injected."""

    def __init__(self, config: ScheduleConfig | None = None) -> None:
        self.config = config or ScheduleConfig()

    def next_run_at(self, last_run: datetime | None) -> datetime | None:
        if last_run is None:
            return None
        return last_run + timedelta(seconds=self.config.interval_s)

    def decide(
        self,
        *,
        now: datetime,
        last_run: datetime | None,
        kill_engaged: bool,
        cycle_in_flight: bool = False,
    ) -> ScheduleDecision:
        """Whether to trigger a cycle at ``now``.

        Order matters: the kill switch is checked before anything else, so a
        halted runtime reports *that* rather than a timing reason. Someone
        reading the log should see why nothing is happening, and "market
        closed" would be a misleading answer while execution is halted.
        """
        poll = self.config.poll_s

        if kill_engaged:
            return ScheduleDecision(
                False, "kill switch engaged — no cycles scheduled", poll, SkipReason.KILL_SWITCH
            )

        if cycle_in_flight:
            # A cycle outrunning its own interval must not stack: overlapping
            # runs would race on the same portfolio state.
            return ScheduleDecision(
                False, "previous cycle still running", poll, SkipReason.ALREADY_RUNNING
            )

        if self.config.market_hours_only and not is_regular_session(now):
            return ScheduleDecision(False, "market closed", poll, SkipReason.MARKET_CLOSED)

        if last_run is None:
            if self.config.run_on_start:
                return ScheduleDecision(True, "first run")
            return ScheduleDecision(False, "waiting for first interval", poll, SkipReason.TOO_SOON)

        due_at = last_run + timedelta(seconds=self.config.interval_s)
        remaining = (due_at - now).total_seconds()
        if remaining > 0:
            return ScheduleDecision(
                False,
                f"next cycle in {_human(remaining)}",
                min(poll, remaining),
                SkipReason.TOO_SOON,
            )
        return ScheduleDecision(True, f"{self.config.label} due")


def _human(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m{secs:02d}s"
    hours, mins = divmod(minutes, 60)
    return f"{hours}h{mins:02d}m"


def sleep(seconds: float) -> None:
    """Indirection so tests can drive the loop without waiting."""
    time.sleep(seconds)


@runtime_checkable
class SchedulableRuntime(Protocol):
    """What the scheduler needs. Narrow on purpose: it can trigger a cycle and
    read state, and there is no method here that could bypass a rule."""

    # Deliberately permissive in the argument and return types: the scheduler
    # neither inspects the outcome nor supplies a progress observer, so pinning
    # them here would only couple this protocol to the cycle's signature.
    def run_cycle(self, trigger: str = ..., progress: Any = ...) -> Any: ...
    def last_cycle_at(self) -> datetime | None: ...
    @property
    def clock(self) -> Clock: ...
    @property
    def kill_switch(self) -> object: ...


class Scheduler:
    """Drives cycles on a schedule until stopped."""

    def __init__(
        self,
        runtime: SchedulableRuntime,
        config: ScheduleConfig | None = None,
        *,
        clock: Clock | None = None,
        on_event: Callable[[str], None] | None = None,
    ) -> None:
        self._runtime = runtime
        self._schedule = Schedule(config)
        # Share the runtime's clock by default. Two clocks would let the
        # scheduler's "now" drift from the timestamps written to the log,
        # so an interval would be measured against a different timeline.
        self._clock = clock or getattr(runtime, "clock", None) or Clock()
        self._on_event = on_event or (lambda _message: None)
        self._stopped = False
        self._last_skip: SkipReason | None = None
        #: How long the last decision said was worth waiting. Sleeping a fixed
        #: poll instead would floor the cadence: a 2s interval would fire every
        #: 5s, quietly ignoring what the user asked for.
        self._next_wait: float = self.config.poll_s

    @property
    def config(self) -> ScheduleConfig:
        return self._schedule.config

    def stop(self) -> None:
        self._stopped = True

    def tick(self) -> object | None:
        """Evaluate once; run a cycle if due. Returns the outcome, or None."""
        decision = self._schedule.decide(
            now=self._clock.now(),
            last_run=self._runtime.last_cycle_at(),
            kill_engaged=bool(self._runtime.kill_switch.is_engaged()),  # type: ignore[attr-defined]
        )
        self._next_wait = decision.wait_s or self.config.poll_s
        if not decision.should_run:
            # Report a skip only when the reason changes, so an idle overnight
            # scheduler does not produce thousands of identical lines.
            if decision.skip != self._last_skip:
                self._last_skip = decision.skip
                self._on_event(decision.reason)
            return None

        self._last_skip = None
        self._on_event(decision.reason)
        outcome = self._runtime.run_cycle(self.config.label)
        # After a run the next one is a full interval away; no need to wake
        # sooner than the poll to find that out.
        self._next_wait = min(float(self.config.interval_s), self.config.poll_s)
        return outcome

    def run_forever(self, max_iterations: int | None = None) -> int:
        """Loop until stopped. ``max_iterations`` bounds it for tests.

        Exceptions from a cycle are caught and reported: one bad cycle must not
        silently end the schedule, leaving a runtime that looks alive and is
        quietly doing nothing.
        """
        iterations = 0
        while not self._stopped:
            if max_iterations is not None and iterations >= max_iterations:
                break
            iterations += 1
            try:
                self.tick()
            except Exception as exc:
                self._on_event(f"cycle failed: {type(exc).__name__}: {exc}")
            if self._stopped:
                break
            # Wait only as long as the schedule says is useful, capped by the
            # poll so a kill switch engaged elsewhere is noticed promptly.
            sleep(max(0.0, min(self._next_wait, self.config.poll_s)))
        return iterations
