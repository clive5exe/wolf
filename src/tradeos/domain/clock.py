"""Injectable clock. Rules and strategies receive ``now`` as data; only
runtime edges hold a Clock. FixedClock powers deterministic tests/replay."""

from __future__ import annotations

from datetime import datetime

from tradeos.domain.common import utc_now


class Clock:
    def now(self) -> datetime:
        return utc_now()


class FixedClock(Clock):
    def __init__(self, fixed: datetime) -> None:
        self._fixed = fixed

    def now(self) -> datetime:
        return self._fixed

    def advance_to(self, new_now: datetime) -> None:
        self._fixed = new_now
