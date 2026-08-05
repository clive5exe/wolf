"""Event store protocol + in-memory implementation for tests.

The durable implementation is storage/sqlite_store.py. Both are append-only:
there is no update or delete anywhere in the interface.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from tradeos.domain.common import new_ulid, utc_now
from tradeos.events.model import Event
from tradeos.events.types import EventType


@runtime_checkable
class EventStore(Protocol):
    def append(
        self,
        event_type: EventType,
        payload: dict[str, Any],
        *,
        occurred_at: datetime | None = None,
        correlation_id: str | None = None,
        causation_id: str | None = None,
        schema_version: int = 1,
    ) -> Event: ...

    def iter_events(
        self,
        *,
        event_types: tuple[EventType, ...] | None = None,
        correlation_id: str | None = None,
        since: datetime | None = None,
    ) -> Iterator[Event]: ...

    def last_event(self, event_type: EventType) -> Event | None: ...

    def count(
        self,
        event_type: EventType,
        *,
        since: datetime | None = None,
    ) -> int: ...


def build_event(
    event_type: EventType,
    payload: dict[str, Any],
    *,
    occurred_at: datetime | None = None,
    correlation_id: str | None = None,
    causation_id: str | None = None,
    schema_version: int = 1,
) -> Event:
    now = utc_now()
    return Event(
        event_id=new_ulid(),
        event_type=event_type,
        occurred_at=occurred_at or now,
        recorded_at=now,
        schema_version=schema_version,
        correlation_id=correlation_id,
        causation_id=causation_id,
        payload=payload,
    )


class InMemoryEventStore:
    """Append-only in-memory store for unit tests and ephemeral runs."""

    def __init__(self) -> None:
        self._events: list[Event] = []

    def append(
        self,
        event_type: EventType,
        payload: dict[str, Any],
        *,
        occurred_at: datetime | None = None,
        correlation_id: str | None = None,
        causation_id: str | None = None,
        schema_version: int = 1,
    ) -> Event:
        event = build_event(
            event_type,
            payload,
            occurred_at=occurred_at,
            correlation_id=correlation_id,
            causation_id=causation_id,
            schema_version=schema_version,
        )
        self._events.append(event)
        return event

    def iter_events(
        self,
        *,
        event_types: tuple[EventType, ...] | None = None,
        correlation_id: str | None = None,
        since: datetime | None = None,
    ) -> Iterator[Event]:
        for event in self._events:
            if event_types is not None and event.event_type not in event_types:
                continue
            if correlation_id is not None and event.correlation_id != correlation_id:
                continue
            if since is not None and event.occurred_at < since:
                continue
            yield event

    def last_event(self, event_type: EventType) -> Event | None:
        for event in reversed(self._events):
            if event.event_type == event_type:
                return event
        return None

    def count(self, event_type: EventType, *, since: datetime | None = None) -> int:
        return sum(1 for _ in self.iter_events(event_types=(event_type,), since=since))
