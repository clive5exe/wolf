# ADR-0005: Append-only event log as the source of truth

**Status:** accepted · 2026-08-05

## Context
Every meaningful decision must be explainable, auditable, and replayable
(product requirement). Mutable CRUD state cannot prove what the system knew
when it acted.

## Decision
All significant state changes append an `Event` (ULID id, type, occurred/
recorded timestamps, correlation id, causation id, schema version, JSON
payload) to an append-only SQLite table protected by UPDATE/DELETE-rejecting
triggers. Derived state (positions, P&L, journal, stats) is rebuilt by
reducers. Replay hash-equality is a release gate (EVALUATION_SPEC §2).
Snapshots are a permitted optimization, never the truth.

## Consequences
- Audit, replay, and evaluation come nearly free. Crash recovery = re-reduce.
- Discipline required: payload schema changes need `schema_version` bumps and
  upcasting functions. Goldens catch accidental divergence.
- Storage growth is acceptable (text events, single user). Compaction is a
  later concern.

## Alternatives rejected
- Plain CRUD tables + audit table: audit drifts from truth. Replay impossible.
- Full ES framework: overkill. ~200 lines of store + reducers suffice.
