"""Kill switch (RISK_POLICY_SPEC §5): event-backed so state survives restarts
and every engage/disengage is itself audit history."""

from __future__ import annotations

from tradeos.events.store import EventStore
from tradeos.events.types import EventType


class KillSwitch:
    def __init__(self, event_store: EventStore) -> None:
        self._events = event_store

    def is_engaged(self) -> bool:
        engaged = self._events.last_event(EventType.KILLSWITCH_ENGAGED)
        disengaged = self._events.last_event(EventType.KILLSWITCH_DISENGAGED)
        if engaged is None:
            return False
        if disengaged is None:
            return True
        return engaged.event_id > disengaged.event_id  # ULIDs order chronologically

    def engage(self, reason: str, *, source: str) -> None:
        self._events.append(EventType.KILLSWITCH_ENGAGED, {"reason": reason, "source": source})

    def disengage(self, *, source: str) -> None:
        # Manual only (spec §5): callers are interfaces acting for the human.
        self._events.append(EventType.KILLSWITCH_DISENGAGED, {"source": source})
