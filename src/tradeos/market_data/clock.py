"""Market session clock.

Limitation (documented, deliberate): v0.1 knows regular NYSE hours
(Mon–Fri 09:30–16:00 America/New_York) but NOT the exchange holiday calendar.
Paper mode may simulate outside hours (MarketStatus.SIMULATED); live modes in
v0.2 must add a holiday source before enabling `trading_hours` for real
orders. Rules never read the clock directly — the runtime injects the result.
"""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

_EASTERN = ZoneInfo("America/New_York")
_OPEN = time(9, 30)
_CLOSE = time(16, 0)


def is_regular_session(now: datetime) -> bool:
    """True during regular NYSE trading hours (holiday-naive — see module doc)."""
    eastern = now.astimezone(_EASTERN)
    if eastern.weekday() >= 5:  # Sat/Sun
        return False
    return _OPEN <= eastern.time() < _CLOSE
