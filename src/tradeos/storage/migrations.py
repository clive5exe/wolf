"""Numbered SQL migrations. Additive only for the events table — its
append-only triggers are part of the audit guarantee (THREAT_MODEL T6)."""

from __future__ import annotations

import sqlite3

MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
        CREATE TABLE IF NOT EXISTS events (
            seq         INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id    TEXT NOT NULL UNIQUE,
            event_type  TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            schema_version INTEGER NOT NULL DEFAULT 1,
            correlation_id TEXT,
            causation_id   TEXT,
            payload     TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
        CREATE INDEX IF NOT EXISTS idx_events_correlation ON events(correlation_id);
        CREATE INDEX IF NOT EXISTS idx_events_occurred ON events(occurred_at);

        CREATE TRIGGER IF NOT EXISTS events_no_update
        BEFORE UPDATE ON events
        BEGIN
            SELECT RAISE(ABORT, 'events are append-only: UPDATE forbidden');
        END;

        CREATE TRIGGER IF NOT EXISTS events_no_delete
        BEFORE DELETE ON events
        BEGIN
            SELECT RAISE(ABORT, 'events are append-only: DELETE forbidden');
        END;
        """,
    ),
]


def apply_migrations(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS migrations (id INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    applied = {row[0] for row in conn.execute("SELECT id FROM migrations")}
    for mig_id, sql in MIGRATIONS:
        if mig_id in applied:
            continue
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO migrations (id, applied_at) VALUES (?, datetime('now'))", (mig_id,)
        )
    conn.commit()
