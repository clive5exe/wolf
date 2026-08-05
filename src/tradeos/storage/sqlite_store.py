"""Durable append-only event store on SQLite (WAL).

Append-only is enforced in-database by triggers (see migrations.py), not by
convention. Secrets never enter this database (ADR-0010): payloads pass the
caller's redaction discipline. There is no secrets table by design.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

from tradeos.events.model import Event
from tradeos.events.store import build_event
from tradeos.events.types import EventType
from tradeos.storage.migrations import apply_migrations


class SQLiteEventStore:
    def __init__(self, db_path: Path | str) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        apply_migrations(self._conn)

    def close(self) -> None:
        self._conn.close()

    # -- writes ---------------------------------------------------------------

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
        self._conn.execute(
            """
            INSERT INTO events (event_id, event_type, occurred_at, recorded_at,
                                schema_version, correlation_id, causation_id, payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                event.event_type.value,
                event.occurred_at.isoformat(),
                event.recorded_at.isoformat(),
                event.schema_version,
                event.correlation_id,
                event.causation_id,
                json.dumps(event.payload, sort_keys=True),
            ),
        )
        self._conn.commit()
        return event

    # -- reads ----------------------------------------------------------------

    def iter_events(
        self,
        *,
        event_types: tuple[EventType, ...] | None = None,
        correlation_id: str | None = None,
        since: datetime | None = None,
    ) -> Iterator[Event]:
        sql = (
            "SELECT event_id, event_type, occurred_at, recorded_at, schema_version, "
            "correlation_id, causation_id, payload FROM events"
        )
        clauses: list[str] = []
        params: list[Any] = []
        if event_types is not None:
            placeholders = ",".join("?" for _ in event_types)
            clauses.append(f"event_type IN ({placeholders})")
            params.extend(t.value for t in event_types)
        if correlation_id is not None:
            clauses.append("correlation_id = ?")
            params.append(correlation_id)
        if since is not None:
            clauses.append("occurred_at >= ?")
            params.append(since.isoformat())
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY seq ASC"
        for row in self._conn.execute(sql, params):
            yield self._row_to_event(row)

    def last_event(self, event_type: EventType) -> Event | None:
        row = self._conn.execute(
            "SELECT event_id, event_type, occurred_at, recorded_at, schema_version, "
            "correlation_id, causation_id, payload FROM events WHERE event_type = ? "
            "ORDER BY seq DESC LIMIT 1",
            (event_type.value,),
        ).fetchone()
        return self._row_to_event(row) if row else None

    def count(self, event_type: EventType, *, since: datetime | None = None) -> int:
        sql = "SELECT COUNT(*) FROM events WHERE event_type = ?"
        params: list[Any] = [event_type.value]
        if since is not None:
            sql += " AND occurred_at >= ?"
            params.append(since.isoformat())
        result = self._conn.execute(sql, params).fetchone()
        return int(result[0])

    def tail(self, limit: int = 50) -> list[Event]:
        rows = self._conn.execute(
            "SELECT event_id, event_type, occurred_at, recorded_at, schema_version, "
            "correlation_id, causation_id, payload FROM events ORDER BY seq DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_event(r) for r in reversed(rows)]

    @staticmethod
    def _row_to_event(row: tuple[Any, ...]) -> Event:
        return Event(
            event_id=row[0],
            event_type=EventType(row[1]),
            occurred_at=datetime.fromisoformat(row[2]),
            recorded_at=datetime.fromisoformat(row[3]),
            schema_version=row[4],
            correlation_id=row[5],
            causation_id=row[6],
            payload=json.loads(row[7]),
        )
