# ADR-0006: SQLite (WAL) initial storage. DuckDB deferred

**Status:** accepted · 2026-08-05

## Context
Local-first single-user storage needs durability, transactions, zero ops, and
JSON support. Stdlib `sqlite3` with JSON1 + WAL verified on the dev machine
(SQLite 3.51.3. JSON1 built-in since 3.38. RESEARCH_NOTES §3).

## Decision
One SQLite database (WAL mode) holding: `events` (append-only, triggers),
`snapshots` (derived-state cache keyed by event seq), `migrations` ledger.
Numbered SQL migrations applied by `storage/migrations.py`. `Decimal` stored
as TEXT, timestamps as ISO-8601 UTC TEXT. Backups = file copy while holding a
`BEGIN IMMEDIATE` checkpoint (`storage/backup.py`).

DuckDB is adopted only when a concrete analytics need (large replay datasets,
columnar scans) measurably outgrows SQLite. As a *read-side* attach, never
the source of truth.

## Consequences
- Zero-dependency persistence, trivially inspectable (`sqlite3` CLI).
- Write throughput is bounded but far above need (< 100 events/s bursts).
- Analytics queries stay simple until DuckDB is justified by evidence.
