"""Event store: append-only enforcement, ordering, filters (ADR-0005/0006)."""

from __future__ import annotations

import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest

from tests.conftest import NOW
from tradeos.domain.common import new_ulid
from tradeos.events.types import EventType
from tradeos.storage.sqlite_store import SQLiteEventStore


@pytest.fixture()
def store(tmp_path: Path) -> SQLiteEventStore:
    return SQLiteEventStore(tmp_path / "events.db")


def test_append_and_read_roundtrip(store: SQLiteEventStore) -> None:
    written = store.append(
        EventType.CYCLE_TRIGGERED,
        {"trigger": "test", "n": 1},
        correlation_id="corr-1",
        occurred_at=NOW,
    )
    events = list(store.iter_events())
    assert len(events) == 1
    read = events[0]
    assert read == written
    assert read.payload == {"trigger": "test", "n": 1}


def test_events_are_ordered_and_ulids_monotonic(store: SQLiteEventStore) -> None:
    ids = [store.append(EventType.INGEST_RAW, {"i": i}).event_id for i in range(50)]
    assert ids == sorted(ids), "ULIDs must sort in creation order"
    read_ids = [e.event_id for e in store.iter_events()]
    assert read_ids == ids


def test_update_is_forbidden_by_trigger(store: SQLiteEventStore, tmp_path: Path) -> None:
    store.append(EventType.CYCLE_TRIGGERED, {"trigger": "x"})
    conn = sqlite3.connect(tmp_path / "events.db")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        conn.execute("UPDATE events SET payload = '{}' WHERE 1=1")
    conn.close()


def test_delete_is_forbidden_by_trigger(store: SQLiteEventStore, tmp_path: Path) -> None:
    store.append(EventType.CYCLE_TRIGGERED, {"trigger": "x"})
    conn = sqlite3.connect(tmp_path / "events.db")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        conn.execute("DELETE FROM events")
    conn.close()


def test_filters(store: SQLiteEventStore) -> None:
    store.append(EventType.CYCLE_TRIGGERED, {}, correlation_id="a", occurred_at=NOW)
    store.append(EventType.CYCLE_COMPLETED, {}, correlation_id="a", occurred_at=NOW)
    store.append(
        EventType.CYCLE_TRIGGERED,
        {},
        correlation_id="b",
        occurred_at=NOW + timedelta(hours=1),
    )
    assert len(list(store.iter_events(event_types=(EventType.CYCLE_TRIGGERED,)))) == 2
    assert len(list(store.iter_events(correlation_id="a"))) == 2
    assert store.count(EventType.CYCLE_TRIGGERED, since=NOW + timedelta(minutes=30)) == 1
    last = store.last_event(EventType.CYCLE_TRIGGERED)
    assert last is not None and last.correlation_id == "b"


def test_migrations_are_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "twice.db"
    first = SQLiteEventStore(path)
    first.append(EventType.INGEST_RAW, {"i": 1})
    first.close()
    second = SQLiteEventStore(path)  # re-applies migrations harmlessly
    assert len(list(second.iter_events())) == 1
    second.close()


def test_ulid_uniqueness_under_burst() -> None:
    ids = {new_ulid() for _ in range(5000)}
    assert len(ids) == 5000
